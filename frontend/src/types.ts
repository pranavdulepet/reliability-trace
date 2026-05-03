export type KeyState = "saved" | "env" | "missing" | "not_required";

export interface ProviderMetadata {
  provider: string;
  label: string;
  default_model: string | null;
  key_env_var: string | null;
  key_state: KeyState;
  capabilities: string[];
}

export interface ProviderKeyView {
  provider: string;
  fingerprint: string;
  status: string;
  created_at: string;
  last_used_at: string | null;
}

export interface RunCreate {
  question: string;
  provider: string;
  model: string | null;
  samples: number;
  max_cost_usd: number;
  use_live_provider: boolean;
}

export interface RunView extends RunCreate {
  run_id: string;
  status: string;
  created_at: string;
  completed_at: string | null;
  graph: ReliabilityGraph | null;
  error: string | null;
}

export interface DocumentView {
  document_id: string;
  title: string;
  source_url: string | null;
  source_type: string;
  content_sha256: string;
  created_at: string;
  chunk_count: number;
}

export interface DocumentMatch {
  chunk_id: string;
  document_id: string;
  text: string;
  title: string;
  source_url: string | null;
  source_type: string;
  relevance_score: number;
}

export interface BenchmarkReport {
  status: string;
  label_count: number;
  ece: number | null;
  brier: number | null;
  summary: string;
  buckets: Array<{
    range: string;
    count: number;
    avg_score: number;
    avg_correctness: number;
  }>;
  ablations: Array<{
    signal: string;
    avg_score_delta: number;
    run_count: number;
  }>;
}

export interface TraceSpan {
  span_id: string;
  run_id: string;
  type: string;
  status: string;
  input_summary: string;
  output_summary: string;
  tool: string;
  cost_usd: number;
  risk_flags: string[];
}

export interface CandidateAnswer {
  candidate_id: string;
  provider: string;
  model: string;
  prompt_variant: string;
  answer_text: string;
  semantic_cluster_id: string | null;
}

export interface Claim {
  claim_id: string;
  text: string;
  type: string;
  importance: string;
  checkability: string;
  risk_flags: string[];
}

export interface EvidenceItem {
  evidence_id: string;
  claim_id: string;
  source_title: string;
  source_url: string | null;
  source_date: string | null;
  source_type: string;
  snippet: string;
  support_relation: string;
  source_quality: string;
}

export interface ClaimAssessment {
  claim_id: string;
  status: string;
  support_score: number;
  explanation: string;
  evidence_ids: string[];
}

export interface Assumption {
  assumption_id: string;
  text: string;
  importance: string;
  evidence_status: string;
  would_change_recommendation_if_false: boolean;
  sensitivity_notes: string;
}

export interface DecisionAnalysis {
  applicable: boolean;
  alternatives: Array<{ name: string; utility: number }>;
  criteria: Array<{ name: string; weight: number }>;
  recommendation: string | null;
  decision_margin?: number;
  sensitivity_summary: string;
  label?: string;
}

export interface StressTest {
  test_type: string;
  answer_changed: boolean;
  new_evidence_introduced: boolean;
  unsupported_flip: boolean;
  impact_on_score: string;
  result: string;
}

export interface ReliabilityGraph {
  run: {
    run_id: string;
    question: string;
    question_type: string;
    provider: string;
    model: string | null;
    samples: number;
    max_cost_usd: number;
    use_live_provider: boolean;
  };
  answer: {
    final_answer: string;
    summary: string;
    recommendation: string | null;
    reliability_score: number;
    calibration_status: string;
    top_positive_signals: string[];
    top_negative_signals: string[];
    main_uncertainty: string;
    what_would_change_the_answer: string;
    recommended_user_action: string;
    unresolved_disagreements: string[];
  };
  claims: Claim[];
  evidence: EvidenceItem[];
  claim_assessments: ClaimAssessment[];
  assumptions: Assumption[];
  decision_analysis: DecisionAnalysis;
  disagreement: {
    candidate_answers: CandidateAnswer[];
    semantic_clusters: Array<{
      cluster_id: string;
      label: string;
      candidate_ids: string[];
      summary: string;
    }>;
    semantic_entropy: number;
    semantic_stability: number;
    minority_hypotheses: string[];
    accepted_rejected_dissent: string;
  };
  stress_tests: StressTest[];
  trace: TraceSpan[];
  calibration: {
    status: string;
    display: string;
    note: string;
  };
  causal_probe: {
    mode: string;
    available: boolean;
    reason: string;
    operations: string[];
    results: Array<{
      operation: string;
      answer_changed: boolean;
      similarity_to_baseline: number;
      unsupported_flip: boolean;
      result: string;
    }>;
  };
  features: Record<string, number>;
  score_caps: string[];
  export: {
    format: string;
    json_ready: boolean;
    contains_plaintext_provider_keys: boolean;
  };
}

export interface StreamEvent {
  type: "progress" | "completed" | "error";
  progress?: number;
  message: string;
  span?: TraceSpan;
  graph?: ReliabilityGraph;
  trace?: TraceSpan[];
}
