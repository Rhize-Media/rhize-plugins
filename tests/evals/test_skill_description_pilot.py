"""Static integrity checks for the shared skill-description pilot fixture."""

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "evals/skill-description-pilot/fixture.json"


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def skill_parts(path: Path) -> tuple[str, bytes, str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    assert len(parts) == 3 and parts[0] == "", f"invalid frontmatter in {path}"
    frontmatter, body = parts[1], parts[2].encode("utf-8")
    lines = frontmatter.splitlines(keepends=True)
    start = next(
        index
        for index, line in enumerate(lines)
        if re.match(r"^description:\s*(?:>|>-|\|\|-)\s*$", line.rstrip("\r\n"))
    )
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1].isspace()):
        end += 1
    value = " ".join(line.strip() for line in lines[start + 1 : end] if line.strip())
    without_description = "".join(lines[:start] + lines[end:])
    return value, body, without_description


def test_fixture_covers_routing_classes_and_explicit_invocation() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == "skill-description-pilot-v1"
    assert "first skill selected" in fixture["evaluation_scope"]
    assert fixture["baseline_source"]["git_commit"] == (
        "8c9003e7ca6bc2d6143d2f091a6d7ad9c40d81fd"
    )
    case_ids = [case["id"] for case in fixture["cases"]]
    assert len(case_ids) == len(set(case_ids))
    assert {case["class"] for case in fixture["cases"]} == {
        "positive",
        "negative",
        "adjacent-skill",
        "explicit-invocation",
    }
    assert all(case["expected"] in {"invoke", "avoid"} for case in fixture["cases"])
    for skill_name in fixture["skills"]:
        cases = [case for case in fixture["cases"] if case["target_skill"] == skill_name]
        assert {case["class"] for case in cases} >= {
            "positive",
            "negative",
            "adjacent-skill",
            "explicit-invocation",
        }


def test_candidate_skills_change_only_the_description_field() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for skill_name, record in fixture["skills"].items():
        current_description, body, frontmatter_without_description = skill_parts(
            ROOT / record["path"]
        )
        baseline_description = record["baseline_description"]
        assert len(baseline_description) == record["baseline_description_characters"]
        assert sha256(baseline_description.encode("utf-8")) == record[
            "baseline_description_sha256"
        ]
        assert re.fullmatch(r"[0-9a-f]{64}", record["baseline_file_sha256"])
        assert current_description == record["candidate_description"], skill_name
        assert len(current_description) == record["candidate_description_characters"]
        assert sha256(current_description.encode("utf-8")) == record[
            "candidate_description_sha256"
        ]
        assert sha256(body) == record["baseline_body_sha256"], skill_name
        assert sha256(frontmatter_without_description.encode("utf-8")) == record[
            "baseline_frontmatter_without_description_sha256"
        ], skill_name
