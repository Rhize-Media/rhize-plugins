"""Paired, source-bound opportunity measurements shared by Claude and Codex."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import statistics
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .awareness import build_catalog, canonical, estimated_tokens, expand_catalog, render_context
from .core import MemoryContextAssembler, MemoryStore, _write_private_replace, default_memory_root, format_time, sha256, utc_now

IMPLEMENTATION_HASHES = {name: sha256(Path(__file__).with_name(name).read_bytes()) for name in ("core.py", "awareness.py", "opportunities.py")}
ARMS = ("A", "B")
PROTOCOL = "rhize-memory-pair-v1"
FILES = ("STATE.md", "CLAUDE.md", "AGENTS.md", "README.md")
MAX_BYTES = 1024 * 1024
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|sntrys_[A-Za-z0-9]{20,}|-----BEGIN .*PRIVATE KEY-----|(?:password|api[_-]?key|secret)\s*[=:]\s*['\"]?[A-Za-z0-9+/=_-]{20,})", re.I)
SIGNALS = re.compile(r"\b(recall|remember|resume|previous|prior|decision|policy|workflow|procedure|procedural|regression|provenance|unavailable|release|deployment|verification|context|memory)\b", re.I)


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9_-]{2,}", text.lower())) - {"the", "and", "for", "with", "this", "that", "from", "what", "which"}


def default_root() -> Path:
    return default_memory_root() / "paired-opportunities-v1"


def read_json(path: Path) -> dict[str, Any]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("measurement document exceeds limit")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("measurement document must be an object")
    return result


class PairStore:
    def __init__(self, root: Path):
        self.root = root.expanduser().absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("measurement root cannot traverse symlinks")
        self.lock = MemoryStore(self.root)

    def write(self, relative: str, value: dict[str, Any]) -> None:
        path = self.root / relative
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != self.root.parent):
            raise ValueError("measurement artifacts cannot be symlinks")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        _write_private_replace(path, canonical(value) + "\n")

    def read(self, relative: str) -> dict[str, Any] | None:
        path = self.root / relative
        if not path.exists():
            return None
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("measurement read cannot traverse symlinks")
        return read_json(path)

    def configure(self, workspaces: list[Path], answer_pairs_per_day: int = 12) -> dict[str, Any]:
        if type(answer_pairs_per_day) is not int or not 0 <= answer_pairs_per_day <= 100:
            raise ValueError("answer pair budget must be 0..100 per host/day")
        if not workspaces or any(not p.is_dir() or p.is_symlink() for p in workspaces):
            raise ValueError("configuration requires existing explicit workspace roots")
        config = {"schemaVersion": 1, "enabled": True, "hosts": ["claude", "codex"],
                  "workspaces": [str(p.resolve()) for p in workspaces], "answerPairsPerHostDay": answer_pairs_per_day,
                  "automaticInjection": False, "subscriptionOnly": True}
        with self.lock._locked():
            self.write("config.json", config)
            if self.read("key.json") is None:
                self.write("key.json", {"key": os.urandom(32).hex()})
        return config

    def fingerprint(self, value: str) -> str:
        key = self.read("key.json")
        if key is None:
            raise ValueError("measurement store is not configured")
        return hmac.new(bytes.fromhex(key["key"]), value.encode(), hashlib.sha256).hexdigest()

    def receipts(self) -> list[dict[str, Any]]:
        directory = self.root / "receipts"
        if directory.is_symlink():
            raise ValueError("receipt directory cannot be a symlink")
        return [read_json(p) for p in sorted(directory.glob("*.json"))]


def _catalog_input(document: dict[str, Any], now: datetime) -> dict[str, Any]:
    value = copy.deepcopy(document)
    value["catalogTokenBudget"] = min(1800, value["request"].get("totalTokenBudget", 4000))
    for adapter in value["adapters"]:
        for candidate in adapter.get("candidates", []):
            content = candidate.pop("content")
            lines = [line.strip("# \t") for line in content.splitlines() if line.strip()]
            label = (lines[0] if lines else candidate["sourceId"])[:160]
            keywords = sorted(tokens(label))[:8]
            candidate["topic"] = {"label": label, "keywords": [w[:40] for w in keywords],
                                  "detailDigest": sha256(content), "verifiedAt": format_time(now)}
    return value


def _run_arm(arm: str, document: dict[str, Any], root: Path, now: datetime) -> tuple[dict[str, Any], str, dict[str, Any]]:
    store = MemoryStore(root)
    state = {c["sourceId"]: c["sourceRevision"] for a in document["adapters"] for c in a.get("candidates", [])}
    catalog_tokens = 0
    index_ms = 0.0
    if arm == "A":
        manifest, payload = MemoryContextAssembler().assemble(document, now)
    else:
        start = time.perf_counter_ns()
        catalog, topic_payload = build_catalog(_catalog_input(document, now), now)
        paths = store.write(catalog, topic_payload)
        query = tokens(document["request"]["query"])
        scored = []
        for c in catalog["candidates"]:
            topic = json.loads(topic_payload["payloads"][c["payloadRef"]])
            score = len(query & tokens(topic["label"] + " " + " ".join(topic["keywords"])))
            if score:
                scored.append((-score, c["rank"], c["memoryId"]))
        selected = [row[2] for row in sorted(scored)[:5]]
        index_ms = (time.perf_counter_ns() - start) / 1e6
        manifest, payload, accounting = expand_catalog(store, *paths, selected, document, state, now)
        catalog_tokens = estimated_tokens(render_context(catalog, topic_payload))
    paths = store.write(manifest, payload)
    if not store.verify(*paths, now=now, source_state=state)["valid"]:
        raise ValueError("source pack failed verification")
    context = render_context(manifest, payload)
    return manifest, context, {"catalogEstimatedTokens": catalog_tokens, "indexBuildMs": round(index_ms, 3)}


def run_pair(document: dict[str, Any], root: Path, *, host: str, model: str | None,
             evidence_kind: str, now: datetime | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    if host not in {"claude", "codex", "host-neutral"} or evidence_kind not in {"curated", "natural", "hook-smoke"}:
        raise ValueError("invalid measurement host or evidence kind")
    if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", model)):
        raise ValueError("invalid model identity")
    if len(canonical(document).encode()) > MAX_BYTES:
        raise ValueError("paired input exceeds limit")
    stamp = now or utc_now()
    snapshot = sha256(canonical(document))
    order = list(ARMS) if int(snapshot[0], 16) % 2 == 0 else list(reversed(ARMS))
    result = {"schemaVersion": PROTOCOL, "evidenceKind": evidence_kind, "host": host, "model": model,
              "armsRequested": list(ARMS), "armOrder": order, "snapshotHash": snapshot,
              "createdAt": format_time(stamp), "selectionMethod": "catalog-keyword-overlap-v1",
              "implementationHashes": dict(IMPLEMENTATION_HASHES),
              "arms": {}, "sourceInputBytes": len(canonical(document).encode()), "automaticInjection": False}
    contexts = {}
    for arm in order:
        start = time.perf_counter_ns()
        row = {"variant": "legacy-direct-v1" if arm == "A" else "awareness-selected-v1",
               "actuallyRan": True, "status": "failed", "taskCorrectness": None, "modelUsage": None}
        try:
            manifest, context, measured = _run_arm(arm, document, root / arm, stamp)
            contexts[arm] = context
            row.update(status="completed", estimatedTokens=estimated_tokens(context) + measured["catalogEstimatedTokens"],
                       presentedTokens=estimated_tokens(context), selectedSourceHashes=[c["sourceIdHash"] for c in manifest["candidates"]],
                       excluded=manifest["exclusionReasonCounts"], **measured)
        except (OSError, ValueError, TypeError, KeyError) as error:
            contexts[arm] = ""
            row["failureClass"] = type(error).__name__
        row["elapsedMs"] = round((time.perf_counter_ns() - start) / 1e6, 3)
        result["arms"][arm] = row
    empty = copy.deepcopy(document)
    empty["adapters"] = []
    empty_manifest, empty_payload = MemoryContextAssembler().assemble(empty, stamp)
    result["emptyMemoryControl"] = {"actuallyRan": True, "estimatedTokens": estimated_tokens(render_context(empty_manifest, empty_payload))}
    result["comparisonStatus"] = "complete" if all(result["arms"][arm]["status"] == "completed" for arm in ARMS) else "incomplete"
    return result, contexts


def source_document(workspace: Path, prompt: str, now: datetime) -> tuple[dict[str, Any], list[dict[str, str]]]:
    project = "project-" + sha256(str(workspace))[:24]
    query = tokens(prompt)
    candidates = []
    bindings = []
    for filename in FILES:
        path = workspace / filename
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 65536:
            continue
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            raw = stream.read(65537)
        if len(raw) > 65536:
            continue
        content = raw.decode("utf-8", errors="strict")
        if SECRET.search(content):
            continue
        revision = sha256(raw)
        bindings.append({"path": str(path), "revision": revision})
        sections = re.split(r"(?m)(?=^#{1,3} )", content)
        for index, section in enumerate(sections):
            if not section.strip() or len(section.encode()) > 12000 or len(candidates) >= 40:
                continue
            source_id = f"doc-{sha256(filename)[:12]}-{index}"
            candidates.append({"sourceSystem": "canonical-file", "sourceId": source_id, "sourceRevision": revision,
                               "tenant": "rhize", "project": project, "trustClass": "verified", "contentRole": "data",
                               "retentionClass": "project", "validUntil": None, "content": section,
                               "relevance": min(1, len(query & tokens(section)) / max(1, len(query))),
                               "provenance": [source_id]})
    return {"schemaVersion": 1, "request": {"tenant": "rhize", "project": project, "query": prompt,
            "totalTokenBudget": 6000, "ttlSeconds": 3600, "laneBudgets": {"semantic": {"maxItems": 20, "maxTokens": 6000}}},
            "adapters": [{"name": "canonical-files", "memoryType": "semantic", "status": "available", "candidates": candidates}]}, bindings


def handle_event(store: PairStore, host: str, event_name: str, event: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if os.environ.get("RHIZE_MEMORY_EVAL_CHILD") == "1":
        return {"status": "child_ignored"}
    if host not in {"claude", "codex"} or len(canonical(event).encode()) > MAX_BYTES:
        raise ValueError("invalid hook event")
    config = store.read("config.json")
    if not config or not config.get("enabled") or host not in config.get("hosts", []):
        return {"status": "disabled"}
    stamp = now or utc_now()
    cwd = event.get("cwd")
    session = event.get("session_id")
    if not isinstance(cwd, str) or not isinstance(session, str) or not session:
        return {"status": "invalid_event"}
    workspace = Path(cwd).resolve(strict=True)
    if not any(workspace == Path(root) or Path(root) in workspace.parents for root in config["workspaces"]):
        return {"status": "scope_denied"}
    session_key = store.fingerprint(host + ":" + session)
    with store.lock._locked():
        health = store.read(f"health/{host}.json") or {"eventsObserved": 0}
        health.update(eventsObserved=health["eventsObserved"] + 1, lastEvent=event_name, lastSeen=format_time(stamp))
        store.write(f"health/{host}.json", health)
        session_state = store.read(f"sessions/{session_key}.json") or {}
        if event_name == "SessionStart":
            session_state["model"] = event.get("model")
            store.write(f"sessions/{session_key}.json", session_state)
            return {"status": "observed"}
        if event_name != "UserPromptSubmit":
            pair_id = session_state.get("pairId")
            if not pair_id:
                return {"status": "no_pending_pair"}
            receipt = store.read(f"receipts/{pair_id}.json")
            if not receipt:
                return {"status": "pending"}
            if event.get("turn_id") and session_state.get("turnKey") != store.fingerprint(str(event["turn_id"])):
                return {"status": "stale_turn_ignored"}
            observation = receipt["observation"]
            if event_name == "PostToolUse":
                tool_id = event.get("tool_use_id") or event.get("tool_call_id")
                if not isinstance(tool_id, str):
                    observation["unidentifiedToolEvents"] += 1
                else:
                    token = store.fingerprint(tool_id)
                    if token not in session_state.get("toolIds", []):
                        session_state.setdefault("toolIds", []).append(token)
                        session_state["toolIds"] = session_state["toolIds"][-2000:]
                        observation["toolCalls"] += 1
                        response = event.get("tool_response")
                        observation["toolErrors"] += int(isinstance(response, dict) and response.get("is_error") is True)
            elif event_name in {"Stop", "Interrupt", "SessionEnd"}:
                observation.update(ended=True, endEvent=event_name, endedAt=format_time(stamp))
            store.write(f"sessions/{session_key}.json", session_state)
            store.write(f"receipts/{pair_id}.json", receipt)
            return {"status": "observed", "pairId": pair_id}
        # An ineligible new turn must not be attributed to the preceding measured turn.
        prior_state = dict(session_state)
        store.write(f"sessions/{session_key}.json", {"model": session_state.get("model")})
        prompt = event.get("prompt")
        if not isinstance(prompt, str) or len(prompt.encode()) > 16000 or not SIGNALS.search(prompt):
            return {"status": "ineligible"}
        if SECRET.search(prompt):
            return {"status": "sensitive_input_skipped"}
        document, bindings = source_document(workspace, prompt, stamp)
        if not document["adapters"][0]["candidates"]:
            return {"status": "unavailable"}
        turn = event.get("turn_id") or store.fingerprint(prompt)
        model = event.get("model") or session_state.get("model")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", model):
            model = None
        pair_id = store.fingerprint(canonical([host, session, turn, model, document, IMPLEMENTATION_HASHES]))
        existing = store.read(f"receipts/{pair_id}.json")
        if existing:
            store.write(f"sessions/{session_key}.json", prior_state)
            return {"status": "duplicate", "pairId": pair_id}
        # Reserve both before executing either. Crashed attempts remain explicitly pending.
        reservation = {"pairId": pair_id, "armsRequested": list(ARMS), "status": "pending", "host": host, "model": model, "createdAt": format_time(stamp)}
        store.write(f"reservations/{pair_id}.json", reservation)
        with tempfile.TemporaryDirectory(prefix="retrieval-", dir=store.root) as directory:
            pair, contexts = run_pair(document, Path(directory), host=host, model=model, evidence_kind="natural", now=stamp)
        pair["pairId"] = pair_id
        pair["observation"] = {"toolCalls": 0, "toolErrors": 0, "unidentifiedToolEvents": 0, "ended": False, "correctness": None}
        pair["answerStatus"] = "queued" if model and config["answerPairsPerHostDay"] and pair["comparisonStatus"] == "complete" else "unavailable_model" if not model else "unavailable_retrieval" if pair["comparisonStatus"] != "complete" else "disabled"
        if pair["answerStatus"] == "queued" and len(list((store.root / "queue").glob("*.json"))) >= 100:
            pair["answerStatus"] = "deferred_queue_full"
        if pair["answerStatus"] == "queued":
            store.write(f"queue/{pair_id}.json", {"pairId": pair_id, "host": host, "model": model, "createdAt": format_time(stamp),
                        "question": prompt, "contexts": contexts, "sourceBindings": bindings, "rubric": None, "evidenceKind": "natural"})
        store.write(f"receipts/{pair_id}.json", pair)
        reservation["status"] = pair["comparisonStatus"]
        store.write(f"reservations/{pair_id}.json", reservation)
        store.write(f"sessions/{session_key}.json", {"pairId": pair_id, "model": model, "toolIds": [], "turnKey": store.fingerprint(str(turn))})
        return {"status": pair["comparisonStatus"], "pairId": pair_id}


def complete_pair(value: dict[str, Any]) -> bool:
    arms = value.get("arms", {})
    return (value.get("comparisonStatus") == "complete" and set(arms) == set(ARMS)
            and all(arms[a].get("actuallyRan") is True and arms[a].get("status") == "completed" for a in ARMS))


def _effect(values: list[float]) -> dict[str, Any]:
    # Case-level bootstrap is descriptive for this curated corpus, not a population guarantee.
    import random
    interval = None
    if len(values) >= 5:
        rng = random.Random(1701)
        means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(1000))
        interval = [means[24], means[974]]
    return {"samples": len(values), "meanBMinusA": statistics.mean(values) if values else None,
            "descriptiveBootstrap95": interval, "seed": 1701, "resamples": 1000}


def aggregate(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in receipts:
        key = canonical([row["evidenceKind"], row["host"], row.get("model"), row.get("implementationHashes"), row.get("corpusHash")])
        groups.setdefault(key, []).append(row)
    summaries = []
    answer_groups: dict[str, list[dict[str, Any]]] = {}
    for key, rows in groups.items():
        valid = [r for r in rows if complete_pair(r)]
        # Repeat deliveries or repeated trials on the same snapshot do not increase n.
        unique = {r["snapshotHash"]: r for r in valid}
        deltas = [r["arms"]["B"]["estimatedTokens"] - r["arms"]["A"]["estimatedTokens"] for r in unique.values()]
        summaries.append({"stratum": json.loads(key), "totalPairs": len(rows), "completePairs": len(valid),
                          "uniqueSnapshots": len(unique), "tokenEstimateEffect": _effect(deltas),
                          "meanEstimatedTokenDeltaBMinusA": statistics.mean(deltas) if deltas else None,
                          "pairedAnswerComplete": sum(complete_pair(r.get("answerComparison", {})) for r in rows)})
        for row in rows:
            answer = row.get("answerComparison")
            if answer:
                models = [answer.get("arms", {}).get(a, {}).get("model") for a in ARMS]
                answer_key = canonical([json.loads(key), models, answer.get("driverHash")])
                answer_groups.setdefault(answer_key, []).append(row)
    outcomes = []
    for key, rows in answer_groups.items():
        valid = [r for r in rows if complete_pair(r) and complete_pair(r["answerComparison"])
                 and r["answerComparison"]["arms"]["A"].get("model") is not None
                 and r["answerComparison"]["arms"]["A"].get("model") == r["answerComparison"]["arms"]["B"].get("model")]
        unique = {r["snapshotHash"]: r for r in valid}
        metrics = {}
        for metric in ("totalInputTokens", "outputTokens", "cachedInputTokens"):
            values = []
            for r in unique.values():
                a, b = [(r["answerComparison"]["arms"][arm].get("usage") or {}).get(metric) for arm in ARMS]
                if type(a) is int and type(b) is int:
                    values.append(b - a)
            metrics[metric] = _effect(values)
        graded = [r for r in unique.values() if all(type(r["answerComparison"]["arms"][a].get("rubricPass")) is bool for a in ARMS)]
        outcomes.append({"stratum": json.loads(key), "totalPairs": len(rows), "completePairs": len(valid),
                         "uniqueSnapshots": len(unique), "usageEffects": metrics, "gradedPairs": len(graded),
                         "rubricPasses": {a: sum(r["answerComparison"]["arms"][a]["rubricPass"] for r in graded) for a in ARMS},
                         "rubricEffect": _effect([int(r["answerComparison"]["arms"]["B"]["rubricPass"]) - int(r["answerComparison"]["arms"]["A"]["rubricPass"]) for r in graded])})
    complete = sum(complete_pair(r) for r in receipts)
    return {"schemaVersion": PROTOCOL, "completePairs": complete, "incompletePairs": len(receipts) - complete,
            "groups": summaries, "answerGroups": outcomes, "taskOutcomeBenefit": "not_inferred_from_retrieval_metrics"}
