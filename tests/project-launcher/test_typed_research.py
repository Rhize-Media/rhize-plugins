"""Behavioral checks for the bounded local typed-decision research runner."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("typed_research", ROOT / "evals/typed-decision/research.py")
RESEARCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESEARCH)


def case(case_id: str, group: str, label: bool, *, stratum: str = "normal") -> dict:
    return {"case_id": case_id, "group_id": group, "decision_type": "verification",
            "stratum": stratum, "label_source": "human-review-1", "adjudicated": True,
            "state": {"summary": f"synthetic-{case_id}"},
            "questions": {"needs_verification": {"type": "noul", "instructions": "Is more verification needed?"}},
            "labels": {"needs_verification": label}, "arm_a": {"needs_verification": False}}


class TypedResearchTests(unittest.TestCase):
    def test_research_requests_bounded_background_admission(self):
        from unittest.mock import patch
        request = {'model': 'typed-decisions', 'questions': {'q': {}}}
        result = {'routing': {'model': 'typed-decisions'}, 'answers': {'q': {}}}
        with patch.object(RESEARCH, 'post_local', return_value=(result, 125.0)) as transport:
            self.assertEqual(RESEARCH.local_call('http://127.0.0.1:8000', request, admission_wait_ms=2000), (result, 125.0))
        transport.assert_called_once_with('http://127.0.0.1:8000', '/v1/systemone', request, 20,
                                          admission_wait_ms=2000)

    def test_operational_call_keeps_default_admission(self):
        from unittest.mock import patch
        request = {'model': 'typed-decisions', 'questions': {'q': {}}}
        result = {'routing': {'model': 'typed-decisions'}, 'answers': {'q': {}}}
        with patch.object(RESEARCH, 'post_local', return_value=(result, 125.0)) as transport:
            RESEARCH.local_call('http://127.0.0.1:8000', request, timeout=0.8)
        transport.assert_called_once_with('http://127.0.0.1:8000', '/v1/systemone', request, 0.8,
                                          admission_wait_ms=0)

    def test_group_split_is_stable_and_disjoint(self):
        rows = [case("a", "same-task", True), case("b", "same-task", False), case("c", "other-task", True)]
        splits = RESEARCH.partition(rows, "fixed-seed")
        locations = {row["case_id"]: split for split, values in splits.items() for row in values}
        self.assertEqual(locations["a"], locations["b"])
        self.assertEqual(len(locations), 3)

    def test_prepare_separates_holdout_and_detects_changed_split(self):
        rows = [case(str(i), f"g{i}", i % 2 == 0) for i in range(8)]
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "split"
            manifest = RESEARCH.prepare_corpus(rows, "fixture", out)
            self.assertFalse(manifest["release_eligible"])
            train = RESEARCH.verified_split(out / "train.jsonl", manifest, "train")
            validation = RESEARCH.verified_split(out / "validation.jsonl", manifest, "validation")
            holdout = RESEARCH.verified_split(out / "holdout.jsonl", manifest, "holdout")
            self.assertEqual(len(train) + len(validation) + len(holdout), len(rows))
            self.assertEqual({row["group_id"] for row in train} & {row["group_id"] for row in holdout}, set())
            (out / "validation.jsonl").write_text(json.dumps(case("replacement", "new", True)) + "\n")
            with self.assertRaisesRegex(ValueError, "frozen manifest"):
                RESEARCH.verified_split(out / "validation.jsonl", manifest, "validation")

    def test_unadjudicated_or_duplicate_labels_fail(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "cases.jsonl"
            invalid = case("a", "a", True)
            invalid["adjudicated"] = False
            path.write_text(json.dumps(invalid) + "\n")
            with self.assertRaisesRegex(ValueError, "adjudicated"):
                RESEARCH.read_jsonl(path)
            valid = case("a", "a", True)
            path.write_text(json.dumps(valid) + "\n" + json.dumps(valid) + "\n")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                RESEARCH.read_jsonl(path)

    def test_critical_false_negative_and_arm_a_are_visible(self):
        rows = [case("a", "a", True, stratum="critical_safety"), case("b", "b", False)]
        candidate = {"id": "baseline", "model": "typed-decisions"}
        def call(_request):
            return {"answers": {"needs_verification": {"type": "noul", "noul": 0.1}},
                    "usage": {"input_tokens": 10, "output_tokens": 0}}, 12.0
        result = RESEARCH.evaluate(rows, candidate, call)
        self.assertEqual(result["critical_misses"], 1)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["usage"], {"input_tokens": 20, "output_tokens": 0})
        self.assertEqual(RESEARCH.arm_a_metrics(rows)["critical_misses"], 1)
        self.assertEqual(RESEARCH.arm_a_metrics([{k: v for k, v in rows[0].items() if k != "arm_a"}]), "unavailable")

    def test_choice_probabilities_receive_brier_score(self):
        row = case("choice", "choice-task", True)
        row["questions"] = {"route": {"type": "choice", "instructions": "Pick route",
                                     "criteria": {"verify": "Check", "continue": "Proceed"}}}
        row["labels"] = {"route": "verify"}
        row["arm_a"] = {"route": "continue"}
        def call(_request):
            return {"answers": {"route": {"type": "choice", "choice": "verify",
                                          "answer_confidence": 0.8,
                                          "probabilities": {"verify": 0.8, "continue": 0.2}}},
                    "usage": {"input_tokens": 7, "output_tokens": 0}}, 10.0
        result = RESEARCH.evaluate([row], {"id": "base", "model": "typed-decisions"}, call)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertAlmostEqual(result["brier_mean"], 0.04)

    def test_prepare_marks_release_ineligible_and_keeps_the_old_gate_informational(self):
        rows = [case(str(i), f"g{i}", i % 2 == 0) for i in range(8)]
        with tempfile.TemporaryDirectory() as root:
            manifest = RESEARCH.prepare_corpus(rows, "fixture", Path(root) / "split")
        self.assertIs(manifest["release_eligible"], False)
        self.assertIs(manifest["legacy_release_gate_met"], False)
        big = [case(str(i), f"g{i}", i % 2 == 0) for i in range(800)]
        with tempfile.TemporaryDirectory() as root:
            manifest = RESEARCH.prepare_corpus(big, "fixture", Path(root) / "split")
        self.assertIs(manifest["release_eligible"], False)   # only typed_promotion can grant eligibility
        self.assertIs(manifest["legacy_release_gate_met"], True)

    def test_prepare_can_materialize_tuning_splits_only(self):
        rows = [case(str(i), f"g{i}", True) for i in range(6)]
        assignments = {f"g{i}": ("train" if i % 2 else "validation") for i in range(6)}
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "split"
            manifest = RESEARCH.prepare_corpus(rows, "fixture", out, split_assignments=assignments,
                                               names=("train", "validation"))
            self.assertEqual(sorted(path.name for path in out.iterdir()), ["manifest.json", "train.jsonl", "validation.jsonl"])
            self.assertEqual(set(manifest["split_counts"]), {"train", "validation"})
            with self.assertRaisesRegex(ValueError, "invalid frozen split"):
                RESEARCH.prepare_corpus(rows, "fixture", Path(root) / "other",
                                        split_assignments={**assignments, "g0": "promotion"},
                                        names=("train", "validation"))

    def test_locked_holdout_requires_exact_saved_candidate_and_one_use(self):
        dataset = "data-hash"
        seed = "seed-hash"
        candidate = "candidate-hash"
        with self.assertRaisesRegex(ValueError, "recorded development keep"):
            RESEARCH.check_holdout_authority([], dataset, seed, candidate)
        ledger = [{"dataset_sha256": dataset, "seed_sha256": seed,
                   "candidate_sha256": candidate, "status": "keep"}]
        RESEARCH.check_holdout_authority(ledger, dataset, seed, candidate)
        ledger.append({"dataset_sha256": dataset, "status": "holdout"})
        with self.assertRaisesRegex(ValueError, "already used"):
            RESEARCH.check_holdout_authority(ledger, dataset, seed, candidate)


if __name__ == "__main__":
    unittest.main()
