"""test_setup_manifest_schema.py — setup manifest schema 1/2/3 validation
(hybrid-setup-wizard.md R2 §1, §6).

Schema 2 keeps evaluation_setup.py's exact-key check unchanged. Schema 3 adds the optional
wizard/doctor/artifacts blocks. Schema 1 is inventory-only (no evaluation binding) and is read
through the lenient read_manifest_inventory(), never the strict validate_manifest().
"""
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "rhize-core" / "scripts" / "evaluation_setup.py"
SPEC = importlib.util.spec_from_file_location("evaluation_setup", SCRIPT)
evaluation_setup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(evaluation_setup)

VALID_EVALUATIONS = {"catalog": "rhize-evaluations-v1", "component": "widgets"}
VALID_WIZARD = {"skill": "widgets:widgets-setup", "purpose": "Set widgets up.", "when": "optional"}
VALID_ARTIFACT = {
    "id": "widgets-config",
    "path": "<home>/.widgets/config.json",
    "kind": "file",
    "purpose": "Widget configuration.",
    "viewer": "cat ~/.widgets/config.json",
    "lifetime": "persistent",
    "confidentiality": "config",
    "source": "authored",
    "tracked": "outside-repo",
    "optional": False,
}


def write_manifest(repo_root: Path, plugin: str, manifest: dict) -> Path:
    path = repo_root / plugin / "setup" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def write_command(repo_root: Path, plugin: str, command: str, *, frontmatter: bool = True) -> Path:
    path = repo_root / plugin / "commands" / f"{command}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if frontmatter:
        path.write_text(f"---\ndescription: does the thing\n---\n\n# /{plugin}:{command}\n", encoding="utf-8")
    else:
        path.write_text(f"# /{plugin}:{command}\n\nNo frontmatter here.\n", encoding="utf-8")
    return path


def base_manifest(schema: int, plugin: str = "widgets", **extra) -> dict:
    manifest = {"schema": schema, "plugin": plugin, "items": [], "dependencies": []}
    if schema != 1:
        manifest["evaluations"] = {"catalog": "rhize-evaluations-v1", "component": plugin}
    manifest.update(extra)
    return manifest


# ---------- schema 1: inventory-only ----------

def test_schema_1_is_inventory_only_and_reports_evaluation_missing(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(1))
    inventory = evaluation_setup.read_manifest_inventory(tmp_path, "widgets")
    assert inventory["evaluation_status"] == "missing"
    assert inventory["schema"] == 1
    assert inventory["wizard"] is None
    assert inventory["artifacts"] == []


def test_schema_1_never_satisfies_the_strict_validator(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(1))
    with pytest.raises(evaluation_setup.SetupError, match="evaluation catalog binding"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_1_rejects_an_evaluations_key() -> None:
    # Schema 1's exact key set is {schema, plugin, items, dependencies} -- no evaluations.
    manifest = base_manifest(1)
    manifest["evaluations"] = VALID_EVALUATIONS
    with pytest.raises(evaluation_setup.SetupError):
        evaluation_setup.exact_keys(manifest, evaluation_setup.MANIFEST_SCHEMA1_KEYS, "manifest")


# ---------- schema 2: unchanged exact-key behavior ----------

def test_schema_2_still_requires_exact_keys(tmp_path: Path) -> None:
    manifest = base_manifest(2)
    manifest["extra"] = "not allowed"
    write_manifest(tmp_path, "widgets", manifest)
    with pytest.raises(evaluation_setup.SetupError, match="must contain exactly"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_2_rejects_wizard_block() -> None:
    # Schema 2 never gained the optional keys -- only schema 3 did.
    manifest = base_manifest(2)
    manifest["wizard"] = VALID_WIZARD
    with pytest.raises(evaluation_setup.SetupError):
        evaluation_setup.exact_keys(manifest, evaluation_setup.MANIFEST_CORE_KEYS, "manifest")


def test_schema_2_parses_and_is_bound(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(2))
    inventory = evaluation_setup.read_manifest_inventory(tmp_path, "widgets")
    assert inventory["evaluation_status"] == "bound"
    assert inventory["schema"] == 2


# ---------- schema 3: optional wizard/doctor/artifacts ----------

def test_schema_3_with_no_optional_keys_is_valid(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3))
    manifest = evaluation_setup.validate_manifest(tmp_path, "widgets")
    assert manifest["schema"] == 3


def test_schema_3_with_only_empty_artifacts_is_valid(tmp_path: Path) -> None:
    # seo-aeo-geo's shape: no wizard, an explicit empty artifacts array.
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[]))
    manifest = evaluation_setup.validate_manifest(tmp_path, "widgets")
    assert manifest["artifacts"] == []


def test_schema_3_rejects_unknown_top_level_keys(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3, notAKey="nope"))
    with pytest.raises(evaluation_setup.SetupError, match="must contain"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_3_wizard_requires_a_real_command_with_frontmatter(tmp_path: Path) -> None:
    write_command(tmp_path, "widgets", "widgets-setup", frontmatter=True)
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=VALID_WIZARD, artifacts=[VALID_ARTIFACT]))
    manifest = evaluation_setup.validate_manifest(tmp_path, "widgets")
    assert manifest["wizard"]["skill"] == "widgets:widgets-setup"


def test_schema_3_wizard_command_must_exist(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=VALID_WIZARD, artifacts=[VALID_ARTIFACT]))
    with pytest.raises(evaluation_setup.SetupError, match="does not exist"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_3_wizard_command_must_have_description_frontmatter(tmp_path: Path) -> None:
    write_command(tmp_path, "widgets", "widgets-setup", frontmatter=False)
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=VALID_WIZARD, artifacts=[VALID_ARTIFACT]))
    with pytest.raises(evaluation_setup.SetupError, match="description"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_3_wizard_implies_non_empty_artifacts(tmp_path: Path) -> None:
    write_command(tmp_path, "widgets", "widgets-setup", frontmatter=True)
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=VALID_WIZARD, artifacts=[]))
    with pytest.raises(evaluation_setup.SetupError, match="wizard but no artifacts"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=VALID_WIZARD))
    with pytest.raises(evaluation_setup.SetupError, match="wizard but no artifacts"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


@pytest.mark.parametrize("when", ["invented", "", "REQUIRED"])
def test_schema_3_wizard_when_is_pinned(tmp_path: Path, when: str) -> None:
    write_command(tmp_path, "widgets", "widgets-setup", frontmatter=True)
    wizard = {**VALID_WIZARD, "when": when}
    write_manifest(tmp_path, "widgets", base_manifest(3, wizard=wizard, artifacts=[VALID_ARTIFACT]))
    with pytest.raises(evaluation_setup.SetupError, match="when"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_3_doctor_kind_is_pinned(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3, doctor={"kind": "web", "value": "http://x"}))
    with pytest.raises(evaluation_setup.SetupError, match="kind"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_schema_3_doctor_shell_and_skill_are_valid(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3, doctor={"kind": "shell", "value": "widgets doctor"}))
    manifest = evaluation_setup.validate_manifest(tmp_path, "widgets")
    assert manifest["doctor"]["kind"] == "shell"


# ---------- artifact path placeholders ----------

@pytest.mark.parametrize("path", [
    "/absolute/path",
    "~/home/path",
    "relative/no-placeholder",
    "<home>/../escape",
    "<home>/ok/<vault>/nested",
])
def test_artifact_path_placeholder_rules_reject_bad_paths(tmp_path: Path, path: str) -> None:
    artifact = {**VALID_ARTIFACT, "path": path}
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[artifact]))
    with pytest.raises(evaluation_setup.SetupError):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


@pytest.mark.parametrize("path", ["<project>/file.json", "<home>/.widgets/config.json", "<vault>/notes/file.md", "<home>"])
def test_artifact_path_placeholder_rules_accept_good_paths(tmp_path: Path, path: str) -> None:
    artifact = {**VALID_ARTIFACT, "path": path}
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[artifact]))
    manifest = evaluation_setup.validate_manifest(tmp_path, "widgets")
    assert manifest["artifacts"][0]["path"] == path


@pytest.mark.parametrize("field,value", [
    ("kind", "folder"),
    ("lifetime", "forever"),
    ("confidentiality", "top-secret"),
    ("source", "magic"),
    ("tracked", "everywhere"),
])
def test_artifact_enum_fields_are_pinned(tmp_path: Path, field: str, value: str) -> None:
    artifact = {**VALID_ARTIFACT, field: value}
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[artifact]))
    with pytest.raises(evaluation_setup.SetupError):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_artifact_ids_must_be_unique(tmp_path: Path) -> None:
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[VALID_ARTIFACT, VALID_ARTIFACT]))
    with pytest.raises(evaluation_setup.SetupError, match="unique"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


def test_artifact_optional_must_be_boolean(tmp_path: Path) -> None:
    artifact = {**VALID_ARTIFACT, "optional": "yes"}
    write_manifest(tmp_path, "widgets", base_manifest(3, artifacts=[artifact]))
    with pytest.raises(evaluation_setup.SetupError, match="optional"):
        evaluation_setup.validate_manifest(tmp_path, "widgets")


# ---------- every shipped manifest parses ----------

def test_every_shipped_manifest_is_schema_3_and_parses() -> None:
    marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    checked = 0
    for entry in marketplace["plugins"]:
        plugin = entry["name"]
        manifest_path = REPO / plugin / "setup" / "manifest.json"
        assert manifest_path.is_file(), f"{plugin} has no setup/manifest.json"
        manifest = evaluation_setup.validate_manifest(REPO, plugin)
        assert manifest["schema"] == 3, f"{plugin} manifest is not schema 3"
        inventory = evaluation_setup.read_manifest_inventory(REPO, plugin)
        assert inventory["evaluation_status"] == "bound"
        checked += 1
    assert checked == len(marketplace["plugins"])


def test_wizard_declaring_plugins_have_resolvable_commands() -> None:
    marketplace = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    wizards_found = 0
    for entry in marketplace["plugins"]:
        plugin = entry["name"]
        manifest = json.loads((REPO / plugin / "setup" / "manifest.json").read_text())
        wizard = manifest.get("wizard")
        if wizard is None:
            continue
        wizards_found += 1
        command_plugin, command_name = wizard["skill"].split(":", 1)
        command_path = REPO / command_plugin / "commands" / f"{command_name}.md"
        assert command_path.is_file(), f"{plugin} wizard references missing command {command_path}"
        assert evaluation_setup.command_has_description_frontmatter(command_path.read_text(encoding="utf-8"))
    assert wizards_found == 5, "expected exactly 5 plugins to declare a wizard in this release"
