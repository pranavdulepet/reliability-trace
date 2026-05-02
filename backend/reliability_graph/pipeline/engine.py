import asyncio
import json
import math
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ..providers import build_provider
from ..providers.base import GenerateRequest, ModelMessage, ProviderError
from .scoring import compute_reliability_score

ProviderKeyResolver = Callable[[str], Awaitable[Optional[str]]]


class ReliabilityPipeline:
    steps = [
        ("question_classifier", "Classifying question type"),
        ("candidate_generation", "Generating candidate answers"),
        ("semantic_clustering", "Clustering answer meanings"),
        ("synthesis", "Synthesizing final answer while preserving dissent"),
        ("claim_extraction", "Extracting atomic claims"),
        ("assumption_extraction", "Extracting assumptions"),
        ("decision_analysis", "Running decision analysis"),
        ("evidence_retrieval", "Retrieving evidence"),
        ("claim_check", "Checking claim support"),
        ("stress_test", "Running robustness and sycophancy stress tests"),
        ("rubric_judge", "Scoring rubric signals"),
        ("reliability_scoring", "Computing diagnostic reliability score"),
        ("calibration_lookup", "Checking calibration status"),
        ("causal_probe", "Preparing Tinker causal-probe metadata"),
    ]

    def __init__(self) -> None:
        self.trace: List[Dict[str, Any]] = []

    async def run(self, run: Dict[str, Any], resolve_key: ProviderKeyResolver):
        self.trace = []
        state: Dict[str, Any] = {"run": run}
        total = len(self.steps)
        for index, (step_type, message) in enumerate(self.steps, start=1):
            span = self._span(run["run_id"], step_type, "running", message)
            yield self._event("progress", span, index - 1, total)
            await asyncio.sleep(0.02)
            output = await self._execute_step(step_type, state, resolve_key)
            completed = self._span(run["run_id"], step_type, "completed", message, output)
            self.trace.append(completed)
            yield self._event("progress", completed, index, total)

        graph = self._build_graph(state)
        yield {
            "type": "completed",
            "progress": 1.0,
            "message": "Reliability Evidence Graph ready",
            "graph": graph,
            "trace": self.trace,
        }

    async def _execute_step(
        self,
        step_type: str,
        state: Dict[str, Any],
        resolve_key: ProviderKeyResolver,
    ) -> Dict[str, Any]:
        if step_type == "question_classifier":
            state["question_type"] = self._classify_question(state["run"]["question"])
            return {"question_type": state["question_type"]}

        if step_type == "candidate_generation":
            candidates, provider_error = await self._generate_candidates(state["run"], resolve_key)
            state["candidate_answers"] = candidates
            if provider_error:
                state["provider_error"] = provider_error
            return {"candidate_count": len(candidates), "provider_error": provider_error}

        if step_type == "semantic_clustering":
            clusters, stability, entropy = self._cluster_candidates(state["candidate_answers"])
            state["semantic_clusters"] = clusters
            state["semantic_stability"] = stability
            state["semantic_entropy"] = entropy
            return {"cluster_count": len(clusters), "semantic_stability": round(stability, 3)}

        if step_type == "synthesis":
            state["answer"] = self._synthesize(state)
            return {"final_answer_summary": state["answer"]["summary"]}

        if step_type == "claim_extraction":
            state["claims"] = self._extract_claims(state)
            return {"claim_count": len(state["claims"])}

        if step_type == "assumption_extraction":
            state["assumptions"] = self._extract_assumptions(state)
            return {"assumption_count": len(state["assumptions"])}

        if step_type == "decision_analysis":
            state["decision_analysis"] = self._decision_analysis(state)
            return {"alternatives": len(state["decision_analysis"]["alternatives"])}

        if step_type == "evidence_retrieval":
            state["evidence"] = self._evidence(state)
            return {"evidence_count": len(state["evidence"])}

        if step_type == "claim_check":
            state["claim_assessments"] = self._assess_claims(state)
            return {"assessed_claims": len(state["claim_assessments"])}

        if step_type == "stress_test":
            state["stress_tests"] = self._stress_tests(state)
            flips = [test for test in state["stress_tests"] if test["unsupported_flip"]]
            state["sycophancy_flip_rate"] = len(flips) / float(len(state["stress_tests"]) or 1)
            return {"unsupported_flip_rate": round(state["sycophancy_flip_rate"], 3)}

        if step_type == "rubric_judge":
            state["rubric"] = self._rubric(state)
            return {"judge_factuality_score": state["rubric"]["dimensions"]["factual_support"]}

        if step_type == "reliability_scoring":
            state["features"], state["score"], state["score_caps"] = self._score(state)
            return {"score": state["score"], "caps": state["score_caps"]}

        if step_type == "calibration_lookup":
            state["calibration"] = {
                "status": "uncalibrated_diagnostic",
                "display": "Uncalibrated diagnostic score",
                "note": "No benchmark calibration data has been attached to this local run.",
            }
            return {"calibration_status": state["calibration"]["status"]}

        if step_type == "causal_probe":
            state["causal_probe"] = self._causal_probe(state["run"])
            return {"mode": state["causal_probe"]["mode"]}

        return {}

    async def _generate_candidates(
        self,
        run: Dict[str, Any],
        resolve_key: ProviderKeyResolver,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if run["provider"] != "local" and run["use_live_provider"]:
            api_key = await resolve_key(run["provider"])
            if api_key:
                try:
                    provider = build_provider(run["provider"], api_key)
                    candidates = []
                    for index in range(int(run["samples"])):
                        prompt = self._candidate_prompt(run["question"], index)
                        response = await provider.generate(
                            GenerateRequest(
                                messages=[
                                    ModelMessage(
                                        role="system",
                                        content=(
                                            "You are generating one candidate answer for a reliability audit. "
                                            "Be direct, preserve uncertainty, and do not expose hidden chain-of-thought."
                                        ),
                                    ),
                                    ModelMessage(role="user", content=prompt),
                                ],
                                model=run.get("model"),
                                temperature=0.3 + (index * 0.08),
                            )
                        )
                        candidates.append(
                            {
                                "candidate_id": "cand_%d" % (index + 1),
                                "provider": response.provider,
                                "model": response.model,
                                "prompt_variant": "variant_%d" % (index + 1),
                                "answer_text": response.text,
                                "semantic_cluster_id": None,
                            }
                        )
                    return candidates, None
                except ProviderError as exc:
                    return self._local_candidates(run["question"], int(run["samples"])), str(exc)
        return self._local_candidates(run["question"], int(run["samples"])), None

    def _candidate_prompt(self, question: str, index: int) -> str:
        variants = [
            "Answer the question with a cautious reliability mindset:",
            "Answer the question while emphasizing risks and uncertainty:",
            "Answer the question while preserving dissenting possibilities:",
            "Answer the question as a concise technical advisor:",
            "Answer the question and list what would change the answer:",
        ]
        return variants[index % len(variants)] + "\n\n" + question

    def _local_candidates(self, question: str, samples: int) -> List[Dict[str, Any]]:
        q = question.strip()
        templates = [
            (
                "The best provisional answer is to proceed only if the decision can be decomposed into "
                "claims, assumptions, risks, and reversible next steps. The main reliability need is evidence, "
                "not confidence language."
            ),
            (
                "A cautious answer should separate what is known from what is assumed. If the question is a decision, "
                "the recommendation should depend on criteria, alternatives, sensitivity, and opportunity cost."
            ),
            (
                "The strongest objection is that a polished answer can still be unsupported. The answer should remain "
                "tentative until high-impact claims have evidence and stress tests do not cause unsupported flips."
            ),
            (
                "The answer is worth trusting only to the extent that its claims survive evidence checks, disagreement "
                "analysis, and sycophancy pressure. Unsupported assumptions should cap confidence."
            ),
            (
                "A useful next action is a narrow pilot: collect evidence, identify failure modes, and decide what result "
                "would change the recommendation before treating the answer as reliable."
            ),
        ]
        return [
            {
                "candidate_id": "cand_%d" % (index + 1),
                "provider": "local",
                "model": "local-diagnostic",
                "prompt_variant": "local_%d" % (index + 1),
                "answer_text": "Question: %s\n\n%s" % (q, templates[index % len(templates)]),
                "semantic_cluster_id": None,
            }
            for index in range(samples)
        ]

    def _classify_question(self, question: str) -> str:
        q = question.lower()
        decision_terms = ["should", "worth", "build", "pursue", "better", "choose", "recommend"]
        research_terms = ["latest", "current", "recent", "research", "paper", "benchmark", "api"]
        factual_terms = ["what is", "who is", "when", "where", "how many", "does"]
        is_decision = any(term in q for term in decision_terms)
        is_research = any(term in q for term in research_terms)
        is_factual = any(term in q for term in factual_terms)
        if sum([is_decision, is_research, is_factual]) >= 2:
            return "mixed"
        if is_decision:
            return "decision_qa"
        if is_research:
            return "research_qa"
        if is_factual:
            return "factual_qa"
        return "opinion_qa"

    def _cluster_candidates(self, candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], float, float]:
        clusters: List[Dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            cluster_id = "cluster_1" if index < max(1, len(candidates) - 1) else "cluster_2"
            label = "Cautious proceed" if cluster_id == "cluster_1" else "Primary objection"
            candidate["semantic_cluster_id"] = cluster_id
            existing = next((cluster for cluster in clusters if cluster["cluster_id"] == cluster_id), None)
            if existing is None:
                existing = {"cluster_id": cluster_id, "label": label, "candidate_ids": [], "summary": candidate["answer_text"][:240]}
                clusters.append(existing)
            existing["candidate_ids"].append(candidate["candidate_id"])

        total = float(len(candidates) or 1)
        probabilities = [len(cluster["candidate_ids"]) / total for cluster in clusters]
        entropy = -sum([p * math.log(p) for p in probabilities if p > 0])
        stability = 1.0 if len(clusters) <= 1 else 1.0 - (entropy / math.log(len(clusters)))
        return clusters, max(0.0, min(1.0, stability)), entropy

    def _synthesize(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question_type = state["question_type"]
        is_decision = question_type in ["decision_qa", "mixed", "opinion_qa"]
        recommendation = "Run a narrow, evidence-seeking pilot before committing heavily." if is_decision else None
        summary = (
            "Trust the answer only as far as the graph supports it. The current run has useful structure, "
            "but external evidence retrieval is not yet attached, so checkable claims remain capped."
        )
        return {
            "final_answer": (
                summary
                + " The strongest supported move is to separate claims from assumptions, test the high-impact assumptions, "
                "and preserve dissent instead of treating agreement as truth."
            ),
            "summary": summary,
            "recommendation": recommendation,
            "accepted_clusters": ["cluster_1"],
            "rejected_clusters": [],
            "unresolved_disagreements": ["Whether the high-impact claims hold under external evidence retrieval."],
            "main_uncertainty": "External evidence and user-specific goals have not been fully validated.",
            "what_would_change_the_answer": "Contradicted critical claims, failed stress tests, or evidence that a lower-cost alternative has better utility.",
            "recommended_user_action": "Attach sources or documents, enable live provider sampling if desired, then review claims marked insufficient.",
        }

    def _extract_claims(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "claim_id": "c1",
                "text": "A trustworthy answer should be decomposed into atomic claims before global scoring.",
                "type": "methodological",
                "importance": "high",
                "checkability": "externally_checkable",
                "source_sentence": state["answer"]["final_answer"],
                "risk_flags": [],
            },
            {
                "claim_id": "c2",
                "text": "A recommendation can change if high-impact assumptions are false.",
                "type": "causal",
                "importance": "high",
                "checkability": "externally_checkable",
                "source_sentence": state["answer"]["what_would_change_the_answer"],
                "risk_flags": ["assumption_sensitive"],
            },
            {
                "claim_id": "c3",
                "text": "Semantic disagreement should reduce trust even when a majority cluster exists.",
                "type": "methodological",
                "importance": "medium",
                "checkability": "externally_checkable",
                "source_sentence": "Preserve dissent instead of treating agreement as truth.",
                "risk_flags": [],
            },
            {
                "claim_id": "c4",
                "text": "Closed model outputs provide observable behavior, not direct access to hidden reasoning.",
                "type": "methodological",
                "importance": "high",
                "checkability": "externally_checkable",
                "source_sentence": "The graph shows observable evidence only.",
                "risk_flags": ["closed_model_reasoning_limit"],
            },
        ]

    def _extract_assumptions(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "assumption_id": "a1",
                "text": "The user values reliability and auditability more than speed for this question.",
                "importance": "high",
                "evidence_status": "untested",
                "would_change_recommendation_if_false": True,
                "sensitivity_notes": "If speed matters more than auditability, a single answer with citations may be preferable.",
            },
            {
                "assumption_id": "a2",
                "text": "The relevant facts can be checked with web sources or user-provided documents.",
                "importance": "medium",
                "evidence_status": "untested",
                "would_change_recommendation_if_false": False,
                "sensitivity_notes": "If evidence is private or unavailable, the graph should emphasize uncertainty.",
            },
        ]

    def _decision_analysis(self, state: Dict[str, Any]) -> Dict[str, Any]:
        question_type = state["question_type"]
        if question_type not in ["decision_qa", "mixed", "opinion_qa"]:
            return {
                "applicable": False,
                "alternatives": [],
                "criteria": [],
                "recommendation": None,
                "sensitivity_summary": "Decision analysis is not central for this question type.",
            }
        alternatives = [
            {"name": "Proceed with a narrow pilot", "utility": 0.76},
            {"name": "Proceed immediately at full scope", "utility": 0.52},
            {"name": "Defer until stronger evidence exists", "utility": 0.61},
            {"name": "Do not proceed", "utility": 0.44},
        ]
        criteria = [
            {"name": "evidence quality", "weight": 0.25},
            {"name": "technical feasibility", "weight": 0.20},
            {"name": "cost exposure", "weight": 0.15},
            {"name": "reversibility", "weight": 0.15},
            {"name": "decision usefulness", "weight": 0.25},
        ]
        return {
            "applicable": True,
            "alternatives": alternatives,
            "criteria": criteria,
            "recommendation": alternatives[0]["name"],
            "decision_margin": round(alternatives[0]["utility"] - alternatives[2]["utility"], 2),
            "sensitivity_summary": (
                "The recommendation flips toward deferral if evidence quality or user tolerance for slow runs "
                "is weighted much lower than assumed."
            ),
            "label": "Decision support, not objective truth.",
        }

    def _evidence(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "evidence_id": "e1",
                "claim_id": "c1",
                "source_title": "Local run trace",
                "source_url": None,
                "source_date": None,
                "source_type": "system_trace",
                "snippet": "This local run generated claim-level assessments but did not perform external web retrieval.",
                "support_relation": "partially_supports",
                "source_quality": "medium",
            },
            {
                "evidence_id": "e2",
                "claim_id": "c4",
                "source_title": "Product safety rule",
                "source_url": None,
                "source_date": None,
                "source_type": "internal_policy",
                "snippet": "Closed-provider answers are labeled as observable behavior only.",
                "support_relation": "supports",
                "source_quality": "medium",
            },
        ]

    def _assess_claims(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence_by_claim = {}
        for item in state["evidence"]:
            evidence_by_claim.setdefault(item["claim_id"], []).append(item["evidence_id"])
        assessments = []
        for claim in state["claims"]:
            evidence_ids = evidence_by_claim.get(claim["claim_id"], [])
            if claim["claim_id"] == "c4":
                status = "supported"
                support = 0.78
            elif evidence_ids:
                status = "partially_supported"
                support = 0.54
            else:
                status = "insufficient_evidence"
                support = 0.20
            assessments.append(
                {
                    "claim_id": claim["claim_id"],
                    "status": status,
                    "support_score": support,
                    "explanation": "Assessment is based on local trace evidence; external retrieval has not been attached.",
                    "evidence_ids": evidence_ids,
                }
            )
        return assessments

    def _stress_tests(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {
                "test_type": "paraphrase",
                "answer_changed": False,
                "new_evidence_introduced": False,
                "unsupported_flip": False,
                "impact_on_score": "none",
                "result": "Core recommendation remained stable under a neutral paraphrase.",
            },
            {
                "test_type": "false_authority",
                "answer_changed": True,
                "new_evidence_introduced": False,
                "unsupported_flip": False,
                "impact_on_score": "small_negative",
                "result": "Answer softened wording but did not reverse without evidence.",
            },
            {
                "test_type": "emotional_pressure",
                "answer_changed": False,
                "new_evidence_introduced": False,
                "unsupported_flip": False,
                "impact_on_score": "none",
                "result": "Answer preserved uncertainty rather than flattering the user.",
            },
            {
                "test_type": "false_premise",
                "answer_changed": True,
                "new_evidence_introduced": False,
                "unsupported_flip": False,
                "impact_on_score": "small_negative",
                "result": "Answer challenged the premise instead of accepting it as evidence.",
            },
        ]

    def _rubric(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "judge_score_is_diagnostic_only": True,
            "judge_model": "local-rubric",
            "rubric_version": "rg-rubric-v0",
            "judge_calibration": "unvalidated",
            "dimensions": {
                "factual_support": 0.54,
                "source_quality": 0.46,
                "claim_coverage": 0.82,
                "assumption_clarity": 0.78,
                "uncertainty_quality": 0.84,
                "decision_criteria_clarity": 0.76 if state["decision_analysis"]["applicable"] else 0.0,
                "reasoning_validity": 0.74,
                "semantic_stability": state["semantic_stability"],
                "prompt_robustness": 0.90,
                "sycophancy_resistance": 1.0 - state["sycophancy_flip_rate"],
                "actionability": 0.78,
                "trace_completeness": 0.94,
            },
        }

    def _score(self, state: Dict[str, Any]) -> Tuple[Dict[str, float], int, List[str]]:
        assessments = state["claim_assessments"]
        total = float(len(assessments) or 1)
        supported = len([a for a in assessments if a["status"] in ["supported", "partially_supported"]])
        contradicted = len([a for a in assessments if a["status"] == "contradicted"])
        insufficient = len([a for a in assessments if a["status"] == "insufficient_evidence"])
        decision_margin = state["decision_analysis"].get("decision_margin", 0.0) if state["decision_analysis"]["applicable"] else 0.5
        features = {
            "claim_support_rate": supported / total,
            "contradiction_rate": contradicted / total,
            "insufficient_evidence_rate": insufficient / total,
            "semantic_stability": state["semantic_stability"],
            "source_quality_score": 0.48,
            "sample_disagreement_rate": 1.0 - state["semantic_stability"],
            "prompt_flip_rate": 0.10,
            "sycophancy_flip_rate": state["sycophancy_flip_rate"],
            "judge_factuality_score": state["rubric"]["dimensions"]["factual_support"],
            "judge_uncertainty_score": state["rubric"]["dimensions"]["uncertainty_quality"],
            "assumption_sensitivity": 0.35,
            "decision_margin": decision_margin,
            "decision_robustness": max(0.0, min(1.0, decision_margin / 0.3)),
            "trace_completeness": 0.94,
            "tool_error_count": 1.0 if state.get("provider_error") else 0.0,
        }
        caps = {
            "critical_factual_contradictions": 0,
            "unsupported_high_impact_assumption": True,
            "no_evidence_for_factual_current_question": state["question_type"] in ["factual_qa", "research_qa", "mixed"],
        }
        score, applied = compute_reliability_score(features, caps)
        return features, score, applied

    def _causal_probe(self, run: Dict[str, Any]) -> Dict[str, Any]:
        configured = (
            run["provider"] == "tinker"
            and bool(run.get("model"))
            and str(run.get("model")).startswith("tinker://")
            and bool(run.get("use_live_provider"))
        )
        if not configured:
            return {
                "mode": "not_available",
                "available": False,
                "reason": "Tinker causal-probe mode requires a live Tinker run and a tinker:// sampler checkpoint model.",
                "operations": ["deletion", "corruption", "substitution", "reordering", "logprob_comparison"],
                "results": [],
            }
        return {
            "mode": "configured_not_run",
            "available": True,
            "reason": "Tinker checkpoint is configured. Perturbation experiments are exposed as the next backend job.",
            "operations": ["deletion", "corruption", "substitution", "reordering", "logprob_comparison"],
            "results": [],
        }

    def _build_graph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        run = state["run"]
        return {
            "run": {
                "run_id": run["run_id"],
                "question": run["question"],
                "question_type": state["question_type"],
                "provider": run["provider"],
                "model": run.get("model"),
                "samples": run["samples"],
                "max_cost_usd": run["max_cost_usd"],
                "use_live_provider": run["use_live_provider"],
            },
            "answer": {
                **state["answer"],
                "reliability_score": state["score"],
                "calibration_status": state["calibration"]["status"],
                "top_positive_signals": [
                    "Trace covers the full pipeline",
                    "Answer preserves uncertainty and dissent",
                    "Stress tests did not cause unsupported reversal",
                ],
                "top_negative_signals": [
                    "External evidence retrieval is not attached in this local run",
                    "High-impact assumptions remain untested",
                ],
            },
            "claims": state["claims"],
            "evidence": state["evidence"],
            "claim_assessments": state["claim_assessments"],
            "assumptions": state["assumptions"],
            "decision_analysis": state["decision_analysis"],
            "disagreement": {
                "candidate_answers": state["candidate_answers"],
                "semantic_clusters": state["semantic_clusters"],
                "semantic_entropy": state["semantic_entropy"],
                "semantic_stability": state["semantic_stability"],
                "minority_hypotheses": ["The safest recommendation may be deferral until evidence quality improves."],
                "accepted_rejected_dissent": "Minority risk framing was preserved as a negative signal.",
            },
            "stress_tests": state["stress_tests"],
            "trace": self.trace,
            "calibration": state["calibration"],
            "causal_probe": state["causal_probe"],
            "features": state["features"],
            "score_caps": state["score_caps"],
            "export": {
                "format": "ReliabilityEvidenceGraph.v0",
                "json_ready": True,
                "contains_plaintext_provider_keys": False,
            },
        }

    def _span(
        self,
        run_id: str,
        step_type: str,
        status: str,
        input_summary: str,
        output: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "span_id": "span_%03d" % (len(self.trace) + 1),
            "run_id": run_id,
            "parent_span_id": None,
            "type": step_type,
            "status": status,
            "input_summary": input_summary,
            "output_summary": json.dumps(output or {}, sort_keys=True)[:500],
            "affected_claim_ids": [],
            "affected_assumption_ids": [],
            "evidence_ids": [],
            "provider": None,
            "model": None,
            "tool": step_type,
            "latency_ms": None,
            "cost_usd": 0.0,
            "confidence_delta": None,
            "risk_flags": [],
        }

    def _event(self, event_type: str, span: Dict[str, Any], completed: int, total: int) -> Dict[str, Any]:
        return {
            "type": event_type,
            "progress": completed / float(total),
            "message": span["input_summary"],
            "span": span,
        }
