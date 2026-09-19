"""Versioned bounded-answer checks and opt-in private review evidence."""
import json
from pathlib import Path
import uuid

from .core import sha256, _write_private_replace

GRADER_VERSION = "answer-term-source-contract-v2"


def grade_answer(answer, source_ids, rubric):
    if rubric is None:
        return {"status": "unavailable_rubric", "passed": None, "method": GRADER_VERSION}
    if not isinstance(rubric, dict):
        raise ValueError("rubric must be an object")
    for key in ("requiredTerms", "forbiddenTerms", "requiredSourceHashes"):
        if not isinstance(rubric.get(key, []), list) or not all(isinstance(x, str) and x for x in rubric.get(key, [])):
            raise ValueError("rubric terms and source hashes must be nonempty strings")
    if not (rubric.get("requiredTerms") or rubric.get("requiredSourceHashes") or rubric.get("expectedAbstention") is True):
        raise ValueError("empty rubric cannot establish correctness")
    text = answer.lower()
    checks = {
        "requiredTerms": all(term.lower() in text for term in rubric.get("requiredTerms", [])),
        "forbiddenTerms": not any(term.lower() in text for term in rubric.get("forbiddenTerms", [])),
        "requiredSources": set(rubric.get("requiredSourceHashes", [])) <= set(source_ids),
    }
    if "expectedAbstention" in rubric:
        if type(rubric["expectedAbstention"]) is not bool:
            raise ValueError("expectedAbstention must be boolean")
        abstained = any(x in text for x in ("unavailable", "insufficient evidence", "cannot determine", "not provided"))
        checks["abstention"] = abstained == rubric["expectedAbstention"]
    return {"status": "graded", "passed": all(checks.values()), "method": GRADER_VERSION,
            "rubricHash": sha256(json.dumps(rubric, sort_keys=True)), "checks": checks,
            "humanReview": "pending", "scope": "bounded_term_and_source_contract"}


def save_review_bundle(directory, question, rubric, answers):
    """Only called by an explicit curated-run option; never from passive capture."""
    directory = Path(directory).expanduser().absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("review directory cannot traverse symlinks")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    identifier = uuid.uuid4().hex
    # Stable opaque labels conceal arm identity from the reviewer. The caller's
    # result keeps the mapping separately, so the review packet itself stays blind.
    ordered = sorted(answers, key=lambda arm: sha256(identifier + arm))
    mapping = {f"response-{i + 1}": arm for i, arm in enumerate(ordered)}
    packet = {"schemaVersion": "answer-review-v1", "question": question, "rubric": rubric,
              "responses": {label: answers[arm] for label, arm in mapping.items()}}
    content = json.dumps(packet, indent=2) + "\n"
    path = directory / f"{identifier}.json"
    _write_private_replace(path, content)
    return {"file": path.name, "sha256": sha256(content), "armMapping": mapping, "reviewStatus": "pending"}
