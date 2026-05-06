import { exportUrl } from "./api";
import { MarkdownText } from "./markdown";
import { useState } from "react";
import type { SyntheticEvent } from "react";
import type { ClaimAssessment, EvidenceItem, ReliabilityGraph, TraceSpan } from "./types";

export const TABS = ["Overview", "Evidence", "Claims", "Consistency", "Robustness", "Score", "Activity", "Export"] as const;

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
  if (tab === "Overview") return <OverviewTab graph={graph} />;
  if (tab === "Evidence") return <EvidenceSourcesTab graph={graph} />;
  if (tab === "Claims") return <ClaimsAuditTab graph={graph} />;
  if (tab === "Consistency") return <ConsistencyTab graph={graph} />;
  if (tab === "Robustness") return <RobustnessTab graph={graph} />;
  if (tab === "Score") return <ScoreTab graph={graph} />;
  if (tab === "Activity") return <ActivityTab graph={graph} />;
  if (tab === "Export") return <ExportTab graph={graph} />;
  return <OverviewTab graph={graph} />;
}

function OverviewTab({ graph }: { graph: ReliabilityGraph }) {
  const meta = answerMeta(graph);
  const issues = reliabilityIssues(graph).slice(0, 4);
  return (
    <div className="overview-layout">
      <section className="overview-score">
        <div>
          <span className={`decision-pill decision-${meta.verdict}`}>{meta.verdictLabel}</span>
          <strong>{graph.answer.reliability_score}/100</strong>
          <p>{graph.answer.reliability_explanation || graph.analysis_explanation || reliabilityOneLine(graph)}</p>
        </div>
      </section>
      <section className="overview-grid">
        <MetricTile label="Sources" value={String(evidenceSourceRows(graph).length)} />
        <MetricTile label="Claims checked" value={String(supportBreakdown(graph).total)} />
        <MetricTile label="Claim support" value={formatPercent(graph.features.claim_support_rate)} />
        <MetricTile label="Sample agreement" value={formatPercent(graph.features.semantic_stability ?? graph.disagreement.semantic_stability)} />
      </section>
      <section className="overview-actions">
        <h3>What to check first</h3>
        {issues.length === 0 ? <p className="empty-state">No blocking issue was found in the completed audit.</p> : <ul>{issues.map((issue) => <li key={`${issue.title}-${issue.detail}`}><strong>{issue.title}</strong><span>{issue.detail}</span></li>)}</ul>}
        <h3>Next step</h3>
        <p>{cleanNextAction(meta.nextAction ?? "", graph)}</p>
      </section>
    </div>
  );
}

function ClaimsAuditTab({ graph }: { graph: ReliabilityGraph }) {
  const evidenceById = new Map(graph.evidence.map((item) => [item.evidence_id, item]));
  const rows = claimAuditRows(graph).sort((left, right) => claimAuditRiskRank(left.relation, left.severity) - claimAuditRiskRank(right.relation, right.severity));
  return (
    <div className="analysis-table-shell">
      <div className="detail-heading">
        <h3>Claim audit</h3>
        <p>{rows.length} atomic item{rows.length === 1 ? "" : "s"} checked or classified.</p>
      </div>
      {rows.length === 0 ? (
        <p className="empty-state">No claim audit rows were returned.</p>
      ) : (
        <div className="analysis-table claim-audit-table">
          <div className="analysis-table-head">
            <span>Status</span>
            <span>Claim</span>
            <span>Evidence</span>
            <span>Why</span>
          </div>
          {rows.map((row) => {
            const matchedEvidence = row.evidence_ids.map((id) => evidenceById.get(id)).filter((item): item is EvidenceItem => Boolean(item));
            return (
              <article className={`analysis-row relation-${relationClass(row.relation)}`} key={row.claim_id}>
                <div>
                  <RelationPill relation={row.relation} />
                  <small>{formatStatus(row.severity || "low")} risk</small>
                </div>
                <div>
                  <strong>{row.claim}</strong>
                  <small>{formatStatus(row.claim_type || "claim")} · {formatStatus(row.importance || "medium")} importance</small>
                </div>
                <div>
                  {matchedEvidence.length === 0 ? (
                    <small>{row.relation === "not_checkable" ? "No source required" : "No matched source"}</small>
                  ) : (
                    matchedEvidence.slice(0, 2).map((item) => (
                      <a href={item.source_url || undefined} key={item.evidence_id} rel="noreferrer" target={item.source_url ? "_blank" : undefined}>
                        {item.source_title || item.source_url || item.evidence_id}
                      </a>
                    ))
                  )}
                </div>
                <div>
                  <p>{row.why || relationExplanation(row.relation)}</p>
                  {row.limitation && <small>{row.limitation}</small>}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function EvidenceSourcesTab({ graph }: { graph: ReliabilityGraph }) {
  const rows = evidenceSourceRows(graph);
  return (
    <div className="analysis-table-shell">
      <div className="detail-heading">
        <h3>Evidence</h3>
        <p>{rows.length === 0 ? "No external evidence was available." : `${rows.length} source${rows.length === 1 ? "" : "s"} used for checking.`}</p>
      </div>
      {rows.length === 0 ? (
        <p className="empty-state">No attached, pasted URL, or web source was available for source-grounded checking.</p>
      ) : (
        <div className="analysis-table evidence-table">
          <div className="analysis-table-head">
            <span>Source</span>
            <span>Quality</span>
            <span>Matches</span>
            <span>Best snippet</span>
          </div>
          {rows.map((row) => (
            <article className="analysis-row" key={row.source_id}>
              <div>
                {row.url ? (
                  <a href={row.url} rel="noreferrer" target="_blank">{row.title}</a>
                ) : (
                  <strong>{row.title}</strong>
                )}
                <small>{formatStatus(row.source_type)} · {formatStatus(row.freshness)}</small>
              </div>
              <div>
                <span className={`source-quality source-quality-${row.quality}`}>{formatStatus(row.quality)}</span>
              </div>
              <div>
                <strong>{row.match_count}</strong>
                <small>{relationSummary(row.relations)}</small>
              </div>
              <div>
                <p>{row.top_snippet ? shortText(row.top_snippet, 320) : "No snippet returned."}</p>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function ConsistencyTab({ graph }: { graph: ReliabilityGraph }) {
  const checks = graph.consistency_checks;
  return (
    <div className="consistency-panel">
      <div className="consistency-grid">
        <MetricTile label="Sample agreement" value={formatPercent(checks?.sample_agreement ?? graph.features.semantic_stability ?? graph.disagreement.semantic_stability)} />
        <MetricTile label="Meaning groups" value={String((checks?.semantic_clusters ?? graph.disagreement.semantic_clusters).length)} />
        <MetricTile label="Sample overlap" value={formatPercent(checks?.sample_overlap_stability ?? graph.features.sample_overlap_stability)} />
        <MetricTile label="Conflict rate" value={formatPercent(checks?.sample_conflict_rate ?? graph.features.sample_conflict_rate)} />
      </div>
      {graph.disagreement.accepted_rejected_dissent && <p className="panel-note">{graph.disagreement.accepted_rejected_dissent}</p>}
      <details className="nested-detail">
        <summary>Sample meanings</summary>
        {(checks?.semantic_clusters ?? graph.disagreement.semantic_clusters).length === 0 ? (
          <p className="empty-state">No candidate sample clusters were recorded.</p>
        ) : (
          <div className="compact-stack">
            {(checks?.semantic_clusters ?? graph.disagreement.semantic_clusters).map((cluster) => (
              <article key={cluster.cluster_id}>
                <strong>{cluster.label || cluster.cluster_id}</strong>
                <span>{cluster.candidate_ids.length} sample{cluster.candidate_ids.length === 1 ? "" : "s"}</span>
                <p>{cluster.summary}</p>
              </article>
            ))}
          </div>
        )}
      </details>
    </div>
  );
}

function RobustnessTab({ graph }: { graph: ReliabilityGraph }) {
  const probe = graph.perturbation_probe ?? graph.causal_probe;
  const changed = probe.results.filter((result) => result.answer_changed).length;
  const unsupportedFlips = probe.results.filter((result) => result.unsupported_flip).length;
  return (
    <div className="consistency-panel">
      <div className="consistency-grid">
        <MetricTile label="Checks run" value={String(probe.results.length || probe.operations.length || 0)} />
        <MetricTile label="Answer changed" value={String(changed)} />
        <MetricTile label="Unsupported flips" value={String(unsupportedFlips)} />
        <MetricTile label="Mode" value={formatStatus(probe.mode || "not available")} />
      </div>
      <p className="panel-note">{probe.reason || "Robustness checks compare observable provider outputs under pressure-style prompt variants."}</p>
      {probe.results.length === 0 ? (
        <p className="empty-state">No robustness runs were recorded.</p>
      ) : (
        <div className="compact-stack">
          {probe.results.map((result) => (
            <article key={result.operation}>
              <strong>{formatStatus(result.operation)}</strong>
              <span>
                {result.answer_changed ? "changed" : "stable"} · similarity {formatNumber(result.similarity_to_baseline)} · unsupported flip{" "}
                {result.unsupported_flip ? "yes" : "no"}
              </span>
              <p>{result.result}</p>
            </article>
          ))}
        </div>
      )}
      {graph.stress_tests.length > 0 && (
        <details className="nested-detail">
          <summary>Other checks</summary>
          <div className="compact-stack">
            {graph.stress_tests.map((test) => (
              <article key={test.test_type}>
                <strong>{formatStatus(test.test_type)}</strong>
                <span>
                  {test.answer_changed ? "changed" : "stable"} · unsupported flip {test.unsupported_flip ? "yes" : "no"}
                </span>
                <p>{test.result}</p>
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function ScoreTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="methods-panel">
      <section className="method-section">
        <h3>Score</h3>
        <p>{calibrationCopy(graph)}</p>
        <p className="panel-note">The Reliability Score estimates answer trustability under the gathered evidence. It is not proof, a guarantee, or a provider confidence score.</p>
        {graph.score_caps.length > 0 && (
          <div className="issue-list">
            {graph.score_caps.map((cap) => (
              <span key={cap}>{cap}</span>
            ))}
          </div>
        )}
        <div className="feature-list">
          {scoreFeatureRows(graph).map(([label, value, meaning]) => (
            <div key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
              <p>{meaning}</p>
            </div>
          ))}
        </div>
      </section>
      {graph.analysis_basis && graph.analysis_basis.length > 0 && (
        <details className="nested-detail">
          <summary>Method basis</summary>
          <div className="compact-stack">
            {graph.analysis_basis.map((item) => (
              <article key={`${item.signal}-${item.method}`}>
                <strong>{item.signal}</strong>
                <span>{formatStatus(item.method)}</span>
                <p>{item.limitation}</p>
              </article>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tile">
      <strong>{value}</strong>
      <span>{label}</span>
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
    if (Array.isArray(parsed.substeps)) {
      const names = parsed.substeps
        .map((step: { step?: string }) => String(step.step || "").replaceAll("_", " "))
        .filter(Boolean);
      if (span.type === "answer_generation") return `Answer generated${names.length ? ` after ${names.join(", ")}` : ""}.`;
      if (span.type === "evidence_build") return `Evidence packet built${names.length ? ` through ${names.join(", ")}` : ""}.`;
      if (span.type === "claim_audit") return `Claims audited${names.length ? ` through ${names.join(", ")}` : ""}.`;
      if (span.type === "score_and_report") return "Final score and reliability report prepared.";
    }
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
      return `Reliability Score ${parsed.score ?? "n/a"}/100.${caps}`;
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
      <section className="reliability-score-panel verdict-do_not_rely" aria-label="Reliability summary">
        <div>
          <span className="decision-pill decision-do_not_rely">Incomplete</span>
          <strong>Reliability analysis incomplete</strong>
          <p>{meta.incompleteReason}</p>
        </div>
      </section>
    );
  }
  return (
    <section className={`reliability-score-panel verdict-${meta.verdict}`} aria-label="Reliability summary">
      <div className="score-panel-main">
        <span className={`decision-pill decision-${meta.verdict}`}>{meta.verdictLabel}</span>
        <strong>Reliability Score {meta.score}/100</strong>
        <small>{scoreStatus(graph)}</small>
      </div>
      <div className="score-panel-copy">
        <p>{graph.answer.reliability_explanation || graph.analysis_explanation || reliabilityOneLine(graph)}</p>
        <small>Next: {cleanNextAction(meta.nextAction ?? "", graph)}</small>
      </div>
    </section>
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
  const [activeTab, setActiveTab] = useState<ReportTab>("Overview");
  const meta = answerMeta(graph);
  return (
    <details className="analysis-drawer" data-reliability-section onToggle={handleDetailToggle} open={meta.verdict === "do_not_rely"}>
      <summary>
        <span>Full reliability analysis</span>
        <small>Evidence, claims, score</small>
      </summary>
      <div className="analysis-drawer-body">
        <nav className="analysis-tab-row" aria-label="Reliability analysis sections">
          {TABS.map((tab) => (
            <button className={activeTab === tab ? "selected" : ""} key={tab} type="button" onClick={() => setActiveTab(tab)}>
              {tab}
            </button>
          ))}
        </nav>
        <div className="detail-panel">{renderTab(activeTab, graph)}</div>
      </div>
    </details>
  );
}

function handleDetailToggle(event: SyntheticEvent<HTMLDetailsElement>) {
  const details = event.currentTarget;
  if (!details.open) return;
  const siblings = details.parentElement?.querySelectorAll<HTMLDetailsElement>(":scope > details[data-reliability-section]");
  siblings?.forEach((sibling) => {
    if (sibling !== details) sibling.open = false;
  });
  window.requestAnimationFrame(() => {
    details.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}

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

function supportBreakdown(graph: ReliabilityGraph) {
  const checkedAssessments = graph.claim_assessments.filter((assessment) => !["not_checkable", "unassessed"].includes(claimRelation(assessment)));
  const direct = checkedAssessments.filter((assessment) => claimRelation(assessment) === "supported").length;
  const partial = checkedAssessments.filter((assessment) => claimRelation(assessment) === "partially_supported").length;
  const contradicted = checkedAssessments.filter((assessment) => claimRelation(assessment) === "contradicted").length;
  const notFound = checkedAssessments.filter((assessment) => ["not_found", "insufficient_evidence"].includes(claimRelation(assessment))).length;
  return {
    total: checkedAssessments.length,
    direct,
    partial,
    contradicted,
    unsupported: contradicted + notFound,
    notFound,
  };
}

function reliabilityIssues(graph: ReliabilityGraph): Array<{ title: string; detail: string }> {
  const meta = answerMeta(graph);
  const support = supportBreakdown(graph);
  const issues: Array<{ title: string; detail: string }> = [];
  if (support.contradicted > 0) {
    issues.push({
      title: `${support.contradicted} contradicted claim${support.contradicted === 1 ? "" : "s"}`,
      detail: "Review the conflicting source snippet before relying on the answer.",
    });
  }
  if (support.notFound > 0) {
    issues.push({
      title: `${support.notFound} claim${support.notFound === 1 ? " was" : "s were"} not found in sources`,
      detail: "The answer includes source-checkable claims that retrieval did not verify.",
    });
  }
  if (support.partial > 0) {
    issues.push({
      title: `${support.partial} partially supported claim${support.partial === 1 ? "" : "s"}`,
      detail: "The sources are relevant, but they do not fully establish the claim wording.",
    });
  }
  if ((graph.features.semantic_stability ?? graph.disagreement.semantic_stability) < 0.55) {
    issues.push({
      title: "Low sample agreement",
      detail: "Different candidate answers did not converge on one meaning.",
    });
  }
  for (const cap of uniqueLines(graph.score_caps)) {
    issues.push({
      title: "Score cap",
      detail: cap,
    });
  }
  if (issues.length === 0 && meta.verdict !== "rely") {
    issues.push({
      title: "Use caution",
      detail: meta.reason || "The decision is cautious because the available signals are not strong enough for unqualified reliance.",
    });
  }
  return issues.slice(0, 6);
}

function uniqueLines(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function scoreStatus(graph: ReliabilityGraph): string {
  if (graph.score_caps.length > 0) return "Capped by risk signals";
  if (graph.answer.calibration_status === "benchmark_tuned" || graph.answer.calibration_status === "benchmark_tuned_diagnostic") return "Benchmark-tuned estimate";
  if (graph.answer.calibration_status === "local_calibration") return "Locally calibrated estimate";
  return "Research-prior estimate";
}

function reliabilityOneLine(graph: ReliabilityGraph): string {
  const meta = answerMeta(graph);
  const uncertainty = shortText(meta.uncertainty ?? "Main uncertainty was not returned.", 150);
  const support = supportBreakdown(graph);
  const contradicted = graph.claim_assessments.filter((item) => claimRelation(item) === "contradicted").length;
  if (contradicted > 0) return `${contradicted} checked claim${contradicted === 1 ? "" : "s"} conflict with available evidence. Main risk: ${uncertainty}`;
  if (support.total > 0 && support.unsupported > 0) {
    return `Sources support ${support.direct + support.partial}/${support.total} checked claims; ${support.unsupported} ${support.unsupported === 1 ? "claim was" : "claims were"} not found. Check: ${uncertainty}`;
  }
  if (support.total > 0 && support.partial > 0) {
    return `Sources directly support ${support.direct}/${support.total} checked claims and partially support ${support.partial}. Review the partial claims before acting.`;
  }
  if (support.total > 0 && support.direct === support.total) {
    return `Sources directly support all ${support.total} checked claims. Remaining uncertainty: ${uncertainty}`;
  }
  const evidence = shortText(meta.evidenceStatus ?? "Evidence status was not returned.", 150);
  if (meta.verdict === "do_not_rely") return `${evidence} Main risk: ${uncertainty}`;
  if (meta.verdict === "rely") return `${evidence} Remaining uncertainty: ${uncertainty}`;
  return `${evidence} Check: ${uncertainty}`;
}

function cleanNextAction(nextAction: string, graph: ReliabilityGraph): string {
  const support = supportBreakdown(graph);
  if (support.partial > 0 && !nextAction.toLowerCase().includes("partial")) {
    return `Open Evidence and review ${support.partial} partially supported claim${support.partial === 1 ? "" : "s"} before acting.`;
  }
  const genericPatterns = [
    "use the answer with the reliability cards and source snippets kept visible",
    "use the answer with the reliability cards",
  ];
  if (genericPatterns.some((pattern) => nextAction.toLowerCase().includes(pattern))) {
    const contradicted = graph.claim_assessments.some((item) => claimRelation(item) === "contradicted");
    if (contradicted) return "Open Evidence and review the contradicted claim before using this.";
    if (externalEvidence(graph).length === 0) return "Add a source or search result before using factual claims.";
    return "Open Evidence for the highest-risk claim before acting on this.";
  }
  return shortText(nextAction, 180);
}

function shortText(text: string, maxLength: number): string {
  const trimmed = text.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;
}

function claimRelation(assessment: ClaimAssessment | undefined, checkability?: string): string {
  if (checkability === "not_checkable") return "not_checkable";
  return assessment?.relation ?? assessment?.status ?? "unassessed";
}

function relationClass(relation: string): string {
  if (relation === "partially_supports") return "partially_supported";
  if (relation === "supports") return "supported";
  if (relation === "contradicts") return "contradicted";
  return relation;
}

function relationLabel(relation: string): string {
  if (relation === "not_found" || relation === "insufficient_evidence") return "not found";
  if (relation === "partially_supported" || relation === "partially_supports") return "partial";
  if (relation === "not_checkable") return "not scored";
  if (relation === "supports") return "supported";
  if (relation === "contradicts") return "contradicted";
  return formatStatus(relation || "unassessed");
}

function RelationPill({ relation }: { relation: string }) {
  return <span className={`relation-pill relation-${relationClass(relation)}`}>{relationLabel(relation)}</span>;
}

function relationExplanation(relation: string): string {
  if (relation === "supported" || relation === "supports") return "A source snippet supports this claim.";
  if (relation === "partially_supported" || relation === "partially_supports") return "A source snippet supports part of this claim, but not the full wording.";
  if (relation === "contradicted" || relation === "contradicts") return "A source snippet conflicts with this claim.";
  if (relation === "not_checkable") return "This item is advice, framing, or interpretation rather than a source-checkable factual claim.";
  return "No source snippet was found that supports this claim.";
}

function calibrationCopy(graph: ReliabilityGraph): string {
  if (graph.answer.calibration_status === "local_calibration") {
    const labels = graph.calibration.benchmark?.label_count ?? 0;
    return labels > 0 ? `Locally calibrated with ${labels} labeled run${labels === 1 ? "" : "s"}` : "Locally calibrated";
  }
  if (graph.answer.calibration_status === "benchmark_tuned" || graph.answer.calibration_status === "benchmark_tuned_diagnostic") {
    return "Benchmark-tuned Reliability Score; use the evidence and final decision with the number";
  }
  return "Research-prior Reliability Score; use the evidence and final decision with the number";
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

type ClaimAuditRow = NonNullable<ReliabilityGraph["claim_audit"]>[number];
type EvidenceSourceRow = NonNullable<ReliabilityGraph["evidence_sources"]>[number];

function claimAuditRows(graph: ReliabilityGraph): ClaimAuditRow[] {
  if (graph.claim_audit && graph.claim_audit.length > 0) return graph.claim_audit;
  const assessmentByClaim = new Map(graph.claim_assessments.map((assessment) => [assessment.claim_id, assessment]));
  return graph.claims.map((claim) => {
    const assessment = assessmentByClaim.get(claim.claim_id);
    const relation = claimRelation(assessment, claim.checkability) as ClaimAuditRow["relation"];
    return {
      claim_id: claim.claim_id,
      claim: claim.text,
      answer_quote: claim.answer_quote,
      claim_type: claim.type,
      checkability: claim.checkability,
      importance: claim.importance,
      relation,
      severity: relation === "contradicted" || relation === "not_found" ? "high" : relation === "partially_supported" ? "medium" : "low",
      evidence_ids: assessment?.evidence_ids ?? [],
      why: assessment?.why ?? assessment?.explanation ?? relationExplanation(relation),
      limitation: assessment?.source_limit ?? "",
      provider_relation: assessment?.provider_relation ?? undefined,
      assessment_method: assessment?.assessment_method,
      verifier: assessment?.verifier,
      entailment_score: assessment?.entailment_score,
      contradiction_score: assessment?.contradiction_score,
      neutral_score: assessment?.neutral_score,
      support_score: assessment?.support_score,
      risk_flags: claim.risk_flags ?? [],
    };
  });
}

function evidenceSourceRows(graph: ReliabilityGraph): EvidenceSourceRow[] {
  if (graph.evidence_sources && graph.evidence_sources.length > 0) return graph.evidence_sources;
  return groupedEvidence(graph).map((group, index) => ({
    source_id: `src_${index + 1}`,
    title: group.title,
    url: group.url,
    source_type: group.type,
    quality: group.quality,
    freshness: group.date || "not_dated",
    match_count: group.matches,
    claim_ids: [],
    evidence_ids: [],
    relations: { [group.relation]: group.matches },
    top_snippet: group.snippets[0] || "",
    top_relevance: group.bestScore,
  }));
}

function relationSummary(relations: Record<string, number>): string {
  const entries = Object.entries(relations || {}).filter(([, count]) => count > 0);
  if (entries.length === 0) return "matched evidence";
  return entries
    .slice(0, 3)
    .map(([relation, count]) => `${count} ${relationLabel(relation)}`)
    .join(" · ");
}

function claimAuditRiskRank(relation: string, severity: string | undefined): number {
  if (relation === "contradicted") return 0;
  if (relation === "not_found" || relation === "insufficient_evidence") return severity === "high" ? 1 : 2;
  if (relation === "partially_supported") return 3;
  if (relation === "not_checkable") return 5;
  return 4;
}

function externalEvidence(graph: ReliabilityGraph): EvidenceItem[] {
  return graph.evidence.filter((item) => item.source_type !== "system_trace" && item.source_type !== "internal_policy");
}

function groupedEvidence(graph: ReliabilityGraph) {
  const evidence = externalEvidence(graph);
  const assessmentByClaim = new Map(graph.claim_assessments.map((assessment) => [assessment.claim_id, assessment]));
  const groups = new Map<
    string,
    {
      key: string;
      title: string;
      url: string | null;
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
    const relation = sourceRelation(item, assessmentByClaim.get(item.claim_id));
    if (!existing) {
      groups.set(key, {
        key,
        title: item.source_title || item.source_url || "Untitled source",
        url: item.source_url,
        type: item.source_type,
        date: item.source_date ?? "not dated",
        quality: item.source_quality,
        relation,
        matches: 1,
        snippets: item.snippet ? [item.snippet] : [],
        bestScore: score,
      });
      continue;
    }
    existing.matches += 1;
    existing.bestScore = Math.max(existing.bestScore, score);
    if (qualityRank(item.source_quality) > qualityRank(existing.quality)) existing.quality = item.source_quality;
    if (relationRank(relation) > relationRank(existing.relation)) existing.relation = relation;
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

function sourceRelation(item: EvidenceItem, assessment: ClaimAssessment | undefined): string {
  const relation = claimRelation(assessment);
  if (["supported", "partially_supported", "contradicted", "not_found"].includes(relation)) return relation;
  if (item.support_relation === "supports") return "supported";
  if (item.support_relation === "partially_supports") return "partially_supported";
  if (item.support_relation === "contradicts") return "contradicted";
  return item.support_relation || "unassessed";
}

function relationRank(relation: string): number {
  if (relation === "contradicted" || relation === "contradicts") return 4;
  if (relation === "not_found" || relation === "insufficient_evidence") return 3;
  if (relation === "partially_supported" || relation === "partially_supports") return 2;
  if (relation === "supported" || relation === "supports") return 1;
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
