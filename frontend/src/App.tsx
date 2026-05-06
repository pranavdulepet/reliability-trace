import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createConversation,
  deleteConversation,
  deleteKey,
  deleteSearchKey,
  fetchSourceUrl,
  getConversation,
  getConversations,
  getKeys,
  getProviderPreference,
  getProviders,
  getSearchPreference,
  getVerifierStatus,
  runEventSource,
  saveKey,
  saveProviderPreference,
  saveSearchKey,
  saveSearchPreference,
  sendConversationMessage,
  uploadDocument,
} from "./api";
import { ActivityTrace, ChatComposer, ConversationList, KeyManager, ProviderSettings, SearchSettings, formatTraceOutput } from "./components";
import { MarkdownText } from "./markdown";
import { AnswerCitations, ReliabilityCards, ReliabilityDetails } from "./report";
import type {
  ConversationMessage,
  ConversationSummary,
  ConversationView,
  DocumentView,
  ProviderKeyView,
  ProviderMetadata,
  ProviderPreferenceResponse,
  ReliabilityGraph,
  SearchPreferenceResponse,
  StreamEvent,
  VerifierStatus,
} from "./types";
import "./styles.css";

type View = "chat" | "settings" | "about";
const MAX_ATTACHMENTS = 6;
const MAX_FILE_BYTES = 1_000_000;
const MAX_URL_LENGTH = 2000;

export interface DraftAttachment {
  id: string;
  kind: "file" | "url";
  title: string;
  text?: string;
  url?: string;
  status: "ready" | "uploading" | "done" | "error";
  document?: DocumentView;
  error?: string;
}

function App() {
  const [providers, setProviders] = useState<ProviderMetadata[]>([]);
  const [keys, setKeys] = useState<ProviderKeyView[]>([]);
  const [preference, setPreference] = useState<ProviderPreferenceResponse | null>(null);
  const [searchPreference, setSearchPreference] = useState<SearchPreferenceResponse | null>(null);
  const [verifierStatus, setVerifierStatus] = useState<VerifierStatus | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationView | null>(null);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<DraftAttachment[]>([]);
  const [keyProvider, setKeyProvider] = useState("");
  const [keyValue, setKeyValue] = useState("");
  const [searchKeyValue, setSearchKeyValue] = useState("");
  const [view, setView] = useState<View>("chat");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streamingRunId, setStreamingRunId] = useState<string | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState("");
  const [streamGraph, setStreamGraph] = useState<ReliabilityGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submitLockRef = useRef(false);

  useEffect(() => {
    void refreshWorkspace().catch(showError);
  }, []);

  useEffect(() => {
    if (!activeConversationId) return;
    void loadConversation(activeConversationId).catch(showError);
  }, [activeConversationId]);

  const connectedProviders = useMemo(
    () => providers.filter((provider) => isRealProvider(provider) && isProviderConnected(provider)),
    [providers],
  );
  const providerReady = Boolean(preference?.resolved);
  const verifierReady = Boolean(verifierStatus?.ready);
  const chatReady = providerReady && verifierReady;
  const progress = events.length === 0 ? 0 : events[events.length - 1].progress ?? 0;

  async function refreshWorkspace() {
    const [nextProviders, nextKeys, nextPreference, nextSearchPreference, nextVerifierStatus, nextConversations] = await Promise.all([
      getProviders(),
      getKeys(),
      getProviderPreference(),
      getSearchPreference(),
      getVerifierStatus(),
      getConversations(),
    ]);
    setProviders(nextProviders);
    setKeys(nextKeys);
    setPreference(nextPreference);
    setSearchPreference(nextSearchPreference);
    setVerifierStatus(nextVerifierStatus);
    setConversations(nextConversations);
    if (!busy && activeConversationId && !nextConversations.some((conversation) => conversation.conversation_id === activeConversationId)) {
      clearActiveConversation();
    }
    setKeyProvider((current) => {
      if (nextProviders.some((provider) => provider.provider === current && isRealProvider(provider))) return current;
      return nextProviders.find(isRealProvider)?.provider ?? current;
    });
  }

  async function loadConversation(conversationId: string) {
    try {
      setConversation(await getConversation(conversationId));
    } catch (err) {
      if (isMissingConversationError(err)) {
        clearActiveConversation();
        setError(null);
        return;
      }
      throw err;
    }
  }

  async function handleNewChat() {
    clearActiveConversation();
    setView("chat");
  }

  async function handleSelectConversation(conversationId: string) {
    setActiveConversationId(conversationId);
    setEvents([]);
    setStreamGraph(null);
    setStreamingRunId(null);
    setView("chat");
  }

  async function handleSaveKey(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await saveKey(keyProvider, keyValue);
      setKeyValue("");
      await refreshWorkspace();
    } catch (err) {
      showError(err);
    }
  }

  async function handleDeleteKey(provider: string) {
    setError(null);
    try {
      await deleteKey(provider);
      await refreshWorkspace();
    } catch (err) {
      showError(err);
    }
  }

  async function handleSavePreference(payload: { provider: string | null; model: string | null; samples: number; max_cost_usd: number }) {
    setError(null);
    try {
      setPreference(await saveProviderPreference(payload));
      await refreshWorkspace();
    } catch (err) {
      showError(err);
    }
  }

  async function handleSaveSearchKey(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await saveSearchKey(searchKeyValue);
      setSearchKeyValue("");
      setSearchPreference(await getSearchPreference());
    } catch (err) {
      showError(err);
    }
  }

  async function handleDeleteSearchKey() {
    setError(null);
    try {
      await deleteSearchKey();
      setSearchPreference(await getSearchPreference());
    } catch (err) {
      showError(err);
    }
  }

  async function handleSaveSearchPreference(payload: { max_results: number }) {
    setError(null);
    try {
      const nextPreference = await saveSearchPreference({ search_mode: "always", max_results: payload.max_results });
      setSearchPreference(nextPreference);
    } catch (err) {
      showError(err);
    }
  }

  async function handleAddFiles(files: FileList | null) {
    if (!files) return;
    setError(null);
    const remaining = Math.max(0, MAX_ATTACHMENTS - attachments.length);
    const accepted = Array.from(files).slice(0, remaining).filter((file) => {
      if (file.size > MAX_FILE_BYTES) {
        setError(`${file.name} is larger than the 1 MB attachment limit.`);
        return false;
      }
      return true;
    });
    if (accepted.length === 0) {
      if (remaining === 0) setError(`Use at most ${MAX_ATTACHMENTS} attachments per message.`);
      return;
    }
    const additions = await Promise.all(
      accepted.map(async (file) => ({
        id: makeId("file"),
        kind: "file" as const,
        title: file.name,
        text: await file.text(),
        status: "ready" as const,
      })),
    );
    setAttachments((current) => [...current, ...additions]);
  }

  function removeAttachment(id: string) {
    setAttachments((current) => current.filter((attachment) => attachment.id !== id));
  }

  async function handleDeleteConversation(conversationId: string) {
    if (busy && conversationId === activeConversationId) {
      setError("Wait for the current answer to finish before deleting this chat.");
      return;
    }
    const target = conversations.find((item) => item.conversation_id === conversationId);
    const title = target?.title || "this chat";
    if (!window.confirm(`Delete "${title}"?`)) return;
    setError(null);
    try {
      await deleteConversation(conversationId);
      if (activeConversationId === conversationId) {
        clearActiveConversation();
      }
      await refreshWorkspace();
    } catch (err) {
      showError(err);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy || !chatReady || submitLockRef.current) return;
    const pastedUrlAttachments = extractUrlAttachments(content, attachments);
    if (attachments.length + pastedUrlAttachments.length > MAX_ATTACHMENTS) {
      setError(`Use at most ${MAX_ATTACHMENTS} files or links per message.`);
      return;
    }

    submitLockRef.current = true;
    setBusy(true);
    setError(null);
    setEvents([]);
    setStreamGraph(null);
    setStreamingAnswer("");
    try {
      const conversationId = activeConversationId ?? (await createConversation()).conversation_id;
      if (!activeConversationId) {
        setActiveConversationId(conversationId);
      }
      const documentIds = await materializeAttachments(pastedUrlAttachments);
      const response = await sendConversationMessage(conversationId, {
        content,
        attachment_document_ids: documentIds,
      });
      setDraft("");
      setAttachments([]);
      setStreamingRunId(response.run.run_id);
      await refreshWorkspace();
      await loadConversation(conversationId);
      await streamRun(response.run.run_id, conversationId);
    } catch (err) {
      showError(err);
      setBusy(false);
    } finally {
      submitLockRef.current = false;
    }
  }

  async function materializeAttachments(pastedUrlAttachments: DraftAttachment[]): Promise<string[]> {
    const documentIds: string[] = [];
    const workItems = [...attachments, ...pastedUrlAttachments];
    if (pastedUrlAttachments.length > 0) {
      setAttachments((current) => [...current, ...pastedUrlAttachments]);
    }
    for (const attachment of workItems) {
      setAttachments((current) => current.map((item) => (item.id === attachment.id ? { ...item, status: "uploading" } : item)));
      try {
        const document =
          attachment.kind === "file"
            ? await uploadDocument({
                title: attachment.title,
                text: attachment.text ?? "",
                source_type: "chat_attachment",
              })
            : await fetchSourceUrl(attachment.url ?? "");
        documentIds.push(document.document_id);
        setAttachments((current) =>
          current.map((item) => (item.id === attachment.id ? { ...item, status: "done", document } : item)),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : "Attachment failed";
        setAttachments((current) =>
          current.map((item) => (item.id === attachment.id ? { ...item, status: "error", error: message } : item)),
        );
        throw err;
      }
    }
    return documentIds;
  }

  async function streamRun(runId: string, conversationId: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const source = runEventSource(runId);
      source.addEventListener("progress", (event) => {
        const parsed = JSON.parse(event.data) as StreamEvent;
        setEvents((current) => [...current, parsed]);
      });
      source.addEventListener("audit_progress", (event) => {
        const parsed = JSON.parse(event.data) as StreamEvent;
        setEvents((current) => [...current, parsed]);
      });
      source.addEventListener("answer_delta", (event) => {
        const parsed = JSON.parse(event.data) as StreamEvent;
        setStreamingAnswer((current) => current + (parsed.delta ?? ""));
      });
      source.addEventListener("answer_completed", (event) => {
        const parsed = JSON.parse(event.data) as StreamEvent;
        setStreamingAnswer(parsed.answer ?? "");
        setEvents((current) => [...current, parsed]);
      });
      source.addEventListener("completed", (event) => {
        const parsed = JSON.parse(event.data) as StreamEvent;
        setEvents((current) => [...current, parsed]);
        if (parsed.graph) setStreamGraph(parsed.graph);
        setBusy(false);
        setStreamingRunId(null);
        source.close();
        void refreshWorkspace();
        void loadConversation(conversationId);
        resolve();
      });
      source.addEventListener("error", (event) => {
        setBusy(false);
        setStreamingRunId(null);
        setStreamingAnswer("");
        source.close();
        reject(new Error(streamErrorMessage(event)));
      });
    });
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : "Something went wrong");
  }

  function clearActiveConversation() {
    setActiveConversationId(null);
    setConversation(null);
    setDraft("");
    setAttachments([]);
    setEvents([]);
    setStreamGraph(null);
    setStreamingRunId(null);
    setStreamingAnswer("");
    setBusy(false);
  }

  function handleDraftChange(value: string) {
    setDraft(value);
    if (error) setError(null);
  }

  return (
    <div className="chat-shell">
      <ConversationList
        conversations={conversations}
        activeConversationId={activeConversationId}
        view={view}
        onNewChat={() => void handleNewChat()}
        onSelectConversation={(id) => void handleSelectConversation(id)}
        onDeleteConversation={(id) => void handleDeleteConversation(id)}
        onOpenAbout={() => setView("about")}
        onOpenSettings={() => setView("settings")}
      />

      <main className="chat-main">
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        {view === "settings" ? (
          <SettingsView
            providers={providers}
            keys={keys}
            preference={preference}
            connectedProviders={connectedProviders}
            keyProvider={keyProvider}
            keyValue={keyValue}
            setKeyProvider={setKeyProvider}
            setKeyValue={setKeyValue}
            onSaveKey={handleSaveKey}
            onDeleteKey={handleDeleteKey}
            onSavePreference={handleSavePreference}
            searchPreference={searchPreference}
            verifierStatus={verifierStatus}
            searchKeyValue={searchKeyValue}
            setSearchKeyValue={setSearchKeyValue}
            onSaveSearchKey={handleSaveSearchKey}
            onDeleteSearchKey={handleDeleteSearchKey}
            onSaveSearchPreference={handleSaveSearchPreference}
          />
        ) : view === "about" ? (
          <AboutView />
        ) : (
          <ChatView
            conversation={conversation}
            events={events}
            streamGraph={streamGraph}
            streamingRunId={streamingRunId}
            streamingAnswer={streamingAnswer}
            progress={progress}
            draft={draft}
            attachments={attachments}
            busy={busy}
            providerReady={providerReady}
            verifierReady={verifierReady}
            verifierMessage={verifierStatus?.message ?? null}
            connectedProviderCount={connectedProviders.length}
            searchAvailable={searchPreference?.key.key_state === "saved" || searchPreference?.key.key_state === "env"}
            setDraft={handleDraftChange}
            onSubmit={handleSubmit}
            onAddFiles={handleAddFiles}
            onRemoveAttachment={removeAttachment}
            onOpenSettings={() => setView("settings")}
          />
        )}
      </main>
    </div>
  );
}

function isMissingConversationError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return err.message.includes("Not Found") || err.message.includes('"detail"');
}

function ChatView({
  conversation,
  events,
  streamGraph,
  streamingRunId,
  streamingAnswer,
  progress,
  draft,
  attachments,
  busy,
  providerReady,
  verifierReady,
  verifierMessage,
  connectedProviderCount,
  searchAvailable,
  setDraft,
  onSubmit,
  onAddFiles,
  onRemoveAttachment,
  onOpenSettings,
}: {
  conversation: ConversationView | null;
  events: StreamEvent[];
  streamGraph: ReliabilityGraph | null;
  streamingRunId: string | null;
  streamingAnswer: string;
  progress: number;
  draft: string;
  attachments: DraftAttachment[];
  busy: boolean;
  providerReady: boolean;
  verifierReady: boolean;
  verifierMessage: string | null;
  connectedProviderCount: number;
  searchAvailable: boolean;
  setDraft: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onAddFiles: (files: FileList | null) => void;
  onRemoveAttachment: (id: string) => void;
  onOpenSettings: () => void;
}) {
  const messages = conversation?.messages ?? [];
  const pendingRunId = streamingRunId ?? streamGraph?.run.run_id ?? null;
  const hasPendingAssistant = Boolean(pendingRunId && !messages.some((message) => message.run_id === pendingRunId && message.role === "assistant"));
  const scrollRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (distanceFromBottom > 360 && !hasPendingAssistant) return;
    const animation = window.requestAnimationFrame(() => {
      element.scrollTo({
        top: element.scrollHeight,
        behavior: hasPendingAssistant ? "smooth" : "auto",
      });
    });
    return () => window.cancelAnimationFrame(animation);
  }, [events.length, hasPendingAssistant, messages.length, streamGraph?.answer.final_answer]);

  return (
    <div className="thread-layout">
      <section ref={scrollRef} className="thread-scroll" aria-busy={busy} aria-label="Conversation">
        {messages.length === 0 && !hasPendingAssistant ? (
          <div className="empty-chat">
            <h1>Ask anything. See why the answer is trustworthy.</h1>
            <p>Attach files or paste links in the message when the answer should be grounded in specific material.</p>
            {!searchAvailable && (
              <p className="search-warning">Web evidence is unavailable until a search key is added in Settings. Current factual answers will be less reliable.</p>
            )}
          </div>
        ) : (
          messages.map((message) => <MessageBubble key={message.message_id} message={message} />)
        )}
        {hasPendingAssistant && (
          <PendingAssistant events={events} graph={streamGraph} progress={progress} streamingAnswer={streamingAnswer} />
        )}
      </section>
      <ChatComposer
        value={draft}
        attachments={attachments}
        busy={busy}
        providerReady={providerReady}
        verifierReady={verifierReady}
        verifierMessage={verifierMessage}
        connectedProviderCount={connectedProviderCount}
        searchAvailable={searchAvailable}
        onChange={setDraft}
        onSubmit={onSubmit}
        onAddFiles={onAddFiles}
        onRemoveAttachment={onRemoveAttachment}
        onOpenSettings={onOpenSettings}
      />
    </div>
  );
}

function MessageBubble({ message }: { message: ConversationMessage }) {
  const graph = message.run?.graph;
  const citationLookup = graph ? new Map((graph.answer.citations ?? []).map((citation) => [citation.citation_id, citation])) : undefined;
  if (message.role === "user") {
    return (
      <article className="message-row user-message">
        <div className="message-content">
          <p>{message.content}</p>
          {message.attachment_document_ids.length > 0 && (
            <div className="message-attachments">{message.attachment_document_ids.length} attachment source{message.attachment_document_ids.length === 1 ? "" : "s"}</div>
          )}
        </div>
      </article>
    );
  }
  return (
    <article className="message-row assistant-message">
      <div className="avatar" aria-hidden="true">RG</div>
      <div className="message-content">
        <MarkdownText text={message.content} citations={graph?.answer.citation_annotations} citationLookup={citationLookup} />
        {graph && (
          <>
            <AnswerCitations graph={graph} />
            <ReliabilityCards graph={graph} />
            <ReliabilityDetails graph={graph} />
          </>
        )}
      </div>
    </article>
  );
}

function GraphActivity({ graph }: { graph: ReliabilityGraph }) {
  return (
    <details className="activity-box">
      <summary>
        <span>Activity</span>
        <strong>100%</strong>
      </summary>
      <div className="activity-progress" aria-label="Activity progress" aria-valuemax={100} aria-valuemin={0} aria-valuenow={100} role="progressbar">
        <span style={{ width: "100%" }} />
      </div>
      <ol>
        {graph.trace.length === 0 ? (
          <li>No observable steps were recorded.</li>
        ) : (
          graph.trace.map((span) => (
            <li key={span.span_id}>
              <strong>{formatTraceType(span.type)}</strong>
              <p>{span.input_summary}</p>
              {span.output_summary && <small>{formatTraceOutput(span)}</small>}
            </li>
          ))
        )}
      </ol>
    </details>
  );
}

function PendingAssistant({
  events,
  graph,
  progress,
  streamingAnswer,
}: {
  events: StreamEvent[];
  graph: ReliabilityGraph | null;
  progress: number;
  streamingAnswer: string;
}) {
  const citationLookup = graph ? new Map((graph.answer.citations ?? []).map((citation) => [citation.citation_id, citation])) : undefined;
  return (
    <article className="message-row assistant-message" aria-live="polite">
      <div className="avatar" aria-hidden="true">RG</div>
      <div className="message-content">
        {streamingAnswer ? (
          <MarkdownText text={streamingAnswer} citations={graph?.answer.citation_annotations} citationLookup={citationLookup} />
        ) : (
          <div className="typing-line" role="status">Starting answer</div>
        )}
        {!graph && streamingAnswer && <div className="checking-line" role="status">Checking reliability...</div>}
        <ActivityTrace events={events} progress={progress} />
        {graph && (
          <>
            <AnswerCitations graph={graph} />
            <ReliabilityCards graph={graph} />
            <ReliabilityDetails graph={graph} />
          </>
        )}
      </div>
    </article>
  );
}

function SettingsView(props: {
  providers: ProviderMetadata[];
  keys: ProviderKeyView[];
  preference: ProviderPreferenceResponse | null;
  connectedProviders: ProviderMetadata[];
  keyProvider: string;
  keyValue: string;
  setKeyProvider: (value: string) => void;
  setKeyValue: (value: string) => void;
  onSaveKey: (event: FormEvent) => void;
  onDeleteKey: (provider: string) => void;
  onSavePreference: (payload: { provider: string | null; model: string | null; samples: number; max_cost_usd: number }) => void;
  searchPreference: SearchPreferenceResponse | null;
  verifierStatus: VerifierStatus | null;
  searchKeyValue: string;
  setSearchKeyValue: (value: string) => void;
  onSaveSearchKey: (event: FormEvent) => void;
  onDeleteSearchKey: () => void;
  onSaveSearchPreference: (payload: { max_results: number }) => void;
}) {
  return (
    <div className="settings-page">
      <header>
        <h1>Settings</h1>
        <p>Manage model providers and defaults for new chats.</p>
      </header>
      <div className="settings-columns">
        <KeyManager
          providers={props.providers}
          keys={props.keys}
          keyProvider={props.keyProvider}
          keyValue={props.keyValue}
          setKeyProvider={props.setKeyProvider}
          setKeyValue={props.setKeyValue}
          onSave={props.onSaveKey}
          onDelete={props.onDeleteKey}
        />
        <ProviderSettings
          providers={props.providers}
          connectedProviders={props.connectedProviders}
          preference={props.preference}
          onSave={props.onSavePreference}
        />
        <SearchSettings
          preference={props.searchPreference}
          keyValue={props.searchKeyValue}
          setKeyValue={props.setSearchKeyValue}
          onSaveKey={props.onSaveSearchKey}
          onDeleteKey={props.onDeleteSearchKey}
          onSavePreference={props.onSaveSearchPreference}
        />
        <section className="settings-panel">
          <div className="section-heading">
            <h2>Entailment verifier</h2>
            <p>Required for claim/source reliability checks.</p>
          </div>
          <div className="key-row">
            <div>
              <strong>{props.verifierStatus?.ready ? "Ready" : "Setup required"}</strong>
              <span>{props.verifierStatus?.message ?? "Checking verifier status..."}</span>
            </div>
          </div>
          {!props.verifierStatus?.ready && <p className="panel-note">Install the local entailment verifier, then restart the app. The setup guide includes the exact command.</p>}
        </section>
      </div>
    </div>
  );
}

function AboutView() {
  const papers = [
    ["FActScore", "Atomic fact decomposition and source support checks.", "https://aclanthology.org/2023.emnlp-main.741/"],
    ["SelfCheckGPT", "Sampling consistency as hallucination evidence.", "https://arxiv.org/abs/2303.08896"],
    ["Semantic Entropy", "Meaning-level disagreement across samples.", "https://www.nature.com/articles/s41586-024-07421-0"],
    ["SAFE / LongFact", "Search-augmented factuality checks.", "https://arxiv.org/abs/2403.18802"],
    ["Calibration", "Reliability diagrams, ECE, and score calibration.", "https://proceedings.mlr.press/v70/guo17a.html"],
    ["Unfaithful CoT", "Why hidden reasoning is not treated as proof.", "https://arxiv.org/abs/2305.04388"],
  ];
  return (
    <section className="about-page">
      <div className="about-hero">
        <h1>ReliabilityGraph explains why an answer should or should not be trusted.</h1>
        <p>
          The system shows observable activity, source support, uncertainty, disagreement, robustness checks, and calibration signals.
          It does not invent hidden reasoning traces.
        </p>
      </div>
      <div className="about-grid">
        {papers.map(([title, body, href]) => (
          <a className="research-card" href={href} key={title} rel="noreferrer" target="_blank">
            <strong>{title}</strong>
            <p>{body}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

function isRealProvider(provider: ProviderMetadata): boolean {
  return provider.provider !== "preview" && provider.provider !== "local";
}

function isProviderConnected(provider: ProviderMetadata): boolean {
  return provider.key_state === "saved" || provider.key_state === "env";
}

function makeId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2)}`;
}

function extractUrlAttachments(content: string, existingAttachments: DraftAttachment[]): DraftAttachment[] {
  const existingUrls = new Set(existingAttachments.map((attachment) => normalizeUrl(attachment.url ?? "")).filter(Boolean));
  const urls: string[] = [];
  for (const match of content.matchAll(/https?:\/\/[^\s<>"']+/gi)) {
    const normalized = normalizeUrl(match[0].replace(/[),.;!?]+$/g, ""));
    if (!normalized || existingUrls.has(normalized) || urls.includes(normalized)) continue;
    urls.push(normalized);
  }
  return urls.map((url) => ({
    id: makeId("url"),
    kind: "url" as const,
    title: urlTitle(url),
    url,
    status: "ready" as const,
  }));
}

function normalizeUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > MAX_URL_LENGTH) return null;
  try {
    const parsed = new URL(trimmed);
    if (!["http:", "https:"].includes(parsed.protocol)) return null;
    if (parsed.username || parsed.password) return null;
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return null;
  }
}

function urlTitle(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname === "/" ? "" : parsed.pathname}`.slice(0, 80);
  } catch {
    return url.replace(/^https?:\/\//, "").slice(0, 80);
  }
}

function streamErrorMessage(event: Event): string {
  const data = "data" in event ? (event as MessageEvent).data : null;
  if (typeof data === "string" && data.trim()) {
    try {
      const parsed = JSON.parse(data) as { message?: string; stage?: string; code?: string };
      if (parsed.message && parsed.stage) return `${formatTraceType(parsed.stage)}: ${parsed.message}`;
      return parsed.message || parsed.code || "Run failed";
    } catch {
      return data;
    }
  }
  return "Run failed";
}

function formatTraceType(value: string): string {
  return value.replaceAll("_", " ");
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
