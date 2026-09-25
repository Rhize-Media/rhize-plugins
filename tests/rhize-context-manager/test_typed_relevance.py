import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rhize-context-manager/scripts"))
from context_experiments import typed_relevance as relevance


def manifest_file(tmp_path):
    path = tmp_path / "pack.json"
    path.write_text(json.dumps({
        "packId": "pack-1", "policy": {"acceptedForUse": True},
        "entries": [
            {"path": "src/target.py", "role": "FULL", "reason": "explicit_or_discovered_target"},
            {"path": "src/helper.py", "role": "INTERFACE", "reason": "static_dependency"},
        ],
    }))
    return path


def test_shadow_rank_preserves_verified_pack_and_records_model(monkeypatch, tmp_path):
    manifest = manifest_file(tmp_path)
    prompt = tmp_path / "pack.md"
    prompt.write_text("verified prompt")
    monkeypatch.setattr(relevance, "git_snapshot", lambda repo: "head")
    monkeypatch.setattr(relevance, "NativeContextPackProvider",
                        lambda: SimpleNamespace(verify_pack=lambda *args: SimpleNamespace(valid=True)))
    def call(base, request):
        assert request["model"] == "typed-decisions"
        assert len(request["questions"]) == 2
        assert "src/" not in json.dumps(request)
        return {"answers": {"c0": {"noul": 0.9}, "c1": {"noul": 0.2}},
                "routing": {"model": "typed-decisions"},
                "usage": {"input_tokens": 10, "output_tokens": 4}}, 5.0
    output = relevance.rank_pack(tmp_path, manifest, prompt, "Implement bounded context selection",
                                 "typed-decisions", "http://127.0.0.1:8000", call)
    assert output["status"] == "shadow" and output["packAltered"] is False
    assert output["ranked"][0]["score"] == 0.9
    assert all(item["incumbentIncluded"] for item in output["ranked"])
    assert "src/" not in json.dumps(output)


def test_stale_pack_never_calls_model(monkeypatch, tmp_path):
    manifest = manifest_file(tmp_path)
    prompt = tmp_path / "pack.md"
    prompt.write_text("verified prompt")
    monkeypatch.setattr(relevance, "git_snapshot", lambda repo: "changed")
    monkeypatch.setattr(relevance, "NativeContextPackProvider",
                        lambda: SimpleNamespace(verify_pack=lambda *args: SimpleNamespace(valid=False)))
    def forbidden(*args):
        pytest.fail("model must not be called on a stale pack")
    with pytest.raises(ValueError, match="stale or rejected"):
        relevance.rank_pack(tmp_path, manifest, prompt, "Task", "typed-decisions",
                            "http://127.0.0.1:8000", forbidden)


@pytest.mark.parametrize("base", ["https://api.typesafe.ai", "http://example.com",
                                   "http://127.0.0.1:8000/path", "http://user:pass@localhost"])
def test_local_only_endpoint(base):
    with pytest.raises(ValueError):
        relevance.local_call(base, {"model": "typed-decisions", "questions": {}})
