export type KeyState = "saved" | "env" | "missing" | "not_required";
export type SearchMode = "auto" | "always" | "off";

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
  provider?: string | null;
  model?: string | null;
  samples?: number;
  max_cost_usd?: number;
  use_live_provider?: boolean;
  conversation_id?: string | null;
  user_message_id?: string | null;
  prior_context?: Array<{ role: string; content: string }>;
  attachment_document_ids?: string[];
  search_mode?: SearchMode;
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

export interface ProviderPreference {
  provider: string | null;
  model: string | null;
  samples: number;
  max_cost_usd: number;
  updated_at: string | null;
}

export interface ProviderPreferenceResponse {
  preference: ProviderPreference;
  resolved: ProviderPreference | null;
}

export interface SearchKeyView {
  provider: "tavily";
  fingerprint: string | null;
  status: string;
  created_at: string | null;
  last_used_at: string | null;
  key_state: "saved" | "env" | "missing";
  key_env_var: string;
}

export interface SearchPreference {
  search_mode: SearchMode;
  max_results: number;
  updated_at: string | null;
}

export interface SearchPreferenceResponse {
  preference: SearchPreference;
  key: SearchKeyView;
}

export interface VerifierStatus {
  ready: boolean;
  provider: string;
  model: string;
  cache_dir: string | null;
  message: string;
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationMessage {
  message_id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  run_id: string | null;
  attachment_document_ids: string[];
  created_at: string;
  run: {
    run_id: string;
    status: string;
    error: string | null;
    graph: ReliabilityGraph | null;
  } | null;
}

export interface ConversationView extends ConversationSummary {
  messages: ConversationMessage[];
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

export interface AnswerCitation {
  citation_id: string;
  evidence_id: string | null;
  claim_id: string | null;
  title: string;
  url: string | null;
  source_type: string;
  snippet: string;
}

export interface CitationAnnotation {
  start_index: number;
  end_index: number;
  citation_ids: string[];
}

export interface ClaimAssessment {
  claim_id: string;
  status: string;
  relation?: "supported" | "partially_supported" | "contradicted" | "not_found";
  support_score: number;
  explanation: string;
  why?: string;
  source_limit?: string;
  evidence_ids: string[];
  assessment_method?: string;
  verifier?: string;
  provider_relation?: string | null;
  entailment_score?: number;
  contradiction_score?: number;
  neutral_score?: number;
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
  alternatives: Array<{ name: string; utility?: number; evidence_status?: string; basis?: string; risk?: string }>;
  criteria: Array<{ name: string; weight?: number; basis?: string }>;
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
    conversation_id?: string | null;
    attachment_document_ids?: string[];
    web_search_document_ids?: string[];
    question: string;
    question_type: string;
    provider: string;
    model: string | null;
    samples: number;
    max_cost_usd: number;
    use_live_provider: boolean;
    search_mode?: SearchMode;
    search_used?: boolean;
  };
  answer: {
    final_answer: string;
    summary: string;
    recommendation: string | null;
    reliability_score: number;
    calibration_status: string;
    verdict?: "rely" | "use_with_caution" | "do_not_rely";
    final_decision?: "rely" | "use_with_caution" | "do_not_rely";
    verdict_reason?: string;
    next_best_action?: string;
    evidence_status?: string;
    source_limitations?: string;
    citations?: AnswerCitation[];
    citation_annotations?: CitationAnnotation[];
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
  web_search?: {
    route: {
      route: "no_search" | "attachments_only" | "web_search" | "hybrid";
      search_mode: SearchMode;
      reason: string;
      query?: string | null;
      recency?: string | null;
    } | null;
    calls: Array<{
      query: string | null;
      result_count: number;
      selected_urls: string[];
      error: string | null;
      response_time: number;
      request_id?: string | null;
    }>;
    documents: DocumentView[];
  };
  calibration: {
    status: string;
    display: string;
    note: string;
    benchmark?: {
      label_count?: number;
      status?: string;
      summary?: string;
      [key: string]: unknown;
    };
    score_weights?: {
      source?: string;
      trained_at?: string | null;
      benchmark_scope?: string | null;
      [key: string]: unknown;
    };
  };
  perturbation_probe?: PerturbationProbe;
  causal_probe: PerturbationProbe;
  features: Record<string, number>;
  score_caps: string[];
  analysis_basis?: Array<{
    signal: string;
    method: string;
    research_lineage: string;
    limitation: string;
  }>;
  export: {
    format: string;
    json_ready: boolean;
    contains_plaintext_provider_keys: boolean;
  };
}

export interface PerturbationProbe {
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
}

export interface StreamEvent {
  type: "progress" | "answer_delta" | "answer_completed" | "completed" | "error";
  progress?: number;
  message: string;
  delta?: string;
  answer?: string;
  run_id?: string;
  code?: string;
  stage?: string;
  retryable?: boolean;
  span?: TraceSpan;
  graph?: ReliabilityGraph;
  trace?: TraceSpan[];
}
