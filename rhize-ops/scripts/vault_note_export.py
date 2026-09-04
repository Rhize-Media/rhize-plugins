#!/usr/bin/env python3
"""vault_note_export.py — turn one Obsidian note into a Jira/Confluence-ready markdown body
plus a JSON manifest, resolving embedded binaries (images, PDFs, etc.) to local files that
can be attached to the destination issue (`export`).

  export --note <vault-relative-path> [--vault-root PATH]... [--out-dir DIR] [--max-bytes N]

Vault roots come from repeated --vault-root flags, or (if none given) from the
colon-separated OBSIDIAN_VAULT_PATH environment variable. Wikilinks and note embeds always
render as plain text (never resolved to a URL); binary embeds are resolved against the vault
roots and reported as `attachments` (found, within --max-bytes, not obsidian-only) or
`unattachable` (not-found / too-large / obsidian-only). --out-dir writes a Markdown copy of
the scrubbed body — named after the note's title — into that directory; --max-bytes caps the
size of an attachable binary (default 100 MiB = 104857600 bytes).

Binaries are deduplicated by basename in first-appearance order: when two embeds in the same
note share a basename (e.g. two different folders each containing an "a.png"), only the first
one encountered is resolved and attached — the second is not tracked as a separate binary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp"}
OBSIDIAN_ONLY_EXTS = {"canvas", "base"}
DEFAULT_MAX_BYTES = 104857600
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
SAFE_TITLE_INVALID_RE = re.compile(r"[/\\:]")
SAFE_TITLE_WHITESPACE_RE = re.compile(r"\s+")


class VaultError(Exception):
    pass


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


def add_binary(
    binaries: list[dict[str, str]], raw_targets: dict[str, str], target: str, kind: str,
) -> None:
    name = os.path.basename(target)
    if not any(b["name"] == name for b in binaries):
        binaries.append({"name": name, "kind": kind})
        raw_targets[name] = target


def add_unresolved(unresolved_links: list[str], value: str) -> None:
    if value not in unresolved_links:
        unresolved_links.append(value)


def display_name(target: str) -> str:
    """The last "/"-separated segment of a wikilink/embed target — used whenever there is
    no alias, so a folder-qualified target like "Projects/Sub/Deep Note" renders as "Deep
    Note" instead of leaking the vault folder structure. The full target is kept separately
    in unresolved_links."""
    return target.rsplit("/", 1)[-1]


def transform_body(body: str) -> tuple[str, list[dict[str, str]], list[str], dict[str, str]]:
    binaries: list[dict[str, str]] = []
    unresolved_links: list[str] = []
    raw_targets: dict[str, str] = {}

    def replace_embed(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
        ext = extension_of(target)
        if ext is None or ext == "md":
            add_unresolved(unresolved_links, target)
            return f"(see: {alias or display_name(target)})"
        add_binary(binaries, raw_targets, target, binary_kind(ext))
        return ""

    def replace_md_image(match: re.Match[str]) -> str:
        src = match.group(2).strip()
        if src.startswith("http://") or src.startswith("https://"):
            return match.group(0)
        add_binary(binaries, raw_targets, src, binary_kind(extension_of(src)))
        return ""

    def replace_wikilink(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = match.group(2).strip() if match.group(2) else None
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

    return "\n".join(rebuilt), binaries, unresolved_links, raw_targets


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


def build_basename_index(root: Path) -> dict[str, Path]:
    """Walk `root` once, skipping dot-directories (.obsidian, .git, .trash, ...), and
    return a basename -> first-resolved-path map. A symlinked file whose resolved target
    escapes `root` is excluded, same as the containment rule used everywhere else."""
    root_resolved = root.resolve()
    index: dict[str, Path] = {}
    for dirpath, dirnames, filenames in os.walk(root_resolved):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if filename in index:
                continue
            candidate = Path(dirpath) / filename
            resolved_candidate = candidate.resolve()
            try:
                resolved_candidate.relative_to(root_resolved)
            except ValueError:
                continue
            index[filename] = resolved_candidate
    return index


def resolve_embed_target(
    raw_target: str, roots: list[Path], basename_index_cache: dict[Path, dict[str, Path]],
) -> Path | None:
    # A dot-prefixed path segment (.trash/x.png, .obsidian/x.png, ...) is never resolved
    # here, matching the dot-directory skip that build_basename_index already applies to
    # the basename-walk branch below.
    has_dot_segment = any(segment.startswith(".") for segment in raw_target.split("/"))
    if "/" in raw_target and not has_dot_segment:
        for root in roots:
            candidate = root / raw_target
            if candidate.is_file():
                root_resolved = root.resolve()
                resolved_candidate = candidate.resolve()
                try:
                    resolved_candidate.relative_to(root_resolved)
                except ValueError:
                    continue
                return resolved_candidate
    basename = os.path.basename(raw_target)
    for root in roots:
        if root not in basename_index_cache:
            basename_index_cache[root] = build_basename_index(root)
        found = basename_index_cache[root].get(basename)
        if found is not None:
            return found
    return None


def resolve_attachments(
    binaries: list[dict[str, str]], raw_targets: dict[str, str], roots: list[Path], max_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attachments: list[dict[str, Any]] = []
    unattachable: list[dict[str, Any]] = []
    if not binaries:
        return attachments, unattachable

    basename_index_cache: dict[Path, dict[str, Path]] = {}
    for entry in binaries:
        name = entry["name"]
        kind = entry["kind"]
        if extension_of(name) in OBSIDIAN_ONLY_EXTS:
            unattachable.append({"name": name, "kind": kind, "reason": "obsidian-only"})
            continue
        resolved = resolve_embed_target(raw_targets[name], roots, basename_index_cache)
        if resolved is None:
            unattachable.append({"name": name, "kind": kind, "reason": "not-found"})
            continue
        size = resolved.stat().st_size
        if size > max_bytes:
            unattachable.append({"name": name, "kind": kind, "reason": "too-large"})
            continue
        attachments.append({"name": name, "path": str(resolved), "bytes": size, "kind": kind})
    return attachments, unattachable


def safe_title(title: str) -> str:
    replaced = SAFE_TITLE_INVALID_RE.sub("-", title)
    collapsed = SAFE_TITLE_WHITESPACE_RE.sub(" ", replaced).strip()
    return collapsed[:120]


def render_attached_section(attachments: list[dict[str, Any]]) -> str:
    items = "\n".join(f"- {a['name']} ({a['kind']})" for a in attachments)
    return f"\n\n## Attached to this issue\n\n{items}"


def render_unattachable_section(unattachable: list[dict[str, Any]]) -> str:
    items = "\n".join(f"- {u['name']} ({u['kind']}) — {u['reason']}" for u in unattachable)
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
    body, binaries, unresolved_links, raw_targets = transform_body(body)
    attachments, unattachable = resolve_attachments(binaries, raw_targets, roots, args.max_bytes)
    body, scrubbed_paths = scrub_local_paths(body)
    if attachments:
        body += render_attached_section(attachments)
    if unattachable:
        body += render_unattachable_section(unattachable)

    title = frontmatter_title if frontmatter_title else resolved.stem

    markdown_file: str | None = None
    if args.out_dir:
        out_dir = Path(args.out_dir)
        file_path = out_dir / f"{safe_title(title)}.md"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            file_path.write_text(body, encoding="utf-8")
        except OSError as exc:
            print(f"failed to write markdown copy: {file_path}: {exc}", file=sys.stderr)
            return 2
        markdown_file = str(file_path.resolve())

    result = {
        "vault_relative_path": args.note,
        "title": title,
        "body_markdown": body,
        "source_sha256": source_sha256,
        "binaries": binaries,
        "unresolved_links": unresolved_links,
        "scrubbed_paths": scrubbed_paths,
        "attachments": attachments,
        "unattachable": unattachable,
        "markdown_file": markdown_file,
    }
    print(json.dumps(result))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export")
    export.add_argument("--note", required=True)
    export.add_argument("--vault-root", action="append")
    export.add_argument("--out-dir")
    export.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    export.set_defaults(handler=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
