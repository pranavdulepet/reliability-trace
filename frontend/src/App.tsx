import { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createConversation,
  deleteKey,
  fetchSourceUrl,
  getConversation,
  getConversations,
  getKeys,
  getProviderPreference,
  getProviders,
  runEventSource,
  saveKey,
  saveProviderPreference,
  sendConversationMessage,
  uploadDocument,
} from "./api";
import { ActivityTrace, ChatComposer, ConversationList, KeyManager, ProviderSettings, formatTraceOutput } from "./components";
import { ReliabilityCards, ReliabilityDetails } from "./report";
import type {
  ConversationMessage,
  ConversationSummary,
  ConversationView,
  DocumentView,
  ProviderKeyView,
  ProviderMetadata,
  ProviderPreferenceResponse,
  ReliabilityGraph,
  StreamEvent,
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
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationView | null>(null);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<DraftAttachment[]>([]);
  const [keyProvider, setKeyProvider] = useState("");
  const [keyValue, setKeyValue] = useState("");
  const [view, setView] = useState<View>("chat");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [streamingRunId, setStreamingRunId] = useState<string | null>(null);
  const [streamGraph, setStreamGraph] = useState<ReliabilityGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  const progress = events.length === 0 ? 0 : events[events.length - 1].progress ?? 0;

  async function refreshWorkspace() {
    const [nextProviders, nextKeys, nextPreference, nextConversations] = await Promise.all([
      getProviders(),
      getKeys(),
      getProviderPreference(),
      getConversations(),
    ]);
    setProviders(nextProviders);
    setKeys(nextKeys);
    setPreference(nextPreference);
    setConversations(nextConversations);
    setKeyProvider((current) => {
      if (nextProviders.some((provider) => provider.provider === current && isRealProvider(provider))) return current;
      return nextProviders.find(isRealProvider)?.provider ?? current;
    });
  }

  async function loadConversation(conversationId: string) {
    setConversation(await getConversation(conversationId));
  }

  async function handleNewChat() {
    setActiveConversationId(null);
    setConversation(null);
    setDraft("");
    setAttachments([]);
    setEvents([]);
    setStreamGraph(null);
    setStreamingRunId(null);
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

  function handleAddUrl(url: string) {
    const trimmed = url.trim();
    if (!trimmed) return;
    setError(null);
    if (attachments.length >= MAX_ATTACHMENTS) {
      setError(`Use at most ${MAX_ATTACHMENTS} attachments per message.`);
      return;
    }
    if (trimmed.length > MAX_URL_LENGTH) {
      setError("URL is too long.");
      return;
    }
    try {
      const parsed = new URL(trimmed);
      if (!["http:", "https:"].includes(parsed.protocol)) {
        setError("Only http and https URLs can be attached.");
        return;
      }
      if (parsed.username || parsed.password) {
        setError("URLs with credentials cannot be attached.");
        return;
      }
    } catch {
      setError("Enter a valid URL.");
      return;
    }
    setAttachments((current) => [
      ...current,
      {
        id: makeId("url"),
        kind: "url",
        title: trimmed.replace(/^https?:\/\//, "").slice(0, 80),
        url: trimmed,
        status: "ready",
      },
    ]);
  }

  function removeAttachment(id: string) {
    setAttachments((current) => current.filter((attachment) => attachment.id !== id));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || busy || !providerReady) return;

    setBusy(true);
    setError(null);
    setEvents([]);
    setStreamGraph(null);
    try {
      const conversationId = activeConversationId ?? (await createConversation()).conversation_id;
      if (!activeConversationId) {
        setActiveConversationId(conversationId);
      }
      const documentIds = await materializeAttachments();
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
    }
  }

  async function materializeAttachments(): Promise<string[]> {
    const documentIds: string[] = [];
    for (const attachment of attachments) {
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
      source.addEventListener("error", () => {
        setBusy(false);
        setStreamingRunId(null);
        source.close();
        reject(new Error("Run stream failed"));
      });
    });
  }

  function showError(err: unknown) {
    setError(err instanceof Error ? err.message : "Something went wrong");
  }

  return (
    <div className="chat-shell">
      <ConversationList
        conversations={conversations}
        activeConversationId={activeConversationId}
        view={view}
        onNewChat={() => void handleNewChat()}
        onSelectConversation={(id) => void handleSelectConversation(id)}
        onOpenAbout={() => setView("about")}
        onOpenSettings={() => setView("settings")}
      />

      <main className="chat-main">
        {error && <div className="error-banner">{error}</div>}
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
          />
        ) : view === "about" ? (
          <AboutView />
        ) : (
          <ChatView
            conversation={conversation}
            events={events}
            streamGraph={streamGraph}
            streamingRunId={streamingRunId}
            progress={progress}
            draft={draft}
            attachments={attachments}
            busy={busy}
            providerReady={providerReady}
            connectedProviderCount={connectedProviders.length}
            setDraft={setDraft}
            onSubmit={handleSubmit}
            onAddFiles={handleAddFiles}
            onAddUrl={handleAddUrl}
            onRemoveAttachment={removeAttachment}
            onOpenSettings={() => setView("settings")}
          />
        )}
      </main>
    </div>
  );
}

function ChatView({
  conversation,
  events,
  streamGraph,
  streamingRunId,
  progress,
  draft,
  attachments,
  busy,
  providerReady,
  connectedProviderCount,
  setDraft,
  onSubmit,
  onAddFiles,
  onAddUrl,
  onRemoveAttachment,
  onOpenSettings,
}: {
  conversation: ConversationView | null;
  events: StreamEvent[];
  streamGraph: ReliabilityGraph | null;
  streamingRunId: string | null;
  progress: number;
  draft: string;
  attachments: DraftAttachment[];
  busy: boolean;
  providerReady: boolean;
  connectedProviderCount: number;
  setDraft: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onAddFiles: (files: FileList | null) => void;
  onAddUrl: (url: string) => void;
  onRemoveAttachment: (id: string) => void;
  onOpenSettings: () => void;
}) {
  const messages = conversation?.messages ?? [];
  const hasPendingAssistant = Boolean(streamingRunId && !messages.some((message) => message.run_id === streamingRunId && message.role === "assistant"));

  return (
    <div className="thread-layout">
      <section className="thread-scroll" aria-label="Conversation">
        {messages.length === 0 && !hasPendingAssistant ? (
          <div className="empty-chat">
            <h1>Ask anything. See why the answer is trustworthy.</h1>
            <p>Attach files or URLs when the answer should be grounded in specific material.</p>
          </div>
        ) : (
          messages.map((message) => <MessageBubble key={message.message_id} message={message} />)
        )}
        {hasPendingAssistant && (
          <PendingAssistant events={events} graph={streamGraph} progress={progress} />
        )}
      </section>
      <ChatComposer
        value={draft}
        attachments={attachments}
        busy={busy}
        providerReady={providerReady}
        connectedProviderCount={connectedProviderCount}
        onChange={setDraft}
        onSubmit={onSubmit}
        onAddFiles={onAddFiles}
        onAddUrl={onAddUrl}
        onRemoveAttachment={onRemoveAttachment}
        onOpenSettings={onOpenSettings}
      />
    </div>
  );
}

function MessageBubble({ message }: { message: ConversationMessage }) {
  const graph = message.run?.graph;
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
        <p>{message.content}</p>
        {graph && (
          <>
            <GraphActivity graph={graph} />
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
      <div className="activity-progress" aria-label="Activity progress">
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

function PendingAssistant({ events, graph, progress }: { events: StreamEvent[]; graph: ReliabilityGraph | null; progress: number }) {
  return (
    <article className="message-row assistant-message">
      <div className="avatar" aria-hidden="true">RG</div>
      <div className="message-content">
        <div className="typing-line">{graph ? "Finalizing answer..." : "Working through the answer..."}</div>
        <ActivityTrace events={events} progress={progress} defaultOpen />
        {graph && (
          <>
            <p>{graph.answer.final_answer}</p>
            <ReliabilityCards graph={graph} />
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

function formatTraceType(value: string): string {
  return value.replaceAll("_", " ");
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
