"""Bounded receipt inventory for offline pilot consumers using a frozen collector runtime."""

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time

LIMIT = 100_000
BYTE_LIMIT = 128 << 20
ROW_LIMIT = 131072
ID = re.compile(r"[a-f0-9]{64}")
SCHEMA = "rhize-receipt-manifest-v1"


def check_time(deadline):
    if time.monotonic() > deadline:
        raise ValueError("receipt inventory deadline")


def names(fd, deadline):
    found = set()
    with os.scandir(fd) as entries:
        for entry in entries:
            check_time(deadline)
            if not entry.name.endswith(".json"):
                continue
            key = entry.name[:-5]
            if not ID.fullmatch(key) or key in found:
                raise ValueError("invalid or duplicate receipt identity")
            if len(found) == LIMIT:
                raise ValueError("receipt inventory resource limit")
            found.add(key)
    return sorted(found)


def read_row(fd, key):
    child = os.open(key + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(child, "rb") as stream:
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode) or info.st_size > ROW_LIMIT:
            raise ValueError("invalid receipt type or size")
        raw = stream.read(ROW_LIMIT + 1)
        if len(raw) != info.st_size:
            raise ValueError("receipt size changed")
    return raw


def scan(root, expected=None, seconds=30):
    """Seal the listed members, or verify those members and return original sorted pairs."""
    deadline = time.monotonic() + seconds
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        keys = names(fd, deadline) if expected is None else list(expected)
        hashes, rows, total = {}, [], 0
        for key in keys:
            check_time(deadline)
            raw = read_row(fd, key)
            total += len(raw)
            if total > BYTE_LIMIT:
                raise ValueError("receipt inventory byte limit")
            digest = hashlib.sha256(raw).hexdigest()
            if expected is not None and digest != expected[key]:
                raise ValueError("sealed receipt changed: " + key)
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                raise ValueError("invalid receipt object: " + key)
            hashes[key] = digest
            if expected is not None:
                rows.append((key, obj))
        check_time(deadline)
        return hashes if expected is None else rows
    finally:
        os.close(fd)


def seal(root, path):
    hashes = scan(root)
    packet = {"schema": SCHEMA, "receipts": str(root.absolute()), "members": hashes}
    raw = json.dumps(packet, separators=(",", ":")).encode()
    # Publish only complete, immutable manifests, including on a concurrent seal.
    with tempfile.NamedTemporaryFile(dir=path.parent) as tmp:
        tmp.write(raw)
        tmp.flush()
        os.fsync(tmp.fileno())
        os.link(tmp.name, path)
    return hashlib.sha256(raw).hexdigest()


def open_manifest(path, digest, root):
    if path.is_symlink() or path.stat().st_size > 16 << 20:
        raise ValueError("invalid manifest")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("manifest digest mismatch")
    obj = json.loads(raw)
    if obj["schema"] != SCHEMA or obj["receipts"] != str(root.absolute()):
        raise ValueError("manifest source mismatch")
    members = obj["members"]
    if (
        not isinstance(members, dict)
        or len(members) > LIMIT
        or list(members) != sorted(members)
        or any(not ID.fullmatch(k) or not ID.fullmatch(v) for k, v in members.items())
    ):
        raise ValueError("invalid manifest members")
    return members


def dispatch(runtime, root, members, name, args):
    """Separate process per consumer. Replace receipt enumeration only, before importing its callers."""
    if any(arg.split("=")[0] in ("--receipts", "--root") for arg in args):
        raise ValueError("consumer root override refused")
    if name == "decision_pilot" and args not in (["report"], ["queue"]):
        raise ValueError("unsupported pilot command")
    if name == "pilot_labels" and not (len(args) == 3 and args[:2] == ["export", "--out"]):
        raise ValueError("unsupported label command")
    if name == "pilot_cycle" and "--shadow-only" not in args:
        raise ValueError("shadow-only required")
    if name == "pilot_autolabel" and args[:1] != ["run"]:
        raise ValueError("unsupported labeler command")
    sys.path[:0] = [str(runtime / "rhize-context-manager/scripts"), str(runtime / "evals/typed-decision")]
    import decision_pilot

    if root.absolute() != (decision_pilot.DEFAULT_ROOT / "receipts").absolute():
        raise ValueError("runtime receipt root mismatch")
    original = decision_pilot.inventory
    data = scan(root, members)
    decision_pilot.inventory = lambda path: (
        data if Path(path).absolute() == root.absolute() else original(path)
    )
    module = importlib.import_module(name)
    sys.argv = [module.__file__, *args]
    if name == "pilot_autolabel" and os.environ.get("RHIZE_LABELER_DEADLINE_MONOTONIC"):
        remaining = int(float(os.environ.pop("RHIZE_LABELER_DEADLINE_MONOTONIC")) - time.monotonic())
        if remaining < 60:
            raise ValueError("insufficient scheduled labeler budget")
        sys.argv.extend(["--deadline-seconds", str(remaining)])
    try:
        return module.main()
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "unavailable", "stage": "consumer", "reason": type(exc).__name__}))
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("seal")
    use = sub.add_parser("use")
    use.add_argument("--sha256", required=True)
    use.add_argument("--runtime", type=Path, required=True)
    use.add_argument("consumer", choices=["decision_pilot", "pilot_labels", "pilot_cycle", "pilot_autolabel"])
    use.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.operation == "seal":
            print(json.dumps({"status": "sealed", "sha256": seal(args.receipts, args.manifest)}))
            return 0
        members = open_manifest(args.manifest, args.sha256, args.receipts)
        return dispatch(args.runtime, args.receipts, members, args.consumer, args.args)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "unavailable", "stage": "inventory", "reason": str(exc)}))
        return 78


if __name__ == "__main__":
    sys.exit(main())
