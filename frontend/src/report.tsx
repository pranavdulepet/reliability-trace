import { exportUrl } from "./api";
import { MarkdownText } from "./markdown";
import { useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, SyntheticEvent } from "react";
import type { ClaimAssessment, EvidenceItem, ReliabilityGraph, TraceSpan } from "./types";

export const TABS = [
  "Summary",
  "Issues",
  "Claims",
  "Sources",
  "Assumptions",
  "Decision",
  "Disagreement",
  "Checks",
  "Calibration",
  "Robustness",
  "Activity",
  "Export",
] as const;

export type ReportTab = (typeof TABS)[number];

interface ReportProps {
  graph: ReliabilityGraph | null;
  activeTab: ReportTab;
  setActiveTab: (tab: ReportTab) => void;
}

export function Report({ graph, activeTab, setActiveTab }: ReportProps) {
  if (!graph) {
    return (
      <section className="report-shell empty-report">
        <h2>Reliability analysis</h2>
        <p>The full claim, source, disagreement, calibration, and probe report appears after the audit finishes.</p>
      </section>
    );
  }

  return (
    <section className="report-shell">
      <div className="report-header">
        <div>
          <h2>Reliability analysis</h2>
          <p>
            {graph.run.question_type} · {formatProvider(graph.run.provider)}
          </p>
        </div>
        <div className="score-block">
          <span>Reliability score</span>
          <strong>{graph.answer.reliability_score} / 100</strong>
          <small>{calibrationCopy(graph)}</small>
        </div>
      </div>
      <nav className="tab-row" aria-label="Report tabs">
        {TABS.map((tab) => (
          <button className={tab === activeTab ? "selected" : ""} key={tab} type="button" onClick={() => setActiveTab(tab)}>
            {tab}
          </button>
        ))}
      </nav>
      <div className="tab-panel">{renderTab(activeTab, graph)}</div>
    </section>
  );
}

function renderTab(tab: ReportTab, graph: ReliabilityGraph) {
  if (tab === "Summary") return <AnswerTab graph={graph} />;
  if (tab === "Issues") return <IssuesTab graph={graph} />;
  if (tab === "Claims") return <ClaimsTab graph={graph} />;
  if (tab === "Sources") return <EvidenceTab graph={graph} />;
  if (tab === "Assumptions") return <AssumptionsTab graph={graph} />;
  if (tab === "Decision") return <DecisionTab graph={graph} />;
  if (tab === "Disagreement") return <DisagreementTab graph={graph} />;
  if (tab === "Checks") return <StressTab graph={graph} />;
  if (tab === "Calibration") return <CalibrationTab graph={graph} />;
  if (tab === "Robustness") return <PerturbationTab graph={graph} />;
  if (tab === "Activity") return <ActivityTab graph={graph} />;
  return <ExportTab graph={graph} />;
}

function AnswerTab({ graph }: { graph: ReliabilityGraph }) {
  const meta = answerMeta(graph);
  return (
    <div className="summary-layout">
      <section className="score-summary">
        <div className="score-ring">
          <strong>{graph.answer.reliability_score}</strong>
          <span>/100</span>
        </div>
        <div>
          <h3>{meta.verdictLabel}</h3>
          <p>{meta.reason}</p>
        </div>
      </section>
      <section className="answer-main">
        <h3>Answer</h3>
        <MarkdownText text={graph.answer.final_answer} />
        {graph.answer.recommendation && (
          <>
            <h3>Recommendation</h3>
            <p>{graph.answer.recommendation}</p>
          </>
        )}
        <h3>Main Uncertainty</h3>
        <p>{meta.uncertainty}</p>
        <h3>What Would Change The Answer</h3>
        <p>{meta.change}</p>
      </section>
      <aside className="signal-panel">
        <h3>Useful Signals</h3>
        <ul>{graph.answer.top_positive_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
        <h3>Risk Signals</h3>
        <ul>{graph.answer.top_negative_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
        <h3>Recommended Action</h3>
        <p>{meta.nextAction}</p>
      </aside>
    </div>
  );
}

function ClaimsTab({ graph }: { graph: ReliabilityGraph }) {
  const assessments = new Map(graph.claim_assessments.map((assessment) => [assessment.claim_id, assessment]));
  return (
    <Table
      columns={["Claim", "Type", "Importance", "Relation", "Method", "Verifier", "Why", "Source limit"]}
      rows={graph.claims.map((claim) => {
        const assessment = assessments.get(claim.claim_id);
        return [
          claim.text,
          claim.type,
          claim.importance,
          assessment?.relation ?? assessment?.status ?? "unassessed",
          assessment?.assessment_method === "provider_entailment_verifier" ? "Provider + entailment verifier" : formatStatus(assessment?.assessment_method ?? "unassessed"),
          verifierSummary(assessment),
          assessment?.why ?? assessment?.explanation ?? "",
          assessment?.source_limit ?? `${assessment?.evidence_ids.length ?? 0} matched evidence item(s)`,
        ];
      })}
    />
  );
}

function IssuesTab({ graph }: { graph: ReliabilityGraph }) {
  const meta = answerMeta(graph);
  if (!meta.complete) {
    return <p className="empty-state">Reliability analysis incomplete: {meta.incompleteReason}</p>;
  }
  return (
    <div className="split-columns">
      <section>
        <h3>What to check first</h3>
        <p>{meta.reason}</p>
        <p>{meta.uncertainty}</p>
        <p>{meta.nextAction}</p>
        {graph.score_caps.length > 0 && (
          <>
            <h3>Score caps</h3>
            <ul>{graph.score_caps.map((cap) => <li key={cap}>{cap}</li>)}</ul>
          </>
        )}
      </section>
      <section>
        <h3>Signals</h3>
        <ul>{graph.answer.top_negative_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
        {graph.answer.top_positive_signals.length > 0 && (
          <>
            <h3>Supporting signals</h3>
            <ul>{graph.answer.top_positive_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
          </>
        )}
      </section>
    </div>
  );
}

function verifierSummary(assessment: ClaimAssessment | undefined): string {
  if (!assessment?.verifier) return "";
  const entailment = assessment.entailment_score === undefined ? "n/a" : assessment.entailment_score.toFixed(2);
  const contradiction = assessment.contradiction_score === undefined ? "n/a" : assessment.contradiction_score.toFixed(2);
  return `${assessment.verifier} · entail ${entailment} · contradict ${contradiction}`;
}

function EvidenceTab({ graph }: { graph: ReliabilityGraph }) {
  const evidence = externalEvidence(graph);
  if (evidence.length === 0) {
    return <p className="empty-state">No attached, fetched, or web source supports these claims yet.</p>;
  }
  return (
    <Table
      columns={["Source", "Type", "Date", "Quality", "Relation", "Matches", "Snippet"]}
      rows={sourceEvidenceRows(evidence)}
    />
  );
}

function AssumptionsTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <Table
      columns={["Assumption", "Importance", "Evidence", "Would change answer", "Sensitivity"]}
      rows={graph.assumptions.map((assumption) => [
        assumption.text,
        assumption.importance,
        assumption.evidence_status,
        assumption.would_change_recommendation_if_false ? "yes" : "no",
        assumption.sensitivity_notes,
      ])}
    />
  );
}

function DecisionTab({ graph }: { graph: ReliabilityGraph }) {
  if (!graph.decision_analysis.applicable) {
    return <p>{graph.decision_analysis.sensitivity_summary}</p>;
  }
  return (
    <div className="split-columns">
      <div>
        <h3>{graph.decision_analysis.label}</h3>
        <p>{graph.decision_analysis.sensitivity_summary}</p>
        <Table
          columns={["Alternative", "Evidence", "Basis", "Risk"]}
          rows={graph.decision_analysis.alternatives.map((alternative) => [
            alternative.name,
            alternative.evidence_status ?? (Number.isFinite(alternative.utility) ? `legacy utility ${formatNumber(alternative.utility ?? 0)}` : ""),
            alternative.basis ?? "",
            alternative.risk ?? "",
          ])}
        />
      </div>
      <div>
        <h3>Criteria</h3>
        <Table
          columns={["Criterion", "Why it matters"]}
          rows={graph.decision_analysis.criteria.map((criterion) => [
            criterion.name,
            criterion.basis ?? (Number.isFinite(criterion.weight) ? `legacy weight ${formatPercent(criterion.weight ?? 0)}` : ""),
          ])}
        />
      </div>
    </div>
  );
}

function DisagreementTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="split-columns">
      <div>
        <h3>Semantic Clusters</h3>
        <Table
          columns={["Cluster", "Label", "Samples", "Summary"]}
          rows={graph.disagreement.semantic_clusters.map((cluster) => [
            cluster.cluster_id,
            cluster.label,
            String(cluster.candidate_ids.length),
            cluster.summary,
          ])}
        />
      </div>
      <div>
        <h3>Signals</h3>
        <p>Semantic stability: {formatPercent(graph.disagreement.semantic_stability)}</p>
        <p>Semantic entropy: {formatNumber(graph.disagreement.semantic_entropy)}</p>
        <p>{graph.disagreement.accepted_rejected_dissent}</p>
      </div>
    </div>
  );
}

function StressTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <Table
      columns={["Check", "Changed", "New evidence", "Unsupported flip", "Impact", "Result"]}
      rows={graph.stress_tests.map((test) => [
        test.test_type,
        test.answer_changed ? "yes" : "no",
        test.new_evidence_introduced ? "yes" : "no",
        test.unsupported_flip ? "yes" : "no",
        test.impact_on_score,
        test.result,
      ])}
    />
  );
}

function CalibrationTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div>
      <h3>{graph.calibration.display}</h3>
      <p>{graph.calibration.note}</p>
      <p className="panel-note">
        The score is a weighted reliability summary from the signals below. It is not a model confidence percentage or a calibrated probability of truth.
      </p>
      <Table
        columns={["Signal", "Value", "Meaning"]}
        rows={scoreFeatureRows(graph)}
      />
      {graph.score_caps.length > 0 && (
        <>
          <h3>Score Caps</h3>
          <ul>{graph.score_caps.map((cap) => <li key={cap}>{cap}</li>)}</ul>
        </>
      )}
      {graph.analysis_basis && graph.analysis_basis.length > 0 && (
        <>
          <h3>Analysis Basis</h3>
          <Table
            columns={["Signal", "Method", "Research", "Limit"]}
            rows={graph.analysis_basis.map((item) => [item.signal, item.method, item.research_lineage, item.limitation])}
          />
        </>
      )}
    </div>
  );
}

function PerturbationTab({ graph }: { graph: ReliabilityGraph }) {
  const probe = graph.perturbation_probe ?? graph.causal_probe;
  return (
    <div>
      <h3>{formatStatus(probe.mode)}</h3>
      <p>{probe.reason}</p>
      {probe.results.length > 0 ? (
        <Table
          columns={["Operation", "Changed", "Similarity", "Unsupported flip", "Result"]}
          rows={probe.results.map((result) => [
            result.operation,
            result.answer_changed ? "yes" : "no",
            formatNumber(result.similarity_to_baseline),
            result.unsupported_flip ? "yes" : "no",
            result.result,
          ])}
        />
      ) : (
        <Table columns={["Available operation"]} rows={probe.operations.map((operation) => [operation])} />
      )}
    </div>
  );
}

function ActivityTab({ graph }: { graph: ReliabilityGraph }) {
  if (graph.trace.length === 0) return <p className="empty-state">No observable activity was recorded.</p>;
  return (
    <ol className="activity-list">
      {graph.trace.map((span) => (
        <li key={span.span_id}>
          <strong>{formatStatus(span.type)}</strong>
          <p>{span.input_summary}</p>
          {span.output_summary && <small>{traceOutput(span)}</small>}
        </li>
      ))}
    </ol>
  );
}

function traceOutput(span: TraceSpan): string {
  try {
    const parsed = JSON.parse(span.output_summary);
    if (span.type === "research_router") {
      const route = parsed.route?.route ? String(parsed.route.route).replaceAll("_", " ") : "no search";
      return `Retrieval plan: ${route}. ${parsed.route?.reason ?? ""}`.trim();
    }
    if (span.type === "web_search") {
      if (parsed.result_count !== undefined) return `Searched "${parsed.query ?? "query"}" and indexed ${parsed.indexed_sources ?? 0} source(s).`;
      const call = Array.isArray(parsed.calls) ? parsed.calls[0] : null;
      return call?.error || "Web search was skipped.";
    }
    if (span.type === "reliability_scoring") {
      const caps = Array.isArray(parsed.caps) && parsed.caps.length ? ` Caps: ${parsed.caps.join("; ")}` : "";
      return `Reliability score ${parsed.score ?? "n/a"}/100.${caps}`;
    }
    return Object.entries(parsed)
      .slice(0, 3)
      .map(([key, value]) => `${key.replaceAll("_", " ")}: ${String(value)}`)
      .join(" · ");
  } catch {
    return span.output_summary;
  }
}

export function ReliabilityCards({ graph }: { graph: ReliabilityGraph }) {
  const meta = answerMeta(graph);
  if (!meta.complete) {
    return (
      <div className="reliability-cards reliability-strip">
        <article className="verdict-card verdict-do_not_rely">
          <CardLabel label="Reliability analysis" topic="Final decision" />
          <strong>Incomplete</strong>
          <p>{meta.incompleteReason}</p>
        </article>
      </div>
    );
  }
  return (
    <div className="reliability-cards reliability-strip">
      <article className={`verdict-card verdict-${meta.verdict}`}>
        <CardLabel label="Final decision" topic="Final decision" />
        <strong>{meta.verdictLabel}</strong>
        <p className="score-line">
          Reliability score: {meta.score}/100 <InfoIcon topic="Reliability score" />
        </p>
        <p className="score-basis">{scoreBasis(graph)}</p>
        <p className="calibration-note">{calibrationCopy(graph)}</p>
      </article>
      <article>
        <CardLabel label="Evidence" topic="Evidence" />
        <strong>{meta.evidenceStatus}</strong>
        <p>{sourceSummary(graph)}</p>
      </article>
      <article>
        <CardLabel label="Main uncertainty" topic="Main uncertainty" />
        <strong>{meta.uncertainty}</strong>
      </article>
      <article>
        <CardLabel label="Next action" topic="Next action" />
        <strong>{meta.nextAction}</strong>
      </article>
    </div>
  );
}

export function AnswerCitations({ graph }: { graph: ReliabilityGraph }) {
  const citations = graph.answer.citations ?? [];
  if (citations.length === 0) return null;
  return (
    <div className="citation-row" aria-label="Sources cited in this answer">
      {citations.slice(0, 6).map((citation) => {
        const label = citation.title || citation.url || citation.citation_id;
        return citation.url ? (
          <a href={citation.url} key={citation.citation_id} rel="noreferrer" target="_blank" title={citation.snippet}>
            [{citation.citation_id}] {label}
          </a>
        ) : (
          <span key={citation.citation_id} title={citation.snippet}>
            [{citation.citation_id}] {label}
          </span>
        );
      })}
    </div>
  );
}

export function ReliabilityDetails({ graph }: { graph: ReliabilityGraph }) {
  const sections: Array<{ title: ReportTab; defaultOpen?: boolean }> = [
    { title: "Issues", defaultOpen: answerMeta(graph).verdict === "do_not_rely" },
    { title: "Claims" },
    { title: "Sources" },
    { title: "Disagreement" },
    { title: "Calibration" },
    { title: "Robustness" },
    { title: "Activity" },
    { title: "Export" },
  ];
  return (
    <div className="answer-details">
      {sections.map((section) => (
        <details key={section.title} onToggle={handleDetailToggle} open={section.defaultOpen}>
          <summary>
            <span>{section.title}</span>
            <InfoIcon topic={section.title} />
          </summary>
          <div className="detail-panel">{renderTab(section.title, graph)}</div>
        </details>
      ))}
    </div>
  );
}

function handleDetailToggle(event: SyntheticEvent<HTMLDetailsElement>) {
  const details = event.currentTarget;
  if (!details.open) return;
  window.requestAnimationFrame(() => {
    details.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}

function CardLabel({ label, topic }: { label: string; topic: InfoTopic }) {
  return (
    <span className="card-label">
      {label}
      <InfoIcon topic={topic} />
    </span>
  );
}

type InfoTopic =
  | "Final decision"
  | "Reliability score"
  | "Evidence"
  | "Main uncertainty"
  | "Next action"
  | "Sources"
  | "Claims"
  | "Disagreement"
  | "Calibration"
  | "Robustness"
  | "Activity"
  | "Issues"
  | "Export";

function InfoIcon({ topic }: { topic: InfoTopic | ReportTab }) {
  const info = INFO_COPY[topic as InfoTopic] ?? INFO_COPY["Reliability score"];
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number; width: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  function positionPanel() {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (!rect) return;
    const width = Math.min(360, window.innerWidth - 24);
    const left = Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2));
    const estimatedHeight = Math.min(360, window.innerHeight - 24);
    const below = rect.bottom + 8;
    const top = below + estimatedHeight > window.innerHeight ? Math.max(12, rect.top - estimatedHeight - 8) : below;
    setPosition({ left, top, width });
  }

  useLayoutEffect(() => {
    if (!open) return;
    positionPanel();
    window.addEventListener("resize", positionPanel);
    window.addEventListener("scroll", positionPanel, true);
    return () => {
      window.removeEventListener("resize", positionPanel);
      window.removeEventListener("scroll", positionPanel, true);
    };
  }, [open]);

  const panelStyle = position ? ({ left: position.left, top: position.top, width: position.width } satisfies CSSProperties) : undefined;

  return (
    <span className={open ? "info-wrap open" : "info-wrap"}>
      <button
        aria-expanded={open}
        aria-label={`About ${topic}`}
        className="info-icon"
        ref={buttonRef}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => {
            if (!current) positionPanel();
            return !current;
          });
        }}
        onFocus={() => {
          positionPanel();
          setOpen(true);
        }}
        onMouseEnter={() => {
          positionPanel();
          setOpen(true);
        }}
        type="button"
      >
        i
      </button>
      <span className="info-panel" role="tooltip" style={panelStyle}>
        <strong>{topic}</strong>
        <span>What this means: {info.meaning}</span>
        <span>How it is computed: {info.computed}</span>
        <span>Research basis: {info.research}</span>
        <span>Limitations: {info.limit}</span>
      </span>
    </span>
  );
}

const INFO_COPY: Record<InfoTopic, { meaning: string; computed: string; research: string; limit: string }> = {
  "Final decision": {
    meaning: "The product's rely/use-with-caution/do-not-rely call for this specific answer.",
    computed: "Derived from the reliability score plus hard caps for contradiction, missing evidence, and robustness failures.",
    research: "FActScore, SAFE / LongFact, SelfCheckGPT, Semantic Entropy, and calibration work.",
    limit: "It is a decision aid, not proof that the answer is true.",
  },
  "Reliability score": {
    meaning: "A 0-100 diagnostic for ranking risk across answers.",
    computed: "Benchmark-tuned weights combine claim support, source match, source quality, sample agreement, and explicit caps.",
    research: "Calibration, FActScore, SAFE / LongFact, SelfCheckGPT, and Semantic Entropy.",
    limit: "It is not a probability, confidence score, or guarantee.",
  },
  Evidence: {
    meaning: "Whether attached, fetched, or web sources support the checked claims.",
    computed: "The selected model judges each claim against retrieved snippets, then an entailment verifier checks whether the snippet supports, partially supports, contradicts, or does not contain the claim.",
    research: "Atomic factuality and source-grounded evaluation.",
    limit: "Retrieval can miss better sources, and weak sources can still be wrong.",
  },
  "Main uncertainty": {
    meaning: "The highest-impact reason not to over-trust the answer.",
    computed: "Selected from contradictions, unsupported high-impact claims, missing source evidence, and disagreement signals.",
    research: "Risk-focused factuality and calibration analysis.",
    limit: "It summarizes the main risk; details may contain additional risks.",
  },
  "Next action": {
    meaning: "The safest practical next step for the user.",
    computed: "Derived from the verdict, source state, contradiction state, and high-stakes detection.",
    research: "Product safety policy informed by reliability literature.",
    limit: "This is guidance, not a research metric.",
  },
  Sources: {
    meaning: "The evidence snippets used for claim checking.",
    computed: "Built from uploaded files, attached URLs, and web results after retrieval and duplicate removal.",
    research: "Search-augmented factuality checking and grounded generation.",
    limit: "Sources are evidence, not instructions, and may be incomplete or stale.",
  },
  Claims: {
    meaning: "Atomic answer claims checked against evidence.",
    computed: "The selected model extracts specific answer claims; each claim is then compared with retrieved source snippets.",
    research: "FActScore and SAFE / LongFact.",
    limit: "Claim extraction can miss or split claims imperfectly.",
  },
  Disagreement: {
    meaning: "Whether sampled answers converge on the same meaning.",
    computed: "Multiple candidate answers are clustered and compared for semantic stability and conflicts.",
    research: "SelfCheckGPT and Semantic Entropy.",
    limit: "Model self-agreement is useful but not proof of truth.",
  },
  Calibration: {
    meaning: "How the score weights and caps should be interpreted.",
    computed: "Weights are fitted on benchmark examples; caps lower the score when source support, contradiction, or robustness checks show risk.",
    research: "Reliability diagrams, ECE, Brier score, and risk coverage.",
    limit: "Calibration only transfers as far as the eval distribution matches the current use case.",
  },
  Robustness: {
    meaning: "Whether pressure or perturbation prompts flip the answer without new evidence.",
    computed: "The provider is asked controlled variants and the outputs are compared.",
    research: "Behavioral perturbation and sycophancy checks.",
    limit: "These probes are not exhaustive adversarial testing.",
  },
  Activity: {
    meaning: "Observable steps the system ran.",
    computed: "The app records visible milestones: deciding what evidence is needed, searching, reading sources, asking the model, checking claims, and computing the final decision.",
    research: "Unfaithful chain-of-thought work motivates showing observable events instead of hidden reasoning.",
    limit: "Activity is transparency, not evidence that the answer is true.",
  },
  Issues: {
    meaning: "The main risks and score caps for this answer.",
    computed: "Collected from negative signals, contradictions, unsupported claims, and score caps.",
    research: "Risk coverage and factuality evaluation.",
    limit: "It prioritizes visible risks and may not list every possible issue.",
  },
  Export: {
    meaning: "A downloadable evidence record for this answer.",
    computed: "Packages the answer, sources, claim checks, scores, activity, and final decision into a JSON record. API keys and secrets are not included.",
    research: "Auditability practice.",
    limit: "The summary UI is easier to read; the export is mainly for review, sharing, or deeper inspection.",
  },
};

function ExportTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="export-panel">
      <p>Download the complete evidence record for this answer.</p>
      <p>Sensitive keys included: {graph.export.contains_plaintext_provider_keys ? "yes" : "no"}</p>
      <a className="primary-link" href={exportUrl(graph.run.run_id)}>
        Download evidence record
      </a>
      <pre>{JSON.stringify(graph, null, 2)}</pre>
    </div>
  );
}

function Table({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return (
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
      <div className="table-cards">
        {rows.map((row, rowIndex) => (
          <article key={rowIndex}>
            <strong>{row[0]}</strong>
            <dl>
              {row.slice(1).map((cell, cellIndex) => (
                <div key={`${rowIndex}-${cellIndex}`}>
                  <dt>{columns[cellIndex + 1]}</dt>
                  <dd>{cell}</dd>
                </div>
              ))}
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}

function formatPercent(value: number | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "n/a";
  return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function formatProvider(provider: string): string {
  if (provider === "local" || provider === "preview") return "Preview";
  if (provider === "openrouter") return "OpenRouter";
  return provider.slice(0, 1).toUpperCase() + provider.slice(1);
}

function formatStatus(value: string): string {
  return value.replaceAll("_", " ");
}

function calibrationCopy(graph: ReliabilityGraph): string {
  if (graph.answer.calibration_status === "local_calibration") {
    const labels = graph.calibration.benchmark?.label_count ?? 0;
    return labels > 0 ? `Locally calibrated with ${labels} labeled run${labels === 1 ? "" : "s"}` : "Locally calibrated";
  }
  if (graph.answer.calibration_status === "benchmark_tuned_diagnostic") {
    return "Benchmark-tuned diagnostic; use the decision and evidence, not the number alone";
  }
  return "Research-prior diagnostic; use the decision and evidence, not the number alone";
}

function scoreBasis(graph: ReliabilityGraph): string {
  const contradicted = graph.claim_assessments.filter((item) => item.relation === "contradicted" || item.status === "contradicted").length;
  if (contradicted > 0) return `Lowered by ${contradicted} contradicted checked claim${contradicted === 1 ? "" : "s"}.`;
  if (graph.score_caps.length > 0) return `Capped: ${graph.score_caps[0]}.`;
  const features = graph.features;
  if (features.evidence_required >= 0.5) {
    return `Driven by claim support ${formatPercent(features.claim_support_rate)}, source match ${formatPercent(features.retrieval_alignment_score)}, and sample agreement ${formatPercent(features.semantic_stability)}.`;
  }
  return `Driven mostly by sample agreement ${formatPercent(features.semantic_stability)} and overlap ${formatPercent(features.sample_overlap_stability)} because no source was required.`;
}

function scoreFeatureRows(graph: ReliabilityGraph): string[][] {
  const featureLabels: Array<[string, string, string]> = [
    ["claim_support_rate", "Claim support", "Share of checked claims supported by source/verifier evidence."],
    ["retrieval_alignment_score", "Source match", "How strongly retrieved snippets matched the extracted claims."],
    ["source_quality_score", "Source quality", "Source provenance from metadata such as official docs, uploaded files, or lower-provenance pages."],
    ["semantic_stability", "Meaning agreement", "Whether provider samples answered with the same meaning."],
    ["sample_overlap_stability", "Sample overlap", "Lexical/meaning overlap between the main answer and other samples."],
    ["retrieval_peak_score", "Best source match", "Strongest individual retrieved match."],
    ["contradiction_rate", "Contradictions", "Share of checked claims contradicted by matched evidence."],
    ["insufficient_evidence_rate", "Unsupported claims", "Share of checked claims not found in evidence."],
  ];
  return featureLabels
    .filter(([key]) => graph.features[key] !== undefined)
    .map(([key, label, meaning]) => [label, formatPercent(graph.features[key]), meaning]);
}

function sourceSummary(graph: ReliabilityGraph): string {
  const external = externalEvidence(graph);
  if (external.length === 0) return graph.answer.source_limitations ?? "No attached, fetched, or web source supports this answer.";
  const groups = groupedEvidence(external);
  const titles = groups.slice(0, 2).map((item) => item.title);
  const matchCount = external.length;
  const extra = groups.length > titles.length ? ` + ${groups.length - titles.length} more` : "";
  return `${groups.length} source${groups.length === 1 ? "" : "s"} · ${matchCount} claim match${matchCount === 1 ? "" : "es"} · ${titles.join(" · ")}${extra}`;
}

function externalEvidence(graph: ReliabilityGraph): EvidenceItem[] {
  return graph.evidence.filter((item) => item.source_type !== "system_trace" && item.source_type !== "internal_policy");
}

function sourceEvidenceRows(evidence: EvidenceItem[]): string[][] {
  return groupedEvidence(evidence).map((group) => [
    group.title,
    group.type,
    group.date,
    group.quality,
    group.relation,
    String(group.matches),
    group.snippets.slice(0, 2).join(" / "),
  ]);
}

function groupedEvidence(evidence: EvidenceItem[]) {
  const groups = new Map<
    string,
    {
      title: string;
      type: string;
      date: string;
      quality: string;
      relation: string;
      matches: number;
      snippets: string[];
      bestScore: number;
    }
  >();
  for (const item of evidence) {
    const key = item.source_url || `${item.source_title}:${item.source_type}`;
    const existing = groups.get(key);
    const score = Number(item.relevance_score ?? 0);
    if (!existing) {
      groups.set(key, {
        title: item.source_title || item.source_url || "Untitled source",
        type: item.source_type,
        date: item.source_date ?? "not dated",
        quality: item.source_quality,
        relation: item.support_relation,
        matches: 1,
        snippets: item.snippet ? [item.snippet] : [],
        bestScore: score,
      });
      continue;
    }
    existing.matches += 1;
    existing.bestScore = Math.max(existing.bestScore, score);
    if (qualityRank(item.source_quality) > qualityRank(existing.quality)) existing.quality = item.source_quality;
    if (relationRank(item.support_relation) > relationRank(existing.relation)) existing.relation = item.support_relation;
    if (item.snippet && !existing.snippets.includes(item.snippet) && existing.snippets.length < 2) {
      existing.snippets.push(item.snippet);
    }
  }
  return Array.from(groups.values()).sort((left, right) => {
    const relationDelta = relationRank(right.relation) - relationRank(left.relation);
    if (relationDelta !== 0) return relationDelta;
    return right.bestScore - left.bestScore;
  });
}

function relationRank(relation: string): number {
  if (relation === "contradicts") return 4;
  if (relation === "supports") return 3;
  if (relation === "partially_supports") return 2;
  return 1;
}

function qualityRank(quality: string): number {
  if (quality === "high") return 3;
  if (quality === "medium") return 2;
  return 1;
}

function answerMeta(graph: ReliabilityGraph) {
  const score = graph.answer.reliability_score;
  const verdict = graph.answer.final_decision ?? graph.answer.verdict;
  const missing = [
    !verdict && "final decision",
    typeof score !== "number" && "reliability score",
    !graph.answer.verdict_reason && "verdict reason",
    !graph.answer.evidence_status && "evidence status",
    !graph.answer.main_uncertainty && "main uncertainty",
    !graph.answer.next_best_action && "next action",
  ].filter(Boolean);
  if (missing.length > 0 || !verdict) {
    return {
      complete: false as const,
      incompleteReason: `Missing ${missing.join(", ") || "required reliability fields"}.`,
      score: typeof score === "number" ? score : 0,
      verdict: "do_not_rely" as const,
      verdictLabel: "Incomplete",
      reason: "",
      evidenceStatus: "Reliability analysis incomplete.",
      uncertainty: "Reliability analysis did not finish cleanly.",
      change: "",
      nextAction: "Retry the run or inspect the error before relying on the answer.",
    };
  }
  return {
    complete: true as const,
    incompleteReason: "",
    score,
    verdict,
    verdictLabel: verdictLabel(verdict),
    reason: graph.answer.verdict_reason,
    evidenceStatus: graph.answer.evidence_status,
    uncertainty: graph.answer.main_uncertainty,
    change: graph.answer.what_would_change_the_answer,
    nextAction: graph.answer.next_best_action,
  };
}

function verdictLabel(verdict: "rely" | "use_with_caution" | "do_not_rely"): string {
  if (verdict === "rely") return "Rely";
  if (verdict === "do_not_rely") return "Do not rely";
  return "Use with caution";
}
