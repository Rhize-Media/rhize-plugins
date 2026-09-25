"""Contract tests for the project-local GSD typed decision client."""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "project-launcher/scripts/typed_decision.py"
SPEC = importlib.util.spec_from_file_location("typed_decision", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@contextmanager
def provider_server(answer_choice="ready", malformed=False, seen=None, routed_model=None):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/v1/systemone":
                self.send_error(404)
                return
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if seen is not None:
                seen.append(request)
            result = {"model": "fixture", "answers": {}, "usage": {"input_tokens": 12, "output_tokens": 2}}
            if routed_model is not None:
                result["routing"] = {"model": routed_model, "repo": f"fixture/{routed_model}"}
            for name, question in request["questions"].items():
                if question["type"] == "noul":
                    result["answers"][name] = {"type": "noul", "noul": 0.9 if name == "needs_verification" else 0.1}
                else:
                    result["answers"][name] = {
                        "type": "choice", "choice": answer_choice, "confidence": 0.95,
                        "probabilities": {key: 0.95 if key == answer_choice else 0.05 for key in question["criteria"]},
                    }
            if malformed:
                result["answers"] = {}
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


class TypedDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        path = self.project / ".planning/config.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"workflow": {"verifier": True}, "agent_skills": {"gsd-planner": ["skills/existing"]}}))

    def tearDown(self):
        self.temp.cleanup()

    def test_install_merges_config_and_copies_self_contained_runtime(self):
        MODULE.install(self.project)
        MODULE.install(self.project)
        config = json.loads((self.project / ".planning/config.json").read_text())
        self.assertEqual(config["workflow"], {"verifier": True})
        self.assertEqual(config["agent_skills"]["gsd-planner"], ["skills/existing", MODULE.SKILL])
        self.assertTrue((self.project / MODULE.CLIENT).is_file())
        self.assertTrue((self.project / MODULE.SKILL / "SKILL.md").is_file())
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertEqual(len(settings["hooks"]["SubagentStart"]), 1)
        self.assertEqual(len(settings["hooks"]["SubagentStop"]), 1)
        self.assertEqual((self.project / ".gitignore").read_text(), "/.planning/decision-layer/receipts.jsonl\n")
        self.assertEqual(MODULE.status(self.project)["status"], "blocked")

    def test_invalid_settings_preflight_does_not_modify_config(self):
        settings_path = self.project / ".claude/settings.json"
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text('{"hooks":{"SubagentStop":"invalid"}}')
        before = (self.project / ".planning/config.json").read_text()
        with self.assertRaisesRegex(MODULE.DecisionError, "must be an array"):
            MODULE.install(self.project)
        self.assertEqual((self.project / ".planning/config.json").read_text(), before)
        self.assertFalse((self.project / MODULE.CLIENT).exists())

    def test_probe_then_advisory_decision_produces_privacy_safe_receipts(self):
        MODULE.install(self.project)
        request = {"state": "phase secret-free summary", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with provider_server(routed_model="typed-decisions") as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base, "TYPESAFE_DEFAULT_MODEL": "typed-decisions", "RHIZE_DECISION_MODE": "advisory"}):
            probe = MODULE.decide(self.project, "launch-probe", request, probe=True)
            result = MODULE.decide(self.project, "gsd-planner", request)
            self.assertEqual(MODULE.status(self.project)["status"], "ready")
        self.assertEqual(probe["status"], "probe")
        self.assertEqual(result["recommendations"], {"next": "ready"})
        receipt_text = (self.project / MODULE.RECEIPTS).read_text()
        self.assertNotIn("phase secret-free summary", receipt_text)
        self.assertIn('"input_tokens": 12', receipt_text)

    def test_stop_hook_requires_this_agents_receipt(self):
        MODULE.install(self.project)
        payload = {"agent_type": "gsd-executor", "agent_id": "agent-123"}
        start = MODULE.hook(self.project, "SubagentStart", payload)
        self.assertIn("--agent-id agent-123", start["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload)["decision"], "block")
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with provider_server() as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}):
            MODULE.decide(self.project, "gsd-executor", request, agent_id="agent-other")
            self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload)["decision"], "block")
            MODULE.decide(self.project, "gsd-executor", request, agent_id="agent-123")
            self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload)["decision"], "block")
            MODULE.supervise(self.project, "gsd-executor", {"phase": "synthetic"}, agent_id="agent-123")
        self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload), {})

    def test_malformed_provider_answer_records_unavailable(self):
        MODULE.install(self.project)
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with provider_server(malformed=True) as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}):
            with self.assertRaises(MODULE.DecisionError):
                MODULE.decide(self.project, "launch-probe", request, probe=True)
        self.assertEqual(MODULE.status(self.project)["status"], "blocked")
        self.assertEqual(json.loads((self.project / MODULE.RECEIPTS).read_text())["outcome"], "unavailable")

    def test_local_model_is_explicit_and_mode_defaults_to_shadow(self):
        MODULE.install(self.project)
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        seen = []
        with provider_server(seen=seen) as base:
            with patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}, clear=True):
                result = MODULE.decide(self.project, "gsd-planner", request)
            with patch.dict(os.environ, {"TYPESAFE_BASE_URL": base, "TYPESAFE_DEFAULT_MODEL": "typed-decisions"}, clear=True):
                MODULE.decide(self.project, "gsd-planner", request)
            with patch.dict(os.environ, {"TYPESAFE_BASE_URL": base, "RHIZE_DECISION_MODE": "advisory"}, clear=True):
                advisory = MODULE.decide(self.project, "gsd-planner", request)
        self.assertNotIn("model", seen[0])
        self.assertEqual(seen[1]["model"], "typed-decisions")
        self.assertEqual(result["status"], "shadow")
        self.assertEqual(result["recommendations"], {})
        self.assertEqual(advisory["recommendations"], {"next": "ready"})

    def test_hosted_jev_keeps_default_model(self):
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        seen = []
        with provider_server(seen=seen) as base:
            with patch.object(MODULE, "endpoint", return_value=(base + "/v1/systemone", "", "jev")), patch.dict(os.environ, {}, clear=True):
                MODULE.call_provider(request)
        self.assertEqual(seen[0]["model"], "jev-latest")

    def test_invalid_mode_never_calls_provider(self):
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with patch.dict(os.environ, {"RHIZE_DECISION_MODE": "active"}), patch.object(MODULE, "call_provider") as call:
            with self.assertRaisesRegex(MODULE.DecisionError, "shadow or advisory"):
                MODULE.decide(self.project, "gsd-planner", request)
        call.assert_not_called()

    def test_hosted_jev_requires_a_key(self):
        with patch.dict(os.environ, {"TYPESAFE_BASE_URL": "https://api.typesafe.ai"}, clear=True):
            with self.assertRaisesRegex(MODULE.DecisionError, "TYPESAFE_API_KEY"):
                MODULE.endpoint()

    def test_remote_non_jev_endpoint_is_rejected(self):
        with patch.dict(os.environ, {"TYPESAFE_BASE_URL": "https://untrusted.example"}):
            with self.assertRaisesRegex(MODULE.DecisionError, "hosted Jev or loopback Laya"):
                MODULE.endpoint()

    def test_question_requires_instructions_before_provider_call(self):
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with self.assertRaisesRegex(MODULE.DecisionError, "instructions"):
            MODULE.validate_request(request)

    def test_probe_rejects_wrong_local_checkpoint_and_records_route(self):
        MODULE.install(self.project)
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with provider_server(routed_model="english") as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base, "TYPESAFE_DEFAULT_MODEL": "typed-decisions"}):
            with self.assertRaisesRegex(MODULE.DecisionError, "different checkpoint"):
                MODULE.decide(self.project, "launch-probe", request, probe=True)
        self.assertEqual(MODULE.status(self.project)["status"], "blocked")
        receipt = json.loads((self.project / MODULE.RECEIPTS).read_text())
        self.assertEqual(receipt["outcome"], "route_mismatch")
        self.assertEqual(receipt["routed_model"], "english")

    def test_local_launch_status_requires_pinned_checkpoint(self):
        MODULE.install(self.project)
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with provider_server(routed_model="english") as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}, clear=True):
            MODULE.decide(self.project, "launch-probe", request, probe=True)
            self.assertEqual(MODULE.status(self.project)["status"], "blocked")

    def test_latest_failed_probe_revokes_prior_readiness(self):
        MODULE.install(self.project)
        request = {"state": "synthetic", "questions": {"next": {"type": "choice", "instructions": "Choose next step", "criteria": {"ready": "Proceed", "blocked": "Investigate"}}}}
        with patch.dict(os.environ, {"TYPESAFE_DEFAULT_MODEL": "typed-decisions"}):
            with provider_server(routed_model="typed-decisions") as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}):
                MODULE.decide(self.project, "launch-probe", request, probe=True)
                self.assertEqual(MODULE.status(self.project)["status"], "ready")
            with provider_server(routed_model="english") as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base}):
                with self.assertRaises(MODULE.DecisionError):
                    MODULE.decide(self.project, "launch-probe", request, probe=True)
                self.assertEqual(MODULE.status(self.project)["status"], "blocked")
        self.assertEqual(MODULE.status(self.project)["status"], "blocked")

    def test_foreman_style_supervision_is_shadow_only_and_evidence_bounded(self):
        MODULE.install(self.project)
        state = {"phase": "verification", "required_checks_passed": True, "independent_review_passed": False}
        with provider_server() as base, patch.dict(os.environ, {"TYPESAFE_BASE_URL": base, "RHIZE_DECISION_MODE": "shadow"}):
            result = MODULE.supervise(self.project, "gsd-verifier", state, agent_id="agent-123")
        self.assertEqual(result["status"], "shadow")
        self.assertEqual(result["recommendations"], {})
        self.assertEqual(result["candidate_directive"], "verify")
        receipt = json.loads((self.project / MODULE.RECEIPTS).read_text())
        self.assertEqual(receipt["question_ids"], sorted(MODULE.SUPERVISOR_CHECKS["gsd-verifier"]))
        self.assertEqual(receipt["candidate_directive"], "verify")
        self.assertEqual(receipt["assessment"]["needs_verification"], 0.9)
        self.assertNotIn("phase", json.dumps(receipt))

    def test_supervisor_finish_proposal_requires_real_checks_and_review(self):
        answers = {name: {"type": "noul", "noul": 0.9} for name in MODULE.SUPERVISOR_CHECKS["gsd-verifier"]}
        answers["needs_verification"]["noul"] = 0.1
        answers["needs_human"]["noul"] = 0.1
        answers["agents_md_drift"]["noul"] = 0.1
        self.assertEqual(MODULE.candidate_directive("gsd-verifier", answers, {"required_checks_passed": True}), "continue")
        self.assertEqual(MODULE.candidate_directive("gsd-verifier", answers, {"required_checks_passed": True, "independent_review_passed": True}), "finish_candidate")

    def test_full_stack_gsd_questions_stay_in_one_bounded_call(self):
        self.assertEqual(len(MODULE.SUPERVISOR_CHECKS["gsd-planner"]), 7)
        self.assertEqual(len(MODULE.SUPERVISOR_CHECKS["gsd-executor"]), 8)
        self.assertEqual(len(MODULE.SUPERVISOR_CHECKS["gsd-verifier"]), 8)
        self.assertIn("graph_context_relevant", MODULE.SUPERVISOR_CHECKS["gsd-planner"])
        self.assertIn("tool_trace_risk", MODULE.SUPERVISOR_CHECKS["gsd-executor"])
        self.assertIn("browser_qa_complete", MODULE.SUPERVISOR_CHECKS["gsd-verifier"])
        risk = {"tool_trace_risk": {"type": "noul", "noul": 0.95}}
        self.assertEqual(MODULE.candidate_directive("gsd-executor", risk, {}), "investigate")
        browser = {"browser_qa_complete": {"type": "noul", "noul": 0.1},
                   "tests_sufficient": {"type": "noul", "noul": 0.9}}
        self.assertEqual(MODULE.candidate_directive("gsd-verifier", browser,
                         {"browser_qa_applicable": True}), "verify")


if __name__ == "__main__":
    unittest.main()
