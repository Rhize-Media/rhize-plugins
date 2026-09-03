#!/usr/bin/env python3
"""vault_note_export.py — turn one Obsidian note into a Confluence-ready markdown body plus
a JSON manifest (`export`), and keep a small local ledger of already-exported notes so
re-exports update instead of duplicate (`record`).

  export --note <vault-relative-path> [--vault-root PATH]... [--ledger PATH]
  record --note <vault-relative-path> --ledger PATH --page-id ID --url URL --sha256 HEX [--title TITLE]

Vault roots come from repeated --vault-root flags, or (if none given) from the
colon-separated OBSIDIAN_VAULT_PATH environment variable. The ledger is a small JSON file
written atomically (temp file in the same directory, then renamed into place, mode 600).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"}
FENCE_RE = re.compile(r"^\s*```")
COMMENT_RE = re.compile(r"%%.*?%%", re.DOTALL)
EMBED_RE = re.compile(r"!\[\[([^\]|\n]+)(?:\|([^\]\n]+))?\]\]")
MD_IMAGE_RE = re.compile(r"!\[([^\]\n]*)\]\(([^)\n]+)\)")
WIKILINK_RE = re.compile(r"\[\[([^\]#|\n]+)(?:#[^\]|\n]*)?(?:\|([^\]\n]+))?\]\]")
MD_LINK_RE = re.compile(r"(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)")
SCRUB_SPLIT_RE = re.compile(r"([\s`'\"()<>,])")
SCRUB_PREFIXES = ("/Users/", "/home/", "~/", "obsidian://")
SCRUB_DRIVE_RE = re.compile(r"^[A-Za-z]:\\")
FRONTMATTER_TITLE_RE = re.compile(r"^title:\s*(.*)$")


class VaultError(Exception):
    pass


class LedgerError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_vault_roots(cli_roots: list[str] | None) -> list[Path]:
    if cli_roots:
        return [Path(r) for r in cli_roots]
    raw = os.environ.get("OBSIDIAN_VAULT_PATH", "")
    return [Path(p) for p in raw.split(":") if p]


def resolve_note_in_root(root: Path, note: str) -> Path | None:
    root_resolved = root.resolve()
    candidates = [root / note]
    if not Path(note).suffix:
        candidates.append(root / f"{note}.md")
    for candidate in candidates:
        if candidate.is_file():
            resolved_candidate = candidate.resolve()
            try:
                resolved_candidate.relative_to(root_resolved)
            except ValueError:
                raise VaultError(f"resolved path escapes vault root: {note}") from None
            return resolved_candidate
    return None


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "notes": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"ledger is not valid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("notes"), dict):
        raise LedgerError(f"ledger has an unsupported shape or version: {path}")
    return data


def write_ledger(path: Path, ledger: dict[str, Any]) -> None:
    parent = path.parent
    created_parent = not parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    if created_parent:
        parent.chmod(0o700)
    temp_path = parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(ledger, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        path.chmod(0o600)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ledger_lookup(ledger: dict[str, Any], target: str) -> dict[str, Any] | None:
    target = target.strip()
    for key, entry in ledger.get("notes", {}).items():
        if key == target:
            return entry
        if key.endswith(".md") and key[:-3] == target:
            return entry
        if Path(key).stem == target:
            return entry
    return None


def strip_frontmatter(raw: str) -> tuple[str, str | None]:
    lines = raw.split("\n")
    if not lines or lines[0].strip() != "---":
        return raw, None
    title = None
    end_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_index = i
            break
        match = FRONTMATTER_TITLE_RE.match(lines[i])
        if match and title is None:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            title = value
    if end_index is None:
        return raw, None
    return "\n".join(lines[end_index + 1:]), title


def strip_obsidian_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def extension_of(name: str) -> str | None:
    base = name.rsplit("/", 1)[-1]
    if "." in base:
        return base.rsplit(".", 1)[-1].lower()
    return None


def binary_kind(ext: str | None) -> str:
    if ext in IMAGE_EXTS:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "other"


def add_binary(binaries: list[dict[str, str]], name: str, kind: str) -> None:
    if not any(b["name"] == name for b in binaries):
        binaries.append({"name": name, "kind": kind})


def add_unresolved(unresolved_links: list[str], value: str) -> None:
    if value not in unresolved_links:
        unresolved_links.append(value)


def display_name(target: str) -> str:
    """The last "/"-separated segment of a wikilink/embed target — used whenever there is
    no alias, so a folder-qualified target like "Projects/Sub/Deep Note" renders as "Deep
    Note" instead of leaking the vault folder structure. The full target is kept separately
    in unresolved_links and for ledger lookup."""
    return target.rsplit("/", 1)[-1]


def transform_body(body: str, ledger: dict[str, Any]) -> tuple[str, list[dict[str, str]], list[str]]:
    binaries: list[dict[str, str]] = []
    unresolved_links: list[str] = []

    def replace_embed(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
        ext = extension_of(target)
        if ext is None or ext == "md":
            entry = ledger_lookup(ledger, target)
            if entry is not None:
                return f"[{alias or display_name(target)}]({entry['url']})"
            add_unresolved(unresolved_links, target)
            return f"(see: {alias or display_name(target)})"
        add_binary(binaries, os.path.basename(target), binary_kind(ext))
        return ""

    def replace_md_image(match: re.Match[str]) -> str:
        src = match.group(2).strip()
        if src.startswith("http://") or src.startswith("https://"):
            return match.group(0)
        add_binary(binaries, os.path.basename(src), binary_kind(extension_of(src)))
        return ""

    def replace_wikilink(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
        entry = ledger_lookup(ledger, target)
        if entry is not None:
            return f"[{alias or display_name(target)}]({entry['url']})"
        add_unresolved(unresolved_links, target)
        return alias or display_name(target)

    def replace_md_link(match: re.Match[str]) -> str:
        text = match.group(1)
        href = match.group(2).strip()
        if href.startswith("http://") or href.startswith("https://") or href.startswith("mailto:") or href.startswith("#"):
            return match.group(0)
        add_unresolved(unresolved_links, href)
        return text

    lines = body.split("\n")
    segments: list[tuple[bool, list[str]]] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if FENCE_RE.match(line):
            if not in_fence:
                if current:
                    segments.append((False, current))
                current = [line]
                in_fence = True
            else:
                current.append(line)
                segments.append((True, current))
                current = []
                in_fence = False
        else:
            current.append(line)
    if current:
        segments.append((in_fence, current))

    rebuilt: list[str] = []
    for is_fence, seg_lines in segments:
        text = "\n".join(seg_lines)
        if not is_fence:
            text = EMBED_RE.sub(replace_embed, text)
            text = MD_IMAGE_RE.sub(replace_md_image, text)
            text = WIKILINK_RE.sub(replace_wikilink, text)
            text = MD_LINK_RE.sub(replace_md_link, text)
        rebuilt.append(text)

    return "\n".join(rebuilt), binaries, unresolved_links


def is_local_path_token(token: str) -> bool:
    return token.startswith(SCRUB_PREFIXES) or bool(SCRUB_DRIVE_RE.match(token))


def scrub_local_paths(text: str) -> tuple[str, int]:
    # Tokenize the same way delegation_lint.py does (split on whitespace, backticks,
    # quotes, parens, angle brackets, commas -- keeping the delimiters) so only a token
    # that literally *starts with* a local-path prefix is replaced; surrounding markdown
    # delimiters (backticks, parens, ...) are preserved untouched.
    parts = SCRUB_SPLIT_RE.split(text)
    count = 0
    rebuilt: list[str] = []
    for part in parts:
        if part and is_local_path_token(part):
            rebuilt.append("<local path removed>")
            count += 1
        else:
            rebuilt.append(part)
    return "".join(rebuilt), count


def render_files_section(binaries: list[dict[str, str]]) -> str:
    items = "\n".join(f"- {b['name']} ({b['kind']})" for b in binaries)
    return f"\n\n## Files to request from the delegator\n\n{items}"


def cmd_export(args: argparse.Namespace) -> int:
    roots = resolve_vault_roots(args.vault_root)
    if not roots:
        print("no vault roots configured", file=sys.stderr)
        return 2

    try:
        resolved = None
        for root in roots:
            resolved = resolve_note_in_root(root, args.note)
            if resolved is not None:
                break
        if resolved is None:
            print(f"note not found in {len(roots)} vault root(s): {args.note}", file=sys.stderr)
            return 2
    except VaultError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ledger: dict[str, Any] = {"version": 1, "notes": {}}
    if args.ledger:
        try:
            ledger = load_ledger(Path(args.ledger))
        except LedgerError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    raw_bytes = resolved.read_bytes()
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"note is not valid UTF-8: {resolved}: {exc}", file=sys.stderr)
        return 2
    raw_text = raw_text.replace("\r\n", "\n")

    body, frontmatter_title = strip_frontmatter(raw_text)
    body = strip_obsidian_comments(body)
    body, binaries, unresolved_links = transform_body(body, ledger)
    body, scrubbed_paths = scrub_local_paths(body)
    if binaries:
        body += render_files_section(binaries)

    entry = ledger.get("notes", {}).get(args.note)
    existing_sha256 = entry["sha256"] if entry else None

    result = {
        "vault_relative_path": args.note,
        "title": frontmatter_title if frontmatter_title else resolved.stem,
        "body_markdown": body,
        "source_sha256": source_sha256,
        "binaries": binaries,
        "unresolved_links": unresolved_links,
        "scrubbed_paths": scrubbed_paths,
        "existing_page_id": entry["pageId"] if entry else None,
        "existing_page_url": entry["url"] if entry else None,
        "existing_sha256": existing_sha256,
        "changed": existing_sha256 != source_sha256,
    }
    print(json.dumps(result))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    try:
        ledger = load_ledger(ledger_path)
    except LedgerError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    ledger["notes"][args.note] = {
        "sha256": args.sha256,
        "pageId": args.page_id,
        "url": args.url,
        "title": args.title if args.title else Path(args.note).stem,
        "updatedAt": now_iso(),
    }
    try:
        write_ledger(ledger_path, ledger)
    except OSError as exc:
        print(f"failed to write ledger: {ledger_path}: {exc}", file=sys.stderr)
        return 2
    print(f"recorded {args.note} -> {args.page_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export")
    export.add_argument("--note", required=True)
    export.add_argument("--vault-root", action="append")
    export.add_argument("--ledger")
    export.set_defaults(handler=cmd_export)

    record = sub.add_parser("record")
    record.add_argument("--note", required=True)
    record.add_argument("--ledger", required=True)
    record.add_argument("--page-id", required=True)
    record.add_argument("--url", required=True)
    record.add_argument("--sha256", required=True)
    record.add_argument("--title")
    record.set_defaults(handler=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
