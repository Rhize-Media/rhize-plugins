"""Read shared Jira Cloud activity for a configured meeting. Never mutates Jira."""
import argparse
import base64
import http.client
import json
import re
import sys
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from jira_attach import DEFAULT_CONFIG_PATH, read_credentials
from meeting_agenda import instant, jira_rows


def collect(read, projects, recipient_id, base, since, as_of):
    start = instant(since)
    if start >= instant(as_of):
        raise ValueError("Invalid interval")
    if not isinstance(projects, list) or any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", k) for k in projects):
        raise ValueError("Invalid Jira scope")
    user = read("myself")
    day = start.astimezone(ZoneInfo(user["timeZone"])).date()
    jql = f'updated >= "{day}"'
    if projects:
        jql += " AND project in (" + ",".join('"' + k + '"' for k in projects) + ")"
    params = {"jql": jql + " ORDER BY key", "fields": "summary,created,security", "maxResults": 100}
    categories = {s["id"]: s["statusCategory"]["key"] for s in read("status")}
    rows, tokens = {}, set()
    limited = False
    while True:
        page = read("search/jql", params)
        for issue in page["issues"]:
            key = issue["key"]
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*-[1-9][0-9]*", key):
                raise ValueError("Invalid issue key")
            users = read("user/viewissue/search", {"issueKey": key, "accountId": recipient_id})
            if not any(u["accountId"] == recipient_id and u.get("active") is True for u in users):
                limited = True
                continue
            # Security schemes may further restrict a project browse permission.
            if issue["fields"].get("security"):
                limited = True
                continue
            history = []
            while True:
                log = read(f"issue/{key}/changelog", {"startAt": len(history), "maxResults": 100})
                if log["startAt"] != len(history):
                    raise ValueError("Incomplete history")
                history.extend(log["values"])
                if log.get("isLast") is True or len(history) == log["total"]:
                    break
                if not log["values"]:
                    raise ValueError("Incomplete history")
            for row in jira_rows({"since": since, "asOf": as_of, "baseUrl": base, "statusCategories": categories,
                                  "issues": [dict(issue, history=history)], "sharedIssueIds": [issue["id"]]}):
                rows[row["id"]] = row
        token = page.get("nextPageToken")
        if not token:
            if page.get("isLast") is False:
                raise ValueError("Incomplete issue listing")
            break
        if token in tokens:
            raise ValueError("Repeated page")
        tokens.add(token)
        params["nextPageToken"] = token
    return {"rows": sorted(rows.values(), key=lambda r: r["text"]), "coverage": "limited" if limited else "complete",
            "since": since, "asOf": as_of}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recipient", "since", "as-of"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(DEFAULT_CONFIG_PATH.read_text())
        person = config["recipients"][args.recipient]
        agenda = person["meetingAgenda"]
        base = config["jira"]["baseUrl"]
        if (config["jira"]["status"] != "ready" or agenda["status"] != "ready"
                or not re.fullmatch(r"https://[a-zA-Z0-9-]+\.atlassian\.net", base)):
            raise ValueError("Jira and agenda setup required")
        projects, recipient_id = agenda["jiraProjects"], person["jiraAccountId"]
        email, token = read_credentials()
        if not token or not email or email.casefold() != agenda["account"].casefold() or not recipient_id:
            raise ValueError("Account binding unavailable")
        auth = base64.b64encode(f"{email}:{token}".encode()).decode("ascii")
        connection = http.client.HTTPSConnection(base.removeprefix("https://"), timeout=30)

        def read(path, params=None):
            target = "/rest/api/3/" + path
            if params:
                target += "?" + urlencode(params)
            connection.request("GET", target, headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
            response = connection.getresponse()
            body = response.read()
            if response.status != 200:
                raise ValueError(f"Jira returned HTTP {response.status}")
            return json.loads(body)

        try:
            result = collect(read, projects, recipient_id, base, args.since, args.as_of)
        finally:
            connection.close()
        print(json.dumps(result))
    except (KeyError, TypeError, OSError, ValueError, http.client.HTTPException) as exc:
        detail = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("Jira returned HTTP ") else type(exc).__name__
        print(f"Jira recap unavailable ({detail}). Verify account, schema, access and complete pagination.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
