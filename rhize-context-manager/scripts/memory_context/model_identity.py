"""Resolve model metadata without guessing aliases or retaining transcript content."""
import json
import os
from pathlib import Path
import re

MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/\[\]-]{0,127}")
MAX_TAIL = 262144


def valid_model(value):
    return value if isinstance(value, str) and MODEL.fullmatch(value) else None


def resolve_model(host, event, session):
    explicit = valid_model(event.get("model"))
    if explicit:
        return explicit, "hook_event"
    # The native hook supplies the path. Only read a bounded tail from the matching
    # session under Claude's transcript root; never search unrelated sessions.
    if host == "claude" and isinstance(event.get("transcript_path"), str):
        path = Path(event["transcript_path"]).expanduser().absolute()
        root = Path.home() / ".claude/projects"
        try:
            path.relative_to(root)
            if (".." in path.parts or path.suffix != ".jsonl" or path.stem != event.get("session_id")
                    or any(p.is_symlink() for p in (path, *path.parents))):
                raise ValueError("untrusted transcript path")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                size = os.fstat(stream.fileno()).st_size
                stream.seek(max(0, size - MAX_TAIL))
                lines = stream.read(MAX_TAIL).splitlines()
            for line in reversed(lines):
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or row.get("sessionId") != event.get("session_id"):
                    continue
                message = row.get("message")
                if row.get("type") == "assistant" and isinstance(message, dict):
                    model = valid_model(message.get("model"))
                    if model:
                        return model, "session_transcript_last_assistant"
        except (OSError, ValueError):
            pass
    model = valid_model(session.get("model"))
    return (model, "session_event_cache") if model else (None, "unavailable")


def answer_eligibility(prompt):
    """Conservative routing label, never a semantic correctness judgment."""
    actions = r"(?:implement|fix|edit|change|deploy|publish|send|delete|proceed|commit|push|run)"
    if re.search(r"(?:^|[\n.!?]\s*|\bthen\s+|\band\s+)(?:please\s+)?" + actions + r"\b", prompt, re.I):
        return "action_request"
    if re.match(r"\s*(?:what|which|how|why|when|where|who|recall|summarize|explain|list|describe)\b", prompt, re.I):
        return "bounded_question_candidate"
    return "unclassified_request"
