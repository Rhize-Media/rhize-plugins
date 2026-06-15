#!/usr/bin/env python3
"""skills_sh.py — discover skills + check partner security audits via the skills.sh API.

API: https://skills.sh/docs/api  ·  base https://skills.sh/api/v1  ·  JSON over HTTPS.
Auth: a short-lived Vercel OIDC token, `Authorization: Bearer <VERCEL_OIDC_TOKEN>`. Provide it in
the VERCEL_OIDC_TOKEN env var. Locally: enable OIDC Federation on the Vercel project, then
`vercel link` + `vercel env pull` writes it to .env.local (~12h validity; 600 req/min per team+project).

Fails loud — with no token it prints how to obtain one and exits 3 (never guesses/fabricates).

Commands:
    search "<query>" [--limit N]   GET /skills/search?q=&limit=   (single word=fuzzy, multi=semantic)
    audit  <id>                    GET /skills/audit/{id}         (Socket/Snyk/Agent-Trust-Hub/... verdicts)
    get    <id>                    GET /skills/{id}               (detail + full file tree)
    curated                        GET /skills/curated
  `id` is "{source}/{slug}", e.g. "vercel-labs/skills/find-skills" (use the id from search results).

Stdlib only (urllib).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://skills.sh/api/v1"

TOKEN_HINT = (
    "No VERCEL_OIDC_TOKEN found. skills.sh authenticates with a short-lived Vercel OIDC token:\n"
    "  1. Vercel dashboard → your project → Settings → OIDC Federation → enable.\n"
    "  2. npm i -g vercel && vercel link && vercel env pull   (writes VERCEL_OIDC_TOKEN to .env.local)\n"
    "  or: export VERCEL_OIDC_TOKEN=...   ·   docs: https://skills.sh/docs/api"
)
RISK_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def get_token() -> "str | None":
    tok = os.environ.get("VERCEL_OIDC_TOKEN")
    if tok:
        return tok
    for p in (".env.local", ".env"):
        try:
            for raw in open(p, encoding="utf-8"):
                if raw.strip().startswith("VERCEL_OIDC_TOKEN="):
                    return raw.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return None


def call(path: str, params: "dict | None" = None):
    tok = get_token()
    if not tok:
        sys.stderr.write(TOKEN_HINT + "\n")
        sys.exit(3)
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        sys.stderr.write(f"skills.sh HTTP {e.code}: {e.read().decode()[:300]}\n")
        sys.exit(3 if e.code == 401 else 1)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"skills.sh request failed: {e}\n")
        sys.exit(1)


def audit_verdict(data: dict):
    audits = data.get("audits", [])
    statuses = {a.get("status") for a in audits}
    worst = max((a.get("riskLevel") or "NONE" for a in audits),
                key=lambda r: RISK_ORDER.get(r, 0), default="NONE")
    verdict = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else ("pass" if audits else "none"))
    return verdict, worst, audits


def main() -> None:
    ap = argparse.ArgumentParser(description="Query skills.sh: discovery + partner security audits.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--json", action="store_true")
    a = sub.add_parser("audit")
    a.add_argument("id")
    a.add_argument("--json", action="store_true")
    g = sub.add_parser("get")
    g.add_argument("id")
    sub.add_parser("curated")
    args = ap.parse_args()

    if args.cmd == "search":
        if len(args.query) < 2:
            sys.exit("query must be at least 2 characters")
        data = call("/skills/search", {"q": args.query, "limit": args.limit})
        if args.json:
            print(json.dumps(data, indent=2))
            return
        items = (data or {}).get("data", [])
        print(f"skills.sh — {(data or {}).get('count', len(items))} matches for {args.query!r} "
              f"({(data or {}).get('searchType', '')}):")
        for it in items:
            print(f"  • {it.get('name')}  [{it.get('id')}]  {it.get('installs', '?')} installs")
            print(f"      install: npx skills add {it.get('installUrl')}")
    elif args.cmd == "audit":
        data = call(f"/skills/audit/{args.id}")
        if not data:
            print(f"no partner audits yet for {args.id} (generated after first install).")
            return
        if args.json:
            print(json.dumps(data, indent=2))
            return
        verdict, risk, audits = audit_verdict(data)
        print(f"skills.sh audit for {args.id}: {verdict.upper()} (max risk {risk}) — {len(audits)} partner(s)")
        for au in audits:
            rl = f" · {au.get('riskLevel')}" if au.get("riskLevel") else ""
            print(f"  - {au.get('provider')}: {au.get('status')}{rl} — {au.get('summary', '')}")
    elif args.cmd == "get":
        print(json.dumps(call(f"/skills/{args.id}"), indent=2))
    elif args.cmd == "curated":
        print(json.dumps(call("/skills/curated"), indent=2))


if __name__ == "__main__":
    main()
