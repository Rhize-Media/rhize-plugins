#!/usr/bin/env python3
"""Project-local Jev/Laya client and GSD installer; standard library only."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SKILL = "skills/rhize-typed-decision"
CLIENT = ".claude/rhize-decision/typed_decision.py"
RECEIPTS = ".planning/decision-layer/receipts.jsonl"
AGENTS = ("gsd-planner", "gsd-executor", "gsd-verifier")
HOOK_EVENTS = ("SubagentStart", "SubagentStop")


class DecisionError(Exception):
    pass


def load_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise DecisionError(f"cannot read JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise DecisionError(f"expected JSON object: {path}")
    return value


def install(project: Path) -> dict:
    config_path = project / ".planning/config.json"
    config = load_object(config_path) if config_path.exists() else {}
    mapping = config.setdefault("agent_skills", {})
    if not isinstance(mapping, dict):
        raise DecisionError("agent_skills must be an object")
    for agent in AGENTS:
        skills = mapping.setdefault(agent, [])
        if not isinstance(skills, list) or not all(isinstance(item, str) for item in skills):
            raise DecisionError(f"agent_skills.{agent} must be a string array")
        if SKILL not in skills:
            skills.append(SKILL)
    settings_path = project / ".claude/settings.json"
    settings = load_object(settings_path) if settings_path.exists() else {}
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise DecisionError("settings hooks must be an object")
    for event in HOOK_EVENTS:
        entries = hooks.setdefault(event, [])
        if not isinstance(entries, list):
            raise DecisionError(f"settings hooks.{event} must be an array")
        command = (
            'python3 "${CLAUDE_PROJECT_DIR}/.claude/rhize-decision/typed_decision.py" '
            f'hook-{event[8:].lower()} --project "${{CLAUDE_PROJECT_DIR}}"'
        )
        entry = {"matcher": "^gsd-(planner|executor|verifier)$", "hooks": [{"type": "command", "command": command}]}
        if entry not in entries:
            entries.append(entry)
    source = Path(__file__).resolve()
    template = source.parent.parent / "skills/project-launcher/references/typed-decision-skill.md"
    if not template.is_file():
        raise DecisionError("project-local install must use the Project Launcher source copy")
    local_skill = project / SKILL / "SKILL.md"
    local_client = project / CLIENT
    local_skill.parent.mkdir(parents=True, exist_ok=True)
    local_client.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, local_skill)
    shutil.copyfile(source, local_client)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n")
    ignore_path = project / ".gitignore"
    ignore_line = "/.planning/decision-layer/receipts.jsonl"
    ignore_text = ignore_path.read_text() if ignore_path.exists() else ""
    if ignore_line not in ignore_text.splitlines():
        prefix = ignore_text.rstrip("\n")
        ignore_path.write_text((prefix + "\n" if prefix else "") + ignore_line + "\n")
    return {"status": "installed", "agents": AGENTS, "project": str(project)}


def validate_request(value: dict) -> None:
    state = value.get("state")
    questions = value.get("questions")
    if not isinstance(state, (str, dict, list)) or len(json.dumps(state)) > 12000:
        raise DecisionError("state must be a string, object, or array <= 12000 JSON characters")
    if not isinstance(questions, dict) or not 1 <= len(questions) <= 8:
        raise DecisionError("questions must contain 1-8 items")
    for name, question in questions.items():
        if not isinstance(name, str) or not name or not isinstance(question, dict):
            raise DecisionError("invalid question")
        kind = question.get("type")
        criteria = question.get("criteria")
        if kind == "choice" and (not isinstance(criteria, dict) or not 2 <= len(criteria) <= 8):
            raise DecisionError("choice criteria must have 2-8 labels")
        if kind == "score" and (not isinstance(criteria, list) or not 2 <= len(criteria) <= 8):
            raise DecisionError("score criteria must have 2-8 levels")
        if kind not in {"choice", "score", "noul"}:
            raise DecisionError("unsupported question type")


def probability(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def validate_result(request: dict, result: dict) -> None:
    answers = result.get("answers")
    usage = result.get("usage")
    if not isinstance(result.get("model"), str) or not result["model"]:
        raise DecisionError("response model missing")
    if not isinstance(answers, dict) or set(answers) != set(request["questions"]):
        raise DecisionError("response answers mismatch")
    if not isinstance(usage, dict) or any(
        not isinstance(usage.get(key), int) or isinstance(usage[key], bool) or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        raise DecisionError("response usage invalid")
    for name, question in request["questions"].items():
        answer = answers[name]
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise DecisionError(f"answer type mismatch: {name}")
        if question["type"] == "choice":
            probs = answer.get("probabilities")
            if (answer.get("choice") not in question["criteria"] or not probability(answer.get("confidence"))
                    or not isinstance(probs, dict) or set(probs) != set(question["criteria"])
                    or not all(probability(item) for item in probs.values())):
                raise DecisionError(f"choice answer invalid: {name}")
        elif question["type"] == "score":
            score = answer.get("score")
            if (not isinstance(score, (float, int)) or isinstance(score, bool)
                    or not 0 <= score <= len(question["criteria"]) - 1
                    or not probability(answer.get("confidence"))):
                raise DecisionError(f"score answer invalid: {name}")
        elif not probability(answer.get("noul")):
            raise DecisionError(f"noul answer invalid: {name}")


def endpoint() -> tuple[str, str, str]:
    base = os.environ.get("TYPESAFE_BASE_URL", "https://api.typesafe.ai").rstrip("/")
    parsed = urlparse(base)
    if base != "https://api.typesafe.ai" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise DecisionError("endpoint must be hosted Jev or loopback Laya")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DecisionError("endpoint URL has unsupported components")
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("LAYA_API_KEY", "")
    provider = "jev" if base == "https://api.typesafe.ai" else "compatible"
    if provider == "jev" and not key:
        raise DecisionError("TYPESAFE_API_KEY is missing")
    return base + "/v1/systemone", key, provider


def call_provider(request: dict) -> tuple[dict, int, str]:
    url, key, provider = endpoint()
    payload = dict(request)
    model = os.environ.get("TYPESAFE_DEFAULT_MODEL")
    if model:
        payload.setdefault("model", model)
    elif provider == "jev":
        payload.setdefault("model", "jev-latest")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    started = time.monotonic()
    try:
        with urlopen(Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST"), timeout=8) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise DecisionError("provider response too large")
        result = json.loads(raw)
    except (URLError, TimeoutError, ValueError) as exc:
        raise DecisionError(f"provider unavailable: {type(exc).__name__}") from exc
    if not isinstance(result, dict):
        raise DecisionError("provider response must be an object")
    validate_result(payload, result)
    return result, round((time.monotonic() - started) * 1000), provider


def append_receipt(project: Path, checkpoint: str, request: dict, result: dict | None, latency: int | None, provider: str | None, outcome: str, agent_id: str | None = None) -> dict:
    entry = {
        "schema": "rhize-typed-decision-v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "checkpoint": checkpoint, "variant": "B_decision_layer", "outcome": outcome,
        "agent_id": agent_id,
        "state_sha256": hashlib.sha256(json.dumps(request["state"], sort_keys=True).encode()).hexdigest(),
        "provider": provider, "model": result.get("model") if result else None,
        "latency_ms": latency, "usage": result.get("usage") if result else None,
    }
    target = project / RECEIPTS
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def decide(project: Path, checkpoint: str, request: dict, probe: bool = False, agent_id: str | None = None) -> dict:
    validate_request(request)
    if not checkpoint or len(checkpoint) > 80:
        raise DecisionError("checkpoint must be 1-80 characters")
    if agent_id is not None and (not agent_id or len(agent_id) > 128):
        raise DecisionError("agent_id must be 1-128 characters")
    mode = os.environ.get("RHIZE_DECISION_MODE", "shadow")
    if mode not in {"shadow", "advisory"}:
        raise DecisionError("RHIZE_DECISION_MODE must be shadow or advisory")
    try:
        result, latency, provider = call_provider(request)
    except DecisionError:
        append_receipt(project, checkpoint, request, None, None, None, "unavailable", agent_id)
        raise
    recommendations = {
        name: answer["choice"] for name, answer in result["answers"].items()
        if answer["type"] == "choice" and answer["confidence"] >= 0.70 and mode == "advisory"
    }
    outcome = "probe" if probe else ("shadow" if mode == "shadow" else ("advisory" if recommendations else "abstain"))
    receipt = append_receipt(project, checkpoint, request, result, latency, provider, outcome, agent_id)
    return {"status": outcome, "answers": result["answers"], "recommendations": recommendations, "receipt": receipt}


def status(project: Path) -> dict:
    config_path = project / ".planning/config.json"
    config = load_object(config_path) if config_path.exists() else {}
    mapping = config.get("agent_skills", {})
    mapped = isinstance(mapping, dict) and all(
        isinstance(mapping.get(agent), list) and SKILL in mapping[agent] for agent in AGENTS
    )
    installed = (project / CLIENT).is_file() and (project / SKILL / "SKILL.md").is_file()
    settings_path = project / ".claude/settings.json"
    settings = load_object(settings_path) if settings_path.exists() else {}
    hooks = settings.get("hooks", {})
    hooked = isinstance(hooks, dict) and all(
        isinstance(hooks.get(event), list) and any(
            isinstance(entry, dict)
            and entry.get("matcher") == "^gsd-(planner|executor|verifier)$"
            and any("typed_decision.py" in item.get("command", "") for item in entry.get("hooks", []) if isinstance(item, dict))
            for entry in hooks[event]
        ) for event in HOOK_EVENTS
    )
    fresh = False
    receipts = project / RECEIPTS
    if receipts.exists():
        with receipts.open() as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(item["at"])
                    if item.get("checkpoint") == "launch-probe" and item.get("outcome") == "probe" and 0 <= age.total_seconds() < 86400:
                        fresh = True
                except (KeyError, ValueError, TypeError):
                    continue
    return {"status": "ready" if installed and mapped and hooked and fresh else "blocked", "installed": installed, "mapped": mapped, "hooked": hooked, "fresh_probe": fresh}


def hook(project: Path, event: str, payload: dict) -> dict:
    agent_type = payload.get("agent_type")
    agent_id = payload.get("agent_id")
    if agent_type not in AGENTS or not isinstance(agent_id, str) or not agent_id:
        raise DecisionError("invalid GSD agent hook payload")
    if event == "SubagentStart":
        message = (
            f"Before finishing, call the project-local typed decision client with "
            f"--checkpoint {agent_type} --agent-id {agent_id}. "
            "Use a bounded, secret-free phase summary. This agent's SubagentStop hook checks its own receipt."
        )
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": message}}
    receipts = project / RECEIPTS
    if receipts.exists():
        with receipts.open() as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if item.get("agent_id") == agent_id and item.get("checkpoint") == agent_type:
                    return {}
    return {"decision": "block", "reason": f"Call the typed decision client for {agent_type} with --agent-id {agent_id}, then finish. Record unavailable/fallback if the provider fails."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "probe", "decide", "status", "hook-start", "hook-stop"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--checkpoint", default="unspecified")
    parser.add_argument("--agent-id")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if args.command == "install":
            output = install(project)
        elif args.command == "status":
            output = status(project)
        elif args.command == "probe":
            output = decide(project, "launch-probe", {"state": "Synthetic launch probe", "questions": {"readiness": {"type": "choice", "criteria": {"ready": "Working endpoint", "blocked": "Unavailable endpoint"}}}}, probe=True)
        elif args.command.startswith("hook-"):
            payload = json.load(sys.stdin)
            output = hook(project, "SubagentStart" if args.command == "hook-start" else "SubagentStop", payload)
        else:
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise DecisionError("stdin must contain a JSON object")
            output = decide(project, args.checkpoint, request, agent_id=args.agent_id)
        print(json.dumps(output, sort_keys=True))
        return 0 if output.get("status") != "blocked" else 1
    except (DecisionError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
