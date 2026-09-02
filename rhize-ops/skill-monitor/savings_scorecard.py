#!/usr/bin/env python3
"""
savings_scorecard.py — Two-tier (measured vs. estimated) token/cost savings
scorecard across the local agent-harness stack (ecc costs.jsonl, rtk, Headroom,
claude-mem, OpenWolf, headroom-learn digest).

MEASURED tier (real per-session token usage / real request-level compression):
  - ~/.claude/metrics/costs.jsonl — the spend DENOMINATOR. Cumulative-per-session
    snapshots; only the latest row per session_id is used (see cost_metrics.py).
  - rtk (`rtk gain --daily --format json`) — measured input/output deltas.
  - Headroom proxy (~/.headroom/proxy_savings.json history[] +
    ~/.headroom/savings_events.jsonl) — measured input-side compression.

ESTIMATED tier (NEVER summed into a measured total; always labeled):
  - claude-mem (~/.claude-mem/claude-mem.db session_summaries.discovery_tokens)
  - OpenWolf (<repo>/.wolf/token-ledger.json across each configured
    RHIZE_REPO_ROOTS entry — see paths.py)
  - headroom-learn digest (~/.headroom/learn-digest.md) — COUNT only, never summed.

Every source gets a coverage line (last event timestamp + event count) so a
dead integration reads "no data", not "no savings".

Usage:
  python3 savings_scorecard.py                  # last 7 days (default)
  python3 savings_scorecard.py --days 28
  python3 savings_scorecard.py --report-dir ./out --json-out ./out/scorecard.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import benchmark_status
import cost_metrics
import paths
import stack_metrics
from stack_metrics import TrustClass

HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent

HEADROOM_DIR = HOME / ".headroom"
PROXY_SAVINGS = HEADROOM_DIR / "proxy_savings.json"
SAVINGS_EVENTS = HEADROOM_DIR / "savings_events.jsonl"
LEARN_DIGEST = HEADROOM_DIR / "learn-digest.md"

CLAUDE_MEM_DB = HOME / ".claude-mem" / "claude-mem.db"

# Mirrors monitor.py's DEFAULT_VAULT_REPORT_DIR pattern: same
# Skill-Audit-and-Monitoring vault folder, sibling "cost-reports" subfolder so
# the scorecard and skill_roi.py reports land "alongside" each other without
# colliding with the weekly-reports/ skill-usage markdown. None when no
# single vault could be resolved (see paths.vault_root()).
DEFAULT_VAULT_REPORT_DIR = paths.vault_report_dir("cost-reports")
DEFAULT_JSON_OUT_DIR = paths.scorecards_dir()


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _tag(trust: TrustClass) -> str:
    """Inline trust-class tag, reusing stack_metrics.py's canonical
    vocabulary rather than inventing a second one. Every rendered figure
    below carries one of these next to the number itself — not as a
    footnote or a legend a reader has to scroll to find."""
    return f"[{trust.value}]"


# ---------------------------------------------------------------------------
# Procedural memory — imported from benchmark_status.py, not re-parsed here
# ---------------------------------------------------------------------------

def load_procedural_memory_status(path: Path | None = None) -> dict:
    """Reads benchmark_status.py's pre-generated JSON snapshot
    (data/benchmark-status.json) rather than re-parsing the vault notes'
    markdown tables — that parsing already lives in benchmark_status.py.
    Never raises: a missing/malformed snapshot is reported as unavailable
    with a reason, same defensive style as every other loader here."""
    p = path if path is not None else benchmark_status.OUTPUT_PATH
    if not p.exists():
        return {"available": False, "error": f"not found: {p}", "notes": {}, "liveness": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "error": str(e), "notes": {}, "liveness": {}}
    return {
        "available": True,
        "error": None,
        "generated_at": data.get("generated_at"),
        "notes": data.get("notes", {}),
        "liveness": data.get("liveness", {}),
    }


# ---------------------------------------------------------------------------
# MEASURED sources
# ---------------------------------------------------------------------------

def load_spend(days: int) -> dict:
    """The denominator: what was actually spent, from costs.jsonl."""
    result = cost_metrics.load_latest_costs_per_session(days=days)
    if not result["available"]:
        return {
            "available": False,
            "error": result.get("error"),
            "last_event_ts": None,
            "event_count": 0,
        }
    sessions = result["sessions"]
    total_cost = sum(cost_metrics.session_cost_usd(r) for r in sessions.values())
    total_tokens = sum(cost_metrics.session_total_tokens(r) for r in sessions.values())
    total_input = sum(r.get("input_tokens") or 0 for r in sessions.values())
    total_output = sum(r.get("output_tokens") or 0 for r in sessions.values())
    total_cache_write = sum(r.get("cache_write_tokens") or 0 for r in sessions.values())
    total_cache_read = sum(r.get("cache_read_tokens") or 0 for r in sessions.values())
    last_ts = result["last_event_ts"]
    return {
        "available": True,
        "error": None,
        "session_count": len(sessions),
        "total_cost_usd": total_cost,
        "total_tokens": total_tokens,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_write_tokens": total_cache_write,
        "total_cache_read_tokens": total_cache_read,
        "last_event_ts": last_ts.isoformat() if last_ts else None,
        "all_time_row_count": result["all_time_row_count"],
    }


def _safe_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_rtk(days: int) -> dict:
    """Measured input/output deltas from rtk's own tracked daily stats."""
    try:
        proc = subprocess.run(
            ["rtk", "gain", "--daily", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return {"available": False, "error": f"rtk unavailable: {e}"}

    if proc.returncode != 0:
        return {
            "available": False,
            "error": f"rtk exited {proc.returncode}: {proc.stderr.strip()[:300]}",
        }
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"available": False, "error": f"rtk output not JSON: {e}"}

    daily = data.get("daily", [])
    cutoff_date = (datetime.now() - timedelta(days=days)).date()
    windowed = [d for d in daily if (dt := _safe_date(d.get("date"))) and dt >= cutoff_date]
    all_dates = [dt for d in daily if (dt := _safe_date(d.get("date")))]
    last_date = max(all_dates) if all_dates else None

    return {
        "available": True,
        "error": None,
        "window_saved_tokens": sum(d.get("saved_tokens", 0) for d in windowed),
        "window_input_tokens": sum(d.get("input_tokens", 0) for d in windowed),
        "window_output_tokens": sum(d.get("output_tokens", 0) for d in windowed),
        "window_commands": sum(d.get("commands", 0) for d in windowed),
        "lifetime_summary": data.get("summary", {}),
        "last_event_ts": last_date.isoformat() if last_date else None,
        "event_count": len(windowed),
        "all_time_day_count": len(daily),
    }


def load_headroom(days: int) -> dict:
    """Measured input-side compression from Headroom's two data files."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out = {
        "proxy_history": {"available": False, "error": f"not found: {PROXY_SAVINGS}"},
        "events": {"available": False, "error": f"not found: {SAVINGS_EVENTS}"},
    }

    if PROXY_SAVINGS.exists():
        try:
            data = json.loads(PROXY_SAVINGS.read_text(encoding="utf-8", errors="replace"))
            history = data.get("history", [])
            windowed = []
            all_ts = []
            for h in history:
                ts = h.get("timestamp")
                if not ts:
                    continue
                try:
                    dt = parse_iso(ts)
                except ValueError:
                    continue
                all_ts.append(dt)
                if dt >= cutoff:
                    windowed.append(h)
            last_ts = max(all_ts) if all_ts else None
            out["proxy_history"] = {
                "available": True,
                "error": None,
                "window_tokens_saved": sum(h.get("total_tokens_saved", 0) for h in windowed),
                "window_compression_usd": sum(
                    h.get("compression_savings_usd", 0.0) for h in windowed
                ),
                "window_cache_usd": sum(h.get("cache_savings_usd", 0.0) for h in windowed),
                "window_event_count": len(windowed),
                "all_time_event_count": len(history),
                "last_event_ts": last_ts.isoformat() if last_ts else None,
                "lifetime": data.get("lifetime", {}),
            }
        except (json.JSONDecodeError, OSError) as e:
            out["proxy_history"] = {"available": False, "error": str(e)}

    if SAVINGS_EVENTS.exists():
        rows = []
        all_ts = []
        alltime_count = 0
        try:
            with SAVINGS_EVENTS.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    alltime_count += 1
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = row.get("ts")
                    if not ts:
                        continue
                    try:
                        dt = parse_iso(ts)
                    except ValueError:
                        continue
                    all_ts.append(dt)
                    if dt >= cutoff:
                        rows.append(row)
            last_ts = max(all_ts) if all_ts else None
            out["events"] = {
                "available": True,
                "error": None,
                "window_saved_tokens": sum(r.get("saved", 0) for r in rows),
                "window_cost_usd": sum(r.get("cost_usd", 0.0) for r in rows),
                "window_event_count": len(rows),
                "all_time_event_count": alltime_count,
                "last_event_ts": last_ts.isoformat() if last_ts else None,
            }
        except OSError as e:
            out["events"] = {"available": False, "error": str(e)}

    return out


# ---------------------------------------------------------------------------
# ESTIMATED sources — never summed into a measured total
# ---------------------------------------------------------------------------

def load_claude_mem(days: int) -> dict:
    """claude-mem's own claimed discovery_tokens. Label: LLM-guess numerator /
    chars÷4 denominator — this is NOT a measured token count."""
    if not CLAUDE_MEM_DB.exists():
        return {"available": False, "error": f"not found: {CLAUDE_MEM_DB}"}
    cutoff_epoch = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    try:
        conn = sqlite3.connect(f"file:{CLAUDE_MEM_DB}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(discovery_tokens), 0), MAX(created_at) "
            "FROM session_summaries WHERE created_at_epoch >= ?",
            (cutoff_epoch,),
        )
        window_count, window_discovery_sum, window_last = cur.fetchone()
        cur.execute("SELECT COUNT(*), MAX(created_at) FROM session_summaries")
        alltime_count, alltime_last = cur.fetchone()
        conn.close()
        return {
            "available": True,
            "error": None,
            "window_summary_count": window_count,
            "window_discovery_tokens_sum": window_discovery_sum,
            "last_event_ts": window_last or alltime_last,
            "all_time_summary_count": alltime_count,
        }
    except sqlite3.Error as e:
        return {"available": False, "error": str(e)}


def load_openwolf(days: int) -> dict:
    """OpenWolf per-repo token-ledger.json. Label: heuristic
    anatomy_hits×200 + chars÷4 — this is the ledger's own self-reported
    estimate, not a measured figure.

    Scans each configured repo root (RHIZE_REPO_ROOTS -- see paths.py) for a
    top-level .wolf/token-ledger.json, replacing the old hardcoded
    ~/dev-local/RHIZE/*/.wolf/token-ledger.json glob. [] configured -> {}."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    repos: dict = {}
    ledgers = sorted(
        root / ".wolf" / "token-ledger.json"
        for root in paths.repo_roots()
        if (root / ".wolf" / "token-ledger.json").exists()
    )
    for ledger in ledgers:
        repo_name = ledger.parent.parent.name
        try:
            data = json.loads(ledger.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError) as e:
            repos[repo_name] = {"available": False, "error": str(e)}
            continue
        sessions = data.get("sessions", [])
        windowed = []
        all_ts = []
        for s in sessions:
            ts_raw = s.get("ended") or s.get("started")
            if not ts_raw:
                continue
            try:
                dt = parse_iso(ts_raw)
            except ValueError:
                continue
            all_ts.append(dt)
            if dt >= cutoff:
                windowed.append(s)
        last_ts = max(all_ts) if all_ts else None
        lifetime = data.get("lifetime", {})
        repos[repo_name] = {
            "available": True,
            "error": None,
            "lifetime_estimated_savings_vs_bare_cli": lifetime.get(
                "estimated_savings_vs_bare_cli"
            ),
            "lifetime_anatomy_hits": lifetime.get("anatomy_hits"),
            "window_session_count": len(windowed),
            "all_time_session_count": len(sessions),
            "last_event_ts": last_ts.isoformat() if last_ts else None,
        }
    return repos


_SECTION_HEADER_RE = re.compile(
    r"^## (\d{4}-\d{2}-\d{2})T[\d:+-]+ — (.+)$", re.MULTILINE
)
_SAVED_ANNOTATION_RE = re.compile(r"tokens/session saved")


def load_learn_digest(days: int) -> dict:
    """COUNT of savings annotations only — never their sum. Label:
    'annotation count, not a token measurement'."""
    if not LEARN_DIGEST.exists():
        return {"available": False, "error": f"not found: {LEARN_DIGEST}"}
    text = LEARN_DIGEST.read_text(encoding="utf-8", errors="replace")
    headers = list(_SECTION_HEADER_RE.finditer(text))
    if not headers:
        total = len(_SAVED_ANNOTATION_RE.findall(text))
        return {
            "available": True,
            "error": None,
            "window_annotation_count": None,
            "all_time_annotation_count": total,
            "last_event_ts": None,
            "note": "no dated '## <ts> — <project>' section headers found; "
            "count is all-time only, cannot be windowed",
        }
    cutoff_date = (datetime.now() - timedelta(days=days)).date()
    window_count = 0
    alltime_count = 0
    last_date = None
    for i, m in enumerate(headers):
        try:
            d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            continue
        if last_date is None or d > last_date:
            last_date = d
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section = text[start:end]
        n = len(_SAVED_ANNOTATION_RE.findall(section))
        alltime_count += n
        if d >= cutoff_date:
            window_count += n
    return {
        "available": True,
        "error": None,
        "window_annotation_count": window_count,
        "all_time_annotation_count": alltime_count,
        "last_event_ts": last_date.isoformat() if last_date else None,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_int(n) -> str:
    if n is None:
        return "n/a"
    return f"{int(n):,}"


def _fmt_usd(n) -> str:
    if n is None:
        return "n/a"
    return f"${float(n):,.4f}"


def _coverage_line(label: str, last_ts, event_count) -> str:
    ts_str = last_ts if last_ts else "no data"
    return f"- **{label}** — last event: `{ts_str}` · events: {_fmt_int(event_count)}"


def render_markdown(days: int, data: dict) -> str:
    now = datetime.now()
    spend = data["spend"]
    rtk = data["rtk"]
    headroom = data["headroom"]
    claude_mem = data["claude_mem"]
    openwolf = data["openwolf"]
    learn_digest = data["learn_digest"]
    procedural_memory = data["procedural_memory"]

    lines: list[str] = []
    lines.append("---")
    lines.append("type: savings-scorecard")
    lines.append(f"date: {now.strftime('%Y-%m-%d')}")
    lines.append(f"window-days: {days}")
    lines.append("tags:")
    lines.append("  - skill-audit")
    lines.append("  - cost-tracking")
    lines.append("---")
    lines.append("")
    lines.append(f"# Savings Scorecard — {now.strftime('%Y-%m-%d %H:%M')} (last {days}d)")
    lines.append("")

    # Headline
    if spend["available"]:
        headline_tokens = _fmt_int(spend["total_tokens"])
        headline_cost = _fmt_usd(spend["total_cost_usd"])
    else:
        headline_tokens = "n/a"
        headline_cost = "n/a"
    rtk_saved = rtk.get("window_saved_tokens") if rtk.get("available") else None
    hr_events = headroom["events"]
    hr_saved = hr_events.get("window_saved_tokens") if hr_events.get("available") else None
    lines.append(
        f"> Spent **{headline_tokens}** tokens (**{headline_cost}**) over the last {days} "
        f"day(s) across **{spend.get('session_count', 'n/a') if spend['available'] else 'n/a'}** "
        f"sessions; avoided: **{_fmt_int(rtk_saved)}** (rtk, {_tag(TrustClass.MEASURED_CAVEATED)}) + "
        f"**{_fmt_int(hr_saved)}** (headroom, {_tag(TrustClass.MEASURED)})."
    )
    lines.append("")

    # A row_missing verdict must be unmissable, not a table cell among
    # others among the Procedural Memory section's own table further down —
    # it means a routine ran and its measurement silently vanished.
    if procedural_memory.get("available"):
        missing = [
            name for name, v in procedural_memory["liveness"].items()
            if v.get("status") == "row_missing"
        ]
        if missing:
            lines.append(
                f"> **PROCEDURAL MEMORY ROW_MISSING** — {', '.join(missing)}: a scheduled "
                'run happened and no benchmark row landed. See "## Procedural Memory" below.'
            )
            lines.append("")

    # --- Measured -----------------------------------------------------
    lines.append("## Measured")
    lines.append("")
    lines.append(
        "*Real per-session token usage and real request-level compression. "
        "Safe to sum, safe to compare against spend.*"
    )
    lines.append("")

    lines.append("### Spend (denominator) — ecc costs.jsonl")
    lines.append("")
    if spend["available"]:
        lines.append(f"- Sessions in window: **{_fmt_int(spend['session_count'])}**")
        lines.append(f"- Total cost: **{_fmt_usd(spend['total_cost_usd'])}** {_tag(TrustClass.MEASURED)}")
        lines.append(f"- Total tokens: **{_fmt_int(spend['total_tokens'])}** {_tag(TrustClass.MEASURED)}")
        lines.append(
            f"  - input: {_fmt_int(spend['total_input_tokens'])} · "
            f"output: {_fmt_int(spend['total_output_tokens'])} · "
            f"cache write: {_fmt_int(spend['total_cache_write_tokens'])} · "
            f"cache read: {_fmt_int(spend['total_cache_read_tokens'])}"
        )
    else:
        lines.append(f"- **unavailable** — {spend.get('error')}")
    lines.append("")

    lines.append(f"### rtk (`rtk gain --daily --format json`) — {_tag(TrustClass.MEASURED_CAVEATED)}")
    lines.append("")
    if rtk.get("available"):
        lines.append(f"- Commands in window: {_fmt_int(rtk['window_commands'])}")
        lines.append(
            f"- Tokens saved in window: **{_fmt_int(rtk['window_saved_tokens'])}** "
            f"{_tag(TrustClass.MEASURED_CAVEATED)}"
        )
        lines.append(
            f"- Input/output tokens in window: {_fmt_int(rtk['window_input_tokens'])} / "
            f"{_fmt_int(rtk['window_output_tokens'])} {_tag(TrustClass.MEASURED_CAVEATED)}"
        )
        lines.append(f"  - *{stack_metrics.RTK_CAVEAT}*")
        ls = rtk.get("lifetime_summary", {})
        lines.append(
            f"- *Lifetime (not window-scoped): {_fmt_int(ls.get('total_saved'))} tokens saved, "
            f"{ls.get('avg_savings_pct', 0):.1f}% avg savings across "
            f"{_fmt_int(ls.get('total_commands'))} commands*"
        )
    else:
        lines.append(f"- **unavailable** — {rtk.get('error')}")
    lines.append("")

    lines.append("### Headroom proxy (input-side compression)")
    lines.append("")
    ph = headroom["proxy_history"]
    if ph.get("available"):
        lines.append(
            f"- `proxy_savings.json` history, window: {_fmt_int(ph['window_tokens_saved'])} "
            f"tokens saved, {_fmt_usd(ph['window_compression_usd'])} compression + "
            f"{_fmt_usd(ph['window_cache_usd'])} cache savings "
            f"({ph['window_event_count']} events) {_tag(TrustClass.MEASURED)}"
        )
        lt = ph.get("lifetime", {})
        lines.append(
            f"  - *Lifetime: {_fmt_int(lt.get('tokens_saved'))} tokens, "
            f"{_fmt_usd(lt.get('compression_savings_usd'))} compression + "
            f"{_fmt_usd(lt.get('cache_savings_usd'))} cache*"
        )
    else:
        lines.append(f"- `proxy_savings.json` **unavailable** — {ph.get('error')}")
    ev = headroom["events"]
    if ev.get("available"):
        lines.append(
            f"- `savings_events.jsonl`, window: {_fmt_int(ev['window_saved_tokens'])} "
            f"tokens saved, {_fmt_usd(ev['window_cost_usd'])} "
            f"({ev['window_event_count']} events) {_tag(TrustClass.MEASURED)}"
        )
    else:
        lines.append(f"- `savings_events.jsonl` **unavailable** — {ev.get('error')}")
    lines.append("")

    # --- Estimated ------------------------------------------------------
    lines.append("## Estimated — do not compare with measured")
    lines.append("")
    lines.append(
        "*These numbers come from each tool's own self-reported heuristic, not from "
        "ecc's real token accounting. Never sum these into the Measured totals above.*"
    )
    lines.append("")

    lines.append(
        f"### claude-mem (label: LLM-guess numerator / chars÷4 denominator) — "
        f"{_tag(TrustClass.INDICATIVE)}"
    )
    lines.append("")
    if claude_mem.get("available"):
        lines.append(
            f"- Session summaries in window: {_fmt_int(claude_mem['window_summary_count'])}"
        )
        lines.append(
            f"- Claimed `discovery_tokens` sum in window: "
            f"**{_fmt_int(claude_mem['window_discovery_tokens_sum'])}** {_tag(TrustClass.INDICATIVE)}"
        )
    else:
        lines.append(f"- **unavailable** — {claude_mem.get('error')}")
    lines.append("")

    lines.append(
        f"### OpenWolf per-repo (label: heuristic anatomy_hits×200 + chars÷4) — "
        f"{_tag(TrustClass.SELF_REPORTED)}"
    )
    lines.append("")
    if openwolf:
        lines.append(
            f"| Repo | Lifetime est. savings (tokens) {_tag(TrustClass.SELF_REPORTED)} | "
            "Sessions in window | Sessions (all-time) |"
        )
        lines.append("| --- | ---: | ---: | ---: |")
        for repo, d in sorted(openwolf.items()):
            if not d.get("available"):
                lines.append(f"| `{repo}` | unavailable ({d.get('error')}) | — | — |")
                continue
            lines.append(
                f"| `{repo}` | {_fmt_int(d['lifetime_estimated_savings_vs_bare_cli'])} | "
                f"{_fmt_int(d['window_session_count'])} | {_fmt_int(d['all_time_session_count'])} |"
            )
    else:
        lines.append("- No `.wolf/token-ledger.json` found under any configured `RHIZE_REPO_ROOTS` entry.")
    lines.append("")

    lines.append(
        f"### headroom-learn digest (count only, never summed) — {_tag(TrustClass.SELF_REPORTED)}"
    )
    lines.append("")
    if learn_digest.get("available"):
        wc = learn_digest.get("window_annotation_count")
        lines.append(
            f"- Savings annotations in window: **{_fmt_int(wc) if wc is not None else 'n/a'}** "
            f"{_tag(TrustClass.SELF_REPORTED)}"
        )
        lines.append(
            f"- Savings annotations all-time: {_fmt_int(learn_digest['all_time_annotation_count'])}"
        )
        if learn_digest.get("note"):
            lines.append(f"- *{learn_digest['note']}*")
    else:
        lines.append(f"- **unavailable** — {learn_digest.get('error')}")
    lines.append("")

    # --- Coverage ---------------------------------------------------------
    lines.append("## Coverage")
    lines.append("")
    lines.append(
        "*Last event timestamp + event count per source, so a dead integration reads "
        "\"no data,\" not \"no savings.\"*"
    )
    lines.append("")
    lines.append(
        _coverage_line(
            "ecc costs.jsonl",
            spend.get("last_event_ts"),
            spend.get("all_time_row_count") if spend["available"] else 0,
        )
    )
    lines.append(
        _coverage_line(
            "rtk",
            rtk.get("last_event_ts"),
            rtk.get("all_time_day_count") if rtk.get("available") else 0,
        )
    )
    lines.append(
        _coverage_line(
            "headroom proxy_savings.json",
            ph.get("last_event_ts"),
            ph.get("all_time_event_count") if ph.get("available") else 0,
        )
    )
    lines.append(
        _coverage_line(
            "headroom savings_events.jsonl",
            ev.get("last_event_ts"),
            ev.get("all_time_event_count") if ev.get("available") else 0,
        )
    )
    lines.append(
        _coverage_line(
            "claude-mem",
            claude_mem.get("last_event_ts"),
            claude_mem.get("all_time_summary_count") if claude_mem.get("available") else 0,
        )
    )
    for repo, d in sorted(openwolf.items()):
        lines.append(
            _coverage_line(
                f"OpenWolf `{repo}`",
                d.get("last_event_ts"),
                d.get("all_time_session_count") if d.get("available") else 0,
            )
        )
    lines.append(
        _coverage_line(
            "headroom-learn digest",
            learn_digest.get("last_event_ts"),
            learn_digest.get("all_time_annotation_count")
            if learn_digest.get("available")
            else 0,
        )
    )
    lines.append("")

    # --- Procedural Memory --------------------------------------------------
    # New section, appended at the bottom per this project's "add new
    # sections at the bottom, never reorder existing ones" convention
    # (downstream readers parse markdown reports positionally).
    lines.append("## Procedural Memory")
    lines.append("")
    lines.append(
        f"*Per-note row counts by arm and the liveness verdict from "
        f"benchmark_status.py — did each benchmark-instrumented routine's capture "
        f"step actually land a row this run? Row counts and dates come directly "
        f"from the vault notes' own markdown tables {_tag(TrustClass.MEASURED)}; "
        f"the liveness verdict itself is a computed classification, not a "
        f"separate measurement.*"
    )
    lines.append("")
    if procedural_memory.get("available"):
        missing = [
            name for name, v in procedural_memory["liveness"].items()
            if v.get("status") == "row_missing"
        ]
        if missing:
            lines.append("> **ROW_MISSING** — a run happened and no row landed:")
            for name in missing:
                lines.append(f"> - **{name}**: {procedural_memory['liveness'][name]['reason']}")
            lines.append("")
        lines.append("| Routine | Liveness | Rows (by arm) | Newest row |")
        lines.append("| --- | --- | --- | --- |")
        for name in sorted(procedural_memory["notes"]):
            note = procedural_memory["notes"][name]
            verdict = procedural_memory["liveness"].get(name, {})
            status = verdict.get("status", "unknown")
            status_cell = f"**{status.upper()}**" if status == "row_missing" else status
            if note.get("error"):
                lines.append(f"| {name} | {status_cell} | ERROR: {note['error']} | — |")
                continue
            by_arm = ", ".join(
                f"{arm}={n}" for arm, n in sorted(note.get("rows_by_arm", {}).items())
            ) or "none"
            lines.append(
                f"| {name} | {status_cell} | {by_arm} ({_fmt_int(note.get('total_rows', 0))} total) | "
                f"{note.get('newest_row_date') or 'n/a'} |"
            )
    else:
        lines.append(f"- **unavailable** — {procedural_memory.get('error')}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7, help="window in days (default 7)")
    ap.add_argument(
        "--report-dir",
        default=str(DEFAULT_VAULT_REPORT_DIR) if DEFAULT_VAULT_REPORT_DIR else None,
        help=("where to write the markdown report (default: the Obsidian "
              "vault, if exactly one is configured — see paths.vault_root())"),
    )
    ap.add_argument(
        "--json-out-dir",
        default=str(DEFAULT_JSON_OUT_DIR),
        help="where to write the raw JSON snapshot",
    )
    args = ap.parse_args()

    days = args.days
    print(f"→ Building savings scorecard (window = {days} days)")

    data = {
        "spend": load_spend(days),
        "rtk": load_rtk(days),
        "headroom": load_headroom(days),
        "claude_mem": load_claude_mem(days),
        "openwolf": load_openwolf(days),
        "learn_digest": load_learn_digest(days),
        "procedural_memory": load_procedural_memory_status(),
    }

    md = render_markdown(days, data)

    md_path = None
    if not args.report_dir:
        print(
            "  ! no --report-dir given and no single Obsidian vault could be "
            "resolved (see paths.vault_root()) — skipping the markdown "
            "report write.",
            file=sys.stderr,
        )
    else:
        report_dir = Path(args.report_dir).expanduser()
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / f"{datetime.now().strftime('%Y-%m-%d')}-savings-scorecard-{days}d.md"
        md_path.write_text(md)

    json_out_dir = Path(args.json_out_dir).expanduser()
    json_out_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_out_dir / f"{datetime.now().strftime('%Y-%m-%d')}-savings-scorecard-{days}d.json"
    json_path.write_text(json.dumps(data, indent=2, default=str))

    if md_path is not None:
        print(f"  ✓ Markdown report → {md_path}")
    print(f"  ✓ JSON snapshot   → {json_path}")
    print("")
    print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
