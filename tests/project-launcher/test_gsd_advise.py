"""GSD directive advice: supervise advise matrix, gate invariance, install wiring, outcomes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "project-launcher/scripts/typed_decision.py"
SPEC = importlib.util.spec_from_file_location("typed_decision_advise", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ADVICE = MODULE.advice_module()
CHECKPOINT = "gsd-verifier"
PASSED = {"summary": "tests green, review done", "required_checks_passed": True, "independent_review_passed": True}
FAILING = {"summary": "tests red", "required_checks_passed": False, "independent_review_passed": False}


@contextmanager
def laya_server(pick="verify", fail_pick=False, seen=None):
    """Fake Laya: /health identity, noul answers for supervision, one `pick` choice answer for advice."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self._send(200, {"loaded": ["typed-decisions"]}) if self.path == "/health" else self.send_error(404)

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if seen is not None:
                seen.append(request)
            questions = request["questions"]
            if "pick" in questions and fail_pick:
                self._send(500, {"error": "down"})
                return
            answers = {}
            for name, question in questions.items():
                if question["type"] == "noul":
                    answers[name] = {"type": "noul", "noul": 0.1}
                else:
                    wanted = dict(MODULE.GSD_CANDIDATES).get(pick)
                    chosen = next((key for key, text in question["criteria"].items() if text == wanted),
                                  next(iter(question["criteria"])))
                    answers[name] = {"type": "choice", "choice": chosen, "confidence": 0.9,
                                     "probabilities": {key: 0.9 if key == chosen else 0.1 / (len(question["criteria"]) - 1)
                                                       for key in question["criteria"]}}
            self._send(200, {"model": "fixture", "answers": answers, "routing": {"model": "typed-decisions"},
                             "usage": {"input_tokens": 5, "output_tokens": 1}})

        def _send(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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


def state_sha(state):
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


class GsdAdviseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "project"
        self.store = Path(self.temp.name) / "store"
        self.project.mkdir()
        self.store.mkdir()
        MODULE.install(self.project)

    def tearDown(self):
        self.temp.cleanup()

    def env(self, base, **extra):
        values = {"TYPESAFE_BASE_URL": base, "TYPESAFE_DEFAULT_MODEL": "typed-decisions",
                  "RHIZE_DECISION_MODE": "advisory", "RHIZE_TYPED_DECISIONS_ROOT": str(self.store)}
        values.update(extra)
        return patch.dict(os.environ, values, clear=True)

    def bind(self, mode="advise", policy_sha=None, instrument_sha=None):
        policy = policy_sha or ADVICE.policy_sha256(MODULE.GSD_DECISION, MODULE.GSD_QUESTION, MODULE.GSD_POLICY)
        (self.store / "registry-state.json").write_text(json.dumps({"decisions": {MODULE.GSD_DECISION: {
            "mode": mode, "policySha256": policy, "instrumentSha256": instrument_sha or ADVICE.INSTRUMENT_SHA256}}}))

    def agent(self, held, state=FAILING):
        """An agent id whose deterministic holdback assignment is `held`."""
        for index in range(500):
            agent_id = f"agent-{index}"
            if ADVICE.holdback(MODULE.GSD_DECISION, f"{agent_id}:{CHECKPOINT}:{state_sha(state)}") is held:
                return agent_id
        raise AssertionError("no agent id found")

    def record(self, result):
        return ADVICE.load(MODULE.GSD_DECISION, result["decision_id"], store=self.store)

    # ---- matrix

    def test_shadow_records_without_advice(self):
        with laya_server() as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(False))
        self.assertNotIn("advice", result)
        self.assertEqual(result["recommendations"], {})
        self.assertEqual(result["status"], "abstain")
        record = self.record(result)
        self.assertEqual((record["mode"], record["laya"]["status"]), ("shadow", "ok"))

    def test_bound_advise_shows_a_labelled_recommendation(self):
        self.bind()
        with laya_server(pick="verify") as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(False))
        self.assertEqual(result["status"], "advisory")
        self.assertEqual(result["recommendations"], {MODULE.GSD_DECISION: "verify"})
        self.assertIn("advisory", result["advice"])
        self.assertIn("`verify`", result["advice"])
        receipt = json.loads((self.project / MODULE.RECEIPTS).read_text().splitlines()[-1])
        self.assertEqual(receipt["advice"], {"mode": "advise", "holdback": False, "recommended": "verify"})
        self.assertNotIn("tests red", json.dumps(receipt))

    def test_unbound_or_stale_state_reads_as_shadow(self):
        for kwargs in ({"policy_sha": "0" * 64}, {"instrument_sha": "0" * 64}, {"mode": "shadow"}):
            with self.subTest(kwargs=kwargs):
                self.bind(**kwargs)
                with laya_server() as base, self.env(base):
                    result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(False))
                self.assertNotIn("advice", result)
                self.assertEqual(self.record(result)["mode"], "shadow")

    def test_holdback_records_but_never_advises(self):
        self.bind()
        with laya_server() as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(True))
        self.assertNotIn("advice", result)
        record = self.record(result)
        self.assertEqual((record["arm"], record["laya"]["status"]), ("holdback", "ok"))

    def test_off_pin_skips_the_record(self):
        self.bind(mode="off")
        with laya_server() as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(False))
        self.assertNotIn("advice", result)
        self.assertIsNone(self.record(result))

    def test_unavailable_advice_still_supervises(self):
        self.bind()
        with laya_server(fail_pick=True) as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=self.agent(False))
        self.assertNotIn("advice", result)
        self.assertEqual(self.record(result)["laya"]["status"], "unavailable")
        self.assertIn(result["candidate_directive"], {"continue", "investigate", "verify", "escalate", "finish_candidate"})

    # ---- candidates and criticality

    def test_finish_candidate_only_offered_after_checks_and_review(self):
        seen = []
        with laya_server(seen=seen) as base, self.env(base):
            blocked = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id="a-fail")
            allowed = MODULE.supervise(self.project, CHECKPOINT, PASSED, agent_id="a-pass")
        picks = [r["questions"]["pick"]["criteria"] for r in seen if "pick" in r["questions"]]
        self.assertEqual(len(picks[0]), 4)
        self.assertNotIn(dict(MODULE.GSD_CANDIDATES)["finish_candidate"], picks[0].values())
        self.assertEqual(len(picks[1]), 5)
        self.assertNotIn("finish_candidate", self.record(blocked)["candidates"])
        self.assertIn("finish_candidate", self.record(allowed)["candidates"])

    def test_critical_if_wrong_is_computed_from_trusted_state(self):
        partial = {"required_checks_passed": True, "independent_review_passed": False}
        with laya_server() as base, self.env(base):
            flags = {name: self.record(MODULE.supervise(self.project, CHECKPOINT, state, agent_id=f"a-{name}"))["criticalIfWrong"]
                     for name, state in (("fail", FAILING), ("partial", partial), ("pass", PASSED))}
        self.assertEqual(flags, {"fail": True, "partial": True, "pass": False})

    def test_request_text_is_bounded_and_secret_scrubbed(self):
        state = dict(FAILING, summary="x" * 5000 + " password=hunter2")
        seen = []
        with laya_server(seen=seen) as base, self.env(base):
            MODULE.supervise(self.project, CHECKPOINT, state, agent_id="a-long")
        sent = next(r for r in seen if "pick" in r["questions"])["state"]["request"]
        self.assertLessEqual(len(sent), ADVICE.REQUEST_CHARS)
        self.assertNotIn("hunter2", sent)

    # ---- the hook never changes with advice

    def stop_sequence(self, project, agent_id):
        payload = {"agent_type": CHECKPOINT, "agent_id": agent_id}
        before = MODULE.hook(project, "SubagentStop", payload)
        MODULE.supervise(project, CHECKPOINT, FAILING, agent_id=agent_id)
        return before, MODULE.hook(project, "SubagentStop", payload)

    def test_hook_allow_block_is_identical_with_and_without_advice(self):
        agent_id = self.agent(False)
        other = Path(self.temp.name) / "other"
        other.mkdir()
        MODULE.install(other)
        with laya_server() as base, self.env(base):
            without_advice = self.stop_sequence(other, agent_id)
        self.bind()
        with laya_server() as base, self.env(base):
            with_advice = self.stop_sequence(self.project, agent_id)
        self.assertEqual(without_advice, with_advice)
        self.assertEqual(with_advice[0]["decision"], "block")
        self.assertEqual(with_advice[1], {})

    def test_stop_hook_records_outcome_and_survives_outcome_failure(self):
        self.bind()
        agent_id = self.agent(False)
        payload = {"agent_type": CHECKPOINT, "agent_id": agent_id}
        with laya_server() as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id=agent_id)
            self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload), {})
            stored = ADVICE.load(MODULE.GSD_DECISION, result["decision_id"], kind="outcome", store=self.store)
            self.assertEqual(stored["chosen"], result["candidate_directive"])
            with patch.object(ADVICE, "record_outcome", side_effect=RuntimeError("disk")):
                self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload), {})

    def test_stop_hook_without_receipt_still_blocks_once(self):
        payload = {"agent_type": CHECKPOINT, "agent_id": "never-called"}
        self.assertEqual(MODULE.hook(self.project, "SubagentStop", payload)["decision"], "block")

    # ---- install, hosted, outcome, status

    def test_install_copies_the_shared_advice_client_byte_identical(self):
        installed = self.project / MODULE.ADVICE_CLIENT
        self.assertEqual(installed.read_bytes(), (ROOT / "project-launcher/scripts/typed_advice.py").read_bytes())
        self.assertEqual(MODULE.install(self.project)["local_laya"], False)
        settings = json.loads((self.project / ".claude/settings.json").read_text())
        self.assertNotIn("env", settings)

    def test_install_local_laya_merges_env_without_secrets(self):
        settings_path = self.project / ".claude/settings.json"
        settings_path.write_text(json.dumps({"env": {"KEEP": "1", "TYPESAFE_BASE_URL": "http://localhost:1"}, "model": "x"}))
        MODULE.install(self.project, local_laya=True)
        settings = json.loads(settings_path.read_text())
        self.assertEqual(settings["env"], {"KEEP": "1", **MODULE.LOCAL_LAYA_ENV})
        self.assertEqual(settings["model"], "x")
        self.assertFalse([key for key in settings["env"] if "KEY" in key or "TOKEN" in key])
        self.assertEqual(len(settings["hooks"]["SubagentStart"]), 1)

    def test_install_local_laya_rejects_a_non_object_env_before_writing(self):
        settings_path = self.project / ".claude/settings.json"
        settings_path.write_text('{"env": []}')
        with self.assertRaisesRegex(MODULE.DecisionError, "env must be an object"):
            MODULE.install(self.project, local_laya=True)
        self.assertEqual(settings_path.read_text(), '{"env": []}')

    def test_hosted_path_never_calls_laya_advice(self):
        request_result = {"model": "jev", "usage": {"input_tokens": 1, "output_tokens": 1},
                          "answers": {name: {"type": "noul", "noul": 0.1} for name in MODULE.SUPERVISOR_CHECKS[CHECKPOINT]}}
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "k", "RHIZE_DECISION_MODE": "advisory",
                                     "RHIZE_TYPED_DECISIONS_ROOT": str(self.store)}, clear=True), \
                patch.object(MODULE, "call_provider", return_value=(request_result, 5, "jev")), \
                patch.object(ADVICE, "advise") as advise:
            result = MODULE.supervise(self.project, CHECKPOINT, PASSED, agent_id="hosted")
        advise.assert_not_called()
        self.assertEqual(result["status"], "abstain")
        self.assertNotIn("decision_id", result)
        self.assertEqual(list(self.store.iterdir()), [])
        self.assertNotIn("decision_id", json.loads((self.project / MODULE.RECEIPTS).read_text()))

    def test_outcome_is_write_once_and_candidate_checked(self):
        with laya_server() as base, self.env(base):
            result = MODULE.supervise(self.project, CHECKPOINT, FAILING, agent_id="a-out")
            decision_id = result["decision_id"]
            self.assertEqual(MODULE.record_outcome(decision_id, "escalate"), {"status": "recorded"})
            self.assertEqual(MODULE.record_outcome(decision_id, "verify"), {"status": "not_recorded"})
            self.assertEqual(MODULE.record_outcome(decision_id, "finish_candidate"), {"status": "not_recorded"})
        self.assertEqual(ADVICE.load(MODULE.GSD_DECISION, decision_id, kind="outcome", store=self.store)["chosen"], "escalate")

    def test_outcome_cli_round_trip(self):
        client = self.project / MODULE.CLIENT
        with laya_server() as base:
            env = {**os.environ, "TYPESAFE_BASE_URL": base, "TYPESAFE_DEFAULT_MODEL": "typed-decisions",
                   "RHIZE_DECISION_MODE": "advisory", "RHIZE_TYPED_DECISIONS_ROOT": str(self.store)}
            supervise = subprocess.run([sys.executable, str(client), "supervise", "--project", str(self.project),
                                        "--checkpoint", CHECKPOINT, "--agent-id", "cli"], input=json.dumps(FAILING),
                                       capture_output=True, text=True, env=env, timeout=30)
            decision_id = json.loads(supervise.stdout)["decision_id"]
            done = subprocess.run([sys.executable, str(client), "outcome", "--decision-id", decision_id, "--chosen", "verify"],
                                   capture_output=True, text=True, env=env, timeout=30)
            again = subprocess.run([sys.executable, str(client), "outcome", "--decision-id", decision_id, "--chosen", "continue"],
                                   capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual((supervise.returncode, done.returncode, again.returncode), (0, 0, 1))
        self.assertEqual(json.loads(done.stdout), {"status": "recorded"})

    def test_status_and_start_hook_report_the_effective_mode(self):
        payload = {"agent_type": CHECKPOINT, "agent_id": "a-start"}
        with self.env("http://127.0.0.1:9"):
            shadow = MODULE.status(self.project)
            shadow_text = MODULE.hook(self.project, "SubagentStart", payload)["hookSpecificOutput"]["additionalContext"]
            self.bind()
            advised = MODULE.status(self.project)
            advise_text = MODULE.hook(self.project, "SubagentStart", payload)["hookSpecificOutput"]["additionalContext"]
        self.assertEqual((shadow["effective_mode"], shadow["configured_mode"], shadow["local_laya"]), ("shadow", "advisory", True))
        self.assertEqual(advised["effective_mode"], "advise")
        self.assertIn("shadow-only", shadow_text)
        self.assertNotIn("advice", shadow_text)
        self.assertIn("`advice` line", advise_text)
        self.assertIn("--agent-id a-start", advise_text)
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "k"}, clear=True):
            hosted = MODULE.status(self.project)
        self.assertEqual((hosted["effective_mode"], hosted["local_laya"]), ("shadow", False))


if __name__ == "__main__":
    unittest.main()
