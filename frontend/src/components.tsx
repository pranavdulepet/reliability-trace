import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { ProviderKeyView, ProviderMetadata, RunCreate, RunView, StreamEvent } from "./types";

interface KeyManagerProps {
  providers: ProviderMetadata[];
  keys: ProviderKeyView[];
  keyProvider: string;
  keyValue: string;
  setKeyProvider: Dispatch<SetStateAction<string>>;
  setKeyValue: Dispatch<SetStateAction<string>>;
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
    <section className="panel key-panel">
      <div className="section-heading">
        <h2>Providers</h2>
        <p>Keys are encrypted before storage and shown only as fingerprints.</p>
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
          <p className="empty">No provider keys saved yet. Connect Tinker or another provider before asking a question.</p>
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

interface RunComposerProps {
  providers: ProviderMetadata[];
  form: RunCreate;
  setForm: Dispatch<SetStateAction<RunCreate>>;
  running: boolean;
  hasResult: boolean;
  onSubmit: (event: FormEvent) => void;
  onOpenSettings: () => void;
}

export function RunComposer({ providers, form, setForm, running, hasResult, onSubmit, onOpenSettings }: RunComposerProps) {
  const realProviders = providers.filter(isRealProvider);
  const selectedProvider = providers.find((provider) => provider.provider === form.provider);
  const providerReady = Boolean(selectedProvider && isProviderConnected(selectedProvider));
  const hasConnectedProvider = realProviders.some(isProviderConnected);
  return (
    <section className="panel composer chat-composer">
      <div className="section-heading">
        <h2>Ask</h2>
        <p>Connect a provider, ask, then inspect the answer and every observable audit step.</p>
      </div>
      <form onSubmit={onSubmit}>
        <textarea
          value={form.question}
          onChange={(event) => setForm((current) => ({ ...current, question: event.target.value }))}
          placeholder="Ask anything you want verified..."
        />
        <div className="composer-meta">
          <span>{form.question.length} / 12000</span>
          <span>{providerReady ? `${selectedProvider?.label} connected` : "Provider required"}</span>
        </div>
        <div className="provider-choice-header">
          <div>
            <h3>Providers</h3>
            <p>{hasConnectedProvider ? "Choose the model endpoint for this answer." : "Connect a key before starting."}</p>
          </div>
          <details className="advanced-options">
            <summary>Options</summary>
            <div className="advanced-grid">
              <label>
                Model
                <input
                  value={form.model ?? ""}
                  placeholder={selectedProvider?.default_model ?? "Auto"}
                  onChange={(event) => setForm((current) => ({ ...current, model: event.target.value || null }))}
                />
              </label>
              <label>
                Samples
                <input
                  min={1}
                  max={5}
                  type="number"
                  value={form.samples}
                  onChange={(event) => setForm((current) => ({ ...current, samples: Number(event.target.value) }))}
                />
              </label>
              <label>
                Max cost
                <input
                  min={0}
                  max={100}
                  step={0.25}
                  type="number"
                  value={form.max_cost_usd}
                  onChange={(event) => setForm((current) => ({ ...current, max_cost_usd: Number(event.target.value) }))}
                />
              </label>
            </div>
          </details>
        </div>
        <div className="provider-card-grid" role="radiogroup" aria-label="Provider">
          {realProviders.map((provider) => {
            const ready = isProviderConnected(provider);
            const selected = form.provider === provider.provider;
            return (
              <button
                className={selected ? "provider-card selected" : "provider-card"}
                key={provider.provider}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => {
                  setForm((current) => ({
                    ...current,
                    provider: provider.provider,
                    model: provider.default_model ?? null,
                    use_live_provider: ready,
                  }));
                }}
              >
                <span className="provider-logo">{provider.label.slice(0, 1)}</span>
                <span>
                  <strong>{provider.label}</strong>
                  <small>{ready ? "Connected" : "Add key"}</small>
                </span>
              </button>
            );
          })}
        </div>
        {!providerReady && (
          <div className="provider-required">
            <strong>Provider required</strong>
            <p>ReliabilityGraph needs Tinker, OpenAI, Claude, Gemini, or OpenRouter to generate real answers.</p>
            <button className="ghost-button" type="button" onClick={onOpenSettings}>
              Connect provider
            </button>
          </div>
        )}
        <div className="run-action-row">
          <button className="primary-action" disabled={running || !providerReady || form.question.trim().length < 3} type="submit">
            {running ? "Auditing" : "Ask & audit"}
          </button>
          <span>{hasResult ? "Latest answer and reliability analysis are below." : "The trace appears as the answer generates."}</span>
        </div>
      </form>
    </section>
  );
}

interface TracePanelProps {
  events: StreamEvent[];
  progress: number;
  running: boolean;
  graph: unknown;
}

export function TracePanel({ events, progress, running, graph }: TracePanelProps) {
  if (!running && events.length === 0 && !graph) {
    return (
      <section className="panel trace-panel">
        <div className="section-heading">
          <h2>Observable Trace</h2>
          <p>The run will stream provider calls, retrieval, checks, and scoring here.</p>
        </div>
        <div className="plan-list">
          {[
            ["Provider call", "Generate answer candidates from the selected model."],
            ["Source retrieval", "Search uploaded and fetched sources for relevant chunks."],
            ["Claim extraction", "Break the answer into checkable statements."],
            ["Source matching", "Map claims to support, contradiction, or missing evidence."],
            ["Reliability score", "Combine support, uncertainty, disagreement, and probes."],
          ].map(([title, body]) => (
            <div className="plan-row" key={title}>
              <strong>{title}</strong>
              <span>{body}</span>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="panel trace-panel">
      <div className="section-heading horizontal">
        <div>
          <h2>Observable Trace</h2>
          <p>{running ? "Streaming run events" : "Complete"}</p>
        </div>
        <strong>{Math.round(progress * 100)}%</strong>
      </div>
      <div className="progress-bar" aria-label="Run progress">
        <span style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      <ol className="trace-list">
        {events.length === 0 ? (
          <li className="empty">Waiting for the first audit event.</li>
        ) : (
          events.map((event, index) => (
            <li key={`${event.message}-${index}`}>
              <div className="trace-line">
                <span>{formatTraceType(event.span?.type ?? event.type)}</span>
                {event.span?.cost_usd ? <small>${event.span.cost_usd.toFixed(4)}</small> : null}
              </div>
              <p>{event.message}</p>
              {event.span?.input_summary && <code>{event.span.input_summary}</code>}
              {event.span?.output_summary && <code>{event.span.output_summary}</code>}
              {event.span?.risk_flags?.length ? (
                <div className="trace-flags">
                  {event.span.risk_flags.map((flag) => <em key={flag}>{flag}</em>)}
                </div>
              ) : null}
            </li>
          ))
        )}
      </ol>
    </section>
  );
}

function isRealProvider(provider: ProviderMetadata): boolean {
  return provider.provider !== "preview" && provider.provider !== "local";
}

function isProviderConnected(provider: ProviderMetadata): boolean {
  return provider.key_state === "saved" || provider.key_state === "env";
}

function formatTraceType(value: string): string {
  const normalized = value.replaceAll("_", " ");
  return normalized.toLowerCase() === "causal probe" ? "Tinker probe" : normalized;
}

interface RunHistoryProps {
  runs: RunView[];
  activeRunId: string | null;
  onSelect: (runId: string) => void;
  expanded?: boolean;
}

export function RunHistory({ runs, activeRunId, onSelect }: RunHistoryProps) {
  return (
    <section className="panel run-history">
      <div className="section-heading">
        <h2>Runs</h2>
        <p>Completed answer audits and their evidence graphs.</p>
      </div>
      <div className="history-list">
        {runs.length === 0 ? (
          <p className="empty">No runs yet.</p>
        ) : (
          runs.map((run) => (
            <button
              className={run.run_id === activeRunId ? "history-row selected" : "history-row"}
              key={run.run_id}
              type="button"
              onClick={() => onSelect(run.run_id)}
            >
              <span>{run.status}</span>
              <strong>{run.question}</strong>
            </button>
          ))
        )}
      </div>
    </section>
  );
}
