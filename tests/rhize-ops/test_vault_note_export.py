"""test_vault_note_export.py — vault_note_export.py note-to-Confluence-body conversion and
ledger tracking per task-1-brief.md Contract A. Fixture vault built under tmp_path; no
network, no real vault.
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
    assert "## Files to request from the delegator" in result["body_markdown"]
    assert "- diagram.png (image)" in result["body_markdown"]


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


def test_record_writes_ledger_then_export_reports_existing_and_changed(roots, capsys, tmp_path):
    root1, _root2 = roots
    note_path = write_note(root1, "Tracked.md", "Version 1\n")

    code, out, _err = run(["export", "--note", "Tracked.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    first_result = json.loads(out)
    sha1 = first_result["source_sha256"]
    assert first_result["existing_page_id"] is None
    assert first_result["existing_page_url"] is None
    assert first_result["changed"] is True

    ledger_path = tmp_path / "new_ledger_dir" / "ledger.json"
    code, out, _err = run(
        [
            "record", "--note", "Tracked.md", "--ledger", str(ledger_path),
            "--page-id", "123", "--url", "https://example.atlassian.net/wiki/pages/123",
            "--sha256", sha1,
        ],
        capsys,
    )
    assert code == 0
    assert out == "recorded Tracked.md -> 123\n"
    assert oct(ledger_path.stat().st_mode)[-3:] == "600"
    assert oct(ledger_path.parent.stat().st_mode)[-3:] == "700"

    code, out, _err = run(
        ["export", "--note", "Tracked.md", "--vault-root", str(root1), "--ledger", str(ledger_path)], capsys,
    )
    assert code == 0
    second_result = json.loads(out)
    assert second_result["existing_page_id"] == "123"
    assert second_result["existing_page_url"] == "https://example.atlassian.net/wiki/pages/123"
    assert second_result["existing_sha256"] == sha1
    assert second_result["changed"] is False

    note_path.write_text("Version 1\nplus an edit\n", encoding="utf-8")
    code, out, _err = run(
        ["export", "--note", "Tracked.md", "--vault-root", str(root1), "--ledger", str(ledger_path)], capsys,
    )
    assert code == 0
    third_result = json.loads(out)
    assert third_result["changed"] is True


def test_wikilink_to_note_already_in_ledger_becomes_markdown_link(roots, capsys, tmp_path):
    root1, _root2 = roots
    write_note(root1, "Linked Note.md", "target content\n")
    write_note(root1, "Referrer.md", "See [[Linked Note]] for details.\n")

    ledger_path = tmp_path / "ledger.json"
    code, out, _err = run(["export", "--note", "Linked Note.md", "--vault-root", str(root1)], capsys)
    assert code == 0
    sha_linked = json.loads(out)["source_sha256"]

    code, out, _err = run(
        [
            "record", "--note", "Linked Note.md", "--ledger", str(ledger_path),
            "--page-id", "456", "--url", "https://example.atlassian.net/wiki/pages/456",
            "--sha256", sha_linked,
        ],
        capsys,
    )
    assert code == 0

    code, out, _err = run(
        ["export", "--note", "Referrer.md", "--vault-root", str(root1), "--ledger", str(ledger_path)], capsys,
    )
    assert code == 0
    result = json.loads(out)
    assert "[Linked Note](https://example.atlassian.net/wiki/pages/456)" in result["body_markdown"]
    assert "Linked Note" not in result["unresolved_links"]


def test_corrupt_ledger_exits_2(roots, capsys, tmp_path):
    root1, _root2 = roots
    write_note(root1, "Note.md", "content\n")
    ledger_path = tmp_path / "corrupt_ledger.json"
    ledger_path.write_text("{not valid json", encoding="utf-8")

    code, out, err = run(
        ["export", "--note", "Note.md", "--vault-root", str(root1), "--ledger", str(ledger_path)], capsys,
    )
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


def test_ledger_write_oserror_exits_2_with_message(roots, capsys, tmp_path):
    root1, _root2 = roots
    write_note(root1, "Note.md", "content\n")
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    ledger_path = readonly_dir / "ledger.json"
    readonly_dir.chmod(0o500)
    try:
        code, out, err = run(
            [
                "record", "--note", "Note.md", "--ledger", str(ledger_path),
                "--page-id", "1", "--url", "https://example.com/1", "--sha256", "deadbeef",
            ],
            capsys,
        )
        assert code == 2
        assert out == ""
        assert len(err.strip().splitlines()) == 1
        assert not ledger_path.exists()
    finally:
        readonly_dir.chmod(0o700)
