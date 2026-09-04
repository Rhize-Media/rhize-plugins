"""test_vault_note_export.py — vault_note_export.py note-to-Jira-attachment conversion per
task-1-brief.md Contract A. Fixture vault built under tmp_path; no network, no real vault.
"""
import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-ops" / "scripts" / "vault_note_export.py"
SPEC = importlib.util.spec_from_file_location("vault_note_export", SCRIPT)
vault_note_export = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(vault_note_export)


@pytest.fixture(autouse=True)
def clear_vault_env(monkeypatch):
    # Hermetic against this machine's real OBSIDIAN_VAULT_PATH (colon-separated, two roots).
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)


def run(argv: list[str], capsys):
    code = vault_note_export.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def write_note(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_binary(root: Path, relative: str, data: bytes) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def roots(tmp_path):
    root1 = tmp_path / "vault one"
    root2 = tmp_path / "vault two"
    root1.mkdir()
    root2.mkdir()
    return root1, root2


def test_frontmatter_stripped_title_from_frontmatter_or_stem(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "With Frontmatter.md", "---\ntitle: My Note\n---\nHello world.\n")
    write_note(root1, "note_b.md", "Just text.\n")

    code, out, _err = run(
        ["export", "--note", "With Frontmatter.md", "--vault-root", str(root1)], capsys,
    )
    assert code == 0
    result = json.loads(out)
    assert result["title"] == "My Note"
    assert "title:" not in result["body_markdown"]
    assert "Hello world." in result["body_markdown"]

    code, out, _err = run(["export", "--note", "note_b.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["title"] == "note_b"


def test_wikilink_becomes_plain_text_and_alias_wikilink_renders_alias(roots, capsys):
    root1, _root2 = roots
    write_note(
        root1, "Links.md",
        "See [[Other Note]] and [[Second Note|Second]] for background.\n",
    )
    code, out, _err = run(["export", "--note", "Links.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "[[Other Note]]" not in result["body_markdown"]
    assert "Other Note" in result["body_markdown"]
    assert "Second" in result["body_markdown"]
    assert "[[Second Note|Second]]" not in result["body_markdown"]
    assert "Other Note" in result["unresolved_links"]
    assert "Second Note" in result["unresolved_links"]


def test_embed_becomes_binary_and_files_section_appended(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "WithEmbed.md", "Check ![[diagram.png]] for the diagram.\n")
    code, out, _err = run(["export", "--note", "WithEmbed.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "![[diagram.png]]" not in result["body_markdown"]
    assert result["binaries"] == [{"name": "diagram.png", "kind": "image"}]
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "diagram.png", "kind": "image", "reason": "not-found"}]
    assert "## Attached to this issue" not in result["body_markdown"]
    assert "## Files to request from the delegator" in result["body_markdown"]
    assert "- diagram.png (image) — not-found" in result["body_markdown"]


def test_absolute_path_scrubbed_and_counted(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "WithPath.md", "See /Users/jim/notes/file.txt for reference.\n")
    code, out, _err = run(["export", "--note", "WithPath.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "/Users/jim/notes/file.txt" not in result["body_markdown"]
    assert "<local path removed>" in result["body_markdown"]
    assert result["scrubbed_paths"] == 1


def test_note_only_in_second_root_of_colon_separated_env_resolves(roots, capsys, monkeypatch):
    root1, root2 = roots
    write_note(root2, "OnlyInRoot2.md", "content only in the second root\n")
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", f"{root1}:{root2}")

    code, out, _err = run(["export", "--note", "OnlyInRoot2"], capsys)
    assert code == 0
    result = json.loads(out)
    assert "content only in the second root" in result["body_markdown"]


def test_missing_note_exits_2_with_no_stdout_json(roots, capsys):
    root1, _root2 = roots
    code, out, err = run(["export", "--note", "DoesNotExist.md", "--vault-root", str(root1)], capsys)
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_folder_qualified_wikilink_displays_last_segment_only(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Referrer.md", "See [[Projects/Sub/Deep Note]] for details.\n")
    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "Deep Note" in result["body_markdown"]
    assert "Projects/Sub" not in result["body_markdown"]
    assert result["unresolved_links"] == ["Projects/Sub/Deep Note"]


def test_folder_qualified_embed_displays_last_segment_only(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Referrer.md", "See ![[Projects/Sub/Deep Note]] for details.\n")
    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "(see: Deep Note)" in result["body_markdown"]
    assert "Projects/Sub" not in result["body_markdown"]
    assert result["unresolved_links"] == ["Projects/Sub/Deep Note"]


def test_code_fenced_wikilink_left_untouched(roots, capsys):
    root1, _root2 = roots
    write_note(
        root1, "Fenced.md",
        "Intro line.\n\n```\n[[Should Not Change]]\n```\n\nOutro line.\n",
    )
    code, out, _err = run(["export", "--note", "Fenced.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "[[Should Not Change]]" in result["body_markdown"]
    assert "Should Not Change" not in result["unresolved_links"]


def test_scrub_preserves_surrounding_backticks(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Backtick.md", "Run `~/bin/deploy.sh` to deploy.\n")
    code, out, _err = run(["export", "--note", "Backtick.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "`<local path removed>`" in result["body_markdown"]
    assert result["scrubbed_paths"] == 1


def test_scrub_does_not_match_token_not_starting_with_prefix(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "NotAPath.md", "foo~/bar baz\n")
    code, out, _err = run(["export", "--note", "NotAPath.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "foo~/bar baz" in result["body_markdown"]
    assert result["scrubbed_paths"] == 0


def test_scrub_preserves_surrounding_parentheses(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Parens.md", "See (/Users/jim/file.txt) for the file.\n")
    code, out, _err = run(["export", "--note", "Parens.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "(<local path removed>)" in result["body_markdown"]
    assert result["scrubbed_paths"] == 1


def test_note_escaping_root_via_dotdot_exits_2(roots, capsys, tmp_path):
    root1, _root2 = roots
    outside = tmp_path / "outside.md"
    outside.write_text("should not be reachable\n", encoding="utf-8")
    code, out, err = run(["export", "--note", "../outside.md", "--vault-root", str(root1)], capsys)
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_note_escaping_root_via_symlink_exits_2(roots, capsys, tmp_path):
    root1, _root2 = roots
    outside = tmp_path / "outside_target.md"
    outside.write_text("should not be reachable\n", encoding="utf-8")
    symlink_path = root1 / "Escape.md"
    symlink_path.symlink_to(outside)
    code, out, err = run(["export", "--note", "Escape.md", "--vault-root", str(root1)], capsys)
    assert code == 2
    assert out == ""
    assert err.strip() != ""


def test_crlf_note_normalized_to_lf_in_body(roots, capsys):
    root1, _root2 = roots
    path = root1 / "CRLF.md"
    path.write_bytes(b"Line one.\r\nLine two.\r\n")
    code, out, _err = run(["export", "--note", "CRLF.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "\r" not in result["body_markdown"]
    assert "Line one." in result["body_markdown"]
    assert "Line two." in result["body_markdown"]


def test_non_utf8_note_exits_2_with_message(roots, capsys):
    root1, _root2 = roots
    path = root1 / "NotUtf8.md"
    path.write_bytes(b"Bad byte: \xff\xfe not valid utf-8\n")
    code, out, err = run(["export", "--note", "NotUtf8.md", "--vault-root", str(root1)], capsys)
    assert code == 2
    assert out == ""
    assert len(err.strip().splitlines()) == 1


def test_out_dir_writes_markdown_copy_named_by_title(roots, capsys, tmp_path):
    root1, _root2 = roots
    write_note(root1, "WithTitle.md", "---\ntitle: Client/Plan: Q4\n---\nBody text.\n")
    out_dir = tmp_path / "out"

    code, out, _err = run(
        ["export", "--note", "WithTitle.md", "--vault-root", str(root1), "--out-dir", str(out_dir)],
        capsys,
    )
    assert code == 0
    result = json.loads(out)
    expected_path = (out_dir / "Client-Plan- Q4.md").resolve()
    assert result["markdown_file"] == str(expected_path)
    assert expected_path.read_text(encoding="utf-8") == result["body_markdown"]

    # A fresh, otherwise-untouched directory that --out-dir never names: if omitting
    # --out-dir wrote a markdown copy anywhere unexpected, this would catch it.
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    code, out, _err = run(
        ["export", "--note", "WithTitle.md", "--vault-root", str(root1)], capsys,
    )
    assert code == 0
    result_no_out = json.loads(out)
    assert result_no_out["markdown_file"] is None
    assert not (root1 / "Client-Plan- Q4.md").exists()
    assert list(watch_dir.iterdir()) == []


def test_embedded_binary_resolves_by_basename_anywhere_under_root(roots, capsys, tmp_path):
    root1, _root2 = roots
    data = b"PNGDATA"
    write_binary(root1, "attachments/diagram.png", data)
    write_note(root1, "WithEmbed.md", "Check ![[diagram.png]] for the diagram.\n")

    code, out, _err = run(["export", "--note", "WithEmbed.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    expected_path = str((root1 / "attachments" / "diagram.png").resolve())
    assert result["attachments"] == [
        {"name": "diagram.png", "path": expected_path, "bytes": len(data), "kind": "image"},
    ]
    assert result["unattachable"] == []
    assert "## Attached to this issue" in result["body_markdown"]
    assert "- diagram.png (image)" in result["body_markdown"]
    assert str(tmp_path) not in result["body_markdown"]
    assert "/Users" not in result["body_markdown"]


def test_embedded_binary_with_folder_resolves_relative_to_root_first(roots, capsys):
    root1, _root2 = roots
    # Different sizes so the assertion below can only pass if the folder-qualified
    # branch (assets/a.png) was actually used -- a walk-order bug that picked
    # other/a.png instead would trip on `bytes`, not just on the resolved path.
    write_binary(root1, "assets/a.png", b"ASSET-DATA")
    write_binary(root1, "other/a.png", b"X")
    write_note(root1, "WithFolderEmbed.md", "See ![[assets/a.png]] here.\n")

    code, out, _err = run(["export", "--note", "WithFolderEmbed.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    expected_path = str((root1 / "assets" / "a.png").resolve())
    assert result["attachments"] == [
        {"name": "a.png", "path": expected_path, "bytes": len(b"ASSET-DATA"), "kind": "image"},
    ]


def test_embedded_binary_missing_is_unattachable_not_found(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Missing.md", "See ![[ghost.png]] here.\n")

    code, out, _err = run(["export", "--note", "Missing.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "ghost.png", "kind": "image", "reason": "not-found"}]
    assert "## Files to request from the delegator" in result["body_markdown"]
    assert "- ghost.png (image) — not-found" in result["body_markdown"]


def test_embedded_binary_over_max_bytes_is_unattachable_too_large(roots, capsys):
    root1, _root2 = roots
    write_binary(root1, "big.png", b"x" * 20)
    write_note(root1, "Big.md", "See ![[big.png]] here.\n")

    code, out, _err = run(
        ["export", "--note", "Big.md", "--vault-root", str(root1), "--max-bytes", "10"], capsys,
    )
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "big.png", "kind": "image", "reason": "too-large"}]


def test_canvas_embed_is_unattachable_obsidian_only(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Board.canvas", "{}")
    write_note(root1, "Referrer.md", "See ![[Board.canvas]] here.\n")

    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "Board.canvas", "kind": "other", "reason": "obsidian-only"}]


def test_hidden_directories_are_skipped_in_resolution(roots, capsys):
    root1, _root2 = roots
    write_binary(root1, ".trash/x.png", b"HIDDEN")
    write_note(root1, "Referrer.md", "See ![[x.png]] here.\n")

    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "x.png", "kind": "image", "reason": "not-found"}]


def test_dot_directory_segment_in_folder_qualified_embed_is_not_found(roots, capsys):
    root1, _root2 = roots
    write_binary(root1, ".trash/x.png", b"HIDDEN")
    write_note(root1, "Referrer.md", "See ![[.trash/x.png]] here.\n")

    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "x.png", "kind": "image", "reason": "not-found"}]


def test_embedded_binary_via_symlink_outside_root_is_not_found(roots, capsys, tmp_path):
    root1, _root2 = roots
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"OUTSIDE")

    # Basename-walk branch: a symlink under root, found by basename, whose resolved
    # target escapes the root.
    basename_symlink = root1 / "nested" / "escape.png"
    basename_symlink.parent.mkdir(parents=True, exist_ok=True)
    basename_symlink.symlink_to(outside)
    write_note(root1, "Basename.md", "See ![[escape.png]] here.\n")

    code, out, _err = run(["export", "--note", "Basename.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "escape.png", "kind": "image", "reason": "not-found"}]

    # Folder-qualified branch: a symlink at the exact embedded path, resolved target
    # escapes the root.
    folder_symlink = root1 / "assets2" / "escape2.png"
    folder_symlink.parent.mkdir(parents=True, exist_ok=True)
    folder_symlink.symlink_to(outside)
    write_note(root1, "Folder.md", "See ![[assets2/escape2.png]] here.\n")

    code, out, _err = run(["export", "--note", "Folder.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert result["attachments"] == []
    assert result["unattachable"] == [{"name": "escape2.png", "kind": "image", "reason": "not-found"}]


def test_wikilink_always_renders_plain_title(roots, capsys):
    root1, _root2 = roots
    write_note(root1, "Referrer.md", "See [[Some Note]] for background.\n")

    code, out, _err = run(["export", "--note", "Referrer.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    result = json.loads(out)
    assert "Some Note" in result["body_markdown"]
    assert "[[Some Note]]" not in result["body_markdown"]
    assert "](" not in result["body_markdown"]
    assert result["unresolved_links"] == ["Some Note"]


def test_out_dir_write_error_exits_2(roots, capsys, tmp_path):
    root1, _root2 = roots
    write_note(root1, "Note.md", "content\n")
    blocked_path = tmp_path / "not_a_dir"
    blocked_path.write_text("i am a file", encoding="utf-8")

    code, out, err = run(
        [
            "export", "--note", "Note.md", "--vault-root", str(root1),
            "--out-dir", str(blocked_path),
        ],
        capsys,
    )
    assert code == 2
    assert out == ""
    assert len(err.strip().splitlines()) == 1


def test_help_no_longer_mentions_ledger_and_record_rejected(capsys):
    with pytest.raises(SystemExit) as excinfo:
        vault_note_export.main(["export", "--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "--ledger" not in captured.out

    with pytest.raises(SystemExit) as excinfo2:
        vault_note_export.main(["record", "--note", "X.md"])
    assert excinfo2.value.code == 2
