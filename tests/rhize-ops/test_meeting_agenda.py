import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "rhize-ops/scripts/meeting_agenda.py"
PAIR = ["alex@example.org", "jo@example.org"]
START = "2026-03-09T13:00:00Z"


def run(operation, **data):
    result = subprocess.run([sys.executable, str(SCRIPT), operation], input=json.dumps(data),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def event(key, start, end, **changes):
    return {"id": key, "recurringEventId": key, "originalStartTime": {"dateTime": start},
            "start": {"dateTime": start}, "end": {"dateTime": end}, "status": "confirmed",
            "organizer": {"email": PAIR[0]}, "attendees": [{"email": PAIR[1]}], **changes}


def test_real_occurrences_across_series_weekend_and_dst():
    previous = event("midweek", "2026-03-05T12:00:00-05:00", "2026-03-05T13:00:00-05:00")
    following = event("weekly", START, "2026-03-09T14:00:00Z")
    friday = event("midweek", "2026-03-06T12:00:00-05:00", "2026-03-06T13:00:00-05:00")
    result = run("window", now="2026-03-06T10:00:00-05:00", editors=PAIR, seriesIds=["weekly", "midweek"],
                 events=[dict(friday, status="cancelled"), previous, following,
                         dict(friday, attendees=[{"email": PAIR[1], "responseStatus": "declined"}]),
                         dict(friday, attendeesOmitted=True),
                         dict(friday, attendees=[{"email": PAIR[1]}, {"email": "other@example.org"}])])
    assert result == {"previous": [previous], "next": [following]}


def test_move_and_tie_are_visible_and_no_match_is_empty():
    moved = event("a", START, "2026-03-09T14:00:00Z", originalStartTime={"dateTime": "2026-03-07T13:00:00Z"})
    other = dict(moved, id="b", recurringEventId="b")
    args = dict(now="2026-03-08T00:00:00Z", editors=PAIR, seriesIds=["a", "b"])
    assert run("window", **args, events=[moved, other]) == {"previous": [], "next": [moved, other]}
    assert run("window", **args, events=[]) == {"previous": [], "next": []}


def test_created_completed_reopened_and_issue_visibility():
    cutoff = "2026-03-10T13:00:00Z"
    def change(at, before, after):
        return {"created": at, "items": [{"fieldId": "status", "from": before, "to": after}]}
    issue = {"id": "55", "key": "APP-1", "fields": {"summary": "Demo", "created": START},
             "history": [change(START, "1", "2"), change(START, "2", "3"), change(START, "3", "1")]}
    others = [dict(issue, id="56", key="APP-2"), dict(issue, id="57", key="APP-3",
              fields={"created": cutoff, "summary": "Outside"}, history=[change(cutoff, "1", "2")]),
              dict(issue, id="58", key="APP-4", fields={"created": "2025-01-01T00:00:00Z", "summary": "Old"},
                   history=[change(START, "2", "3")])]
    rows = run("jira", since=START, asOf=cutoff, baseUrl="https://example.atlassian.net",
               sharedIssueIds=["55", "57", "58"], statusCategories={"1": "new", "2": "done", "3": "done"},
               issues=[issue, *others])
    assert {r["id"] for r in rows} == {"55-Created", "55-Completed"}
    assert all(r["url"] == "https://example.atlassian.net/browse/APP-1" for r in rows)


def write_args():
    return dict(document={"documentId": "doc", "revisionId": "r3", "body": {"content": [
                {"startIndex": 1, "endIndex": 2, "paragraph": {}}]}}, documentId="doc",
                seriesId="a", originalStart=START, meetingLabel="Team meeting",
                group="discussion", sectionLabel="Discussion", rows=[{"id": "task", "text": "📅 Decide"}])


def test_conditional_edits_utf16_and_retry():
    args = write_args()
    plan = run("docs", **args)
    assert plan["writeControl"] == {"requiredRevisionId": "r3"}
    ranges = [r["createNamedRange"] for r in plan["requests"] if "createNamedRange" in r]
    assert len(ranges) == 3
    assert ranges[-1]["range"]["endIndex"] - ranges[-1]["range"]["startIndex"] == len("• 📅 Decide") + 1
    args["document"]["namedRanges"] = {r["name"]: {"namedRanges": [{"ranges": [r["range"]]}]} for r in ranges}
    assert run("docs", **args)["requests"] == []
    args["document"]["body"]["content"] = [{"startIndex": 1, "endIndex": 14, "paragraph": {}},
        {"startIndex": 14, "endIndex": 25, "paragraph": {}}, {"startIndex": 25, "endIndex": 42, "paragraph": {}}]
    args["rows"].append({"id": "other", "text": "Next item"})
    second = run("docs", **args)["requests"][0]["insertText"]
    assert second == {"location": {"index": 25}, "text": "• Next item\n"}


def test_skip_and_empty_jira_recap():
    args = write_args()
    args["rows"] = []
    assert run("docs", **args)["requests"] == []
    args.update(group="jira", sectionLabel="Jira activity since Friday")
    assert "Jira activity since Friday" in run("docs", **args)["requests"][0]["insertText"]["text"]


@pytest.mark.parametrize("row", [{"id": "t", "text": "See /Users/example/private"},
                                 {"id": "t", "text": "two\nlines"},
                                 {"id": "t", "text": "link", "url": "http://example.org"}])
def test_unsafe_external_text_is_rejected(row):
    args = write_args()
    args["rows"] = [row]
    result = subprocess.run([sys.executable, str(SCRIPT), "docs"], input=json.dumps(args),
                            text=True, capture_output=True)
    assert result.returncode == 2 and not result.stdout


def test_jira_reader_pages_and_checks_the_actual_issue(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    from agenda_jira import collect
    requests = []
    issue = {"id": "123", "key": "TEAM-1", "fields": {"summary": "Review", "created": START}}
    def read(endpoint, params=None):
        requests.append((endpoint, dict(params or {})))
        if endpoint == "myself":
            return {"timeZone": "America/New_York"}
        if endpoint == "status":
            return [{"id": "1", "statusCategory": {"key": "new"}}, {"id": "2", "statusCategory": {"key": "done"}}]
        if endpoint == "search/jql":
            if params.get("nextPageToken"):
                return {"issues": [dict(issue, id="124", key="TEAM-2")]}
            return {"issues": [issue], "nextPageToken": "page2"}
        if endpoint == "user/viewissue/search":
            return [{"accountId": "person", "active": True}] if params["issueKey"] == "TEAM-1" else []
        if endpoint == "issue/TEAM-1/changelog":
            history = {"created": START, "items": [{"field": "status", "from": "1", "to": "2"}]}
            return {"startAt": params["startAt"], "values": [history], "total": 2}
        pytest.fail(endpoint)
    result = collect(read, ["TEAM"], "person", "https://example.atlassian.net", START, "2026-03-10T12:00:00Z")
    assert result["coverage"] == "limited"
    assert {r["id"] for r in result["rows"]} == {"123-Created", "123-Completed"}
    searches = [p for e, p in requests if e == "search/jql"]
    assert len(searches) == 2 and 'project in ("TEAM")' in searches[0]["jql"]
    assert [p["startAt"] for e, p in requests if e.endswith("/changelog")] == [0, 1]
