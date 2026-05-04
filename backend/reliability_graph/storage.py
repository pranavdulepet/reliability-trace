import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import RunCreate


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(
                """
                create table if not exists provider_keys (
                  user_id text not null,
                  provider text not null,
                  ciphertext text not null,
                  fingerprint text not null,
                  status text not null,
                  created_at text not null,
                  last_used_at text,
                  primary key (user_id, provider)
                );

                create table if not exists runs (
                  run_id text primary key,
                  user_id text not null,
                  conversation_id text,
                  user_message_id text,
                  question text not null,
                  provider text not null,
                  model text,
                  samples integer not null,
                  max_cost_usd real not null,
                  use_live_provider integer not null,
                  status text not null,
                  created_at text not null,
                  completed_at text,
                  search_mode text,
                  prior_context_json text,
                  attachment_document_ids_json text,
                  graph_json text,
                  trace_json text,
                  error text
                );

                create table if not exists conversations (
                  conversation_id text primary key,
                  user_id text not null,
                  title text not null,
                  created_at text not null,
                  updated_at text not null
                );

                create table if not exists messages (
                  message_id text primary key,
                  conversation_id text not null,
                  user_id text not null,
                  role text not null,
                  content text not null,
                  run_id text,
                  attachment_document_ids_json text,
                  created_at text not null
                );

                create table if not exists provider_preferences (
                  user_id text primary key,
                  provider text,
                  model text,
                  samples integer not null,
                  max_cost_usd real not null,
                  updated_at text not null
                );

                create table if not exists search_keys (
                  user_id text not null,
                  provider text not null,
                  ciphertext text not null,
                  fingerprint text not null,
                  status text not null,
                  created_at text not null,
                  last_used_at text,
                  primary key (user_id, provider)
                );

                create table if not exists search_preferences (
                  user_id text primary key,
                  search_mode text not null,
                  max_results integer not null,
                  updated_at text not null
                );

                create table if not exists labels (
                  label_id text primary key,
                  run_id text not null,
                  user_id text not null,
                  usefulness integer,
                  correctness integer,
                  notes text,
                  created_at text not null
                );

                create table if not exists documents (
                  document_id text primary key,
                  user_id text not null,
                  title text not null,
                  source_url text,
                  source_type text not null,
                  content_sha256 text not null,
                  created_at text not null
                );

                create table if not exists document_chunks (
                  chunk_id text primary key,
                  document_id text not null,
                  user_id text not null,
                  chunk_index integer not null,
                  text text not null,
                  embedding_json text not null,
                  token_count integer not null,
                  created_at text not null
                );

                create index if not exists document_chunks_user_idx
                  on document_chunks(user_id, document_id);

                create index if not exists conversations_user_updated_idx
                  on conversations(user_id, updated_at desc);

                create index if not exists messages_conversation_idx
                  on messages(user_id, conversation_id, created_at);
                """
            )
            self._ensure_column(con, "runs", "conversation_id", "text")
            self._ensure_column(con, "runs", "user_message_id", "text")
            self._ensure_column(con, "runs", "search_mode", "text")
            self._ensure_column(con, "runs", "prior_context_json", "text")
            self._ensure_column(con, "runs", "attachment_document_ids_json", "text")

    def _ensure_column(self, con: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
        columns = {row["name"] for row in con.execute("pragma table_info(%s)" % table).fetchall()}
        if column not in columns:
            con.execute("alter table %s add column %s %s" % (table, column, column_type))

    def save_provider_key(
        self,
        user_id: str,
        provider: str,
        ciphertext: str,
        fingerprint: str,
    ) -> Dict[str, Any]:
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into provider_keys
                  (user_id, provider, ciphertext, fingerprint, status, created_at, last_used_at)
                values (?, ?, ?, ?, 'active', ?, null)
                on conflict(user_id, provider) do update set
                  ciphertext=excluded.ciphertext,
                  fingerprint=excluded.fingerprint,
                  status='active',
                  created_at=excluded.created_at,
                  last_used_at=null
                """,
                (user_id, provider, ciphertext, fingerprint, now),
            )
        return self.get_provider_key_view(user_id, provider)

    def list_provider_keys(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select provider, fingerprint, status, created_at, last_used_at
                from provider_keys
                where user_id = ?
                order by provider
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_provider_key_view(self, user_id: str, provider: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select provider, fingerprint, status, created_at, last_used_at
                from provider_keys
                where user_id = ? and provider = ?
                """,
                (user_id, provider),
            ).fetchone()
        if row is None:
            raise KeyError("provider key not found")
        return dict(row)

    def get_provider_key_ciphertext(self, user_id: str, provider: str) -> Optional[str]:
        with self._connect() as con:
            row = con.execute(
                """
                select ciphertext
                from provider_keys
                where user_id = ? and provider = ? and status = 'active'
                """,
                (user_id, provider),
            ).fetchone()
        return None if row is None else str(row["ciphertext"])

    def mark_provider_key_used(self, user_id: str, provider: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                update provider_keys
                set last_used_at = ?
                where user_id = ? and provider = ?
                """,
                (utcnow(), user_id, provider),
            )

    def delete_provider_key(self, user_id: str, provider: str) -> bool:
        with self._connect() as con:
            cursor = con.execute(
                "delete from provider_keys where user_id = ? and provider = ?",
                (user_id, provider),
            )
        return cursor.rowcount > 0

    def save_search_key(
        self,
        user_id: str,
        provider: str,
        ciphertext: str,
        fingerprint: str,
    ) -> Dict[str, Any]:
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into search_keys
                  (user_id, provider, ciphertext, fingerprint, status, created_at, last_used_at)
                values (?, ?, ?, ?, 'active', ?, null)
                on conflict(user_id, provider) do update set
                  ciphertext=excluded.ciphertext,
                  fingerprint=excluded.fingerprint,
                  status='active',
                  created_at=excluded.created_at,
                  last_used_at=null
                """,
                (user_id, provider, ciphertext, fingerprint, now),
            )
        return self.get_search_key_view(user_id, provider)

    def get_search_key_view(self, user_id: str, provider: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select provider, fingerprint, status, created_at, last_used_at
                from search_keys
                where user_id = ? and provider = ?
                """,
                (user_id, provider),
            ).fetchone()
        if row is None:
            raise KeyError("search key not found")
        return dict(row)

    def get_search_key_ciphertext(self, user_id: str, provider: str) -> Optional[str]:
        with self._connect() as con:
            row = con.execute(
                """
                select ciphertext
                from search_keys
                where user_id = ? and provider = ? and status = 'active'
                """,
                (user_id, provider),
            ).fetchone()
        return None if row is None else str(row["ciphertext"])

    def mark_search_key_used(self, user_id: str, provider: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                update search_keys
                set last_used_at = ?
                where user_id = ? and provider = ?
                """,
                (utcnow(), user_id, provider),
            )

    def delete_search_key(self, user_id: str, provider: str) -> bool:
        with self._connect() as con:
            cursor = con.execute(
                "delete from search_keys where user_id = ? and provider = ?",
                (user_id, provider),
            )
        return cursor.rowcount > 0

    def get_search_preference(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select search_mode, max_results, updated_at
                from search_preferences
                where user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return {
                "search_mode": "auto",
                "max_results": 6,
                "updated_at": None,
            }
        return dict(row)

    def save_search_preference(self, user_id: str, search_mode: str, max_results: int) -> Dict[str, Any]:
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into search_preferences
                  (user_id, search_mode, max_results, updated_at)
                values (?, ?, ?, ?)
                on conflict(user_id) do update set
                  search_mode=excluded.search_mode,
                  max_results=excluded.max_results,
                  updated_at=excluded.updated_at
                """,
                (user_id, search_mode, max_results, now),
            )
        return self.get_search_preference(user_id)

    def get_provider_preference(self, user_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select provider, model, samples, max_cost_usd, updated_at
                from provider_preferences
                where user_id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return {
                "provider": None,
                "model": None,
                "samples": 3,
                "max_cost_usd": 1.0,
                "updated_at": None,
            }
        return dict(row)

    def save_provider_preference(
        self,
        user_id: str,
        provider: Optional[str],
        model: Optional[str],
        samples: int,
        max_cost_usd: float,
    ) -> Dict[str, Any]:
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into provider_preferences
                  (user_id, provider, model, samples, max_cost_usd, updated_at)
                values (?, ?, ?, ?, ?, ?)
                on conflict(user_id) do update set
                  provider=excluded.provider,
                  model=excluded.model,
                  samples=excluded.samples,
                  max_cost_usd=excluded.max_cost_usd,
                  updated_at=excluded.updated_at
                """,
                (user_id, provider, model, samples, max_cost_usd, now),
            )
        return self.get_provider_preference(user_id)

    def create_conversation(self, user_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        conversation_id = "conv_" + secrets.token_urlsafe(10)
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into conversations
                  (conversation_id, user_id, title, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (conversation_id, user_id, (title or "New chat").strip()[:120] or "New chat", now, now),
            )
        return self.get_conversation(user_id, conversation_id)

    def list_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select c.conversation_id, c.title, c.created_at, c.updated_at,
                       count(m.message_id) as message_count
                from conversations c
                left join messages m on m.conversation_id = c.conversation_id and m.user_id = c.user_id
                where c.user_id = ?
                group by c.conversation_id
                order by c.updated_at desc
                limit 80
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select conversation_id, title, created_at, updated_at
                from conversations
                where user_id = ? and conversation_id = ?
                """,
                (user_id, conversation_id),
            ).fetchone()
        if row is None:
            raise KeyError("conversation not found")
        conversation = dict(row)
        conversation["messages"] = self.list_messages(user_id, conversation_id)
        return conversation

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        run_id: Optional[str] = None,
        attachment_document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        self.get_conversation(user_id, conversation_id)
        message_id = "msg_" + secrets.token_urlsafe(10)
        now = utcnow()
        attachments = attachment_document_ids or []
        with self._connect() as con:
            con.execute(
                """
                insert into messages
                  (message_id, conversation_id, user_id, role, content, run_id,
                   attachment_document_ids_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, user_id, role, content, run_id, json.dumps(attachments), now),
            )
            con.execute(
                "update conversations set updated_at = ? where user_id = ? and conversation_id = ?",
                (now, user_id, conversation_id),
            )
        return self.get_message(user_id, message_id)

    def update_conversation_title(self, user_id: str, conversation_id: str, title: str) -> None:
        with self._connect() as con:
            con.execute(
                """
                update conversations
                set title = ?, updated_at = ?
                where user_id = ? and conversation_id = ?
                """,
                (title.strip()[:120] or "New chat", utcnow(), user_id, conversation_id),
            )

    def list_messages(self, user_id: str, conversation_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select m.message_id, m.conversation_id, m.role, m.content, m.run_id,
                       m.attachment_document_ids_json, m.created_at,
                       r.status as run_status, r.error as run_error, r.graph_json
                from messages m
                left join runs r on r.run_id = m.run_id and r.user_id = m.user_id
                where m.user_id = ? and m.conversation_id = ?
                order by m.created_at asc
                """,
                (user_id, conversation_id),
            ).fetchall()
        return [self._message_row_to_dict(row) for row in rows]

    def get_message(self, user_id: str, message_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select m.message_id, m.conversation_id, m.role, m.content, m.run_id,
                       m.attachment_document_ids_json, m.created_at,
                       r.status as run_status, r.error as run_error, r.graph_json
                from messages m
                left join runs r on r.run_id = m.run_id and r.user_id = m.user_id
                where m.user_id = ? and m.message_id = ?
                """,
                (user_id, message_id),
            ).fetchone()
        if row is None:
            raise KeyError("message not found")
        return self._message_row_to_dict(row)

    def assistant_message_exists_for_run(self, user_id: str, run_id: str) -> bool:
        with self._connect() as con:
            row = con.execute(
                """
                select 1 from messages
                where user_id = ? and run_id = ? and role = 'assistant'
                limit 1
                """,
                (user_id, run_id),
            ).fetchone()
        return row is not None

    def create_run(self, user_id: str, request: RunCreate) -> Dict[str, Any]:
        run_id = "run_" + secrets.token_urlsafe(10)
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into runs
                  (run_id, user_id, conversation_id, user_message_id, question, provider, model, samples,
                   max_cost_usd, use_live_provider, status, created_at, search_mode, prior_context_json,
                   attachment_document_ids_json)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    request.conversation_id,
                    request.user_message_id,
                    request.question,
                    request.provider or "preview",
                    request.model,
                    request.samples,
                    request.max_cost_usd,
                    1 if request.use_live_provider else 0,
                    now,
                    request.search_mode,
                    json.dumps(request.prior_context),
                    json.dumps(request.attachment_document_ids),
                ),
            )
        return self.get_run(user_id, run_id)

    def list_runs(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select run_id, conversation_id, user_message_id, question, provider, model, samples,
                       max_cost_usd, use_live_provider, status, created_at, completed_at, search_mode,
                       attachment_document_ids_json, error
                from runs
                where user_id = ?
                order by created_at desc
                limit 50
                """,
                (user_id,),
            ).fetchall()
        return [self._run_row_to_dict(row, include_graph=False) for row in rows]

    def get_run(self, user_id: str, run_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                "select * from runs where user_id = ? and run_id = ?",
                (user_id, run_id),
            ).fetchone()
        if row is None:
            raise KeyError("run not found")
        return self._run_row_to_dict(row)

    def set_run_status(self, user_id: str, run_id: str, status: str) -> None:
        with self._connect() as con:
            con.execute(
                "update runs set status = ? where user_id = ? and run_id = ?",
                (status, user_id, run_id),
            )

    def complete_run(self, user_id: str, run_id: str, graph: Dict[str, Any], trace: List[Dict[str, Any]]) -> None:
        with self._connect() as con:
            con.execute(
                """
                update runs
                set status = 'completed',
                    completed_at = ?,
                    graph_json = ?,
                    trace_json = ?,
                    error = null
                where user_id = ? and run_id = ?
                """,
                (utcnow(), json.dumps(graph), json.dumps(trace), user_id, run_id),
            )

    def fail_run(self, user_id: str, run_id: str, error: str, trace: List[Dict[str, Any]]) -> None:
        with self._connect() as con:
            con.execute(
                """
                update runs
                set status = 'failed',
                    completed_at = ?,
                    trace_json = ?,
                    error = ?
                where user_id = ? and run_id = ?
                """,
                (utcnow(), json.dumps(trace), error, user_id, run_id),
            )

    def delete_run(self, user_id: str, run_id: str) -> bool:
        with self._connect() as con:
            con.execute("delete from labels where user_id = ? and run_id = ?", (user_id, run_id))
            cursor = con.execute("delete from runs where user_id = ? and run_id = ?", (user_id, run_id))
        return cursor.rowcount > 0

    def save_label(
        self,
        user_id: str,
        run_id: str,
        usefulness: Optional[int],
        correctness: Optional[int],
        notes: Optional[str],
    ) -> Dict[str, Any]:
        self.get_run(user_id, run_id)
        label_id = "label_" + secrets.token_urlsafe(8)
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into labels
                  (label_id, run_id, user_id, usefulness, correctness, notes, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (label_id, run_id, user_id, usefulness, correctness, notes, now),
            )
        return {
            "label_id": label_id,
            "run_id": run_id,
            "usefulness": usefulness,
            "correctness": correctness,
            "notes": notes,
            "created_at": now,
        }

    def save_document(
        self,
        user_id: str,
        title: str,
        text: str,
        source_url: Optional[str],
        source_type: str,
        chunks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        document_id = "doc_" + secrets.token_urlsafe(10)
        now = utcnow()
        content_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._connect() as con:
            con.execute(
                """
                insert into documents
                  (document_id, user_id, title, source_url, source_type, content_sha256, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, user_id, title, source_url, source_type, content_sha, now),
            )
            for chunk in chunks:
                con.execute(
                    """
                    insert into document_chunks
                      (chunk_id, document_id, user_id, chunk_index, text, embedding_json, token_count, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "chunk_" + secrets.token_urlsafe(10),
                        document_id,
                        user_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["embedding_json"],
                        chunk["token_count"],
                        now,
                    ),
                )
        return self.get_document(user_id, document_id)

    def find_document_by_signature(
        self,
        user_id: str,
        content_sha256: str,
        source_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        params: List[Any] = [user_id, content_sha256]
        source_filter = ""
        if source_url:
            source_filter = " or source_url = ?"
            params.append(source_url)
        with self._connect() as con:
            row = con.execute(
                """
                select document_id
                from documents
                where user_id = ? and (content_sha256 = ?%s)
                order by created_at desc
                limit 1
                """
                % source_filter,
                params,
            ).fetchone()
        if row is None:
            return None
        return self.get_document(user_id, row["document_id"])

    def get_document(self, user_id: str, document_id: str) -> Dict[str, Any]:
        with self._connect() as con:
            row = con.execute(
                """
                select d.document_id, d.title, d.source_url, d.source_type, d.content_sha256, d.created_at,
                       count(c.chunk_id) as chunk_count
                from documents d
                left join document_chunks c on c.document_id = d.document_id and c.user_id = d.user_id
                where d.user_id = ? and d.document_id = ?
                group by d.document_id
                """,
                (user_id, document_id),
            ).fetchone()
        if row is None:
            raise KeyError("document not found")
        return dict(row)

    def list_documents(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select d.document_id, d.title, d.source_url, d.source_type, d.content_sha256, d.created_at,
                       count(c.chunk_id) as chunk_count
                from documents d
                left join document_chunks c on c.document_id = d.document_id and c.user_id = d.user_id
                where d.user_id = ?
                group by d.document_id
                order by d.created_at desc
                limit 100
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_document_chunks(self, user_id: str, document_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if document_ids is not None and len(document_ids) == 0:
            return []
        params: List[Any] = [user_id]
        document_filter = ""
        if document_ids is not None:
            placeholders = ",".join(["?"] * len(document_ids))
            document_filter = " and c.document_id in (%s)" % placeholders
            params.extend(document_ids)
        with self._connect() as con:
            rows = con.execute(
                """
                select c.chunk_id, c.document_id, c.chunk_index, c.text, c.embedding_json, c.token_count,
                       d.title, d.source_url, d.source_type, d.created_at
                from document_chunks c
                join documents d on d.document_id = c.document_id and d.user_id = c.user_id
                where c.user_id = ?%s
                order by d.created_at desc, c.chunk_index asc
                limit 2000
                """
                % document_filter,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def list_labeled_runs(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select r.run_id, r.graph_json, l.usefulness, l.correctness, l.created_at as label_created_at
                from labels l
                join runs r on r.run_id = l.run_id and r.user_id = l.user_id
                where l.user_id = ? and r.status = 'completed' and r.graph_json is not null
                order by l.created_at desc
                limit 500
                """,
                (user_id,),
            ).fetchall()
        results = []
        for row in rows:
            data = dict(row)
            data["graph"] = json.loads(data.pop("graph_json"))
            results.append(data)
        return results

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _run_row_to_dict(self, row: sqlite3.Row, include_graph: bool = True) -> Dict[str, Any]:
        data = dict(row)
        data["use_live_provider"] = bool(data.get("use_live_provider"))
        data["search_mode"] = data.get("search_mode") or "auto"
        data["prior_context"] = json.loads(data["prior_context_json"]) if data.get("prior_context_json") else []
        data["attachment_document_ids"] = (
            json.loads(data["attachment_document_ids_json"]) if data.get("attachment_document_ids_json") else []
        )
        if include_graph:
            data["graph"] = json.loads(data["graph_json"]) if data.get("graph_json") else None
            data["trace"] = json.loads(data["trace_json"]) if data.get("trace_json") else []
        data.pop("graph_json", None)
        data.pop("trace_json", None)
        data.pop("prior_context_json", None)
        data.pop("attachment_document_ids_json", None)
        data.pop("user_id", None)
        return data

    def _message_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["attachment_document_ids"] = (
            json.loads(data["attachment_document_ids_json"]) if data.get("attachment_document_ids_json") else []
        )
        data["run"] = None
        if data.get("run_id"):
            data["run"] = {
                "run_id": data["run_id"],
                "status": data.pop("run_status", None),
                "error": data.pop("run_error", None),
                "graph": json.loads(data["graph_json"]) if data.get("graph_json") else None,
            }
        else:
            data.pop("run_status", None)
            data.pop("run_error", None)
        data.pop("graph_json", None)
        data.pop("attachment_document_ids_json", None)
        return data
