"""Operational attempts retain failures, deadlines and grouped order variants."""
import importlib.util
import json
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[2] / "evals/typed-decision"
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("operational", HERE / "operational.py")
operational = importlib.util.module_from_spec(spec)


def row(identity="one"):
    return {"case_id": identity, "group_id": "same-task", "decision_type": "skill-fit",
            "stratum": "routine", "adjudicated": True, "label_source": "fixture", "state": "Synthetic",
            "questions": {"q": {"type": "choice", "instructions": "Choose",
                                  "criteria": {"right": "Correct", "other": "Distractor"}}},
            "labels": {"q": "right"}}


def answer(choice="right", latency=1):
    return {"answers": {"q": {"type": "choice", "choice": choice, "confidence": .8,
            "probabilities": {"right": .8 if choice == "right" else .2,
                              "other": .2 if choice == "right" else .8}}}}, latency


def test_status_denominator_and_deadline_yield():
    spec.loader.exec_module(operational)
    replies = iter([answer(), answer(latency=801), TimeoutError(), ValueError("private text"),
                    urllib.error.HTTPError("http://127.0.0.1", 503, "private", None, None),
                    ConnectionRefusedError()])
    def call(_request):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply
    result = operational.run([row(str(i)) for i in range(6)], {"id": "base", "model": "fixture"}, call, 800)
    assert result["statuses"] == {"ok": 1, "late": 1, "timeout": 1, "invalid": 1, "busy": 1, "unavailable": 1}
    assert result["attempts"] == 6 and result["independent_groups"] == 1
    assert result["correct_before_deadline"] == 1
    assert result["deadline_yield"] == pytest.approx(1 / 6)
    assert result["successful_latency_ms"]["n"] == 1
    assert "private" not in json.dumps(result)
    assert next(r for r in result["cases"] if r["status"] == "timeout")["censored"]


def test_order_variants_change_request_order_not_labels_or_groups(tmp_path):
    spec.loader.exec_module(operational)
    variants = operational.menu_panel([row()])
    assert len(variants) == 2
    assert len({r["case_id"] for r in variants}) == 2
    assert {r["group_id"] for r in variants} == {"same-task"}
    assert all(r["labels"] == row()["labels"] for r in variants)
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in variants))
    variants = operational.research.read_jsonl(path)
    seen = []
    def first_position(request):
        order = list(request["questions"]["q"]["criteria"])
        seen.append(order)
        return answer(order[0])
    result = operational.run(variants, {"id": "position", "model": "fixture"}, first_position, 800)
    assert seen == [["right", "other"], ["other", "right"]]
    assert result["menu_order"]["comparable_sources"] == result["menu_order"]["disagreements"] == 1
    assert operational.research.digest(variants[0]) != operational.research.digest(variants[1])


@pytest.mark.parametrize("deadline", [0, -1, True, float("nan"), float("inf")])
def test_invalid_deadlines_never_call_provider(deadline):
    spec.loader.exec_module(operational)
    with pytest.raises(ValueError):
        operational.run([row()], {"id": "base", "model": "fixture"}, lambda _: pytest.fail("called"), deadline)


def test_shared_transport_deadline_covers_health_probe_before_post():
    spec.loader.exec_module(operational)
    posts = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            time.sleep(.15)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"loaded":["fixture"]}')
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            posts.append(True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        report = operational.run([row()], {'id': 'base', 'model': 'fixture'},
                                 lambda request: operational.research.local_call(url, request, timeout=.03), 30)
        assert report['statuses']['timeout'] == 1 and report['deadline_yield'] == 0
        assert posts == [] and report['successful_latency_ms']['n'] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_existing_output_is_refused_before_inference(tmp_path, monkeypatch):
    spec.loader.exec_module(operational)
    output = tmp_path / 'report.json'
    output.write_text('existing evidence')
    monkeypatch.setattr(sys, 'argv', ['operational', 'run', '--cases', 'not-read', '--output', str(output),
                                    '--candidate', 'not-read', '--deadline-ms', '800', '--condition', 'warm',
                                    '--runtime-evidence', 'not-read'])
    monkeypatch.setattr(operational.research, 'local_call', lambda *a, **kw: pytest.fail('provider called'))
    with pytest.raises(SystemExit) as error:
        operational.main()
    assert error.value.code == 2 and output.read_text() == 'existing evidence'
