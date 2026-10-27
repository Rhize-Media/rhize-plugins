#!/usr/bin/env python3
"""Validate and retain independent blinded reviews of a controlled memory pilot."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rhize-context-manager/scripts"))
from memory_context.core import _safe_id, sha256


def import_reviews(run_path, review_directory, review_paths):
    run_bytes = Path(run_path).read_bytes()
    run_hash = sha256(run_bytes)
    run = json.loads(run_bytes)
    packets = {}
    for row in run["rows"]:
        bundle = row.get("answerComparison", {}).get("reviewBundle")
        if not bundle:
            continue
        filename = bundle["file"]
        if Path(filename).name != filename:
            raise ValueError("review bundle must be a direct child filename")
        path = Path(review_directory) / filename
        if path.is_symlink():
            raise ValueError("review bundle cannot be a symlink")
        content = path.read_bytes()
        if sha256(content) != bundle["sha256"]:
            raise ValueError("review packet hash mismatch")
        packet = json.loads(content)
        if set(packet["responses"]) != set(bundle["armMapping"]):
            raise ValueError("review packet response labels do not match run")
        for label, arm in bundle["armMapping"].items():
            if sha256(packet["responses"][label]["answer"]) != row["answerComparison"]["arms"][arm]["answerHash"]:
                raise ValueError("review answer does not bind the recorded arm")
        packets[bundle["sha256"]] = packet
    records, seen = [], set()
    for review_path in review_paths:
        document = json.loads(Path(review_path).read_text())
        if set(document) != {"schemaVersion", "runSha256", "reviewerId", "basis", "reviews"} or document["schemaVersion"] != "memory-pilot-review-v1":
            raise ValueError("review document has an invalid shape")
        if document["runSha256"] != run_hash:
            raise ValueError("review belongs to another run")
        _safe_id(document["reviewerId"], "reviewerId")
        if document["basis"] not in {"human", "model"} or not isinstance(document["reviews"], list):
            raise ValueError("review basis or reviews is invalid")
        for item in document["reviews"]:
            keys = {"packetSha256", "responseId", "correctness", "materialOmissions", "unsupportedClaims", "correction", "abstentionAppropriate", "notes"}
            if not isinstance(item, dict) or set(item) != keys:
                raise ValueError("review item has an invalid shape")
            packet = packets.get(item["packetSha256"])
            if packet is None or item["responseId"] not in packet["responses"]:
                raise ValueError("review references an unknown packet or response")
            for key in ("correctness", "abstentionAppropriate"):
                if item[key] is not None and type(item[key]) is not bool:
                    raise ValueError(f"review {key} must be boolean or null")
            for key in ("materialOmissions", "unsupportedClaims"):
                if not isinstance(item[key], list) or not all(isinstance(value, str) and value for value in item[key]):
                    raise ValueError(f"review {key} must be an array of nonempty strings")
            if not isinstance(item["notes"], str) or (item["correction"] is not None and not isinstance(item["correction"], str)):
                raise ValueError("review notes/correction must be text")
            identity = (document["reviewerId"], item["packetSha256"], item["responseId"])
            if identity in seen:
                raise ValueError("duplicate reviewer response; retain revisions separately")
            seen.add(identity)
            records.append({"reviewerId": document["reviewerId"], "basis": document["basis"], **item})
    groups = {}
    for record in records:
        key = (record["packetSha256"], record["responseId"])
        groups.setdefault(key, []).append(record)
    disagreements = [{"packetSha256": key[0], "responseId": key[1], "field": field}
                     for key, group in groups.items() for field in ("correctness", "abstentionAppropriate")
                     if len({record[field] for record in group if record[field] is not None}) > 1]
    return {"schemaVersion": "memory-pilot-review-import-v1", "runSha256": run_hash,
            "records": records, "disagreements": disagreements, "humanAcceptance": None,
            "reviewerIdentityAuthenticated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = import_reviews(args.run, args.review_dir, args.reviews)
        target = args.output.expanduser().absolute()
        if any(path.is_symlink() for path in (target, *target.parents)):
            raise ValueError("review output cannot traverse symlinks")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"ERROR: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
