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
                  question text not null,
                  provider text not null,
                  model text,
                  samples integer not null,
                  max_cost_usd real not null,
                  use_live_provider integer not null,
                  status text not null,
                  created_at text not null,
                  completed_at text,
                  graph_json text,
                  trace_json text,
                  error text
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
                """
            )

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

    def create_run(self, user_id: str, request: RunCreate) -> Dict[str, Any]:
        run_id = "run_" + secrets.token_urlsafe(10)
        now = utcnow()
        with self._connect() as con:
            con.execute(
                """
                insert into runs
                  (run_id, user_id, question, provider, model, samples, max_cost_usd,
                   use_live_provider, status, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
                """,
                (
                    run_id,
                    user_id,
                    request.question,
                    request.provider,
                    request.model,
                    request.samples,
                    request.max_cost_usd,
                    1 if request.use_live_provider else 0,
                    now,
                ),
            )
        return self.get_run(user_id, run_id)

    def list_runs(self, user_id: str) -> List[Dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                """
                select run_id, question, provider, model, samples, max_cost_usd,
                       use_live_provider, status, created_at, completed_at, error
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

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        return con

    def _run_row_to_dict(self, row: sqlite3.Row, include_graph: bool = True) -> Dict[str, Any]:
        data = dict(row)
        data["use_live_provider"] = bool(data.get("use_live_provider"))
        if include_graph:
            data["graph"] = json.loads(data["graph_json"]) if data.get("graph_json") else None
            data["trace"] = json.loads(data["trace_json"]) if data.get("trace_json") else []
        data.pop("graph_json", None)
        data.pop("trace_json", None)
        data.pop("user_id", None)
        return data
