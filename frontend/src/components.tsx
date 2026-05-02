import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { ProviderKeyView, ProviderMetadata, RunCreate, RunView, StreamEvent } from "./types";

interface ProviderRailProps {
  providers: ProviderMetadata[];
}

export function ProviderRail({ providers }: ProviderRailProps) {
  return (
    <section className="provider-rail" aria-label="Provider status">
      {providers.map((provider) => (
        <div className="provider-status" key={provider.provider}>
          <span className={`status-dot status-${provider.key_state}`} />
          <div>
            <strong>{provider.label}</strong>
            <span>{provider.key_state.replace("_", " ")}</span>
          </div>
        </div>
      ))}
    </section>
  );
}

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
  const keyProviders = providers.filter((provider) => provider.provider !== "local");
  return (
    <section className="panel key-panel">
      <div className="section-heading">
        <h2>Keys</h2>
        <p>Stored encrypted on the backend. Plaintext is never returned.</p>
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
          <p className="empty">No saved keys. You can still run the local diagnostic pipeline.</p>
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
  onSubmit: (event: FormEvent) => void;
}

export function RunComposer({ providers, form, setForm, running, onSubmit }: RunComposerProps) {
  const selectedProvider = providers.find((provider) => provider.provider === form.provider);
  return (
    <section className="panel composer">
      <div className="section-heading">
        <h2>Question</h2>
        <p>Ask one serious question. The graph audits the answer, not hidden model thoughts.</p>
      </div>
      <form onSubmit={onSubmit}>
        <textarea
          value={form.question}
          onChange={(event) => setForm((current) => ({ ...current, question: event.target.value }))}
          placeholder="Should I build an LLM answer-reliability product?"
        />
        <div className="control-grid">
          <label>
            Provider
            <select
              value={form.provider}
              onChange={(event) => {
                const provider = providers.find((item) => item.provider === event.target.value);
                setForm((current) => ({
                  ...current,
                  provider: event.target.value,
                  model: provider?.default_model ?? null,
                }));
              }}
            >
              {providers.map((provider) => (
                <option key={provider.provider} value={provider.provider}>
                  {provider.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Model
            <input
              value={form.model ?? ""}
              placeholder={selectedProvider?.default_model ?? "local-diagnostic"}
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
        <label className="check-row">
          <input
            checked={form.use_live_provider}
            disabled={form.provider === "local"}
            type="checkbox"
            onChange={(event) => setForm((current) => ({ ...current, use_live_provider: event.target.checked }))}
          />
          Use saved provider key for live candidate generation
        </label>
        <button className="primary-action" disabled={running || form.question.trim().length < 3} type="submit">
          {running ? "Running" : "Run Reliability Trace"}
        </button>
      </form>
    </section>
  );
}

interface TracePanelProps {
  events: StreamEvent[];
  progress: number;
  running: boolean;
}

export function TracePanel({ events, progress, running }: TracePanelProps) {
  return (
    <section className="panel trace-panel">
      <div className="section-heading horizontal">
        <div>
          <h2>Live Trace</h2>
          <p>{running ? "Streaming pipeline events" : "Idle"}</p>
        </div>
        <strong>{Math.round(progress * 100)}%</strong>
      </div>
      <div className="progress-bar" aria-label="Run progress">
        <span style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
      <ol className="trace-list">
        {events.length === 0 ? (
          <li className="empty">Progress events will appear here.</li>
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
}

export function RunHistory({ runs, activeRunId, onSelect }: RunHistoryProps) {
  return (
    <section className="panel run-history">
      <div className="section-heading">
        <h2>Runs</h2>
        <p>Local history scoped to the current workspace user.</p>
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
