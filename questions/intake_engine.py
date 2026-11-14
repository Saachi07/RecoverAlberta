"""
The adaptive intake engine.

This wraps the trained decision tree to do Akinator-style adaptive
questioning. At each step, given the answers so far, it:

  1. Runs Monte Carlo inference to get the predicted distribution over
     plans, treating unanswered features as random draws from their
     training-data marginals.
  2. If one plan already has probability >= CONFIDENCE_THRESHOLD, stops
     and returns the plan.
  3. Otherwise, picks the next question by expected information gain:
     for each unanswered question, simulates each possible answer,
     measures how much it would reduce the entropy of the prediction,
     and picks the question with the biggest expected drop.

State is held externally (in `answers` dicts you pass in), so the engine
is safe to share across requests in a Flask app — just instantiate it
once at startup.
"""

import pickle
from typing import Dict, List, Optional

import numpy as np

from questions import FEATURE_NAMES, QUESTIONS


CONFIDENCE_THRESHOLD = 0.80   # stop asking once we're this sure
MC_SAMPLES = 200              # Monte Carlo samples for partial-answer inference
EPS = 1e-12


class IntakeEngine:
    def __init__(
        self,
        model_path: str = "intake_model.pkl",
        data_path: str = "synthetic_data.npz",
        rng_seed: int = 42,
    ):
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)  # nosemgrep: python.lang.security.deserialization.pickle.avoid-pickle 
        data = np.load(data_path)
        self.X_train = data["X"]
        self.rng = np.random.default_rng(rng_seed)

        # Pre-compute marginal distribution for each feature.
        self.marginals: Dict[str, tuple] = {}
        for i, feat in enumerate(FEATURE_NAMES):
            values, counts = np.unique(self.X_train[:, i], return_counts=True)
            probs = counts / counts.sum()
            self.marginals[feat] = (values, probs)

        # Cache feature index lookup.
        self.feat_idx = {f: i for i, f in enumerate(FEATURE_NAMES)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict_distribution(self, answers: Dict[str, int]) -> np.ndarray:
        """
        Probability distribution over plans given the answers given so far.

        Unanswered features are filled in by drawing from their marginal
        distribution (estimated from the training data), then the model's
        predictions are averaged across MC_SAMPLES draws.
        """
        samples = np.zeros((MC_SAMPLES, len(FEATURE_NAMES)), dtype=np.int32)
        for i, feat in enumerate(FEATURE_NAMES):
            if feat in answers:
                samples[:, i] = answers[feat]
            else:
                values, probs = self.marginals[feat]
                samples[:, i] = self.rng.choice(values, size=MC_SAMPLES, p=probs)
        probs = self.model.predict_proba(samples)
        return probs.mean(axis=0)

    def next_question(self, answers: Dict[str, int]) -> Optional[dict]:
        """
        Return the next question to ask, or None if we're confident enough
        (or have run out of questions).
        """
        dist = self.predict_distribution(answers)
        if dist.max() >= CONFIDENCE_THRESHOLD:
            return None

        unanswered = self._unanswered_questions(answers)
        if not unanswered:
            return None

        current_entropy = self._entropy(dist)
        best_q, best_gain = None, -1.0
        for q in unanswered:
            gain = self._expected_info_gain(answers, q, current_entropy)
            if gain > best_gain:
                best_q, best_gain = q, gain
        return best_q

    def final_plan(self, answers: Dict[str, int]) -> tuple:
        """Return (plan_id, confidence) given the current answers."""
        dist = self.predict_distribution(answers)
        pid = int(np.argmax(dist))
        return pid, float(dist[pid])

    def record_answer(
        self, answers: Dict[str, int], question: dict, answer
    ) -> Dict[str, int]:
        """
        Mutate `answers` to incorporate the user's response to `question`.

        For single-select questions, `answer` is the chosen value (int).
        For multi-select, `answer` is a list of selected option values
        (or an empty list / None if the user selected nothing).
        """
        if question["type"] == "single":
            answers[question["feature"]] = int(answer)
        else:
            selected = set(answer) if answer else set()
            for feat in question["feature"]:
                answers[feat] = 1 if feat in selected else 0
        return answers

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _unanswered_questions(self, answers: Dict[str, int]) -> List[dict]:
        out = []
        for q in QUESTIONS:
            feats = q["feature"] if isinstance(q["feature"], list) else [q["feature"]]
            # A question is considered unanswered if any of its features
            # has not been set yet.
            if any(f not in answers for f in feats):
                out.append(q)
        return out

    def _entropy(self, dist: np.ndarray) -> float:
        p = dist[dist > 0]
        return float(-np.sum(p * np.log2(p + EPS)))

    def _expected_info_gain(
        self, answers: Dict[str, int], question: dict, current_entropy: float
    ) -> float:
        """
        How much does answering `question` reduce expected entropy?

        For single-select: iterate over each possible answer, weight by
        the conditional probability of that answer estimated from
        training data, and sum the resulting entropies.

        For multi-select: iterate over all 2^k combinations of the k
        binary features. With k <= 4, that's at most 16 combinations.
        """
        if question["type"] == "single":
            feat = question["feature"]
            values, conditional_probs = self._conditional(feat, answers)
            expected_entropy = 0.0
            for v, p in zip(values, conditional_probs):
                if p <= 0:
                    continue
                trial = dict(answers)
                trial[feat] = int(v)
                d = self.predict_distribution(trial)
                expected_entropy += p * self._entropy(d)
            return current_entropy - expected_entropy

        # multi-select
        feats = question["feature"]
        k = len(feats)
        expected_entropy = 0.0
        for combo in range(1 << k):
            trial = dict(answers)
            for i, f in enumerate(feats):
                trial[f] = (combo >> i) & 1
            # Estimate joint probability of this combo, conditional on
            # the answers we've already collected.
            p = self._joint_conditional(feats, trial, answers)
            if p <= 0:
                continue
            d = self.predict_distribution(trial)
            expected_entropy += p * self._entropy(d)
        return current_entropy - expected_entropy

    def _conditional(self, feat: str, answers: Dict[str, int]):
        """
        Estimate P(feat = v | answers) from the training data.

        Falls back to the unconditional marginal if no training rows
        match the given answers.
        """
        mask = self._row_mask(answers)
        if mask.sum() == 0:
            return self.marginals[feat]
        col = self.X_train[mask, self.feat_idx[feat]]
        values, counts = np.unique(col, return_counts=True)
        probs = counts / counts.sum()
        return values, probs

    def _joint_conditional(
        self,
        feats: List[str],
        full_assignment: Dict[str, int],
        prior_answers: Dict[str, int],
    ) -> float:
        """
        Estimate P(feats = full_assignment[feats] | prior_answers) from
        training data, with fallback to product of marginals.
        """
        mask = self._row_mask(prior_answers)
        if mask.sum() == 0:
            # Fall back to product of unconditional marginals.
            p = 1.0
            for f in feats:
                values, probs = self.marginals[f]
                vi = list(values).index(full_assignment[f])
                p *= float(probs[vi])
            return p

        # Intersect: rows matching prior + the full assignment.
        match = mask.copy()
        for f in feats:
            match &= self.X_train[:, self.feat_idx[f]] == full_assignment[f]
        return float(match.sum()) / float(mask.sum())

    def _row_mask(self, answers: Dict[str, int]) -> np.ndarray:
        """Boolean mask of training rows matching all given answers."""
        mask = np.ones(len(self.X_train), dtype=bool)
        for f, v in answers.items():
            mask &= self.X_train[:, self.feat_idx[f]] == v
        return mask
