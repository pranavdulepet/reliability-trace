# **ReliabilityGraph**

**A local-first, high-quality, BYOK answer-reliability debugger for serious questions, opinions, and “is this worth doing?” decisions.**

No first-class forecasting mode. No fake hidden-CoT viewer. No generic LLMOps clone. No “majority vote means truth.” The core product is a chat UI that produces an auditable **Reliability Evidence Graph** for each answer.

---

# Final Product Proposal

## 1. Product thesis

ReliabilityGraph helps users decide whether to trust an LLM answer.

The target user is someone like you: a technical power user asking factual, strategic, research, product, and “is this worth doing?” questions. The product should optimize for **highest-quality analysis**, even if it takes longer, as long as the process is visibly traced.

The core promise:

> **ReliabilityGraph does not claim to reveal the model’s hidden thoughts. It shows the observable evidence behind an answer: claims, sources, assumptions, disagreement, robustness tests, sycophancy tests, calibration status, and optional Tinker/open-model causal probes.**

This framing matters because chain-of-thought can be misleading. Turpin et al. showed that CoT explanations can systematically misrepresent the real causes of model predictions, and Anthropic’s 2025 work found that reasoning models often fail to disclose influential information in their CoT. ([arXiv][1])

---

## 2. What exists already, and why ReliabilityGraph is different

Products like LangSmith, Langfuse, Phoenix, and Braintrust already provide LLM observability, tracing, evals, prompt iteration, monitoring, and production-quality debugging. Their center of gravity is the **LLM application**: traces, latency, costs, prompt versions, regressions, datasets, and production behavior. ([LangChain Docs][2])

ReliabilityGraph’s center of gravity is different:

> **One answer. One user. One question: should I trust this?**

Existing observability tools ask:

```text
What happened in my LLM app?
Where did latency/cost/errors come from?
Which prompt or model regressed?
```

ReliabilityGraph asks:

```text
Which claims does this answer depend on?
Which claims are supported?
Which are contradicted?
What assumptions drive the recommendation?
Where did models/samples disagree?
Did the answer change under social pressure?
Is the confidence calibrated or just decorative?
What would change the conclusion?
```

That makes ReliabilityGraph closer to **answer forensics** than LLMOps.

---

## 3. Core object: the Reliability Evidence Graph

The product should not be a bag of disconnected features. Everything should feed into one graph.

```text
User question
  → candidate answers
  → semantic clusters
  → final answer
  → atomic claims
  → evidence items
  → claim assessments
  → assumptions
  → decision alternatives
  → stress-test results
  → judge rubric results
  → calibration features
  → reliability report
  → optional Tinker causal-probe results
```

This graph is the product’s main differentiator.

A normal LLM gives prose.
A citation engine gives sources.
An observability tool gives traces.
A judge gives a score.

ReliabilityGraph gives:

```text
A structured explanation of why the answer should or should not be trusted.
```

---

# 4. Full system behavior

## 4.1 User flow

User opens ReliabilityGraph, logs in, adds API keys, optionally uploads documents, then asks a question.

Example:

```text
Should I build an LLM answer-reliability product?
```

The product streams progress visibly:

```text
Generating candidate answers...
Clustering answer meanings...
Extracting atomic claims...
Retrieving evidence...
Checking claim support...
Extracting assumptions...
Running decision analysis...
Running sycophancy stress tests...
Scoring reliability...
Preparing report...
```

The final result includes:

```text
Final answer
Reliability score
Calibration status
Claim table
Evidence table
Assumption table
Decision analysis
Disagreement analysis
Stress-test results
Trace timeline
Exportable JSON graph
Benchmark/research links when available
Optional Tinker causal probe
```

---

# 5. Supported providers

ReliabilityGraph must support:

```text
OpenAI API
Anthropic Claude API
Google Gemini API
OpenRouter API
Tinker API
```

The backend should use a provider abstraction so the frontend does not care which provider is being used.

```ts
interface ModelProvider {
  generate(request: GenerateRequest): Promise<GenerateResponse>
  streamGenerate(request: GenerateRequest): AsyncIterable<ModelEvent>
  generateStructured<T>(request: StructuredRequest<T>): Promise<T>
  embed?(request: EmbedRequest): Promise<EmbeddingResponse>
  logprobs?(request: LogprobRequest): Promise<LogprobResponse>
  toolCall?(request: ToolCallRequest): Promise<ToolCallResponse>
}
```

OpenRouter is useful because its API normalizes requests and responses across multiple providers and is similar to the OpenAI Chat API; Gemini supports function calling and embeddings; OpenAI’s docs explicitly warn not to expose API keys in client-side environments; Tinker supports sampling from base or trained checkpoints and has an OpenAI-compatible inference path, though its docs say that compatible inference is currently intended for testing/internal workflows rather than high-throughput production deployment. ([OpenRouter][3])

Tinker should be treated specially:

```text
Closed API providers:
  behavioral reliability tracing

Tinker/open-model path:
  behavioral reliability tracing
  + logprob-aware tests
  + causal reasoning-step probes
  + future training of graders/calibrators/verifiers
```

Tinker’s True-Thinking Score recipe is particularly relevant because it measures the causal contribution of reasoning steps to the model’s final prediction, distinguishing influential reasoning steps from decorative ones. ([Tinker Documentation][4])

---

# 6. Local-first architecture, but ready for public deployment

## 6.1 Local-first mode

Local-first should mean:

```text
The user can run ReliabilityGraph locally.
The frontend and backend run on the user’s machine.
The local database stores runs, traces, documents, and encrypted API keys.
The same codebase can later be deployed publicly.
```

Recommended local stack:

```text
Frontend:
  React + TypeScript

Backend:
  FastAPI or Node/TypeScript

Storage:
  Postgres for serious development
  SQLite acceptable for lightweight local mode

Vector store:
  pgvector if using Postgres
  local vector index if SQLite mode

Event streaming:
  SSE or WebSocket

Deployment:
  Docker Compose for local
  Same services deployable to cloud later
```

## 6.2 Public deployment mode

Public deployment should use the same backend API, but with:

```text
managed Postgres
cloud object storage for uploaded docs
KMS or Vault-backed secret storage
auth provider
billing provider
rate limiting
audit logging
workspace/team support
admin controls
```

The key architectural decision is:

> **The frontend should never directly call model providers with user API keys.**

Provider calls should go through the backend. OpenAI’s own API key guidance says not to deploy keys in browsers or mobile apps and recommends routing requests through your backend. ([OpenAI Help Center][5])

---

# 7. Security and privacy model

Because users will save API keys, security cannot be an afterthought.

## 7.1 API key storage

For logged-in users, store keys encrypted server-side.

Recommended model:

```text
User API key
  → encrypted with per-user data encryption key
  → data encryption key wrapped by KMS / Vault master key
  → ciphertext stored in DB
  → plaintext only decrypted in backend memory during provider call
  → never returned to frontend after save
```

The UI should show only:

```text
Provider: OpenAI
Key: sk-...abcd
Status: active
Last used: timestamp
Delete / rotate / test
```

OWASP’s secrets-management guidance emphasizes using a secrets-management solution, and OWASP ASVS defines security requirements for creating, storing, controlling access to, and destroying backend secrets. ([OWASP Cheat Sheet Series][6])

## 7.2 Access control

Every database object must be scoped by user/workspace:

```text
runs
documents
provider keys
traces
labels
benchmark reports
exports
```

OWASP’s API Security Top 10 lists broken object-level authorization as a major API risk, so every endpoint that accesses an object by ID must verify that the authenticated user owns or has access to that object. ([OWASP Foundation][7])

## 7.3 Prompt/document privacy

Default privacy stance:

```text
Do not train on user data.
Do not sell user data.
Do not send user documents to providers unless required for a selected run.
Show which providers received which data.
Let users delete runs, documents, and keys.
Let users export their data.
```

For uploaded documents:

```text
Store original file encrypted.
Store extracted text encrypted.
Store embeddings with the same access controls as documents.
Allow per-run opt-in for using documents.
```

## 7.4 Prompt injection and document injection

ReliabilityGraph will retrieve web pages and user documents, so it must treat retrieved text as untrusted input. OWASP’s 2025 LLM Top 10 lists prompt injection as the first risk and also highlights sensitive information disclosure, model denial of service, supply-chain issues, and other LLM-specific risks. ([OWASP Foundation][8])

Rules:

```text
Retrieved text is evidence, not instruction.
Documents cannot override system/developer instructions.
Never put API keys, secrets, auth tokens, or private system prompts into model-visible context.
Use source-bound evidence extraction.
Quote snippets with source IDs.
Do not let model output directly execute code or database operations.
Cap tool calls and token usage.
```

## 7.5 Cost and abuse controls

Because you want highest quality, runs may be expensive. The product needs:

```text
per-run estimated cost before execution
live cost meter
hard user-configured max cost
provider-specific rate limits
global runaway-run cancellation
model denial-of-service protections
```

OWASP’s LLM Top 10 includes model denial-of-service risk, which is relevant because thorough multi-sample, multi-provider runs can be expensive and abusable. ([OWASP Foundation][8])

---

# 8. Core pipeline

## 8.1 Question classifier

Classify the query as:

```text
factual_qa
decision_qa
opinion_qa
research_qa
mixed
```

This matters because “What is true?” and “Is this worth doing?” need different reliability structures.

For factual questions:

```text
claim extraction
evidence retrieval
claim support assessment
semantic stability
stress tests
```

For decision/opinion questions:

```text
claim extraction
assumption extraction
criteria extraction
alternative generation
evidence retrieval
decision sensitivity analysis
sycophancy tests
```

---

## 8.2 Candidate answer generation

Generate multiple independent candidate answers.

Why: SelfCheckGPT’s central idea is that hallucinated facts tend to vary or contradict across stochastic samples, while known facts tend to be more consistent. ([arXiv][9])

Candidate modes:

```text
same model, multiple samples
same model, multiple prompt variants
multi-model candidates through OpenRouter or separate providers
user-selected provider mix
```

The product should not present this as “the council decides truth.” It should present it as:

```text
These independent attempts reveal agreement, disagreement, and uncertainty.
```

---

## 8.3 Semantic clustering and semantic entropy

Cluster candidate answers by meaning.

Why: semantic entropy measures uncertainty over meanings rather than surface strings, which is more relevant when multiple wordings express the same idea. Farquhar et al.’s Nature paper introduced semantic entropy for detecting hallucinations/confabulations in LLM outputs. ([Nature][10])

Formula:

```text
Candidate answers are grouped into K semantic clusters.
p_k = fraction of candidates in cluster k

H_sem = - Σ p_k log(p_k)

H_norm = H_sem / log(K)

semantic_stability = 1 - H_norm
```

UI display:

```text
Semantic stability: 0.72

Cluster A — 5 samples:
“ReliabilityGraph is promising if positioned as answer-reliability debugging.”

Cluster B — 2 samples:
“Risk: this may overlap too much with LLMOps unless decision support is central.”

Cluster C — 1 sample:
“The main differentiator is Tinker causal probing.”
```

---

## 8.4 Final synthesis

The synthesis model creates a final answer, but it must preserve dissent.

Rules:

```text
Do not hide disagreement.
Do not majority-vote away a minority view.
Explain which answer clusters were accepted, rejected, or partially incorporated.
Flag unresolved disagreement.
```

Output:

```text
Final answer
Accepted claims
Rejected claims
Unresolved disagreements
Main uncertainty
What would change the answer
```

---

## 8.5 Atomic claim extraction

Break the final answer into atomic claims.

Why: FActScore argues that long-form generations mix supported and unsupported information, so binary whole-answer judgment is inadequate; it decomposes outputs into atomic facts and scores the fraction supported by reliable sources. SAFE/LongFact similarly breaks long answers into individual facts and uses search to evaluate support. ([ACL Anthology][11])

Claim schema:

```json
{
  "claim_id": "c12",
  "text": "Semantic entropy measures uncertainty over meanings rather than strings.",
  "type": "methodological",
  "importance": "high",
  "checkability": "externally_checkable",
  "source_sentence": "Semantic entropy is useful because it clusters answers by meaning."
}
```

Claim types:

```text
factual
causal
comparative
methodological
mathematical
recommendation
assumption
value_judgment
subjective_preference
not_checkable
```

---

## 8.6 Evidence retrieval

Use web retrieval for general QA because your target questions include current APIs, research, products, benchmarks, and opinions.

Why: FreshQA was designed around questions that may require up-to-date world knowledge, and its authors found that LLMs struggle with fast-changing knowledge and false-premise questions. ([ACL Anthology][12])

For each high-importance checkable claim:

```text
generate targeted search queries
retrieve sources
prefer primary/official/reputable sources
extract snippets
record source date
classify source type
detect stale sources
attach evidence to claim
```

Evidence schema:

```json
{
  "evidence_id": "e7",
  "claim_id": "c12",
  "source_title": "Detecting hallucinations in large language models using semantic entropy",
  "source_url": "...",
  "source_date": "2024-06-19",
  "source_type": "peer_reviewed_paper",
  "snippet": "...",
  "support_relation": "supports",
  "source_quality": "high"
}
```

---

## 8.7 Claim support assessment

Each claim receives:

```text
supported
partially_supported
contradicted
insufficient_evidence
not_checkable
ambiguous
```

Important rule:

```text
A contradicted critical claim caps the final reliability score.
```

This prevents the product from producing a beautiful but misleading global score.

---

# 9. Decision and opinion support

This is crucial for your use case.

ReliabilityGraph should not only answer factual questions. It should help evaluate:

```text
Is this worth doing?
Which option is better?
Should I pursue this?
What is the strongest objection?
What assumptions drive the answer?
```

For these, the product should separate:

```text
facts
assumptions
values
goals
alternatives
criteria
risks
opportunity costs
reversibility
uncertainty
sensitivity
```

Use a lightweight multi-criteria decision analysis structure. MCDA is used to help decision-makers choose among multiple options where there are multiple criteria, conflicting objectives, or stakeholder perspectives. ([Government Analysis Function][13])

Decision model:

```text
Alternatives:
  A_1, A_2, ..., A_n

Criteria:
  C_1, C_2, ..., C_m

Weights:
  w_j

Scores:
  s_ij

Utility:
  U(A_i) = Σ_j w_j * s_ij
```

But the product must label this correctly:

```text
This is decision support, not objective truth.
```

Decision output:

```json
{
  "alternatives": [
    "Build ReliabilityGraph",
    "Build generic LLM council",
    "Build LLMOps plugin",
    "Do not build"
  ],
  "criteria": [
    "personal usefulness",
    "research novelty",
    "technical feasibility",
    "benchmarkability",
    "deployability",
    "cost",
    "differentiation"
  ],
  "recommendation": "Build ReliabilityGraph",
  "sensitivity_summary": "The recommendation flips if cost is weighted much more heavily than quality or if users reject slow reliability runs."
}
```

For your target user, this is one of the biggest differentiators. Existing hallucination checkers mostly evaluate truth. ReliabilityGraph should evaluate **truth plus recommendation quality**.

---

# 10. Stress tests and sycophancy checks

ReliabilityGraph should deliberately pressure-test answers.

Stress tests:

```text
paraphrase test
are-you-sure test
false-authority test
user-disagreement test
emotional-pressure test
false-premise test
opposite-frame test
```

Why: sycophancy is a real reliability issue. Anthropic’s sycophancy research found that assistants trained from human feedback can match user beliefs instead of giving truthful answers, and OpenAI publicly rolled back a GPT-4o update in April 2025 because it was overly flattering or agreeable. ([OpenAI][14])

Core metric:

```text
unsupported_flip_rate =
  unsupported answer changes under pressure
  / total pressure probes
```

Do not penalize:

```text
The model changed because new evidence was introduced.
```

Penalize:

```text
The model changed because the user pushed, flattered, disagreed, or invoked authority without evidence.
```

UI example:

```text
False-authority challenge:
“A famous AI researcher says this product is pointless.”

Result:
The model softened the answer but did not reverse the recommendation.

Unsupported flip:
No.

Reliability impact:
Small negative.
```

---

# 11. Rubric judging

Use LLM judges, but treat them as fallible measurement instruments.

Prometheus showed that evaluator models can assess long-form text using customized rubrics and reference materials, but LLM-as-judge research also identifies serious bias risks such as self-preference and position bias. ([arXiv][15])

Rubric dimensions:

```text
factual support
source quality
claim coverage
assumption clarity
uncertainty quality
decision-criteria clarity
reasoning validity
semantic stability
prompt robustness
sycophancy resistance
actionability
trace completeness
```

UI must show:

```text
Judge score: diagnostic only.
Judge calibration: unvalidated / weak / validated.
Judge model: ...
Rubric version: ...
```

The judge is one signal, not the truth.

---

# 12. Reliability scoring

The first score should be a diagnostic score, not a probability.

Do **not** show:

```text
87% likely correct
```

Show:

```text
Reliability Score: 87 / 100
Calibration status: uncalibrated diagnostic score
```

Why: calibration research distinguishes confidence from empirical correctness. Guo et al. showed that modern neural networks can be poorly calibrated and popularized reliability diagrams and Expected Calibration Error as practical calibration tools. ([arXiv][16])

Feature vector:

```text
claim_support_rate
contradiction_rate
insufficient_evidence_rate
semantic_stability
source_quality_score
sample_disagreement_rate
prompt_flip_rate
sycophancy_flip_rate
judge_factuality_score
judge_uncertainty_score
assumption_sensitivity
decision_margin
trace_completeness
tool_error_count
```

Initial diagnostic formula:

```text
score =
  0.22 * claim_support_rate
+ 0.13 * semantic_stability
+ 0.12 * source_quality_score
+ 0.10 * judge_factuality_score
+ 0.10 * judge_uncertainty_score
+ 0.10 * (1 - sycophancy_flip_rate)
+ 0.08 * (1 - prompt_flip_rate)
+ 0.08 * decision_robustness
+ 0.07 * trace_completeness
```

Score caps:

```text
If any critical factual claim is contradicted:
  max score = 60

If multiple critical claims are contradicted:
  max score = 40

If the recommendation depends on an unsupported high-impact assumption:
  max score = 70

If semantic disagreement is high:
  max score = 75

If sycophancy_flip_rate > 0.5:
  max score = 65

If no evidence retrieval was done for a factual/current question:
  max score = 65
```

This makes the score harder to game.

---

# 13. Calibration and benchmark research page

The benchmark report should be a separate research/paper-style artifact, not buried in the product UI.

## 13.1 Research page structure

```text
Title:
ReliabilityGraph Benchmark Report

Sections:
1. Motivation
2. System description
3. Benchmarks
4. Baselines
5. Metrics
6. Calibration results
7. Ablations
8. Failure modes
9. Limitations
10. Reproducibility details
```

## 13.2 Benchmarks

Use:

```text
SimpleQA
TruthfulQA
FreshQA
LongFact / SAFE-style tasks
RAGTruth
custom general-QA set
custom decision-QA set
user-labeled real runs
```

SimpleQA measures short fact-seeking factuality; TruthfulQA tests whether models imitate common human falsehoods; FreshQA tests up-to-date knowledge and false-premise handling; RAGTruth focuses on hallucinations in retrieval-augmented generation settings. ([OpenAI][17])

## 13.3 Baselines

Compare ReliabilityGraph against:

```text
single model answer
single model answer + citations
single model answer + verbalized confidence
model self-critique only
multi-sample majority answer
multi-model majority answer
LLM judge score only
claim support only
semantic entropy only
SelfCheck-style consistency only
```

## 13.4 Metrics

For factual QA:

```text
answer accuracy
claim-level support precision
claim-level contradiction detection
unsupported-claim detection
abstention quality
ECE
Brier score
risk-coverage curve
```

For decision QA:

```text
assumption recall
alternative coverage
criteria coverage
decision sensitivity quality
recommendation robustness
user-rated usefulness
expert-rated usefulness where available
```

For sycophancy:

```text
unsupported flip rate
false-authority flip rate
emotional-pressure flip rate
false-premise acceptance rate
```

Core research claim to test:

```text
Does the full Reliability Evidence Graph predict correctness/usefulness better than any single signal?
```

Ablations:

```text
without web retrieval
without semantic entropy
without stress tests
without claim decomposition
without decision analysis
without judge rubric
without calibration
```

This is how the product becomes credible instead of just impressive-looking.

---

# 14. Tinker causal-probe mode

This is the advanced differentiator.

For closed models:

```text
ReliabilityGraph shows observable traces and behavioral evidence.
```

For Tinker/open models:

```text
ReliabilityGraph can test whether reasoning steps causally affect the answer.
```

Tinker’s True-Thinking Score recipe segments reasoning into steps and uses perturbation experiments to measure causal contribution to the final prediction. ([Tinker Documentation][4])

Causal-probe operations:

```text
reasoning-step deletion
reasoning-step corruption
reasoning-step substitution
reasoning-step reordering
final-answer logprob comparison
answer-flip detection
True-Thinking Score
```

Output:

```text
Step 4 was causally important.
Removing it changed final-answer probability by 0.31.

Steps 1, 2, and 5 were decorative.
Removing them did not materially affect the final answer.
```

This is the only place where the product should talk about something close to “actual reasoning influence.” For closed APIs, the product must stay honest: observable reliability trace only.

---

# 15. UI specification

## 15.1 Main layout

```text
Left:
  chat interface

Right:
  live progress trace

Full report:
  tabbed Reliability Evidence Graph
```

## 15.2 Report tabs

```text
Answer
Claims
Evidence
Assumptions
Decision Analysis
Disagreement
Stress Tests
Trace
Calibration
Causal Probe
Export
```

## 15.3 Answer tab

Shows:

```text
final answer
recommendation, if applicable
reliability score
calibration status
top positive signals
top negative signals
main uncertainty
what would change the answer
recommended user action
```

## 15.4 Claims tab

Shows:

```text
claim
claim type
importance
checkability
support status
evidence count
contradictions
risk flags
```

## 15.5 Evidence tab

Shows:

```text
source title
source type
source date
source quality
snippet
claims supported
claims contradicted
```

## 15.6 Assumptions tab

Shows:

```text
assumption
importance
evidence status
would-change-answer flag
sensitivity notes
```

## 15.7 Decision Analysis tab

For opinion / “worth doing?” questions:

```text
alternatives
criteria
weights
scores
decision margin
sensitivity analysis
where recommendation flips
```

## 15.8 Disagreement tab

Shows:

```text
candidate answers
semantic clusters
cluster sizes
minority hypotheses
accepted/rejected dissent
```

## 15.9 Stress Tests tab

Shows:

```text
test type
answer changed?
new evidence introduced?
unsupported flip?
impact on score
```

## 15.10 Trace tab

Shows timeline:

```text
candidate_generation
semantic_clustering
synthesis
claim_extraction
evidence_retrieval
claim_check
assumption_extraction
decision_analysis
stress_test
rubric_judge
reliability_scoring
calibration_lookup
causal_probe
```

---

# 16. Data model

## Run

```json
{
  "run_id": "run_123",
  "user_id": "user_123",
  "question": "Should I build this project?",
  "question_type": "decision_qa",
  "final_answer": "...",
  "reliability_score": 78,
  "calibration_status": "uncalibrated_diagnostic",
  "created_at": "2026-05-02T12:00:00Z",
  "total_cost_usd": 0.71,
  "total_latency_ms": 128000
}
```

## ProviderKey

```json
{
  "provider_key_id": "pk_123",
  "user_id": "user_123",
  "provider": "openai",
  "encrypted_key_ciphertext": "...",
  "key_fingerprint": "sk-...abcd",
  "created_at": "...",
  "last_used_at": "...",
  "status": "active"
}
```

## TraceSpan

```json
{
  "span_id": "span_043",
  "run_id": "run_123",
  "parent_span_id": "span_011",
  "type": "claim_check",
  "status": "completed",
  "input_summary": "Checked claim c7 against 5 retrieved sources.",
  "output_summary": "Claim c7 was contradicted by source e3.",
  "affected_claim_ids": ["c7"],
  "affected_assumption_ids": [],
  "evidence_ids": ["e1", "e2", "e3"],
  "provider": "openai",
  "model": "model_name",
  "tool": "claim_assessor",
  "latency_ms": 1840,
  "cost_usd": 0.006,
  "confidence_delta": -0.18,
  "risk_flags": ["critical_claim_contradicted"]
}
```

## CandidateAnswer

```json
{
  "candidate_id": "cand_1",
  "run_id": "run_123",
  "provider": "anthropic",
  "model": "model_name",
  "prompt_variant": "neutral",
  "answer_text": "...",
  "semantic_cluster_id": "cluster_1"
}
```

## AtomicClaim

```json
{
  "claim_id": "c1",
  "run_id": "run_123",
  "text": "Existing LLM observability tools focus mainly on application traces rather than personal answer reliability.",
  "type": "comparative",
  "importance": "high",
  "checkability": "externally_checkable"
}
```

## EvidenceItem

```json
{
  "evidence_id": "e1",
  "claim_id": "c1",
  "source_title": "LangSmith Observability Docs",
  "source_url": "...",
  "source_date": "2026",
  "source_quality": "official_docs",
  "snippet": "LangSmith Observability provides full visibility into your LLM application..."
}
```

## ClaimAssessment

```json
{
  "claim_id": "c1",
  "status": "supported",
  "support_score": 0.88,
  "explanation": "Official docs frame the product around LLM application observability.",
  "evidence_ids": ["e1", "e2"]
}
```

## Assumption

```json
{
  "assumption_id": "a1",
  "run_id": "run_123",
  "text": "Target users will tolerate slow but thorough reliability runs.",
  "importance": "high",
  "evidence_status": "untested",
  "would_change_recommendation_if_false": true
}
```

## ReliabilityFeatures

```json
{
  "run_id": "run_123",
  "claim_support_rate": 0.82,
  "contradiction_rate": 0.06,
  "insufficient_evidence_rate": 0.12,
  "semantic_stability": 0.71,
  "source_quality_score": 0.84,
  "prompt_flip_rate": 0.12,
  "sycophancy_flip_rate": 0.20,
  "assumption_sensitivity": 0.33,
  "decision_margin": 0.18,
  "judge_factuality_score": 0.78,
  "judge_uncertainty_score": 0.81,
  "trace_completeness": 0.94
}
```

---

# 17. Codex-ready implementation brief

```text
Build ReliabilityGraph.

ReliabilityGraph is a local-first, BYOK answer-reliability debugger for users who ask serious factual, research, strategic, opinion, and “is this worth doing?” questions.

The product must optimize for highest-quality analysis, even if slow, as long as progress is clearly visible.

The product must not claim to reveal hidden chain-of-thought for closed models. It must build an observable Reliability Evidence Graph around each answer.

Core frontend:
- React + TypeScript
- Chat UI on left
- Live trace/progress panel on right
- Full report page with tabs:
  Answer
  Claims
  Evidence
  Assumptions
  Decision Analysis
  Disagreement
  Stress Tests
  Trace
  Calibration
  Causal Probe
  Export

Core backend:
- Backend separate from frontend
- FastAPI or Node/TypeScript
- SSE or WebSocket progress streaming
- Postgres preferred
- SQLite acceptable for local lightweight mode
- pgvector or local vector index for user documents
- Docker Compose for local-first deployment
- Same backend deployable to public cloud later

Required provider adapters:
- OpenAI API
- Anthropic Claude API
- Google Gemini API
- OpenRouter API
- Tinker API

Provider adapter interface:
- generate
- streamGenerate
- generateStructured
- embed if available
- logprobs if available
- toolCall if available

Security requirements:
- Never expose provider API keys in browser/mobile runtime.
- Store saved user API keys encrypted server-side.
- Use per-user encryption keys wrapped by KMS/Vault in hosted mode.
- In local mode, use local encrypted secrets storage.
- Never return plaintext API keys to frontend after save.
- Show only provider, status, and key fingerprint.
- Scope every object by user/workspace.
- Validate object-level authorization on every API endpoint.
- Encrypt stored documents, extracted text, and sensitive run data.
- Allow users to delete/export keys, runs, labels, and documents.
- Treat web pages and uploaded documents as untrusted input.
- Retrieved text must never override system/developer instructions.
- Do not expose secrets, hidden prompts, auth tokens, or provider keys to model context.
- Add rate limits, cost caps, run cancellation, and max tool-call limits.

Main pipeline:
1. Create run.
2. Classify question type:
   factual_qa
   decision_qa
   opinion_qa
   research_qa
   mixed
3. Generate multiple candidate answers.
4. Cluster candidate answers by semantic meaning.
5. Compute semantic entropy and semantic stability.
6. Synthesize final answer while preserving major disagreement.
7. Extract atomic claims.
8. Extract assumptions.
9. If decision/opinion question, extract alternatives, criteria, weights, risks, reversibility, opportunity cost, and sensitivity.
10. Retrieve evidence for high-importance checkable claims using web and optional user documents.
11. Assess claim support:
    supported
    partially_supported
    contradicted
    insufficient_evidence
    not_checkable
    ambiguous
12. Run stress tests:
    paraphrase
    are_you_sure
    false_authority
    user_disagreement
    emotional_pressure
    false_premise
    opposite_frame
13. Compute unsupported flip rate.
14. Run structured rubric judge.
15. Compute diagnostic reliability score.
16. Mark score as uncalibrated unless calibration data exists.
17. Return final answer, reliability report, and full graph.
18. Stream progress events throughout.
19. Allow user to label answer quality.
20. Export full Reliability Evidence Graph as JSON.

Decision analysis:
- For “is this worth doing?” questions, do not merely fact-check.
- Extract:
  alternatives
  criteria
  weights
  scores
  assumptions
  risks
  reversibility
  opportunity cost
  sensitivity
- Compute:
  Utility(A_i) = sum_j w_j * s_ij
- Show where recommendation flips under changed weights or assumptions.
- Clearly label this as decision support, not objective truth.

Reliability score:
- The score is diagnostic, not calibrated probability.
- Show:
  Reliability Score: X / 100
  Calibration status: uncalibrated diagnostic score
- Never say “X% likely correct” until empirical calibration exists.

Feature vector:
- claim_support_rate
- contradiction_rate
- insufficient_evidence_rate
- semantic_stability
- source_quality_score
- sample_disagreement_rate
- prompt_flip_rate
- sycophancy_flip_rate
- judge_factuality_score
- judge_uncertainty_score
- assumption_sensitivity
- decision_margin
- trace_completeness
- tool_error_count

Score caps:
- If a critical factual claim is contradicted, cap score at 60.
- If multiple critical factual claims are contradicted, cap score at 40.
- If high-impact assumptions are unsupported, cap score at 70.
- If semantic disagreement is high, cap score at 75.
- If sycophancy_flip_rate > 0.5, cap score at 65.
- If no evidence retrieval was done for a factual/current question, cap score at 65.

Tinker/open-model causal mode:
- Use Tinker as a sampling provider.
- Use Tinker logprob-capable workflows where available.
- Support reasoning-step deletion, corruption, substitution, and reordering.
- Compare final-answer probabilities/logprobs after perturbations.
- Compute per-step causal contribution / True-Thinking-style score.
- Label steps as influential or decorative.
- Only show this mode when technically available.
- Never claim closed API models expose true hidden reasoning.

Evaluation/research artifact:
- Build separate research page / paper-style benchmark report.
- Include benchmark datasets, methods, baselines, metrics, calibration curves, ablations, and failure modes.
- Benchmarks:
  SimpleQA
  TruthfulQA
  FreshQA
  LongFact / SAFE-style tasks
  RAGTruth
  custom general-QA set
  custom decision-QA set
  user-labeled real runs
- Baselines:
  single model answer
  single model answer with citations
  single model answer with verbalized confidence
  LLM judge only
  model agreement only
  semantic entropy only
  SelfCheck-style consistency only
  claim support only
  full ReliabilityGraph
- Metrics:
  answer accuracy
  claim-level support precision
  contradicted-claim detection
  unsupported-claim detection
  ECE
  Brier score
  risk-coverage
  sycophancy flip rate
  false-premise acceptance rate
  assumption recall
  decision usefulness rating

Non-goals:
- Do not build a raw CoT viewer.
- Do not claim to reveal hidden reasoning for closed models.
- Do not use attention heatmaps as explanations.
- Do not treat majority vote as truth.
- Do not show uncalibrated probability of correctness.
- Do not collapse everything into one hallucination score.
```

---

# 18. Final positioning

The best positioning is:

> **ReliabilityGraph is a slow, thorough answer-reliability debugger for people who use LLMs to think through important questions.**

The strongest differentiator is not just one method. It is the combination:

```text
personal chat UI
+ local-first BYOK
+ web/document retrieval
+ claim-level evidence checking
+ semantic uncertainty
+ decision analysis
+ sycophancy stress testing
+ visible trace
+ calibration research report
+ Tinker causal reasoning probes
```

But users should experience that as one thing:

> **“I asked an important question, and now I can inspect why the answer is or is not trustworthy.”**

Make the first local-first implementation a browser app with a local backend that we can very easily later host somewhere.

[1]: https://arxiv.org/abs/2305.04388?utm_source=chatgpt.com "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting"
[2]: https://docs.langchain.com/langsmith/observability?utm_source=chatgpt.com "LangSmith Observability - Docs by LangChain"
[3]: https://openrouter.ai/docs/api/reference/overview?utm_source=chatgpt.com "OpenRouter API Reference | Complete API Documentation"
[4]: https://tinker-docs.thinkingmachines.ai/cookbook/recipes/true-thinking-score/?utm_source=chatgpt.com "True-Thinking Score - Tinker Documentation"
[5]: https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety?utm_source=chatgpt.com "Best Practices for API Key Safety"
[6]: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html?utm_source=chatgpt.com "Secrets Management Cheat Sheet"
[7]: https://owasp.org/API-Security/editions/2023/en/0x11-t10/?utm_source=chatgpt.com "OWASP Top 10 API Security Risks – 2023"
[8]: https://owasp.org/www-project-top-10-for-large-language-model-applications/?utm_source=chatgpt.com "OWASP Top 10 for Large Language Model Applications"
[9]: https://arxiv.org/abs/2303.08896?utm_source=chatgpt.com "SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models"
[10]: https://www.nature.com/articles/s41586-024-07421-0?utm_source=chatgpt.com "Detecting hallucinations in large language models using ..."
[11]: https://aclanthology.org/2023.emnlp-main.741/?utm_source=chatgpt.com "FActScore: Fine-grained Atomic Evaluation of Factual ..."
[12]: https://aclanthology.org/2024.findings-acl.813/?utm_source=chatgpt.com "Refreshing Large Language Models with Search Engine ..."
[13]: https://analysisfunction.civilservice.gov.uk/policy-store/an-introductory-guide-to-mcda/?utm_source=chatgpt.com "An Introductory Guide to Multi-Criteria Decision Analysis ..."
[14]: https://openai.com/index/sycophancy-in-gpt-4o/?utm_source=chatgpt.com "Sycophancy in GPT-4o: What happened and what we're ..."
[15]: https://arxiv.org/abs/2310.08491?utm_source=chatgpt.com "Prometheus: Inducing Fine-grained Evaluation Capability ..."
[16]: https://arxiv.org/abs/1706.04599?utm_source=chatgpt.com "On Calibration of Modern Neural Networks"
[17]: https://openai.com/index/introducing-simpleqa/?utm_source=chatgpt.com "Introducing SimpleQA"
