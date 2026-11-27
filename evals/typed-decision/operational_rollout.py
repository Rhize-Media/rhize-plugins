"""Stage offline pilot consumers after two independently verified, scheduled inventory reads."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys
import tempfile
import time

import receipt_snapshot as reader


class Rollout:
    def __init__(self, config):
        self.release = Path(__file__).resolve().parents[2]
        self.tool = Path(reader.__file__).resolve()
        self.root = Path.home() / ".local/share/rhize/workflow-selection/receipts"
        self.state = Path(config["auditRoot"])
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.binding = config["release"]
        if self.release != Path(config["releaseRoot"]) or digest(self.tool) != config["readerSha256"]:
            raise ValueError("operational release binding changed")
        self.pins = {Path(p) for p in config["pins"]}
        self.path = None
        self.sha = None

    def active(self):
        marks = sorted(self.state.glob("qualified-*.json"))
        launches = set()
        for mark in marks:
            item = json.loads(mark.read_text())
            if item["release"] == self.binding and item["readerSha256"] == digest(self.tool):
                launches.add(item["launch"])
        return len(launches) >= 2

    def manifest(self):
        if self.path is None:
            folder = Path(tempfile.mkdtemp(prefix="read-", dir=self.state))
            path = folder / "manifest.json"
            sha = reader.seal(self.root, path)
            publish(folder / "binding.json", {"release": self.binding, "sha256": sha})
            self.path, self.sha = path, sha
        return self.path, self.sha

    def command(self, script, args):
        script = Path(script)
        pin = script.parents[2]
        if pin not in self.pins:
            raise ValueError("unreviewed consumer pin")
        path, sha = self.manifest()
        return [
            str(self.tool),
            "--receipts",
            str(self.root),
            "--manifest",
            str(path),
            "use",
            "--sha256",
            sha,
            "--runtime",
            str(pin),
            script.stem,
            *map(str, args),
        ]

    def observe(self, config, pid, launch):
        if self.active():
            return {"status": "active", "release": self.binding}
        job = subprocess.run(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/media.rhize.laya-autolabel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        if not re.search(rf"^\s*pid = {pid}\s*$", job.stdout, re.MULTILINE) or pid != os.getppid():
            raise ValueError("scheduled caller binding unavailable")
        token = hashlib.sha256(launch.read_bytes()).hexdigest()
        destination = self.state / ("qualified-" + token + ".json")
        if destination.exists():
            return {"status": "already_observed", "launch": token}
        path, sha = self.manifest()
        members = reader.open_manifest(path, sha, self.root)
        # An independent pass checks sealed bytes and counts new arrivals for the next manifest.
        deadline = time.monotonic() + 30
        seen = set()
        total = 0
        for p in self.root.glob("*.json"):
            reader.check_time(deadline)
            if len(seen) >= reader.LIMIT or not reader.ID.fullmatch(p.stem) or p.is_symlink():
                raise ValueError("invalid oracle inventory")
            seen.add(p.stem)
            if p.stem in members:
                size, value = oracle_digest(p, reader.BYTE_LIMIT - total)
                total += size
                if value != members[p.stem]:
                    raise ValueError("receipt oracle mismatch")
        if members.keys() - seen:
            raise ValueError("incomplete receipt oracle")
        outputs = {}
        for pin in config["collectionPins"]:
            scripts = Path(pin) / "rhize-context-manager/scripts"
            for tool, args in [
                ("decision_pilot", ["report"]),
                ("decision_pilot", ["queue"]),
                ("pilot_labels", ["export", "--out", str(path.parent / "export.jsonl")]),
            ]:
                result = subprocess.run(
                    [sys.executable, *self.command(scripts / (tool + ".py"), args)],
                    capture_output=True,
                    timeout=60,
                    check=True,
                )
                obj = json.loads(result.stdout)
                if args[0] == "report":
                    value = obj["v2Coverage"]["rawEvents"]
                elif args[0] == "queue":
                    value = len(obj["items"])
                else:
                    value = obj["count"]
                    (path.parent / "export.jsonl").unlink()
                outputs[pin + "/" + args[0]] = value
        evidence = {
            "release": self.binding,
            "readerSha256": digest(self.tool),
            "launch": token,
            "manifest": str(path),
            "manifestSha256": sha,
            "members": len(members),
            "deferred": len(seen - members.keys()),
            "consumers": outputs,
        }
        publish(destination, evidence)
        return {"status": "qualified", **evidence}


def oracle_digest(path, remaining):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(fd)
        limit = min(remaining, reader.ROW_LIMIT)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("invalid oracle receipt")
        raw = stream.read(limit + 1)
        if len(raw) != info.st_size:
            raise ValueError("oracle receipt changed")
        return len(raw), hashlib.sha256(raw).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(path, obj):
    with tempfile.NamedTemporaryFile(dir=path.parent) as f:
        f.write(json.dumps(obj, sort_keys=True).encode())
        f.flush()
        os.fsync(f.fileno())
        os.link(f.name, path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    sub = p.add_subparsers(dest="op", required=True)
    obs = sub.add_parser("observe")
    obs.add_argument("pid", type=int)
    obs.add_argument("launch", type=Path)
    use = sub.add_parser("consume")
    use.add_argument("script", type=Path)
    use.add_argument("args", nargs=argparse.REMAINDER)
    options = p.parse_args()
    started = time.monotonic()
    config = json.loads(options.config.read_text())
    rollout = Rollout(config)
    if options.op == "observe":
        print(json.dumps(rollout.observe(config, options.pid, options.launch)))
    else:
        args = [str(options.script), *options.args]
        if rollout.active():
            if options.script.stem == "pilot_autolabel":
                limits = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
                limits.add_argument("--deadline-seconds", type=int, default=2400)
                limit, _ = limits.parse_known_args(options.args)
                if limit.deadline_seconds < 60:
                    raise ValueError("invalid scheduled labeler budget")
                os.environ["RHIZE_LABELER_DEADLINE_MONOTONIC"] = str(
                    started + min(limit.deadline_seconds, 2400)
                )
            args = rollout.command(options.script, options.args)
        os.execv(sys.executable, [sys.executable, *args])


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {"status": "unavailable", "stage": "operational_reader_startup", "reason": type(exc).__name__}
            )
        )
        sys.exit(78)
