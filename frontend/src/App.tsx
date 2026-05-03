import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createRun,
  deleteKey,
  fetchSourceUrl,
  getBenchmarkReport,
  getDocuments,
  getKeys,
  getProviders,
  getRun,
  getRuns,
  runEventSource,
  saveKey,
  searchDocuments,
  uploadDocument,
} from "./api";
import {
  KeyManager,
  RunComposer,
  RunHistory,
  TracePanel,
} from "./components";
import { Report, type ReportTab, TABS } from "./report";
import type {
  BenchmarkReport,
  DocumentMatch,
  DocumentView,
  ProviderKeyView,
  ProviderMetadata,
  ReliabilityGraph,
  RunCreate,
  RunView,
  StreamEvent,
} from "./types";
import "./styles.css";

type WorkspaceView = "workbench" | "runs" | "sources" | "benchmarks" | "settings";

const initialRunForm: RunCreate = {
  question: "Should I build an LLM answer-reliability product?",
  provider: "preview",
  model: null,
  samples: 3,
  max_cost_usd: 1,
  use_live_provider: false,
};

function App() {
  const [providers, setProviders] = useState<ProviderMetadata[]>([]);
  const [keys, setKeys] = useState<ProviderKeyView[]>([]);
  const [runs, setRuns] = useState<RunView[]>([]);
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [benchmarkReport, setBenchmarkReport] = useState<BenchmarkReport | null>(null);
  const [form, setForm] = useState<RunCreate>(initialRunForm);
  const [keyProvider, setKeyProvider] = useState("tinker");
  const [keyValue, setKeyValue] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [graph, setGraph] = useState<ReliabilityGraph | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [activeTab, setActiveTab] = useState<ReportTab>(TABS[0]);
  const [view, setView] = useState<WorkspaceView>("workbench");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void refresh().catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load workspace state");
    });
  }, []);

  const progress = useMemo(() => {
    if (graph) return 1;
    if (events.length === 0) return 0;
    return events[events.length - 1].progress ?? 0;
  }, [events, graph]);

  async function refresh() {
    const [nextProviders, nextKeys, nextRuns, nextDocuments, nextBenchmarkReport] = await Promise.all([
      getProviders(),
      getKeys(),
      getRuns(),
      getDocuments(),
      getBenchmarkReport(),
    ]);
    setProviders(nextProviders.map(normalizeProvider));
    setKeys(nextKeys);
    setRuns(nextRuns);
    setDocuments(nextDocuments);
    setBenchmarkReport(nextBenchmarkReport);
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
        use_live_provider: isPreviewProvider(form.provider) ? false : form.use_live_provider,
      });
      setActiveRunId(run.run_id);
      setView("workbench");
      await streamRun(run.run_id);
      await refresh();
    } catch (err) {
      setRunning(false);
      setError(err instanceof Error ? err.message : "Run failed");
    }
  }

  async function streamRun(runId: string): Promise<void> {
    return new Promise((resolve, reject) => {
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
          setActiveTab("Summary");
        }
        setRunning(false);
        source.close();
        resolve();
      });

      source.addEventListener("error", () => {
        setRunning(false);
        source.close();
        reject(new Error("Run stream failed"));
      });
    });
  }

  async function handleSelectRun(runId: string) {
    setError(null);
    try {
      const run = await getRun(runId);
      setActiveRunId(runId);
      setGraph(run.graph);
      setEvents([]);
      setView("workbench");
      setActiveTab("Summary");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    }
  }

  async function handleUploadDocument(payload: { title: string; text: string; source_url?: string | null }) {
    setError(null);
    try {
      await uploadDocument({ ...payload, source_type: payload.source_url ? "manual_source" : "uploaded_document" });
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload document");
    }
  }

  async function handleFetchSource(url: string) {
    setError(null);
    try {
      await fetchSourceUrl(url);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch source");
    }
  }

  async function handleSearchDocuments(query: string): Promise<DocumentMatch[]> {
    return searchDocuments(query);
  }

  return (
    <div className="workspace-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true">RG</div>
          <div>
            <h1>ReliabilityGraph</h1>
            <p>Reliability workspace</p>
          </div>
        </div>
        <nav className="main-nav" aria-label="Workspace">
          <NavButton active={view === "workbench"} label="Workbench" onClick={() => setView("workbench")} />
          <NavButton active={view === "runs"} label="Runs" onClick={() => setView("runs")} />
          <NavButton active={view === "sources"} label="Sources" onClick={() => setView("sources")} />
          <NavButton active={view === "benchmarks"} label="Benchmarks" onClick={() => setView("benchmarks")} />
          <NavButton active={view === "settings"} label="Settings" onClick={() => setView("settings")} />
        </nav>
        <button className="vault-card" type="button" onClick={() => setView("settings")}>
          <span>Provider vault</span>
          <strong>{providerSummary(providers)}</strong>
        </button>
      </aside>

      <div className="content-shell">
        <header className="workspace-header">
          <div>
            <h2>{headerTitle(view)}</h2>
            <p>{headerSubtitle(view)}</p>
          </div>
          <div className="header-actions">
            <button className="ghost-button hide-mobile" type="button" onClick={() => setView("settings")}>
              Provider Vault
            </button>
            <button className="primary-compact" type="button" onClick={() => setView("workbench")}>
              New Audit
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <main>
          {view === "workbench" && (
            <>
              <div className="upper-grid">
                <RunComposer
                  providers={providers}
                  form={form}
                  setForm={setForm}
                  running={running}
                  hasResult={Boolean(graph)}
                  onSubmit={handleStartRun}
                />
                <TracePanel events={events} progress={progress} running={running} graph={graph} />
              </div>
              <Report graph={graph} activeTab={activeTab} setActiveTab={setActiveTab} />
            </>
          )}

          {view === "runs" && <RunsPage runs={runs} activeRunId={activeRunId} onSelect={handleSelectRun} />}

          {view === "sources" && (
            <SourcesPage
              graph={graph}
              documents={documents}
              onFetchSource={handleFetchSource}
              onSearch={handleSearchDocuments}
              onUploadDocument={handleUploadDocument}
            />
          )}

          {view === "benchmarks" && <BenchmarksPage graph={graph} report={benchmarkReport} />}

          {view === "settings" && (
            <SettingsPage
              providers={providers}
              keys={keys}
              keyProvider={keyProvider}
              keyValue={keyValue}
              setKeyProvider={setKeyProvider}
              setKeyValue={setKeyValue}
              onSave={handleSaveKey}
              onDelete={handleDeleteKey}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function NavButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className={active ? "nav-button active" : "nav-button"} type="button" onClick={onClick}>
      <span className="nav-glyph">{label.slice(0, 1)}</span>
      {label}
    </button>
  );
}

function RunsPage({
  runs,
  activeRunId,
  onSelect,
}: {
  runs: RunView[];
  activeRunId: string | null;
  onSelect: (runId: string) => void;
}) {
  return (
    <section className="page-panel">
      <RunHistory runs={runs} activeRunId={activeRunId} onSelect={onSelect} expanded />
    </section>
  );
}

function SourcesPage({
  graph,
  documents,
  onFetchSource,
  onSearch,
  onUploadDocument,
}: {
  graph: ReliabilityGraph | null;
  documents: DocumentView[];
  onFetchSource: (url: string) => Promise<void>;
  onSearch: (query: string) => Promise<DocumentMatch[]>;
  onUploadDocument: (payload: { title: string; text: string; source_url?: string | null }) => Promise<void>;
}) {
  const evidence = graph?.evidence ?? [];
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [matches, setMatches] = useState<DocumentMatch[]>([]);
  const [busy, setBusy] = useState(false);

  async function submitDocument(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    await onUploadDocument({ title: title || "Untitled document", text, source_url: sourceUrl || null });
    setTitle("");
    setText("");
    setSourceUrl("");
    setBusy(false);
  }

  async function fetchUrl() {
    if (!sourceUrl.trim()) return;
    setBusy(true);
    await onFetchSource(sourceUrl.trim());
    setSourceUrl("");
    setBusy(false);
  }

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!searchQuery.trim()) return;
    setMatches(await onSearch(searchQuery.trim()));
  }

  function handleFile(file: File | null) {
    if (!file) return;
    setTitle(file.name);
    void file.text().then(setText);
  }

  return (
    <section className="page-panel source-workspace">
      <div className="page-copy wide">
        <h3>Sources</h3>
        <p>Add documents or source URLs before a run. The backend chunks them, builds local retrieval vectors, and matches claims to the most relevant chunks.</p>
      </div>
      <div className="source-grid">
        <form className="panel source-form" onSubmit={submitDocument}>
          <div className="section-heading">
            <h2>Add document</h2>
            <p>Paste text or choose a local text file.</p>
          </div>
          <input value={title} placeholder="Title" onChange={(event) => setTitle(event.target.value)} />
          <input value={sourceUrl} placeholder="Optional source URL" onChange={(event) => setSourceUrl(event.target.value)} />
          <input type="file" accept=".txt,.md,.csv,.json,.log" onChange={(event) => handleFile(event.target.files?.[0] ?? null)} />
          <textarea value={text} placeholder="Paste source text" onChange={(event) => setText(event.target.value)} />
          <div className="run-action-row">
            <button className="primary-action" disabled={busy || text.trim().length < 20} type="submit">
              Add source
            </button>
            <button className="ghost-button" disabled={busy || !sourceUrl.trim()} type="button" onClick={() => void fetchUrl()}>
              Fetch URL
            </button>
          </div>
        </form>
        <div className="panel">
          <div className="section-heading">
            <h2>Library</h2>
            <p>{documents.length} sources available for retrieval.</p>
          </div>
          <form className="inline-search" onSubmit={runSearch}>
            <input value={searchQuery} placeholder="Search source chunks" onChange={(event) => setSearchQuery(event.target.value)} />
            <button type="submit">Search</button>
          </form>
          <div className="source-list compact">
            {documents.length === 0 ? (
              <p className="empty">No sources added yet.</p>
            ) : (
              documents.map((document) => (
                <article className="source-row" key={document.document_id}>
                  <strong>{document.title}</strong>
                  <span>{document.source_type} · {document.chunk_count} chunks</span>
                </article>
              ))
            )}
          </div>
        </div>
      </div>
      {matches.length > 0 && (
        <div className="source-list">
          {matches.map((match) => (
            <article className="source-row" key={match.chunk_id}>
              <strong>{match.title}</strong>
              <span>{match.source_type} · relevance {Math.round(match.relevance_score * 100)}%</span>
              <p>{match.text}</p>
            </article>
          ))}
        </div>
      )}
      <div className="source-list">
        {evidence.length === 0 ? (
          <div className="empty-state">No source-backed evidence has been collected for the selected run yet.</div>
        ) : (
          evidence.map((item) => (
            <article className="source-row" key={item.evidence_id}>
              <strong>{item.source_title}</strong>
              <span>{item.source_type} · {item.source_quality}</span>
              <p>{item.snippet}</p>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function BenchmarksPage({ graph, report }: { graph: ReliabilityGraph | null; report: BenchmarkReport | null }) {
  return (
    <section className="page-panel benchmark-grid">
      <div className="metric-tile">
        <span>Calibration</span>
        <strong>{report ? report.status.replaceAll("_", " ") : "Awaiting labeled runs"}</strong>
      </div>
      <div className="metric-tile">
        <span>Labeled runs</span>
        <strong>{report?.label_count ?? 0}</strong>
      </div>
      <div className="metric-tile">
        <span>ECE</span>
        <strong>{report?.ece == null ? "Needs labels" : report.ece.toFixed(3)}</strong>
      </div>
      <div className="metric-tile">
        <span>Brier</span>
        <strong>{report?.brier == null ? "Needs labels" : report.brier.toFixed(3)}</strong>
      </div>
      <div className="page-copy wide">
        <h3>Benchmark Report</h3>
        <p>{report?.summary ?? "Label completed runs to populate calibration and ablation analysis."}</p>
      </div>
      <TableCard title="Calibration Buckets" columns={["Range", "Runs", "Avg score", "Avg label"]} rows={(report?.buckets ?? []).map((bucket) => [
        bucket.range,
        String(bucket.count),
        formatDecimal(bucket.avg_score),
        formatDecimal(bucket.avg_correctness),
      ])} />
      <TableCard title="Ablations" columns={["Signal", "Avg score delta", "Runs"]} rows={(report?.ablations ?? []).map((row) => [
        row.signal,
        formatDecimal(row.avg_score_delta),
        String(row.run_count),
      ])} />
    </section>
  );
}

function TableCard({ title, columns, rows }: { title: string; columns: string[]; rows: string[][] }) {
  return (
    <section className="panel table-card">
      <div className="section-heading">
        <h2>{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="empty">No rows yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function formatDecimal(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : "0.000";
}

function SettingsPage(props: {
  providers: ProviderMetadata[];
  keys: ProviderKeyView[];
  keyProvider: string;
  keyValue: string;
  setKeyProvider: Dispatch<SetStateAction<string>>;
  setKeyValue: Dispatch<SetStateAction<string>>;
  onSave: (event: FormEvent) => void;
  onDelete: (provider: string) => void;
}) {
  return (
    <div className="settings-grid">
      <KeyManager {...props} />
      <section className="panel">
        <div className="section-heading">
          <h2>Provider Readiness</h2>
          <p>Choose the provider mix for higher-quality audits.</p>
        </div>
        <div className="provider-readiness-list">
          {props.providers.map((provider) => (
            <div className="provider-readiness-row" key={provider.provider}>
              <span className={`status-dot status-${provider.key_state}`} />
              <strong>{provider.label}</strong>
              <span>{provider.key_state === "not_required" ? "ready" : provider.key_state}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function headerTitle(view: WorkspaceView): string {
  if (view === "runs") return "Runs";
  if (view === "sources") return "Sources";
  if (view === "benchmarks") return "Benchmarks";
  if (view === "settings") return "Provider vault";
  return "Workbench";
}

function headerSubtitle(view: WorkspaceView): string {
  if (view === "runs") return "Review previous audits and reopen their evidence graphs.";
  if (view === "sources") return "Inspect source coverage and claim-linked evidence.";
  if (view === "benchmarks") return "Track diagnostic score quality as labeled runs accumulate.";
  if (view === "settings") return "Connect Tinker, OpenAI, Claude, Gemini, and OpenRouter keys.";
  return "Ask a question. Get a clear reliability audit.";
}

function isPreviewProvider(provider: string): boolean {
  return provider === "preview" || provider === "local";
}

function providerSummary(providers: ProviderMetadata[]): string {
  const connected = providers.filter((provider) => provider.key_state === "saved" || provider.key_state === "env").length;
  return `${connected} connected`;
}

function normalizeProvider(provider: ProviderMetadata): ProviderMetadata {
  if (provider.provider === "preview" || provider.provider === "local") {
    return { ...provider, label: "Core Engine" };
  }
  return provider;
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
