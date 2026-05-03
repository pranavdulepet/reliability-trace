import { Dispatch, FormEvent, SetStateAction, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  createRun,
  deleteKey,
  fetchSourceUrl,
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

type WorkspaceView = "chat" | "runs" | "sources" | "about" | "settings";

const initialRunForm: RunCreate = {
  question: "",
  provider: "tinker",
  model: null,
  samples: 3,
  max_cost_usd: 1,
  use_live_provider: true,
};

function App() {
  const [providers, setProviders] = useState<ProviderMetadata[]>([]);
  const [keys, setKeys] = useState<ProviderKeyView[]>([]);
  const [runs, setRuns] = useState<RunView[]>([]);
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [form, setForm] = useState<RunCreate>(initialRunForm);
  const [keyProvider, setKeyProvider] = useState("tinker");
  const [keyValue, setKeyValue] = useState("");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [graph, setGraph] = useState<ReliabilityGraph | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [activeTab, setActiveTab] = useState<ReportTab>(TABS[0]);
  const [view, setView] = useState<WorkspaceView>("chat");
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
    const [nextProviders, nextKeys, nextRuns, nextDocuments] = await Promise.all([
      getProviders(),
      getKeys(),
      getRuns(),
      getDocuments(),
    ]);
    const normalizedProviders = nextProviders;
    setProviders(normalizedProviders);
    setKeys(nextKeys);
    setRuns(nextRuns);
    setDocuments(nextDocuments);
    setForm((current) => selectDefaultProvider(current, normalizedProviders));
    setKeyProvider((current) => {
      if (normalizedProviders.some((provider) => provider.provider === current && isRealProvider(provider))) {
        return current;
      }
      return normalizedProviders.find((provider) => provider.provider === "tinker")?.provider ?? current;
    });
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
    const question = form.question.trim();
    const selectedProvider = providers.find((provider) => provider.provider === form.provider);
    if (question.length < 3) {
      setError("Ask a question before starting an audit.");
      return;
    }
    if (!selectedProvider || !isRealProvider(selectedProvider) || !isProviderConnected(selectedProvider)) {
      setError("Connect Tinker or another LLM provider before asking a question.");
      setView("settings");
      return;
    }
    setGraph(null);
    setEvents([]);
    setRunning(true);
    try {
      const run = await createRun({
        ...form,
        model: form.model?.trim() ? form.model.trim() : null,
        provider: selectedProvider.provider,
        question,
        use_live_provider: true,
      });
      setActiveRunId(run.run_id);
      setView("chat");
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
      setView("chat");
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
            <p>Answer audits</p>
          </div>
        </div>
        <nav className="main-nav" aria-label="Workspace">
          <NavButton active={view === "chat"} label="Chat" onClick={() => setView("chat")} />
          <NavButton active={view === "runs"} label="Runs" onClick={() => setView("runs")} />
          <NavButton active={view === "sources"} label="Sources" onClick={() => setView("sources")} />
          <NavButton active={view === "about"} label="About" onClick={() => setView("about")} />
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
              Providers
            </button>
            <button className="primary-compact" type="button" onClick={() => setView("chat")}>
              New Question
            </button>
          </div>
        </header>

        {error && <div className="error-banner">{error}</div>}

        <main>
          {view === "chat" && (
            <div className="chat-grid">
              <div className="chat-column">
                <RunComposer
                  providers={providers}
                  form={form}
                  setForm={setForm}
                  running={running}
                  hasResult={Boolean(graph)}
                  onSubmit={handleStartRun}
                  onOpenSettings={() => setView("settings")}
                />
                {graph && <AnswerCard graph={graph} />}
                <Report graph={graph} activeTab={activeTab} setActiveTab={setActiveTab} />
              </div>
              <TracePanel events={events} progress={progress} running={running} graph={graph} />
            </div>
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

          {view === "about" && <AboutPage />}

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
        <p>Add documents or source URLs before a run. The backend chunks them, builds retrieval vectors, and matches claims to the most relevant chunks.</p>
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

function AnswerCard({ graph }: { graph: ReliabilityGraph }) {
  return (
    <section className="answer-card" aria-label="Generated answer">
      <div className="answer-card-header">
        <div>
          <span>Answer</span>
          <h2>{formatProviderName(graph.run.provider)} · {graph.run.model ?? "auto"}</h2>
        </div>
        <div className="answer-score">
          <strong>{graph.answer.reliability_score}</strong>
          <span>/100</span>
        </div>
      </div>
      <p>{graph.answer.final_answer}</p>
      <div className="answer-facts">
        <span>{graph.claims.length} claims</span>
        <span>{graph.evidence.length} source matches</span>
        <span>{graph.disagreement.semantic_clusters.length} answer clusters</span>
      </div>
    </section>
  );
}

function AboutPage() {
  const papers = [
    {
      title: "FActScore",
      href: "https://aclanthology.org/2023.emnlp-main.741/",
      body: "Atomic fact decomposition and source support checks for long-form answers.",
    },
    {
      title: "SelfCheckGPT",
      href: "https://arxiv.org/abs/2303.08896",
      body: "Sampling consistency as a black-box hallucination signal.",
    },
    {
      title: "Semantic Entropy",
      href: "https://www.nature.com/articles/s41586-024-07421-0",
      body: "Meaning-level disagreement across samples as an uncertainty signal.",
    },
    {
      title: "SAFE / LongFact",
      href: "https://arxiv.org/abs/2403.18802",
      body: "Search-augmented factuality evaluation for long-form model outputs.",
    },
    {
      title: "Calibration",
      href: "https://proceedings.mlr.press/v70/guo17a.html",
      body: "Reliability diagrams, ECE, and Brier-style thinking for score quality.",
    },
    {
      title: "Unfaithful CoT",
      href: "https://arxiv.org/abs/2305.04388",
      body: "Why the product treats hidden chain-of-thought as evidence only when the provider explicitly returns it.",
    },
    {
      title: "Tinker True-Thinking Score",
      href: "https://tinker-docs.thinkingmachines.ai/cookbook/recipes/true-thinking-score/",
      body: "Perturbation-style tests that ask whether a reasoning step changes the final answer.",
    },
  ];

  return (
    <section className="about-page">
      <div className="about-hero">
        <span>About ReliabilityGraph</span>
        <h2>Answer first. Evidence immediately after.</h2>
        <p>
          ReliabilityGraph runs the provider answer through source matching, claim checks, disagreement analysis,
          perturbation probes, and calibration signals. It shows observable steps from the run; it does not invent
          hidden reasoning traces.
        </p>
      </div>
      <div className="about-grid">
        {papers.map((paper) => (
          <a className="research-card" href={paper.href} key={paper.title} rel="noreferrer" target="_blank">
            <strong>{paper.title}</strong>
            <p>{paper.body}</p>
          </a>
        ))}
      </div>
      <section className="panel about-note">
        <h2>How Tinker fits</h2>
        <p>
          Tinker is one supported LLM provider. Its probe is an optional extra run for perturbation consistency:
          paraphrase pressure, false-premise pressure, and authority pressure. That is behavioral evidence, not
          special access to hidden reasoning.
        </p>
      </section>
    </section>
  );
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
          {props.providers.filter(isRealProvider).map((provider) => (
            <div className="provider-readiness-row" key={provider.provider}>
              <span className={`status-dot status-${provider.key_state}`} />
              <strong>{provider.label}</strong>
              <span>{isProviderConnected(provider) ? "connected" : "missing key"}</span>
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
  if (view === "about") return "About";
  if (view === "settings") return "Providers";
  return "Ask a question";
}

function headerSubtitle(view: WorkspaceView): string {
  if (view === "runs") return "Review previous audits and reopen their evidence graphs.";
  if (view === "sources") return "Inspect source coverage and claim-linked evidence.";
  if (view === "about") return "Research basis, design limits, and provider behavior.";
  if (view === "settings") return "Connect Tinker, OpenAI, Claude, Gemini, and OpenRouter keys.";
  return "Ask with a connected provider, then inspect the answer and every observable audit step.";
}

function formatProviderName(provider: string): string {
  if (provider === "openrouter") return "OpenRouter";
  return provider.slice(0, 1).toUpperCase() + provider.slice(1);
}

function isRealProvider(provider: ProviderMetadata): boolean {
  return provider.provider !== "preview" && provider.provider !== "local";
}

function isProviderConnected(provider: ProviderMetadata): boolean {
  return provider.key_state === "saved" || provider.key_state === "env";
}

function providerSummary(providers: ProviderMetadata[]): string {
  const connected = providers.filter((provider) => isRealProvider(provider) && isProviderConnected(provider)).length;
  return `${connected} connected`;
}

function selectDefaultProvider(current: RunCreate, providers: ProviderMetadata[]): RunCreate {
  const currentProvider = providers.find((provider) => provider.provider === current.provider);
  if (currentProvider && isRealProvider(currentProvider) && isProviderConnected(currentProvider)) {
    return {
      ...current,
      model: current.model ?? currentProvider.default_model,
      use_live_provider: true,
    };
  }

  const tinker = providers.find((provider) => provider.provider === "tinker" && isProviderConnected(provider));
  const connected = providers.find((provider) => isRealProvider(provider) && isProviderConnected(provider));
  const fallback =
    tinker ??
    connected ??
    providers.find((provider) => provider.provider === "tinker") ??
    providers.find(isRealProvider);

  if (!fallback) return current;
  return {
    ...current,
    provider: fallback.provider,
    model: fallback.default_model,
    use_live_provider: isProviderConnected(fallback),
  };
}

createRoot(document.getElementById("root") as HTMLElement).render(<App />);
