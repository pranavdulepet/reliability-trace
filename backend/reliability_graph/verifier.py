import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .retrieval import support_relation


DEFAULT_NLI_REPO = "cross-encoder/nli-deberta-base"
DEFAULT_MODEL_FILE = "onnx/model.onnx"
DEFAULT_CACHE_DIR = Path(os.getenv("RG_NLI_MODEL_DIR", "data/models/nli-deberta-base"))


class VerifierUnavailable(RuntimeError):
    pass


@dataclass
class EntailmentResult:
    relation: str
    entailment_score: float
    contradiction_score: float
    neutral_score: float
    model: str


class EntailmentVerifier:
    name = "entailment_verifier"

    def status(self) -> Dict[str, Any]:
        raise NotImplementedError

    def verify(self, premise: str, hypothesis: str) -> EntailmentResult:
        raise NotImplementedError


class UnavailableEntailmentVerifier(EntailmentVerifier):
    name = "unavailable"

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def status(self) -> Dict[str, Any]:
        return {
            "ready": False,
            "provider": "onnxruntime",
            "model": DEFAULT_NLI_REPO,
            "cache_dir": str(DEFAULT_CACHE_DIR),
            "message": self.reason,
        }

    def verify(self, premise: str, hypothesis: str) -> EntailmentResult:
        del premise, hypothesis
        raise VerifierUnavailable(self.reason)


class OnnxEntailmentVerifier(EntailmentVerifier):
    name = "onnx_nli"

    def __init__(self, model_dir: Path = DEFAULT_CACHE_DIR) -> None:
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / "model.onnx"
        self.tokenizer_path = self.model_dir / "tokenizer.json"
        self.config_path = self.model_dir / "config.json"
        self._session = None
        self._tokenizer = None
        self._labels: Dict[int, str] = {}
        self._load_error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        ready, message = self._is_ready()
        return {
            "ready": ready,
            "provider": "onnxruntime",
            "model": DEFAULT_NLI_REPO,
            "cache_dir": str(self.model_dir),
            "message": message,
        }

    def verify(self, premise: str, hypothesis: str) -> EntailmentResult:
        ready, message = self._is_ready()
        if not ready:
            raise VerifierUnavailable(message)
        session, tokenizer = self._load()
        encoded = tokenizer.encode(premise, hypothesis)
        input_ids = encoded.ids[:512]
        attention_mask = encoded.attention_mask[:512]
        type_ids = encoded.type_ids[:512]
        feed = {}
        for model_input in session.get_inputs():
            name = model_input.name
            if name == "input_ids":
                feed[name] = _int64_batch(input_ids)
            elif name == "attention_mask":
                feed[name] = _int64_batch(attention_mask)
            elif name == "token_type_ids":
                feed[name] = _int64_batch(type_ids or [0] * len(input_ids))
        if "input_ids" not in feed or "attention_mask" not in feed:
            raise VerifierUnavailable("NLI model inputs are not compatible with the verifier.")
        logits = session.run(None, feed)[0][0]
        probabilities = _softmax([float(value) for value in logits])
        by_label = {self._label(index): probabilities[index] for index in range(len(probabilities))}
        contradiction = by_label.get("contradiction", 0.0)
        entailment = by_label.get("entailment", 0.0)
        neutral = by_label.get("neutral", max(0.0, 1.0 - contradiction - entailment))
        if contradiction >= 0.55 and contradiction >= entailment:
            relation = "contradicted"
        elif entailment >= 0.65 and entailment >= contradiction:
            relation = "supported"
        else:
            relation = "partially_supported"
        return EntailmentResult(
            relation=relation,
            entailment_score=round(entailment, 4),
            contradiction_score=round(contradiction, 4),
            neutral_score=round(neutral, 4),
            model=DEFAULT_NLI_REPO,
        )

    def _is_ready(self) -> tuple[bool, str]:
        if not self.model_path.exists():
            return False, "NLI verifier model is missing. Run `python scripts/setup_nli_verifier.py`."
        if not self.tokenizer_path.exists():
            return False, "NLI verifier tokenizer is missing. Run `python scripts/setup_nli_verifier.py`."
        try:
            import numpy  # noqa: F401
            import onnxruntime  # noqa: F401
            import tokenizers  # noqa: F401
        except Exception as exc:
            return False, "NLI verifier dependencies are missing: %s" % exc
        if self._load_error:
            return False, self._load_error
        return True, "NLI verifier is ready."

    def _load(self):
        if self._session is not None and self._tokenizer is not None:
            return self._session, self._tokenizer
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
            self._tokenizer = Tokenizer.from_file(str(self.tokenizer_path))
            self._labels = self._load_labels()
        except Exception as exc:
            self._load_error = "NLI verifier failed to load: %s" % exc
            raise VerifierUnavailable(self._load_error) from exc
        return self._session, self._tokenizer

    def _load_labels(self) -> Dict[int, str]:
        if not self.config_path.exists():
            return {0: "contradiction", 1: "entailment", 2: "neutral"}
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {0: "contradiction", 1: "entailment", 2: "neutral"}
        raw = data.get("id2label") or {}
        labels = {}
        for key, value in raw.items():
            try:
                labels[int(key)] = str(value).lower()
            except (TypeError, ValueError):
                continue
        return labels or {0: "contradiction", 1: "entailment", 2: "neutral"}

    def _label(self, index: int) -> str:
        label = self._labels.get(index, "").lower()
        if "contrad" in label:
            return "contradiction"
        if "entail" in label:
            return "entailment"
        if "neutral" in label:
            return "neutral"
        defaults = {0: "contradiction", 1: "entailment", 2: "neutral"}
        return defaults.get(index, "neutral")


class FixtureEntailmentVerifier(EntailmentVerifier):
    name = "fixture_nli"

    def status(self) -> Dict[str, Any]:
        return {
            "ready": True,
            "provider": "fixture",
            "model": "fixture-entailment",
            "cache_dir": None,
            "message": "Fixture verifier is ready for tests and offline evals.",
        }

    def verify(self, premise: str, hypothesis: str) -> EntailmentResult:
        relation = support_relation(hypothesis, premise)
        if relation == "contradicts":
            return EntailmentResult("contradicted", 0.05, 0.9, 0.05, "fixture-entailment")
        if relation == "supports":
            return EntailmentResult("supported", 0.9, 0.03, 0.07, "fixture-entailment")
        return EntailmentResult("partially_supported", 0.35, 0.05, 0.6, "fixture-entailment")


def build_entailment_verifier() -> EntailmentVerifier:
    verifier = OnnxEntailmentVerifier()
    ready, message = verifier._is_ready()
    if ready:
        return verifier
    return UnavailableEntailmentVerifier(message)


def _int64_batch(values: List[int]):
    import numpy as np

    return np.array([values], dtype=np.int64)


def _softmax(values: List[float]) -> List[float]:
    peak = max(values) if values else 0.0
    exps = [math.exp(value - peak) for value in values]
    total = sum(exps) or 1.0
    return [value / total for value in exps]
