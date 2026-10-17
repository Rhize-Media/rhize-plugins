#!/usr/bin/env python3
"""Project-local Jev/Laya client and GSD installer; standard library only."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

SKILL = "skills/rhize-typed-decision"
CLIENT = ".claude/rhize-decision/typed_decision.py"
ADVICE_CLIENT = ".claude/rhize-decision/typed_advice.py"
RECEIPTS = ".planning/decision-layer/receipts.jsonl"
AGENTS = ("gsd-planner", "gsd-executor", "gsd-verifier")
HOOK_EVENTS = ("SubagentStart", "SubagentStop")
LOCAL_LAYA_ENV = {
    "RHIZE_DECISION_MODE": "advisory",
    "TYPESAFE_BASE_URL": "http://127.0.0.1:8000",
    "TYPESAFE_DEFAULT_MODEL": "typed-decisions",
}
GSD_DECISION = "gsd-directive"
GSD_QUESTION = "Which directive best fits this GSD checkpoint, given the evidence summary and check status?"
GSD_CANDIDATES = (
    ("continue", "Continue the current work as planned."),
    ("investigate", "Investigate drift, a stuck worker or a trace risk before proceeding."),
    ("verify", "Run further independent verification before finishing."),
    ("escalate", "Ask a human for input or approval now."),
    ("finish_candidate", "The work looks complete; checks and independent review have passed."),
)
# The registry binding covers the full candidate set; per-call suppression of finish_candidate never changes it.
GSD_POLICY = {"candidates": [item[0] for item in GSD_CANDIDATES], "version": 1}
SUPERVISOR_CHECKS = {
    "gsd-planner": {
        "requirements_covered": "Does the plan cover every stated requirement with a concrete verification route?",
        "skill_workflow_fit": "Are the selected skill and workflow candidates relevant to the stated plan?",
        "graph_context_relevant": "Are the included source-bound graph and code context candidates relevant to this plan?",
        "context_retention_safe": "Will planned context compaction preserve requirements, decisions, and unresolved risks?",
        "worker_route_fit": "Are the pre-authorized worker choices suitable for this plan?",
        "planning_uncertainty": "Does unresolved uncertainty materially threaten the plan?",
        "needs_human": "Does this decision require human input or approval now?",
    },
    "gsd-executor": {
        "implementation_complete": "Is the requested implementation complete based on the observed evidence?",
        "meaningful_progress": "Is the worker making meaningful progress toward the request?",
        "worker_stuck": "Is the worker looping or repeatedly failing without progress?",
        "work_off_track": "Is the work materially drifting from the requested outcome?",
        "agents_md_drift": "Does the work conflict with repository agent instructions?",
        "model_route_fit": "Is the pre-authorized model choice suitable for the current implementation work?",
        "tool_trace_risk": "Do observed tool or trace signals warrant additional risk review?",
        "needs_human": "Does the work require human input or approval now?",
    },
    "gsd-verifier": {
        "implementation_complete": "Is the requested implementation complete based on the observed evidence?",
        "requirements_satisfied": "Does the result satisfy every stated requirement?",
        "ready_to_finish": "Is there enough evidence to consider this task complete?",
        "tests_sufficient": "Do the executed tests adequately cover the changed behavior and risks?",
        "browser_qa_complete": "If browser QA is applicable, do its functional, error, accessibility and responsive checks have evidence?",
        "needs_verification": "Is further independent verification needed?",
        "agents_md_drift": "Does the result conflict with repository agent instructions?",
        "needs_human": "Does completion require human input or approval now?",
    },
}


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


def install(project: Path, local_laya: bool = False) -> dict:
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
    if local_laya:
        env = settings.setdefault("env", {})
        if not isinstance(env, dict):
            raise DecisionError("settings env must be an object")
        env.update(LOCAL_LAYA_ENV)
    source = Path(__file__).resolve()
    advice_source = source.parent / "typed_advice.py"
    if not advice_source.is_file():
        raise DecisionError("project-local install needs typed_advice.py beside the Project Launcher client")
    template = source.parent.parent / "skills/project-launcher/references/typed-decision-skill.md"
    if not template.is_file():
        raise DecisionError("project-local install must use the Project Launcher source copy")
    local_skill = project / SKILL / "SKILL.md"
    local_client = project / CLIENT
    local_skill.parent.mkdir(parents=True, exist_ok=True)
    local_client.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, local_skill)
    shutil.copyfile(source, local_client)
    shutil.copyfile(advice_source, project / ADVICE_CLIENT)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n")
    ignore_path = project / ".gitignore"
    ignore_line = "/.planning/decision-layer/receipts.jsonl"
    ignore_text = ignore_path.read_text() if ignore_path.exists() else ""
    if ignore_line not in ignore_text.splitlines():
        prefix = ignore_text.rstrip("\n")
        ignore_path.write_text((prefix + "\n" if prefix else "") + ignore_line + "\n")
    return {"status": "installed", "agents": AGENTS, "project": str(project), "local_laya": local_laya}


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
        instructions = question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip() or len(instructions) > 1000:
            raise DecisionError("question instructions must be 1-1000 characters")
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
    if "routing" in result and not isinstance(result["routing"], dict):
        raise DecisionError("response routing invalid")
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


class _NoRedirect(HTTPRedirectHandler):
    # A 3xx is an error here (HTTPError), so the Authorization header is never re-sent to another URL.
    def redirect_request(self, *args, **kwargs):
        return None


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
        opener = build_opener(ProxyHandler({}), _NoRedirect())  # no env proxy, no redirects: the key goes only to `url`
        with opener.open(Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST"), timeout=8) as response:
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


def append_receipt(project: Path, checkpoint: str, request: dict, result: dict | None, latency: int | None, provider: str | None, outcome: str, agent_id: str | None = None, advice: dict | None = None) -> dict:
    routing = result.get("routing", {}) if result else {}
    if not isinstance(routing, dict):
        routing = {}
    entry = {
        "schema": "rhize-typed-decision-v1", "at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "checkpoint": checkpoint, "variant": "B_decision_layer", "outcome": outcome,
        "question_ids": sorted(request["questions"]),
        "agent_id": agent_id,
        "state_sha256": hashlib.sha256(json.dumps(request["state"], sort_keys=True).encode()).hexdigest(),
        "provider": provider, "model": result.get("model") if result else None,
        "requested_model": request.get("model") or os.environ.get("TYPESAFE_DEFAULT_MODEL"),
        "routed_model": routing.get("model"), "checkpoint_repo": routing.get("repo"),
        "latency_ms": latency, "usage": result.get("usage") if result else None,
    }
    if (result and checkpoint in SUPERVISOR_CHECKS
            and set(request["questions"]) == set(SUPERVISOR_CHECKS[checkpoint])
            and isinstance(request["state"], dict)):
        entry["assessment"] = {name: result["answers"][name]["noul"] for name in SUPERVISOR_CHECKS[checkpoint]}
        entry["candidate_directive"] = candidate_directive(checkpoint, result["answers"], request["state"])
    if advice:
        recommendation = advice.get("recommendation") or {}
        entry["decision_id"] = advice["decisionId"]
        entry["advice"] = {"mode": advice["mode"], "holdback": advice["holdback"], "recommended": recommendation.get("id")}
    target = project / RECEIPTS
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def checks_and_review_passed(state: dict) -> bool:
    return state.get("required_checks_passed") is True and state.get("independent_review_passed") is True


def candidate_directive(checkpoint: str, answers: dict, state: dict) -> str:
    """Foreman-style deterministic proposal; never executes an intervention."""
    def yes(name: str, threshold: float) -> bool:
        answer = answers.get(name, {})
        return isinstance(answer, dict) and probability(answer.get("noul")) and answer["noul"] >= threshold

    if yes("needs_human", 0.80):
        return "escalate"
    if yes("agents_md_drift", 0.80) or yes("work_off_track", 0.80) or yes("worker_stuck", 0.80) or yes("tool_trace_risk", 0.80):
        return "investigate"
    if checkpoint == "gsd-planner" and state.get("compaction_performed") is True and not yes("context_retention_safe", 0.75):
        return "investigate"
    if checkpoint == "gsd-verifier":
        if state.get("browser_qa_applicable") is True and not yes("browser_qa_complete", 0.75):
            return "verify"
        if yes("needs_verification", 0.65) or not yes("tests_sufficient", 0.75):
            return "verify"
        if (all(yes(name, 0.75) for name in ("implementation_complete", "requirements_satisfied", "ready_to_finish"))
                and checks_and_review_passed(state)):
            return "finish_candidate"
    return "continue"


_ADVICE_MODULE: list = []


def advice_module():
    """The sibling typed_advice.py (loaded once), or None when it is not installed."""
    if not _ADVICE_MODULE:
        path = Path(__file__).with_name("typed_advice.py")
        module = None
        if path.is_file():
            spec = importlib.util.spec_from_file_location("typed_advice", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        _ADVICE_MODULE.append(module)
    return _ADVICE_MODULE[0]


def local_laya_endpoint() -> str | None:
    """The literal-loopback base URL typed_advice accepts when TYPESAFE_BASE_URL names a local server."""
    parsed = urlparse(os.environ.get("TYPESAFE_BASE_URL", ""))
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return None
    return f"http://{'[::1]' if parsed.hostname == '::1' else '127.0.0.1'}:{parsed.port or 80}"


def decision_mode() -> dict:
    """Configured env mode, the registry's effective mode for gsd-directive, and whether local Laya is set."""
    configured = os.environ.get("RHIZE_DECISION_MODE", "shadow")
    local = local_laya_endpoint() is not None
    advice = advice_module()
    effective = "shadow"
    if configured == "advisory" and local and advice is not None:
        effective = advice.effective_mode(GSD_DECISION, advice.policy_sha256(GSD_DECISION, GSD_QUESTION, GSD_POLICY))
    return {"configured_mode": configured, "effective_mode": effective, "local_laya": local,
            "advice_client": advice is not None}


def advise_gsd(project: Path, checkpoint: str, state: dict, agent_id: str | None) -> dict | None:
    """Ask local Laya for an advisory directive. None unless advisory mode with local Laya; never raises.

    The directive is text for the agent only: no gate, verification step or hook result reads it.
    """
    endpoint_url = local_laya_endpoint()
    advice = advice_module()
    if os.environ.get("RHIZE_DECISION_MODE") != "advisory" or endpoint_url is None or advice is None:
        return None
    passed = checks_and_review_passed(state)
    candidates = [{"id": name, "criterion": text} for name, text in GSD_CANDIDATES if passed or name != "finish_candidate"]
    state_sha = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    summary = state["summary"] if isinstance(state.get("summary"), str) else json.dumps(state, sort_keys=True)
    request = (f"{checkpoint} required_checks_passed={state.get('required_checks_passed') is True} "
               f"independent_review_passed={state.get('independent_review_passed') is True} {summary}")
    try:
        return advice.advise(GSD_DECISION, request, candidates, f"{agent_id or project}:{checkpoint}:{state_sha}",
                             critical_if_wrong=not passed, question=GSD_QUESTION, policy=GSD_POLICY,
                             endpoint=endpoint_url)
    except Exception:  # noqa: BLE001 - advice must never break supervision
        return None


def supervise(project: Path, checkpoint: str, state: dict, agent_id: str | None = None) -> dict:
    if checkpoint not in SUPERVISOR_CHECKS or not isinstance(state, dict):
        raise DecisionError("supervise requires a GSD checkpoint and object state")
    request = {"state": state, "questions": {
        name: {"type": "noul", "instructions": instruction}
        for name, instruction in SUPERVISOR_CHECKS[checkpoint].items()
    }}
    advice = advise_gsd(project, checkpoint, state, agent_id)
    result = decide(project, checkpoint, request, agent_id=agent_id, advice=advice)
    result["candidate_directive"] = candidate_directive(checkpoint, result["answers"], state)
    if advice:
        result["decision_id"] = advice["decisionId"]
        line = advice_module().advice_line(GSD_DECISION, advice, "the next GSD directive")
        if line:
            result["advice"] = line
    return result


def record_outcome(decision_id: str, chosen: str) -> dict:
    advice = advice_module()
    if advice is None:
        raise DecisionError("typed_advice.py is not installed beside the client")
    return {"status": "recorded" if advice.record_outcome(GSD_DECISION, decision_id, chosen) else "not_recorded"}


def decide(project: Path, checkpoint: str, request: dict, probe: bool = False, agent_id: str | None = None, advice: dict | None = None) -> dict:
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
        append_receipt(project, checkpoint, request, None, None, None, "unavailable", agent_id, advice)
        raise
    requested_model = request.get("model") or os.environ.get("TYPESAFE_DEFAULT_MODEL")
    if probe and provider == "compatible" and requested_model and result.get("routing", {}).get("model") != requested_model:
        append_receipt(project, checkpoint, request, result, latency, provider, "route_mismatch", agent_id)
        raise DecisionError("local provider routed a different checkpoint than requested")
    recommendations = {
        name: answer["choice"] for name, answer in result["answers"].items()
        if answer["type"] == "choice" and answer["confidence"] >= 0.70 and mode == "advisory"
    }
    if mode == "advisory" and advice and advice.get("recommendation"):
        recommendations[GSD_DECISION] = advice["recommendation"]["id"]
    status_value = "probe" if probe else ("shadow" if mode == "shadow" else ("advisory" if recommendations else "abstain"))
    receipt = append_receipt(project, checkpoint, request, result, latency, provider, status_value, agent_id, advice)
    return {"status": status_value, "answers": result["answers"], "recommendations": recommendations, "receipt": receipt}


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
        latest_probe = None
        with receipts.open() as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                    if item.get("checkpoint") == "launch-probe":
                        latest_probe = item
                except (ValueError, TypeError):
                    continue
        if latest_probe:
            try:
                age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(latest_probe["at"])
                _, _, current_provider = endpoint()
                route_ok = (latest_probe.get("provider") == current_provider and (
                    current_provider != "compatible" or (
                        latest_probe.get("requested_model")
                        and latest_probe.get("requested_model") == os.environ.get("TYPESAFE_DEFAULT_MODEL")
                        and latest_probe.get("routed_model") == latest_probe["requested_model"]
                    )
                ))
                fresh = latest_probe.get("outcome") == "probe" and route_ok and 0 <= age.total_seconds() < 86400
            except (DecisionError, KeyError, ValueError, TypeError):
                pass
    return {"status": "ready" if installed and mapped and hooked and fresh else "blocked", "installed": installed, "mapped": mapped, "hooked": hooked, "fresh_probe": fresh, **decision_mode()}


def hook(project: Path, event: str, payload: dict) -> dict:
    agent_type = payload.get("agent_type")
    agent_id = payload.get("agent_id")
    if agent_type not in AGENTS or not isinstance(agent_id, str) or not agent_id:
        raise DecisionError("invalid GSD agent hook payload")
    if event == "SubagentStart":
        if decision_mode()["effective_mode"] == "advise":
            tail = ("The output may carry an `advice` line from Laya; it is advisory and never replaces tests, review or "
                    "approval gates. Afterwards record what you did with `outcome --decision-id <decision_id> --chosen <directive>`. ")
        else:
            tail = "The suggested action is shadow-only. "
        message = (
            f"Before finishing, call the project-local typed decision client: supervise "
            f"--checkpoint {agent_type} --agent-id {agent_id}. "
            "Pipe a bounded, secret-free JSON evidence object on stdin. " + tail +
            "This agent's SubagentStop hook checks its own receipt."
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
                if (item.get("agent_id") == agent_id and item.get("checkpoint") == agent_type
                        and item.get("question_ids") == sorted(SUPERVISOR_CHECKS[agent_type])):
                    return {}
    return {"decision": "block", "reason": f"Call the typed decision client for {agent_type} with --agent-id {agent_id}, then finish. Record unavailable/fallback if the provider fails."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "probe", "decide", "supervise", "status", "outcome", "hook-start", "hook-stop"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--checkpoint", default="unspecified")
    parser.add_argument("--agent-id")
    parser.add_argument("--local-laya", action="store_true", help="install: write local Laya advisory env (no secrets)")
    parser.add_argument("--decision-id", help="outcome: decision id from the supervise output")
    parser.add_argument("--chosen", help="outcome: the directive actually taken")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if args.command == "install":
            output = install(project, local_laya=args.local_laya)
        elif args.command == "status":
            output = status(project)
        elif args.command == "probe":
            output = decide(project, "launch-probe", {"state": "Synthetic launch probe", "questions": {"readiness": {"type": "choice", "instructions": "Is this decision endpoint available?", "criteria": {"ready": "Working endpoint", "blocked": "Unavailable endpoint"}}}}, probe=True)
        elif args.command.startswith("hook-"):
            payload = json.load(sys.stdin)
            output = hook(project, "SubagentStart" if args.command == "hook-start" else "SubagentStop", payload)
        elif args.command == "outcome":
            if not args.decision_id or not args.chosen:
                raise DecisionError("outcome requires --decision-id and --chosen")
            output = record_outcome(args.decision_id, args.chosen)
        elif args.command == "supervise":
            output = supervise(project, args.checkpoint, json.load(sys.stdin), agent_id=args.agent_id)
        else:
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise DecisionError("stdin must contain a JSON object")
            output = decide(project, args.checkpoint, request, agent_id=args.agent_id)
        print(json.dumps(output, sort_keys=True))
        return 0 if output.get("status") not in ("blocked", "not_recorded") else 1
    except (DecisionError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
