import { exportUrl } from "./api";
import { MarkdownText } from "./markdown";
import { useState } from "react";
import type { SyntheticEvent } from "react";
import type { ClaimAssessment, EvidenceItem, ReliabilityGraph, TraceSpan } from "./types";

export const TABS = ["Summary", "Issues", "Evidence", "Consistency", "Methods"] as const;

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
  if (tab === "Evidence") return <EvidenceReviewTab graph={graph} />;
  if (tab === "Consistency") return <ConsistencyTab graph={graph} />;
  if (tab === "Methods") return <MethodsTab graph={graph} />;
  return <AnswerTab graph={graph} />;
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

function EvidenceReviewTab({ graph }: { graph: ReliabilityGraph }) {
  const assessments = new Map(graph.claim_assessments.map((assessment) => [assessment.claim_id, assessment]));
  const evidenceById = new Map(graph.evidence.map((item) => [item.evidence_id, item]));
  const claimRows = graph.claims
    .map((claim) => ({ claim, assessment: assessments.get(claim.claim_id) }))
    .sort((left, right) => claimRiskRank(left.assessment, left.claim.checkability) - claimRiskRank(right.assessment, right.claim.checkability));
  const evidenceGroups = groupedEvidence(externalEvidence(graph));

  return (
    <div className="evidence-review">
      <section>
        <div className="detail-heading">
          <h3>Claim checks</h3>
          <p>{claimRows.length} claim{claimRows.length === 1 ? "" : "s"} checked or classified.</p>
        </div>
        {claimRows.length === 0 ? (
          <p className="empty-state">No claim checks were returned for this answer.</p>
        ) : (
          <div className="claim-list">
            {claimRows.map(({ claim, assessment }) => {
              const relation = claimRelation(assessment, claim.checkability);
              const matchedEvidence = (assessment?.evidence_ids ?? []).map((id) => evidenceById.get(id)).filter((item): item is EvidenceItem => Boolean(item));
              return (
                <article className={`claim-row relation-${relationClass(relation)}`} key={claim.claim_id}>
                  <header>
                    <RelationPill relation={relation} />
                    <strong>{claim.text}</strong>
                  </header>
                  <div className="claim-meta">
                    <span>{formatStatus(claim.type)}</span>
                    <span>{formatStatus(claim.importance)} importance</span>
                    <span>{methodLabel(assessment, relation)}</span>
                  </div>
                  <details>
                    <summary>Why and source</summary>
                    <p>{assessment?.why ?? assessment?.explanation ?? relationExplanation(relation)}</p>
                    <p>{assessment?.source_limit ?? evidenceLimitText(relation, matchedEvidence.length)}</p>
                    {matchedEvidence.length > 0 && (
                      <ul className="evidence-snippet-list">
                        {matchedEvidence.slice(0, 3).map((item) => (
                          <li key={item.evidence_id}>
                            <strong>{item.source_title || item.source_url || "Source"}</strong>
                            <span>{item.snippet}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </details>
                </article>
              );
            })}
          </div>
        )}
      </section>
      <section>
        <div className="detail-heading">
          <h3>Sources used</h3>
          <p>{evidenceGroups.length === 0 ? "No external evidence was available." : `${evidenceGroups.length} grouped source${evidenceGroups.length === 1 ? "" : "s"}.`}</p>
        </div>
        {evidenceGroups.length === 0 ? (
          <p className="empty-state">No attached, fetched, or web source was used for claim checking.</p>
        ) : (
          <div className="source-list">
            {evidenceGroups.map((group) => (
              <article className="source-row" key={group.key}>
                <header>
                  <div>
                    {group.url ? (
                      <a href={group.url} rel="noreferrer" target="_blank">
                        {group.title}
                      </a>
                    ) : (
                      <strong>{group.title}</strong>
                    )}
                    <span>
                      {formatStatus(group.type)} · {group.matches} match{group.matches === 1 ? "" : "es"} · {formatStatus(group.quality)}
                    </span>
                  </div>
                  <RelationPill relation={group.relation} />
                </header>
                {group.snippets[0] && <p>{group.snippets[0]}</p>}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ConsistencyTab({ graph }: { graph: ReliabilityGraph }) {
  const probe = graph.perturbation_probe ?? graph.causal_probe;
  const changed = probe.results.filter((result) => result.answer_changed).length;
  const unsupportedFlips = probe.results.filter((result) => result.unsupported_flip).length;
  return (
    <div className="consistency-panel">
      <div className="consistency-grid">
        <MetricTile label="Sample agreement" value={formatPercent(graph.features.semantic_stability ?? graph.disagreement.semantic_stability)} />
        <MetricTile label="Meaning groups" value={String(graph.disagreement.semantic_clusters.length)} />
        <MetricTile label="Robustness changes" value={`${changed}/${probe.results.length || probe.operations.length || 0}`} />
        <MetricTile label="Unsupported flips" value={String(unsupportedFlips)} />
      </div>
      {graph.disagreement.accepted_rejected_dissent && <p className="panel-note">{graph.disagreement.accepted_rejected_dissent}</p>}
      <details className="nested-detail">
        <summary>Sample meanings</summary>
        {graph.disagreement.semantic_clusters.length === 0 ? (
          <p className="empty-state">No candidate sample clusters were recorded.</p>
        ) : (
          <div className="compact-stack">
            {graph.disagreement.semantic_clusters.map((cluster) => (
              <article key={cluster.cluster_id}>
                <strong>{cluster.label || cluster.cluster_id}</strong>
                <span>{cluster.candidate_ids.length} sample{cluster.candidate_ids.length === 1 ? "" : "s"}</span>
                <p>{cluster.summary}</p>
              </article>
            ))}
          </div>
        )}
      </details>
      <details className="nested-detail">
        <summary>Robustness checks</summary>
        <p>{probe.reason}</p>
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
      </details>
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

function MethodsTab({ graph }: { graph: ReliabilityGraph }) {
  return (
    <div className="methods-panel">
      <section className="method-section">
        <h3>Score</h3>
        <p>{calibrationCopy(graph)}</p>
        <p className="panel-note">The score ranks risk across answers. It is not a probability or guarantee.</p>
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
      <details className="nested-detail">
        <summary>Observable activity</summary>
        <ActivityTab graph={graph} />
      </details>
      <details className="nested-detail">
        <summary>Export</summary>
        <ExportTab graph={graph} />
      </details>
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
  const [helpOpen, setHelpOpen] = useState(false);
  if (!meta.complete) {
    return (
      <section className="reliability-strip-v2 verdict-do_not_rely" aria-label="Reliability summary">
        <div className="reliability-mainline">
          <div className="decision-cell">
            <span className="decision-pill decision-do_not_rely">Incomplete</span>
            <strong>Reliability analysis incomplete</strong>
            <small>Required fields were missing.</small>
          </div>
          <div className="reliability-read">
            <span>Can I rely on this?</span>
            <p>{meta.incompleteReason}</p>
          </div>
          <div className="next-cell">
            <span>Next</span>
            <p>{meta.nextAction}</p>
          </div>
        </div>
      </section>
    );
  }
  const metrics = reliabilityMetrics(graph);
  return (
    <section className={`reliability-strip-v2 verdict-${meta.verdict}`} aria-label="Reliability summary">
      <div className="reliability-mainline">
        <div className="decision-cell">
          <span className={`decision-pill decision-${meta.verdict}`}>{meta.verdictLabel}</span>
          <strong>{meta.score}/100</strong>
          <small>{scoreStatus(graph)}</small>
        </div>
        <div className="reliability-read">
          <span>Can I rely on this?</span>
          <p>{reliabilityOneLine(graph)}</p>
        </div>
        <div className="next-cell">
          <span>Next</span>
          <p>{cleanNextAction(meta.nextAction ?? "", graph)}</p>
        </div>
      </div>
      <div className="reliability-metrics" aria-label="Reliability metrics">
        {metrics.map((metric) => (
          <span className="metric-chip" key={metric.label}>
            <b>{metric.value}</b>
            {metric.label}
          </span>
        ))}
        <button className="method-link" type="button" onClick={() => setHelpOpen((open) => !open)}>
          {helpOpen ? "Hide method" : "How this was checked"}
        </button>
      </div>
      {helpOpen && <ReliabilityHelpDrawer graph={graph} />}
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
  const sections: Array<{ title: ReportTab; defaultOpen?: boolean }> = [
    { title: "Issues", defaultOpen: answerMeta(graph).verdict === "do_not_rely" },
    { title: "Evidence" },
    { title: "Consistency" },
    { title: "Methods" },
  ];
  return (
    <div className="answer-details">
      {sections.map((section) => (
        <details data-reliability-section key={section.title} onToggle={handleDetailToggle} open={section.defaultOpen}>
          <summary>
            <span>{section.title}</span>
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
  const siblings = details.parentElement?.querySelectorAll<HTMLDetailsElement>(":scope > details[data-reliability-section]");
  siblings?.forEach((sibling) => {
    if (sibling !== details) sibling.open = false;
  });
  window.requestAnimationFrame(() => {
    details.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
}

function ReliabilityHelpDrawer({ graph }: { graph: ReliabilityGraph }) {
  const rows = [
    {
      title: "Final decision",
      meaning: "The product's practical call for this answer: rely, use with caution, or do not rely.",
      interpret: "Start here. If the decision is caution or do not rely, read Issues before acting.",
      limit: "It is a decision aid, not proof that the answer is true.",
    },
    {
      title: "Evidence checks",
      meaning: "Answer claims are compared with retrieved web, URL, or file snippets.",
      interpret: "Supported claims raise trust; contradictions and missing evidence lower trust.",
      limit: "Search can miss better sources, and weak sources can still be wrong.",
    },
    {
      title: "Sample agreement",
      meaning: "The app asks for multiple candidate answers and checks whether they converge on the same meaning.",
      interpret: `Current agreement: ${formatPercent(graph.features.semantic_stability ?? graph.disagreement.semantic_stability)}.`,
      limit: "Model self-agreement is useful risk evidence, not independent verification.",
    },
    {
      title: "Score",
      meaning: "A benchmark-tuned 0-100 risk-ranking signal.",
      interpret: graph.score_caps.length > 0 ? `The score was capped by ${graph.score_caps.length} risk rule${graph.score_caps.length === 1 ? "" : "s"}.` : "Use it to compare relative risk, not as a truth percentage.",
      limit: "It is not a probability, confidence score, or guarantee.",
    },
  ];
  return (
    <div className="help-drawer">
      <div className="help-drawer-header">
        <h3>How this was checked</h3>
        <p>Plain-language guide to the reliability summary above.</p>
      </div>
      <div className="help-grid">
        {rows.map((row) => (
          <article key={row.title}>
            <h4>{row.title}</h4>
            <p>
              <strong>Means:</strong> {row.meaning}
            </p>
            <p>
              <strong>Read it as:</strong> {row.interpret}
            </p>
            <p>
              <strong>Limit:</strong> {row.limit}
            </p>
          </article>
        ))}
      </div>
    </div>
  );
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

function reliabilityMetrics(graph: ReliabilityGraph): Array<{ label: string; value: string }> {
  const external = externalEvidence(graph);
  const groupedSources = groupedEvidence(external);
  const checkedAssessments = graph.claim_assessments.filter((assessment) => !["not_checkable", "unassessed"].includes(claimRelation(assessment)));
  const supported = checkedAssessments.filter((assessment) => {
    const relation = claimRelation(assessment);
    return relation === "supported" || relation === "partially_supported";
  }).length;
  return [
    { label: "sources", value: String(groupedSources.length) },
    { label: "claims checked", value: String(checkedAssessments.length) },
    { label: "supported", value: `${supported}/${checkedAssessments.length || graph.claim_assessments.length || graph.claims.length || 0}` },
    { label: "sample agreement", value: formatPercent(graph.features.semantic_stability ?? graph.disagreement.semantic_stability) },
  ];
}

function scoreStatus(graph: ReliabilityGraph): string {
  if (graph.score_caps.length > 0) return "Capped by risk signals";
  if (graph.answer.calibration_status === "benchmark_tuned_diagnostic") return "Benchmark-tuned risk signal";
  if (graph.answer.calibration_status === "local_calibration") return "Locally calibrated risk signal";
  return "Risk-ranking signal";
}

function reliabilityOneLine(graph: ReliabilityGraph): string {
  const meta = answerMeta(graph);
  const evidence = shortText(meta.evidenceStatus ?? "Evidence status was not returned.", 150);
  const uncertainty = shortText(meta.uncertainty ?? "Main uncertainty was not returned.", 150);
  if (meta.verdict === "do_not_rely") return `${evidence} Main risk: ${uncertainty}`;
  if (meta.verdict === "rely") return `${evidence} Remaining uncertainty: ${uncertainty}`;
  return `${evidence} Check: ${uncertainty}`;
}

function cleanNextAction(nextAction: string, graph: ReliabilityGraph): string {
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

function claimRiskRank(assessment: ClaimAssessment | undefined, checkability?: string): number {
  const relation = claimRelation(assessment, checkability);
  if (relation === "contradicted") return 0;
  if (relation === "not_found" || relation === "insufficient_evidence") return 1;
  if (relation === "partially_supported") return 2;
  if (relation === "unassessed") return 3;
  if (relation === "not_checkable") return 4;
  if (relation === "supported") return 5;
  return 3;
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

function methodLabel(assessment: ClaimAssessment | undefined, relation: string): string {
  if (relation === "not_checkable") return "not scored";
  if (assessment?.assessment_method === "provider_entailment_verifier") return "model + entailment";
  return assessment?.assessment_method ? formatStatus(assessment.assessment_method) : "unassessed";
}

function relationExplanation(relation: string): string {
  if (relation === "supported" || relation === "supports") return "A source snippet supports this claim.";
  if (relation === "partially_supported" || relation === "partially_supports") return "A source snippet supports part of this claim, but not the full wording.";
  if (relation === "contradicted" || relation === "contradicts") return "A source snippet conflicts with this claim.";
  if (relation === "not_checkable") return "This item is advice, framing, or interpretation rather than a source-checkable factual claim.";
  return "No source snippet was found that supports this claim.";
}

function evidenceLimitText(relation: string, matchCount: number): string {
  if (relation === "not_checkable") return "No source match is required for this non-scored item.";
  if (matchCount > 0) return `${matchCount} matched evidence item${matchCount === 1 ? "" : "s"} found.`;
  return "No matched source snippet was available for this claim.";
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

function externalEvidence(graph: ReliabilityGraph): EvidenceItem[] {
  return graph.evidence.filter((item) => item.source_type !== "system_trace" && item.source_type !== "internal_policy");
}

function groupedEvidence(evidence: EvidenceItem[]) {
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
    if (!existing) {
      groups.set(key, {
        key,
        title: item.source_title || item.source_url || "Untitled source",
        url: item.source_url,
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
