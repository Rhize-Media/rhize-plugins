"""Describe both assigned arms of the Claude skill trial; never writes labels or changes modes."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

STUDY = "claude-skill-advice-v1"


def load(path):
    return json.loads(path.read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def first_eligible(turns):
    return next((t for t in turns if t["eligible"]), None)


def reviewed_outcome(path, session, turn):
    """An independently prepared, private reviewer packet for the index task."""
    packet = load(path)
    if (packet.get("schema") != "claude-skill-task-review-v1" or packet.get("session") != session
            or packet.get("token") != turn["token"] or packet.get("promptHash") != turn["promptHash"]
            or packet.get("basis") not in ("explicit_user_review", "independent_verifier")
            or packet.get("result") not in ("accepted_without_rework", "material_rework", "unsuccessful")
            or type(packet.get("irrelevantInterruptions")) is not int or packet["irrelevantInterruptions"] < 0):
        raise ValueError("invalid index-task review")
    # The reviewer keeps its source next to the packet. Never follow an arbitrary packet-provided path.
    evidence = path.with_name("task-review.evidence")
    if evidence.is_symlink() or not evidence.is_file() or digest(evidence.read_bytes()) != packet.get("evidenceSha256"):
        raise ValueError("missing or changed review evidence")
    return packet


def report(root):
    cfg = load(root / "config.json")
    if cfg.get("study") != STUDY or cfg.get("population") not in ("live", "validation"):
        raise ValueError("unknown study configuration")
    result = {"study": STUDY, "population": cfg["population"], "enabled": cfg["enabled"],
              "start": cfg["start"], "end": cfg["end"], "arms": {}, "result": "descriptive_only"}
    for arm in ("control", "live"):
        result["arms"][arm] = dict.fromkeys(("assignedSessions", "observedTurns", "eligibleTurns", "nativeSkillCalls", "stoppedTurns", "wouldOffer", "malformedResponse", "unverifiedResponse", "awaitingStopOrInterrupted",
            "scoredOK", "shownAlternatives", "unconfirmedOffers", "feedback", "follow", "challenge",
            "neither", "abstain", "noResponse", "feedbackConflicts", "indexTasks", "outcomesJoined",
            "acceptedWithoutRework", "materialRework", "unsuccessful", "interruptionsOnCompletedTasks"), 0)
    for arm in result["arms"].values():
        arm.update(scoreStatus={}, feedbackReasons={}, measuredLatencyMs=[], indexTaskStrata={
            key: {"tasks": 0, "outcomesJoined": 0, "acceptedWithoutRework": 0}
            for key in ("would_offer", "no_alternative", "incompatible_or_unscored")})
    for assignment in sorted((root / "sessions").glob("*/assignment.json")):
        a = load(assignment)
        if a["study"] != STUDY or a["population"] != cfg["population"] or a["session"] != assignment.parent.name:
            raise ValueError("assignment binding mismatch")
        arm = result["arms"][a["arm"]]
        arm["assignedSessions"] += 1
        turns = sorted((load(p) for p in assignment.parent.glob("*.turn.json")), key=lambda t: (t["at"], t["token"]))
        for t in turns:
            if (t["session"] != a["session"] or t["arm"] != a["arm"]
                    or not re.fullmatch(r"[a-f0-9]{32}", t["token"])):
                raise ValueError("turn binding mismatch")
            arm["observedTurns"] += 1
            arm["eligibleTurns"] += int(t["eligible"])
            answer = (t["record"] or {}).get("laya", {})
            status = answer.get("status", "no_score")
            arm["scoreStatus"][status] = arm["scoreStatus"].get(status, 0) + 1
            arm["scoredOK"] += int(status == "ok")
            if isinstance(answer.get("latencyMs"), (int, float)):
                arm["measuredLatencyMs"].append(answer["latencyMs"])
            stem = t["token"]
            arm["stoppedTurns"] += int((assignment.parent / (stem + ".stop.json")).exists())
            for item in assignment.parent.glob(stem + ".*.skill.json"):
                call = load(item)
                if call["session"] != a["session"] or call["token"] != stem:
                    raise ValueError("skill invocation binding mismatch")
                arm["nativeSkillCalls"] += 1
            arm["wouldOffer"] += int(t["wouldOffer"])
            if not t["offered"]:
                continue
            token = t["token"]
            delivery = assignment.parent / (token + ".delivered.json")
            if not delivery.exists():
                arm["unconfirmedOffers"] += 1
                continue
            d = load(delivery)
            if a["arm"] != "live" or d["token"] != token or d["payloadHash"] != t["payloadHash"]:
                raise ValueError("delivery binding mismatch")
            arm["shownAlternatives"] += 1
            feedback = assignment.parent / (token + ".feedback.json")
            if not feedback.exists():
                if (assignment.parent / (token + ".unverified.json")).exists():
                    arm["unverifiedResponse"] += 1
                elif (assignment.parent / (token + ".malformed.json")).exists():
                    arm["malformedResponse"] += 1
                elif (assignment.parent / (token + ".stop.json")).exists():
                    arm["noResponse"] += 1
                else:
                    arm["awaitingStopOrInterrupted"] += 1
                continue
            f = load(feedback)
            if any(f[k] != t[k] for k in ("session", "token", "promptHash", "messageHash", "payloadHash")):
                raise ValueError("feedback binding mismatch")
            arm["feedback"] += 1
            if f["response"] not in ("follow", "challenge", "neither", "abstain"):
                raise ValueError("unknown feedback disposition")
            arm[f["response"]] += 1
            arm["feedbackReasons"][f["reason"]] = arm["feedbackReasons"].get(f["reason"], 0) + 1
            arm["feedbackConflicts"] += int((assignment.parent / (token + ".conflict.json")).exists())
        turn = first_eligible(turns)
        if turn:
            arm["indexTasks"] += 1
            key = "would_offer" if turn["wouldOffer"] else "no_alternative" if turn["compatible"] else "incompatible_or_unscored"
            subgroup = arm["indexTaskStrata"][key]
            subgroup["tasks"] += 1
            file = assignment.parent / "task-review.json"
            if file.exists():
                review = reviewed_outcome(file, a["session"], turn)
                arm["outcomesJoined"] += 1
                subgroup["outcomesJoined"] += 1
                subgroup["acceptedWithoutRework"] += int(review["result"] == "accepted_without_rework")
                arm[{"accepted_without_rework": "acceptedWithoutRework", "material_rework": "materialRework",
                     "unsuccessful": "unsuccessful"}[review["result"]]] += 1
                if review["result"] != "unsuccessful":
                    arm["interruptionsOnCompletedTasks"] += review["irrelevantInterruptions"]
    for arm in result["arms"].values():
        latency = sorted(arm.pop("measuredLatencyMs"))
        arm["latencyObservations"] = len(latency)
        arm["maxObservedModelMs"] = max(latency) if latency else None
        arm["assignedWithoutObservedIndexTask"] = arm["assignedSessions"] - arm["indexTasks"]
        arm["usage"] = None
        completed = arm["acceptedWithoutRework"] + arm["materialRework"]
        arm["missingTaskOutcomes"] = arm["indexTasks"] - arm["outcomesJoined"]
        arm["outcomeCoverage"] = arm["outcomesJoined"] / arm["indexTasks"] if arm["indexTasks"] else None
        arm["interruptionsPerReviewedCompletedTask"] = arm["interruptionsOnCompletedTasks"] / completed if completed else None
    control, live = (result["arms"][k] for k in ("control", "live"))
    # Worst/best missing outcomes on all randomized units, including silent sessions.
    if control["assignedSessions"] and live["assignedSessions"]:
        def bounds(arm):
            accepted, n = arm["acceptedWithoutRework"], arm["assignedSessions"]
            return accepted / n, (accepted + n - arm["outcomesJoined"]) / n
        c_min, c_max = bounds(control)
        l_min, l_max = bounds(live)
        result["acceptanceDifferenceMissingOutcomeBounds"] = [l_min - c_max, l_max - c_min]
    else:
        result["acceptanceDifferenceMissingOutcomeBounds"] = None
    result["sufficientForIndependentReview"] = cfg["population"] == "live" and all(
        a["outcomesJoined"] >= 50 and a["outcomesJoined"] >= .8 * a["assignedSessions"]
        and not a["feedbackConflicts"] for a in (control, live))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(os.environ.get("RHIZE_SKILL_STUDY_ROOT",
                   Path.home() / ".local/share/rhize/skill-advice-study")))
    try:
        print(json.dumps(report(p.parse_args().root), sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError) as error:
        p.exit(1, f"Study report unavailable: {error}\n")
