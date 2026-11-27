"""Prepare shared-agenda updates from verified provider reads. JSON stdin/stdout, no network."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys

from delegation_lint import lint


def instant(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("An explicit timezone is required")
    return stamp.astimezone(timezone.utc)


def meeting_window(data):
    now = instant(data["now"])
    people = {email.casefold() for email in data["editors"]}
    if len(people) != 2:
        raise ValueError("Expected two distinct editors")
    meetings = {}
    for event in data["events"]:
        series = event.get("recurringEventId")
        if series not in data["seriesIds"] or event.get("status") != "confirmed":
            continue
        if event.get("attendeesOmitted") or not event.get("start", {}).get("dateTime"):
            continue
        attendees = event.get("attendees", [])
        organizer = event.get("organizer", {}).get("email", "").casefold()
        audience = {p.get("email", "").casefold() for p in attendees} | {organizer}
        if audience != people or any(p.get("responseStatus") == "declined" for p in attendees):
            continue
        original = instant(event["originalStartTime"]["dateTime"]).isoformat()
        meetings[(series, original)] = event
    previous, following = [], []
    for event in meetings.values():
        start = instant(event["start"]["dateTime"])
        if start > now:
            following.append((start, event))
        elif instant(event["end"]["dateTime"]) <= now:
            previous.append((start, event))
    last = max((t for t, _ in previous), default=None)
    first = min((t for t, _ in following), default=None)
    return {"previous": [e for t, e in previous if t == last],
            "next": [e for t, e in following if t == first]}


def jira_rows(data):
    start, cutoff = instant(data["since"]), instant(data["asOf"])
    if cutoff <= start:
        raise ValueError("Invalid meeting window")
    visible = set(data["sharedIssueIds"])
    categories = data["statusCategories"]
    rows = {}
    for issue in data["issues"]:
        issue_id = issue["id"]
        if issue_id not in visible:
            continue
        key = issue["key"]
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*", key) or not issue_id.isdecimal():
            raise ValueError("Invalid Jira issue identity")
        fields = issue["fields"]
        kinds = []
        if start <= instant(fields["created"]) < cutoff:
            kinds.append("Created")
        for history in issue["history"]:
            if not start <= instant(history["created"]) < cutoff:
                continue
            for item in history["items"]:
                if item.get("fieldId", item.get("field")) != "status":
                    continue
                if categories[item["to"]] == "done" and (not item.get("from") or categories[item["from"]] != "done"):
                    kinds.append("Completed")
        for kind in set(kinds):
            rows[(kind, key)] = {"id": f"{issue_id}-{kind}",
                                 "text": f"{kind} · {key} · {' '.join(fields['summary'].split())}",
                                 "url": f"{data['baseUrl']}/browse/{key}"}
    return [rows[k] for k in sorted(rows)]


def anchor(*parts):
    return "agenda_" + hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def line(value):
    if (not value.strip() or not value.isprintable()
            or any(f["severity"] == "FAIL" for f in lint(value, "attachment-body", 1500, 3000))):
        raise ValueError("Unsafe agenda text")
    return value


def units(text):
    return len(text.encode("utf-16-le")) // 2


def docs_update(data):
    doc = data["document"]
    if doc["documentId"] != data["documentId"] or not doc["revisionId"]:
        raise ValueError("Agenda identity or revision missing")
    group = data["group"]
    if group not in ("discussion", "jira"):
        raise ValueError("Unknown agenda section")
    meeting = anchor(data["seriesId"], instant(data["originalStart"]).isoformat())
    section = anchor(meeting, group)
    content = doc
    if doc.get("tabs") is not None:
        tabs = doc["tabs"]
        if len(tabs) != 1 or tabs[0].get("childTabs") or tabs[0].get("parentTabId"):
            raise ValueError("Select a single-tab agenda")
        content = tabs[0].get("documentTab", tabs[0])
    ranges = content.get("namedRanges") or {}
    paragraphs = content["body"]["content"]

    def after_heading(name):
        names = ranges[name]["namedRanges"]
        if len(names) != 1 or len(names[0]["ranges"]) != 1:
            raise ValueError("Ambiguous agenda heading")
        index = names[0]["ranges"][0]["startIndex"]
        for p in paragraphs:
            if p.get("startIndex", 0) <= index < p["endIndex"] and "paragraph" in p:
                return p["endIndex"]
        raise ValueError("Agenda heading unavailable")

    pending = {}
    for row in data["rows"]:
        if not row["id"]:
            raise ValueError("Missing row ID")
        name = anchor(section, row["id"])
        if name not in ranges:
            pending[name] = row
    if not pending and (group != "jira" or section in ranges):
        return {"requests": [], "status": "already present"}
    lines = []
    if section in ranges:
        index = after_heading(section)
    else:
        index = after_heading(meeting) if meeting in ranges else 1
        if meeting not in ranges:
            lines.append((meeting, line(data["meetingLabel"]), "HEADING_1", None))
        lines.append((section, line(data["sectionLabel"]), "HEADING_2", None))
    for name, row in pending.items():
        url = row.get("url")
        if url and not re.fullmatch(r"https://[^\s<>]+", url):
            raise ValueError("Invalid task URL")
        lines.append((name, "• " + line(row["text"]), "NORMAL_TEXT", url))
    # Google reserves the final newline. A human may have deleted our trailing blank.
    prefix = ""
    if index >= paragraphs[-1]["endIndex"]:
        index = paragraphs[-1]["endIndex"] - 1
        prefix = "\n"
    text = prefix + "".join(value + "\n" for _, value, _, _ in lines)
    requests = [{"insertText": {"location": {"index": index}, "text": text}}]
    pos = index + len(prefix)
    for name, value, style, url in lines:
        end = pos + units(value)
        span = {"startIndex": pos, "endIndex": end}
        requests.append({"updateParagraphStyle": {"range": span,
                         "paragraphStyle": {"namedStyleType": style}, "fields": "namedStyleType"}})
        requests.append({"createNamedRange": {"name": name, "range": span}})
        if url:
            requests.append({"updateTextStyle": {"range": span, "textStyle": {"link": {"url": url}},
                                                 "fields": "link"}})
        pos = end + 1
    return {"writeControl": {"requiredRevisionId": doc["revisionId"]}, "requests": requests}


def main():
    modes = {"window": meeting_window, "jira": jira_rows, "docs": docs_update}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=modes)
    try:
        print(json.dumps(modes[parser.parse_args().operation](json.load(sys.stdin))))
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        print(f"Agenda input could not be verified ({type(exc).__name__})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
