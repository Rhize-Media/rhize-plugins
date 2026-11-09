"""Shipped agent instructions must not regress the approved indexing boundary."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / "obsidian-second-brain"


def test_setup_surfaces_share_the_approved_indexing_procedure():
    for relative in ("README.md", "GUIDE.md", "commands/vault-setup.md", "skills/qmd-search/SKILL.md"):
        text = (ROOT / relative).read_text()
        assert "approved-indexing.md" in text, relative
        assert "whole vault" in " ".join(text.split()), relative
    reference = (ROOT / "skills/qmd-search/references/approved-indexing.md").read_text()
    for boundary in ("strict subfolder", "symlink", ".rhize/compiled-knowledge", "compiler output",
                     "old indexed", "update hooks", "not activation switches"):
        assert boundary in reference
    assert reference.index('"$QMD_INDEX" update') < reference.index('"$QMD_INDEX" embed')


def test_operational_examples_cannot_use_legacy_or_unscoped_qmd_commands():
    files = [ROOT / "README.md", ROOT / "GUIDE.md", *ROOT.glob("commands/*.md"),
             *ROOT.glob("skills/qmd-search/**/*.md")]
    for path in files:
        text = path.read_text()
        assert not re.search(r"npm install -g qmd\b|qmd (?:status|embed|search|vsearch|query) vault\b", text), path
        assert not re.search(r"qmd collection add vault\b|--include [\"']\*\.md", text), path
        # Executable retrieval examples must select both index and collection.
        examples = re.findall(r'`(qmd [^`\n]+)`', text)
        examples += [line for line in text.splitlines() if line.startswith("qmd ")]
        for command in examples:
            if re.search(r'\b(?:search|vsearch|query)\s+"', command):
                assert "--index" in command and " -c " in command, (path, command)


def test_retrieval_and_health_instructions_preserve_boundaries():
    for name in ("vault-search", "vault-recall", "vault-connect"):
        text = (ROOT / f"commands/{name}.md").read_text()
        assert "approved indexing procedure" in text
        assert "same authorized note scope" in text
        assert "Never silently broaden" in text
    for relative in ("commands/vault-align.md", "skills/knowledge-compiler/SKILL.md", "GUIDE.md"):
        text = (ROOT / relative).read_text()
        assert "read-only" in text or "observation-only scheduled tasks" in text
        assert "recover" in text
