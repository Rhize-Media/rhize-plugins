"""Frontend instruction contracts plus real compiler/router behavior; native outcomes are separate."""
import importlib.util
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "rhize-devflow"


def test_ui_specialist_has_a_matching_risk_category():
    text = (DEV / "commands/review.md").read_text()
    taxonomy = text.split("## Phase 3: Build the Risk Map", 1)[1].split("## Phase 4:", 1)[0]
    assert "UI/browser-facing changes" in taxonomy
    assert "animation" in taxonomy and "accessibility" in taxonomy


def test_browser_evidence_covers_visible_and_async_states():
    text = (DEV / "commands/browser-qa.md").read_text().lower()
    for contract in ["inspect screenshots", "keyboard", "focus", "reduced-motion", "re-entry", "pending", "empty", "unavailable", "playwright-cli", "75th percentile"]:
        assert contract in text, contract
    assert "inp/fid" not in text
    assert "immediate success stub" in text
    assert "disabled-button clicks may never reach the handler" in text


def test_mechanics_defer_to_active_schema():
    text = (DEV / "skills/chrome-devtools-mcp/SKILL.md").read_text()
    assert "active tool schema" in text
    assert "`sourceSelector`" not in text
    assert "`expression`" not in text
    reference = (DEV / "skills/chrome-devtools-mcp/references/TROUBLESHOOTING.md").read_text()
    assert "networkidle2" not in reference


def test_frontend_compiled_routing_and_nonvisual_controls():
    path = ROOT / "scripts/build_skill_map.py"
    spec = importlib.util.spec_from_file_location("frontend_build_map", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    index = module.build_router_index(module.build())
    script = r"""const fs=require('fs'); const core=require(process.argv[1]);
const index=JSON.parse(fs.readFileSync(0,'utf8'));
const prompts=['Plan frontend development for this page.', 'Improve the visual design of our dashboard.', 'Apply UI polish to the settings panel.', 'Plan frontend motion for this dialog.', 'Fix a backend SQL query.', 'Explain design patterns for database services.', 'Design a database schema for dashboard analytics.', 'Do not use frontend-development. Rename this variable only.', 'Use rhize-devflow:scroll-craft.', 'Use scroll craft to plan this launch.'];
console.log(JSON.stringify(prompts.map(p=>core.routeFromIndex(index,core.tokenize(p),p)?.skillId??null)));"""
    result = subprocess.run(["node", "-e", script, str(ROOT / "rhize-context-manager/hooks/lib/route-core.js")], input=json.dumps(index), text=True, capture_output=True, check=True)
    actual = json.loads(result.stdout)
    target = "skill:rhize-devflow/frontend-development"
    assert actual[:4] == [target] * 4
    assert all(value not in {target, 'skill:rhize-devflow/scroll-craft'} for value in actual[4:8])
    assert actual[8:] == ['skill:rhize-devflow/scroll-craft'] * 2


def test_native_case_contract_covers_families_and_controls():
    cases = json.loads((ROOT / "evals/rhize-devflow/frontend_cases.json").read_text())
    assert {c["family"] for c in cases if c["family"]} == {"taste", "designlang", "react-bits", "gsap", "playwright", "impeccable", "transitions", "reanimate", "unslop", "scroll-craft"}
    assert len({c["id"] for c in cases}) == len(cases)
    assert any(c["id"] == "backend-only" for c in cases)
    assert any(c["id"] == "unavailable" for c in cases)


def test_scroll_craft_is_bundled_but_narrowly_selected():
    skill = DEV / "skills/scroll-craft"
    assert {p.name for p in skill.iterdir()} == {"SKILL.md", "LICENSE"}
    text = (skill / "SKILL.md").read_text()
    manifest = json.loads((DEV / ".codex-plugin/plugin.json").read_text())
    assert manifest["skills"] == "./skills/"
    frontmatter = text.split("---", 2)[1]
    assert "name: scroll-craft" in frontmatter
    assert "allowed-tools:" not in frontmatter
    assert "Not for ordinary transitions" in frontmatter
    owner = (DEV / "skills/frontend-development/SKILL.md").read_text()
    row = next(line for line in owner.splitlines() if "rhize-devflow:scroll-craft" in line)
    assert "Explicit Scrollcraft or original scroll-driven narrative" in row
    assert "One direction owner" in row
    assert "Not a default" in row
    assert (DEV / "skills/frontend-development" / "../scroll-craft/SKILL.md").resolve() == (skill / "SKILL.md").resolve()
    assert "Copyright (c) 2026 Nate Herk" in (skill / "LICENSE").read_text()
    assert "75d81f74e83692add18cd7a8a8e078b8a887a579" in text
    for requirement in ("midpoint and exit", "worst frame", "failed media", "real phone",
                        "keyboard", "reduced motion", "Kie.ai"):
        assert requirement in text, requirement
    assert "does not run upstream scripts" in text
    assert "access credentials" in text and "upload assets" in text
