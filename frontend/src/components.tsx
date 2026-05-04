import { Dispatch, FormEvent, SetStateAction, useEffect, useRef, useState } from "react";
import type { DraftAttachment } from "./App";
import type {
  ConversationSummary,
  ProviderKeyView,
  ProviderMetadata,
  ProviderPreferenceResponse,
  SearchMode,
  SearchPreferenceResponse,
  StreamEvent,
  TraceSpan,
} from "./types";

interface ConversationListProps {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  view: string;
  onNewChat: () => void;
  onSelectConversation: (conversationId: string) => void;
  onOpenAbout: () => void;
  onOpenSettings: () => void;
}

export function ConversationList({
  conversations,
  activeConversationId,
  view,
  onNewChat,
  onSelectConversation,
  onOpenAbout,
  onOpenSettings,
}: ConversationListProps) {
  const visibleConversations = conversations.slice(0, 50);
  return (
    <aside className="conversation-rail">
      <div className="brand-block">
        <div className="brand-mark" aria-hidden="true">RG</div>
        <strong>ReliabilityGraph</strong>
      </div>
      <button className="new-chat-button" type="button" onClick={onNewChat}>
        New chat
      </button>
      <nav className="conversation-list" aria-label="Conversations">
        {conversations.length === 0 ? (
          <p className="empty">No conversations yet.</p>
        ) : (
          visibleConversations.map((conversation) => (
            <button
              className={conversation.conversation_id === activeConversationId && view === "chat" ? "conversation-item active" : "conversation-item"}
              key={conversation.conversation_id}
              type="button"
              onClick={() => onSelectConversation(conversation.conversation_id)}
            >
              <span>{conversation.title}</span>
              <small>{conversation.message_count} messages</small>
            </button>
          ))
        )}
        {conversations.length > visibleConversations.length && (
          <p className="rail-note">Showing latest {visibleConversations.length} chats.</p>
        )}
      </nav>
      <div className="rail-footer">
        <button className={view === "about" ? "rail-link active" : "rail-link"} type="button" onClick={onOpenAbout}>
          About
        </button>
        <button className={view === "settings" ? "rail-link active" : "rail-link"} type="button" onClick={onOpenSettings}>
          Settings
        </button>
      </div>
    </aside>
  );
}

interface ChatComposerProps {
  value: string;
  attachments: DraftAttachment[];
  busy: boolean;
  providerReady: boolean;
  connectedProviderCount: number;
  searchMode: SearchMode;
  onSearchModeChange: (value: SearchMode) => void;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onAddFiles: (files: FileList | null) => void;
  onAddUrl: (url: string) => void;
  onRemoveAttachment: (id: string) => void;
  onOpenSettings: () => void;
}

export function ChatComposer({
  value,
  attachments,
  busy,
  providerReady,
  connectedProviderCount,
  searchMode,
  onSearchModeChange,
  onChange,
  onSubmit,
  onAddFiles,
  onAddUrl,
  onRemoveAttachment,
  onOpenSettings,
}: ChatComposerProps) {
  const [urlDraft, setUrlDraft] = useState("");
  const [toolsOpen, setToolsOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const disabled = busy || value.trim().length < 3 || !providerReady;
  const canAddUrl = !busy && urlDraft.trim().length > 0;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 190)}px`;
  }, [value]);

  return (
    <form className="chat-composer" onSubmit={onSubmit}>
      {attachments.length > 0 && (
        <div className="attachment-row">
          {attachments.map((attachment) => (
            <button
              className={`attachment-chip status-${attachment.status}`}
              key={attachment.id}
              title={attachment.error ?? attachment.title}
              type="button"
              onClick={() => onRemoveAttachment(attachment.id)}
            >
              <span>{attachment.kind === "file" ? "File" : "URL"}</span>
              {attachment.title}
            </button>
          ))}
        </div>
      )}
      <textarea
        ref={textareaRef}
        aria-label="Message"
        value={value}
        placeholder="Ask a question..."
        rows={1}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          const nativeEvent = event.nativeEvent as KeyboardEvent;
          if (nativeEvent.isComposing) return;
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <div className="composer-actions">
        <label className={busy ? "attachment-button disabled-control" : "attachment-button"} aria-disabled={busy}>
          Attach files
          <input
            accept=".txt,.md,.csv,.json,.log"
            disabled={busy}
            multiple
            type="file"
            onChange={(event) => {
              onAddFiles(event.target.files);
              event.target.value = "";
            }}
          />
        </label>
        <div className="url-adder">
          <input
            aria-label="Attachment URL"
            disabled={busy}
            value={urlDraft}
            placeholder="Add URL"
            onChange={(event) => setUrlDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter") return;
              event.preventDefault();
              if (!canAddUrl) return;
              onAddUrl(urlDraft);
              setUrlDraft("");
            }}
          />
          <button
            disabled={!canAddUrl}
            type="button"
            onClick={() => {
              onAddUrl(urlDraft);
              setUrlDraft("");
            }}
          >
            Add
          </button>
        </div>
        <details className="tools-menu" open={toolsOpen} onToggle={(event) => setToolsOpen(event.currentTarget.open)}>
          <summary>Search: {searchModeLabel(searchMode)}</summary>
          <div className="search-mode-options">
            {(["auto", "always", "off"] as SearchMode[]).map((mode) => (
              <label key={mode}>
                <input
                  checked={searchMode === mode}
                  name="search-mode"
                  type="radio"
                  value={mode}
                  onChange={() => {
                    onSearchModeChange(mode);
                    setToolsOpen(false);
                  }}
                />
                <span>{searchModeLabel(mode)}</span>
              </label>
            ))}
          </div>
        </details>
        <div className="composer-status">
          {busy ? "Working" : providerReady ? "Ready" : connectedProviderCount === 0 ? "Connect a provider in Settings" : "Choose a default provider in Settings"}
        </div>
        {!providerReady && (
          <button className="text-link" type="button" onClick={onOpenSettings}>
            Settings
          </button>
        )}
        <button aria-busy={busy} className="send-button" disabled={disabled} type="submit">
          {busy ? "Sending" : "Send"}
        </button>
      </div>
    </form>
  );
}

export function ActivityTrace({
  events,
  progress,
  defaultOpen = false,
}: {
  events: StreamEvent[];
  progress: number;
  defaultOpen?: boolean;
}) {
  const visibleEvents = compactEvents(events);
  return (
    <details className="activity-box" open={defaultOpen}>
      <summary>
        <span>Activity</span>
        <strong>{Math.round(progress * 100)}%</strong>
      </summary>
      <div className="activity-progress" aria-label="Activity progress" aria-valuemax={100} aria-valuemin={0} aria-valuenow={Math.round(progress * 100)} role="progressbar">
        <span style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      <ol>
        {events.length === 0 ? (
          <li>Waiting for the first observable step.</li>
        ) : (
          visibleEvents.map((event, index) => (
            <li key={`${event.message}-${index}`}>
              <strong>{formatTraceType(event.span?.type ?? event.type)}</strong>
              <p>{event.message}</p>
              {event.span?.status === "completed" && event.span.output_summary !== "{}" && <small>{formatTraceOutput(event.span)}</small>}
            </li>
          ))
        )}
      </ol>
    </details>
  );
}

interface KeyManagerProps {
  providers: ProviderMetadata[];
  keys: ProviderKeyView[];
  keyProvider: string;
  keyValue: string;
  setKeyProvider: Dispatch<SetStateAction<string>> | ((value: string) => void);
  setKeyValue: Dispatch<SetStateAction<string>> | ((value: string) => void);
  onSave: (event: FormEvent) => void;
  onDelete: (provider: string) => void;
}

export function KeyManager({
  providers,
  keys,
  keyProvider,
  keyValue,
  setKeyProvider,
  setKeyValue,
  onSave,
  onDelete,
}: KeyManagerProps) {
  const keyProviders = providers.filter((provider) => provider.provider !== "local" && provider.provider !== "preview");
  return (
    <section className="settings-panel">
      <div className="section-heading">
        <h2>Provider keys</h2>
        <p>Keys stay server-side and appear only as fingerprints.</p>
      </div>
      <form className="inline-form" onSubmit={onSave}>
        <select value={keyProvider} onChange={(event) => setKeyProvider(event.target.value)}>
          {keyProviders.map((provider) => (
            <option key={provider.provider} value={provider.provider}>
              {provider.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Provider API key"
          placeholder="Paste API key"
          type="password"
          value={keyValue}
          onChange={(event) => setKeyValue(event.target.value)}
        />
        <button type="submit">Save</button>
      </form>
      <div className="key-list">
        {keys.length === 0 ? (
          <p className="empty">No provider keys saved.</p>
        ) : (
          keys.map((key) => (
            <div className="key-row" key={key.provider}>
              <div>
                <strong>{key.provider}</strong>
                <span>{key.fingerprint}</span>
              </div>
              <button className="quiet-button" type="button" onClick={() => onDelete(key.provider)}>
                Delete
              </button>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

export function ProviderSettings({
  providers,
  connectedProviders,
  preference,
  onSave,
}: {
  providers: ProviderMetadata[];
  connectedProviders: ProviderMetadata[];
  preference: ProviderPreferenceResponse | null;
  onSave: (payload: { provider: string | null; model: string | null; samples: number; max_cost_usd: number }) => void;
}) {
  const [provider, setProvider] = useState<string | null>(preference?.preference.provider ?? connectedProviders[0]?.provider ?? null);
  const [model, setModel] = useState(preference?.preference.model ?? "");
  const [samples, setSamples] = useState(preference?.preference.samples ?? 3);
  const [maxCost, setMaxCost] = useState(preference?.preference.max_cost_usd ?? 1);

  useEffect(() => {
    setProvider(preference?.preference.provider ?? connectedProviders[0]?.provider ?? null);
    setModel(preference?.preference.model ?? "");
    setSamples(preference?.preference.samples ?? 3);
    setMaxCost(preference?.preference.max_cost_usd ?? 1);
  }, [preference, connectedProviders]);

  const realProviders = providers.filter((item) => item.provider !== "local" && item.provider !== "preview");
  return (
    <section className="settings-panel">
      <div className="section-heading">
        <h2>Default model</h2>
        <p>Chat uses this default unless only one provider is connected.</p>
      </div>
      <form
        className="preference-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSave({ provider, model: model.trim() || null, samples, max_cost_usd: maxCost });
        }}
      >
        <label>
          Provider
          <select value={provider ?? ""} onChange={(event) => setProvider(event.target.value || null)}>
            <option value="">Auto</option>
            {realProviders.map((item) => (
              <option disabled={!connectedProviders.some((connected) => connected.provider === item.provider)} key={item.provider} value={item.provider}>
                {item.label} {connectedProviders.some((connected) => connected.provider === item.provider) ? "" : "(missing key)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Model
          <input value={model} placeholder="Provider default" onChange={(event) => setModel(event.target.value)} />
        </label>
        <div className="settings-number-row">
          <label>
            Samples
            <input min={1} max={5} type="number" value={samples} onChange={(event) => setSamples(Number(event.target.value))} />
          </label>
          <label>
            Max cost
            <input min={0} max={100} step={0.25} type="number" value={maxCost} onChange={(event) => setMaxCost(Number(event.target.value))} />
          </label>
        </div>
        <button type="submit">Save defaults</button>
      </form>
      <div className="provider-readiness-list">
        {realProviders.map((item) => (
          <div className="provider-readiness-row" key={item.provider}>
            <span className={`status-dot ${connectedProviders.some((connected) => connected.provider === item.provider) ? "ready" : "missing"}`} />
            <strong>{item.label}</strong>
            <span>{connectedProviders.some((connected) => connected.provider === item.provider) ? "connected" : "missing key"}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function SearchSettings({
  preference,
  keyValue,
  setKeyValue,
  onSaveKey,
  onDeleteKey,
  onSavePreference,
}: {
  preference: SearchPreferenceResponse | null;
  keyValue: string;
  setKeyValue: (value: string) => void;
  onSaveKey: (event: FormEvent) => void;
  onDeleteKey: () => void;
  onSavePreference: (payload: { search_mode: SearchMode; max_results: number }) => void;
}) {
  const [mode, setMode] = useState<SearchMode>(preference?.preference.search_mode ?? "auto");
  const [maxResults, setMaxResults] = useState(preference?.preference.max_results ?? 6);
  const key = preference?.key;

  useEffect(() => {
    setMode(preference?.preference.search_mode ?? "auto");
    setMaxResults(preference?.preference.max_results ?? 6);
  }, [preference]);

  return (
    <section className="settings-panel search-panel">
      <div className="section-heading">
        <h2>Web search</h2>
        <p>Search discovers source evidence. The selected model still writes the answer and ReliabilityGraph audits it.</p>
      </div>
      <form className="inline-form" onSubmit={onSaveKey}>
        <select value="tavily" disabled aria-label="Web search provider">
          <option value="tavily">Tavily</option>
        </select>
        <input
          aria-label="Web search API key"
          placeholder="Paste search API key"
          type="password"
          value={keyValue}
          onChange={(event) => setKeyValue(event.target.value)}
        />
        <button type="submit">Save</button>
      </form>
      <div className="key-list">
        <div className="key-row">
          <div>
            <strong>Search key</strong>
            <span>{key?.key_state === "saved" || key?.key_state === "env" ? key.fingerprint ?? key.key_state : "missing"}</span>
          </div>
          {(key?.key_state === "saved" || key?.key_state === "env") && (
            <button className="quiet-button" type="button" onClick={onDeleteKey} disabled={key.key_state === "env"}>
              {key.key_state === "env" ? "Env" : "Delete"}
            </button>
          )}
        </div>
      </div>
      <form
        className="preference-form search-preference-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSavePreference({ search_mode: mode, max_results: maxResults });
        }}
      >
        <div className="settings-number-row">
          <label>
            Default search
            <select value={mode} onChange={(event) => setMode(event.target.value as SearchMode)}>
              <option value="auto">Auto</option>
              <option value="always">On</option>
              <option value="off">Off</option>
            </select>
          </label>
          <label>
            Max results
            <input min={1} max={10} type="number" value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))} />
          </label>
        </div>
        <button type="submit">Save search defaults</button>
      </form>
    </section>
  );
}

function formatTraceType(value: string): string {
  return value.replaceAll("_", " ");
}

function compactEvents(events: StreamEvent[]): StreamEvent[] {
  const keyed = new Map<string, StreamEvent>();
  const unkeyed: StreamEvent[] = [];
  for (const event of events) {
    if (event.span?.span_id) {
      keyed.set(event.span.span_id, event);
    } else {
      unkeyed.push(event);
    }
  }
  return [...keyed.values(), ...unkeyed].slice(-16);
}

export function formatTraceOutput(span: TraceSpan): string {
  const parsed = parseOutput(span.output_summary);
  if (!parsed) return span.output_summary;
  if (span.type === "research_router") {
    const route = parsed.route?.route ? String(parsed.route.route).replaceAll("_", " ") : "no search";
    const reason = parsed.route?.reason ? ` ${parsed.route.reason}` : "";
    return `Retrieval plan: ${route}.${reason}`;
  }
  if (span.type === "question_classifier") {
    return `Question type: ${String(parsed.question_type ?? "unknown").replaceAll("_", " ")}.`;
  }
  if (span.type === "web_search") {
    if (parsed.result_count !== undefined) {
      return `Searched "${parsed.query ?? "query"}" and indexed ${parsed.indexed_sources ?? 0} source${parsed.indexed_sources === 1 ? "" : "s"}.`;
    }
    const call = Array.isArray(parsed.calls) ? parsed.calls[0] : null;
    if (call?.error) return call.error;
    return "Web search was skipped.";
  }
  if (span.type === "candidate_generation") {
    const count = parsed.candidate_count ?? 0;
    return parsed.provider_error ? `${count} candidates generated; provider recovered from an issue.` : `${count} candidates generated.`;
  }
  if (span.type === "semantic_clustering") {
    return `${parsed.cluster_count ?? 0} meaning cluster${parsed.cluster_count === 1 ? "" : "s"}; stability ${formatMetric(parsed.semantic_stability)}.`;
  }
  if (span.type === "claim_extraction") {
    return `${parsed.claim_count ?? 0} checked claim${parsed.claim_count === 1 ? "" : "s"} extracted${parsed.structured ? " with structured output" : ""}.`;
  }
  if (span.type === "assumption_extraction") {
    return `${parsed.assumption_count ?? 0} assumption${parsed.assumption_count === 1 ? "" : "s"} extracted.`;
  }
  if (span.type === "decision_analysis") {
    return `${parsed.alternative_count ?? 0} alternative${parsed.alternative_count === 1 ? "" : "s"} compared.`;
  }
  if (span.type === "evidence_retrieval") {
    return `${parsed.evidence_count ?? 0} source match${parsed.evidence_count === 1 ? "" : "es"} from ${parsed.source_chunk_count ?? 0} source chunk${parsed.source_chunk_count === 1 ? "" : "s"}.`;
  }
  if (span.type === "claim_check") {
    return `${parsed.assessed_claims ?? 0} claim${parsed.assessed_claims === 1 ? "" : "s"} checked against available evidence.`;
  }
  if (span.type === "stress_test") {
    return `Unsupported flip rate ${formatMetric(parsed.unsupported_flip_rate)}.`;
  }
  if (span.type === "rubric_judge") {
    return `Factuality judge score ${formatMetric(parsed.factuality_score)}.`;
  }
  if (span.type === "reliability_scoring") {
    const caps = Array.isArray(parsed.caps) && parsed.caps.length ? ` Caps: ${parsed.caps.join("; ")}` : "";
    return `Diagnostic score ${parsed.score ?? "n/a"}/100.${caps}`;
  }
  if (span.type === "calibration_lookup") {
    return `Calibration: ${String(parsed.calibration_status ?? "unknown").replaceAll("_", " ")}.`;
  }
  if (span.type === "perturbation_probe") {
    return `Robustness checks: ${String(parsed.mode ?? "unknown").replaceAll("_", " ")}.`;
  }
  const entries = Object.entries(parsed).slice(0, 3);
  return entries.map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`).join(" · ");
}

function searchModeLabel(mode: SearchMode): string {
  if (mode === "always") return "On";
  if (mode === "off") return "Off";
  return "Auto";
}

function parseOutput(value: string): Record<string, any> | null {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function formatMetric(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "n/a";
}
