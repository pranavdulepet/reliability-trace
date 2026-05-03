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
        <h2>Provider Vault</h2>
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
          <p className="empty">No provider keys saved yet. Built-in audits remain available.</p>
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
}

export function RunComposer({ providers, form, setForm, running, hasResult, onSubmit }: RunComposerProps) {
  const selectedProvider = providers.find((provider) => provider.provider === form.provider);
  const providerReady = selectedProvider?.key_state === "saved" || selectedProvider?.key_state === "env";
  const isPreview = form.provider === "preview" || form.provider === "local";
  return (
    <section className="panel composer hero-panel">
      <div className="section-heading">
        <h2>Ask</h2>
        <p>We’ll audit the answer and show what supports it, what weakens it, and what would change it.</p>
      </div>
      <form onSubmit={onSubmit}>
        <textarea
          value={form.question}
          onChange={(event) => setForm((current) => ({ ...current, question: event.target.value }))}
          placeholder="Should I build an LLM answer-reliability product?"
        />
        <div className="composer-meta">
          <span>{form.question.length} / 12000</span>
          <span>Shift + Enter for a new line</span>
        </div>
        <div className="provider-choice-header">
          <div>
            <h3>Providers</h3>
            <p>Start simple, or use a connected provider when you want live candidates.</p>
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
          {providers.map((provider) => {
            const ready = provider.key_state === "saved" || provider.key_state === "env" || provider.key_state === "not_required";
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
                    use_live_provider: provider.key_state === "saved" || provider.key_state === "env",
                  }));
                }}
              >
                <span className="provider-logo">{provider.label.slice(0, 1)}</span>
                <span>
                  <strong>{provider.label}</strong>
                  <small>{ready ? provider.key_state === "not_required" ? "Smart default" : "Connected" : "Add key"}</small>
                </span>
              </button>
            );
          })}
        </div>
        <label className="check-row">
          <input
            checked={form.use_live_provider}
            disabled={isPreview || !providerReady}
            type="checkbox"
            onChange={(event) => setForm((current) => ({ ...current, use_live_provider: event.target.checked }))}
          />
          Use connected provider for candidate generation
        </label>
        <div className="run-action-row">
          <button className="primary-action" disabled={running || form.question.trim().length < 3} type="submit">
            {running ? "Auditing" : "Run audit"}
          </button>
          <span>{hasResult ? "Your latest result is below." : "Typical audit takes under a minute."}</span>
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
          <h2>Audit Plan</h2>
          <p>The timeline appears when an audit starts.</p>
        </div>
        <div className="plan-list">
          {[
            ["Generate answers", "Collect independent candidate responses."],
            ["Find claims", "Break the answer into checkable pieces."],
            ["Check reliability", "Score support, uncertainty, and robustness."],
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
          <h2>Audit Timeline</h2>
          <p>{running ? "Streaming evidence graph events" : "Complete"}</p>
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
              <span>{event.span?.type ?? event.type}</span>
              <p>{event.message}</p>
            </li>
          ))
        )}
      </ol>
    </section>
  );
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
