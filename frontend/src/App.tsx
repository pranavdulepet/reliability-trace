import { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createRun,
  deleteKey,
  getKeys,
  getProviders,
  getRun,
  getRuns,
  runEventSource,
  saveKey,
} from "./api";
import {
  KeyManager,
  ProviderRail,
  RunComposer,
  RunHistory,
  TracePanel,
} from "./components";
import { Report, type ReportTab, TABS } from "./report";
import type { ProviderKeyView, ProviderMetadata, ReliabilityGraph, RunCreate, RunView, StreamEvent } from "./types";
import "./styles.css";

const initialRunForm: RunCreate = {
  question: "Should I build an LLM answer-reliability product?",
  provider: "local",
  model: null,
  samples: 3,
  max_cost_usd: 1,
  use_live_provider: false,
};

function App() {
  const [providers, setProviders] = useState<ProviderMetadata[]>([]);
  const [keys, setKeys] = useState<ProviderKeyView[]>([]);
  const [runs, setRuns] = useState<RunView[]>([]);
  const [form, setForm] = useState<RunCreate>(initialRunForm);
  const [keyProvider, setKeyProvider] = useState("tinker");
  const [keyValue, setKeyValue] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [graph, setGraph] = useState<ReliabilityGraph | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [activeTab, setActiveTab] = useState<ReportTab>(TABS[0]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh();
  }, []);

  const progress = useMemo(() => {
    if (graph) return 1;
    if (events.length === 0) return 0;
    return events[events.length - 1].progress ?? 0;
  }, [events, graph]);

  async function refresh() {
    const [nextProviders, nextKeys, nextRuns] = await Promise.all([getProviders(), getKeys(), getRuns()]);
    setProviders(nextProviders);
    setKeys(nextKeys);
    setRuns(nextRuns);
  }

  async function handleSaveKey(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await saveKey(keyProvider, keyValue);
      setKeyValue("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save key");
    }
  }

  async function handleDeleteKey(provider: string) {
    setError(null);
    try {
      await deleteKey(provider);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete key");
    }
  }

  async function handleStartRun(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setGraph(null);
    setEvents([]);
    setRunning(true);
    try {
      const run = await createRun({
        ...form,
        model: form.model?.trim() ? form.model.trim() : null,
        question: form.question.trim(),
        use_live_provider: form.provider === "local" ? false : form.use_live_provider,
      });
      setActiveRunId(run.run_id);
      await streamRun(run.run_id);
      await refresh();
    } catch (err) {
      setRunning(false);
      setError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function streamRun(runId: string) {
    const source = runEventSource(runId);

    source.addEventListener("progress", (event) => {
      const parsed = JSON.parse(event.data) as StreamEvent;
      setEvents((current) => [...current, parsed]);
    });

    source.addEventListener("completed", (event) => {
      const parsed = JSON.parse(event.data) as StreamEvent;
      setEvents((current) => [...current, parsed]);
      if (parsed.graph) {
        setGraph(parsed.graph);
        setActiveTab("Answer");
      }
      setRunning(false);
      source.close();
    });

    source.addEventListener("error", () => {
      setRunning(false);
      source.close();
    });
  }

  async function handleSelectRun(runId: string) {
    setError(null);
    try {
      const run = await getRun(runId);
      setActiveRunId(runId);
      setGraph(run.graph);
      setEvents([]);
      setActiveTab("Answer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>ReliabilityGraph</h1>
          <p>Local-first answer reliability debugger</p>
        </div>
        <div className="topbar-note">BYOK · Observable evidence · No hidden-CoT claims</div>
      </header>

      <ProviderRail providers={providers} />

      {error && <div className="error-banner">{error}</div>}

      <main>
        <div className="upper-grid">
          <div className="left-stack">
            <RunComposer providers={providers} form={form} setForm={setForm} running={running} onSubmit={handleStartRun} />
            <KeyManager
              providers={providers}
              keys={keys}
              keyProvider={keyProvider}
              keyValue={keyValue}
              setKeyProvider={setKeyProvider}
              setKeyValue={setKeyValue}
              onSave={handleSaveKey}
              onDelete={handleDeleteKey}
            />
          </div>
          <div className="right-stack">
            <TracePanel events={events} progress={progress} running={running} />
            <RunHistory runs={runs} activeRunId={activeRunId} onSelect={handleSelectRun} />
          </div>
        </div>

        <Report graph={graph} activeTab={activeTab} setActiveTab={setActiveTab} />
      </main>
    </div>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
