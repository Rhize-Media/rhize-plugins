"""Public parsing adapted from Agent Reach 1.6.1 (MIT); see provenance.json."""

from __future__ import annotations

import datetime as _dt

import re

from typing import Any, Optional

_ANTIBOT_SCAN_BYTES = 4096

_EXA_HEADER_RE = re.compile(r"^(Title|URL|Published|Author):\s*(.*)$")

def make_item(
    *,
    title: Optional[str] = None,
    url: Optional[str] = None,
    author: Optional[str] = None,
    published_at: Optional[str] = None,
    text: Optional[str] = None,
    raw: Any = None,
) -> dict:
    """One normalized item. Missing fields are null; `raw` keeps upstream data."""
    return {
        "title": title or None,
        "url": url or None,
        "author": author or None,
        "published_at": published_at or None,
        "text": text or None,
        "raw": raw,
    }

def unix_to_iso(value: Any) -> Optional[str]:
    """Convert a unix timestamp to ISO 8601 UTC, or None."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _is_antibot_page(body: bytes) -> bool:
    """Recognize high-confidence Jina/Cloudflare challenge responses."""
    sample = body[:_ANTIBOT_SCAN_BYTES].decode("utf-8", errors="ignore").casefold()

    jina_captcha_warning = "warning:" in sample and "requiring captcha" in sample
    challenge_structure = any(
        marker in sample
        for marker in (
            "title: just a moment...",
            "## performing security verification",
            "title: attention required! | cloudflare",
        )
    )
    cloudflare_block = "title: attention required! | cloudflare" in sample and (
        "ray id" in sample or "/cdn-cgi/challenge-platform/" in sample
    )
    return (jina_captcha_warning and challenge_structure) or cloudflare_block

def _parse_exa_text(text: str) -> list:
    """Split Exa's `Title: / URL: / Published: / Author:` blocks into items."""
    items = []
    for block in re.split(r"\n(?=Title: )", "\n" + text.strip()):
        block = block.strip()
        if not block.startswith("Title:"):
            continue
        fields, body = {}, []
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            m = _EXA_HEADER_RE.match(lines[i])
            if not m:
                break
            fields[m.group(1).lower()] = m.group(2).strip()
            i += 1
        for line in lines[i:]:
            if line.strip() in ("Highlights:", "Text:"):
                continue
            body.append(line)
        na = lambda v: None if v in (None, "", "N/A") else v  # noqa: E731
        items.append(
            make_item(
                title=na(fields.get("title")),
                url=na(fields.get("url")),
                author=na(fields.get("author")),
                published_at=na(fields.get("published")),
                text="\n".join(body).strip(),
                raw=fields,
            )
        )
    return items

def _parse_jina(url: str, body: str) -> dict:
    title = re.search(r"^Title:\s*(.*)$", body, re.M)
    published = re.search(r"^Published Time:\s*(.*)$", body, re.M)
    content = body.split("Markdown Content:", 1)[1] if "Markdown Content:" in body else body
    return make_item(
        title=title.group(1).strip() if title else None,
        url=url,
        published_at=published.group(1).strip() if published else None,
        text=content.strip(),
    )

def _repo_item(repo: dict, readme: str | None = None) -> dict:
    return make_item(
        title=repo.get("full_name"),
        url=repo.get("html_url"),
        author=(repo.get("owner") or {}).get("login"),
        published_at=repo.get("created_at"),
        text=readme or repo.get("description"),
        raw={
            k: repo.get(k)
            for k in ("description", "stargazers_count", "forks_count", "language",
                      "topics", "pushed_at", "open_issues_count", "archived")
        }
        | {"license": (repo.get("license") or {}).get("spdx_id")},
    )

def _topic_item(topic: dict, text: Any = None, raw: Any = None) -> dict:
    member = topic.get("member") or {}
    return make_item(
        title=topic.get("title"),
        url=topic.get("url"),
        author=member.get("username"),
        published_at=unix_to_iso(topic.get("created")),
        text=topic.get("content") if text is None else text,
        raw=topic if raw is None else raw,
    )
