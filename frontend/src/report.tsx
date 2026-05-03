import { exportUrl } from "./api";
import type { ClaimAssessment, EvidenceItem, ReliabilityGraph } from "./types";

export const TABS = [
  "Summary",
  "Claims",
  "Sources",
  "Assumptions",
  "Decision",
  "Disagreement",
  "Checks",
  "Calibration",
  "Tinker Probe",
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
        <h2>Evidence graph</h2>
        <p>Your summary will appear here after the audit finishes.</p>
      </section>
    );
  }

  return (
    <section className="report-shell">
      <div className="report-header">
        <div>
          <h2>Latest result</h2>
          <p>
            {graph.run.question_type} · {formatProvider(graph.run.provider)}
          </p>
        </div>
        <div className="score-block">
          <span>Reliability Score</span>
          <strong>{graph.answer.reliability_score} / 100</strong>
          <small>{formatStatus(graph.answer.calibration_status)}</small>
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
  if (tab === "Claims") return <ClaimsTab graph={graph} />;
  if (tab === "Sources") return <EvidenceTab graph={graph} />;
  if (tab === "Assumptions") return <AssumptionsTab graph={graph} />;
  if (tab === "Decision") return <DecisionTab graph={graph} />;
  if (tab === "Disagreement") return <DisagreementTab graph={graph} />;
  if (tab === "Checks") return <StressTab graph={graph} />;
  if (tab === "Calibration") return <CalibrationTab graph={graph} />;
  if (tab === "Tinker Probe") return <CausalProbeTab graph={graph} />;
  return <ExportTab graph={graph} />;
}

function AnswerTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="summary-layout">
      <section className="score-summary">
        <div className="score-ring">
          <strong>{graph.answer.reliability_score}</strong>
          <span>/100</span>
        </div>
        <div>
          <h3>Reliability is {scoreLabel(graph.answer.reliability_score).toLowerCase()}</h3>
          <p>{graph.answer.summary}</p>
        </div>
      </section>
      <section className="answer-main">
        <h3>Answer</h3>
        <p>{graph.answer.final_answer}</p>
        {graph.answer.recommendation && (
          <>
            <h3>Recommendation</h3>
            <p>{graph.answer.recommendation}</p>
          </>
        )}
        <h3>Main Uncertainty</h3>
        <p>{graph.answer.main_uncertainty}</p>
        <h3>What Would Change The Answer</h3>
        <p>{graph.answer.what_would_change_the_answer}</p>
      </section>
      <aside className="signal-panel">
        <h3>Trust Signals</h3>
        <ul>{graph.answer.top_positive_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
        <h3>Risk Signals</h3>
        <ul>{graph.answer.top_negative_signals.map((signal) => <li key={signal}>{signal}</li>)}</ul>
        <h3>Recommended Action</h3>
        <p>{graph.answer.recommended_user_action}</p>
      </aside>
    </div>
  );
}

function ClaimsTab({ graph }: { graph: ReliabilityGraph }) {
  const assessments = new Map(graph.claim_assessments.map((assessment) => [assessment.claim_id, assessment]));
  return (
    <Table
      columns={["Claim", "Type", "Importance", "Checkability", "Assessment", "Evidence"]}
      rows={graph.claims.map((claim) => {
        const assessment = assessments.get(claim.claim_id);
        return [
          claim.text,
          claim.type,
          claim.importance,
          claim.checkability,
          assessment?.status ?? "unassessed",
          String(assessment?.evidence_ids.length ?? 0),
        ];
      })}
    />
  );
}

function EvidenceTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <Table
      columns={["Source", "Type", "Date", "Quality", "Relation", "Snippet"]}
      rows={graph.evidence.map((item: EvidenceItem) => [
        item.source_title,
        item.source_type,
        item.source_date ?? "not dated",
        item.source_quality,
        item.support_relation,
        item.snippet,
      ])}
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
          columns={["Alternative", "Utility"]}
          rows={graph.decision_analysis.alternatives.map((alternative) => [alternative.name, formatNumber(alternative.utility)])}
        />
      </div>
      <div>
        <h3>Criteria</h3>
        <Table
          columns={["Criterion", "Weight"]}
          rows={graph.decision_analysis.criteria.map((criterion) => [criterion.name, formatPercent(criterion.weight)])}
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
      columns={["Test", "Changed", "New evidence", "Unsupported flip", "Impact", "Result"]}
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
      <Table
        columns={["Feature", "Value"]}
        rows={Object.entries(graph.features).map(([key, value]) => [key, formatNumber(value)])}
      />
      {graph.score_caps.length > 0 && (
        <>
          <h3>Score Caps</h3>
          <ul>{graph.score_caps.map((cap) => <li key={cap}>{cap}</li>)}</ul>
        </>
      )}
    </div>
  );
}

function CausalProbeTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div>
      <h3>{formatStatus(graph.causal_probe.mode)}</h3>
      <p>{graph.causal_probe.reason}</p>
      {graph.causal_probe.results.length > 0 ? (
        <Table
          columns={["Operation", "Changed", "Similarity", "Unsupported flip", "Result"]}
          rows={graph.causal_probe.results.map((result) => [
            result.operation,
            result.answer_changed ? "yes" : "no",
            formatNumber(result.similarity_to_baseline),
            result.unsupported_flip ? "yes" : "no",
            result.result,
          ])}
        />
      ) : (
        <Table columns={["Available operation"]} rows={graph.causal_probe.operations.map((operation) => [operation])} />
      )}
    </div>
  );
}

function ExportTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="export-panel">
      <p>Format: {graph.export.format}</p>
      <p>Plaintext provider keys included: {graph.export.contains_plaintext_provider_keys ? "yes" : "no"}</p>
      <a className="primary-link" href={exportUrl(graph.run.run_id)}>
        Export JSON
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
    </div>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function formatProvider(provider: string): string {
  if (provider === "local" || provider === "preview") return "Core Engine";
  if (provider === "openrouter") return "OpenRouter";
  return provider.slice(0, 1).toUpperCase() + provider.slice(1);
}

function formatStatus(value: string): string {
  return value.replaceAll("_", " ");
}

function scoreLabel(score: number): string {
  if (score >= 80) return "Strong";
  if (score >= 60) return "Moderate";
  return "Limited";
}
