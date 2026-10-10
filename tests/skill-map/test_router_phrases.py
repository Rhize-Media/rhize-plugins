"""test_router_phrases.py — per-skill router phrases (`metadata.rhize.router.phrases`).

Covers scripts/build_skill_map.py's parse_router_phrases() validation (the
accepted shape plus every BuildError case), build_router_index()'s weight-2
`phrase` signal for the declaring skill only, and the committed artifacts
compiling to the phrases the five name-echo skills declare.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
build = load_module(REPO_ROOT / "scripts" / "build_skill_map.py", "build_skill_map_phrases")

REL = "plugin/skills/demo/SKILL.md"


def parse(router, own=frozenset()):
    return build.parse_router_phrases(router, set(own), REL)


# --- parse_router_phrases: accepted input ----------------------------------

def test_absent_router_yields_no_phrases():
    assert parse(None) == []
    assert parse({}) == []
    assert parse({"phrases": None}) == []


def test_valid_phrases_are_normalized_and_sorted():
    result = parse({"phrases": ["Web  Clipping", "cms-development", "learning curation"]})
    assert result == ["cms development", "learning curation", "web clipping"]


def test_three_phrases_is_the_limit_and_allowed():
    assert len(parse({"phrases": ["a b", "c d", "e f"]})) == 3


def test_phrase_differing_from_own_slug_is_allowed():
    assert parse({"phrases": ["context optimization"]}, {"context-engineering"}) == [
        "context optimization"
    ]


# --- parse_router_phrases: each BuildError ---------------------------------

@pytest.mark.parametrize(
    "router, own, message",
    [
        (["web clipping"], set(), "must be a mapping"),
        ({"phrases": ["web clipping"], "weight": 3}, set(), "unknown key"),
        ({"phrases": "web clipping"}, set(), "must be a list"),
        ({"phrases": ["a b", "c d", "e f", "g h"]}, set(), "at most 3"),
        ({"phrases": [42]}, set(), "must be a string"),
        ({"phrases": ["clipping"]}, set(), "at least 2 words"),
        ({"phrases": ["  web--  "]}, set(), "at least 2 words"),
        ({"phrases": ["web clipping", "Web-Clipping"]}, set(), "duplicate"),
        ({"phrases": ["context compression"]}, {"context-compression"}, "own tag slug"),
        ({"phrases": ["Context Compression"]}, {"context-compression"}, "own tag slug"),
    ],
)
def test_invalid_phrases_raise_build_error(router, own, message):
    with pytest.raises(build.BuildError) as excinfo:
        parse(router, own)
    assert message in str(excinfo.value)
    assert REL in str(excinfo.value)


# --- build_router_index ----------------------------------------------------

def _doc():
    return {
        "schemaVersion": "1.1.0",
        "nodes": [
            {"id": "skill:p/with-phrase", "kind": "skill", "name": "with-phrase",
             "routerPhrases": ["web clipping", "article extraction"]},
            {"id": "skill:p/plain", "kind": "skill", "name": "plain"},
            {"id": "tag:topic/content-authoring", "kind": "tag", "name": "content-authoring"},
        ],
        "edges": [
            {"from": "skill:p/with-phrase", "to": "tag:topic/content-authoring",
             "type": "topic-tag", "source": "frontmatter"},
            {"from": "skill:p/plain", "to": "tag:topic/content-authoring",
             "type": "topic-tag", "source": "frontmatter"},
        ],
    }


def test_router_index_emits_phrase_signals_for_declaring_skill_only():
    signals = build.build_router_index(_doc())["signals"]
    assert signals["skill:p/with-phrase"] == [
        {"kind": "name", "weight": 1, "label": "with-phrase"},
        {"kind": "phrase", "weight": 2, "label": "article extraction"},
        {"kind": "phrase", "weight": 2, "label": "web clipping"},
        {"kind": "tag", "facet": "topic", "weight": 2, "label": "content-authoring"},
    ]
    assert all(s["kind"] != "phrase" for s in signals["skill:p/plain"])


def test_router_index_is_deterministic_regardless_of_phrase_order():
    doc_a = _doc()
    doc_b = _doc()
    doc_b["nodes"][0]["routerPhrases"] = list(reversed(doc_b["nodes"][0]["routerPhrases"]))
    assert build.build_router_index(doc_a) == build.build_router_index(doc_b)


# --- committed artifacts ---------------------------------------------------

EXPECTED = {
    "skill:obsidian-second-brain/defuddle": ["web clipping"],
    "skill:rhize-devflow/sanity-development": ["cms development"],
    "skill:rhize-outreach/review-outreach-businesses": ["candidate businesses"],
    "skill:rhize-context-manager/context-optimization": ["context optimization"],
    "skill:rhize-context-manager/learning-curation": ["learning curation"],
}


def test_repo_sources_compile_to_declared_phrases():
    """Built from the repo's own SKILL.md sources in memory (not the committed
    generated/ files, which are regenerated separately)."""
    document = build.build()
    declared = {
        n["id"]: n["routerPhrases"] for n in document["nodes"] if n.get("routerPhrases")
    }
    assert declared == EXPECTED
    for skill_id, signals in build.build_router_index(document)["signals"].items():
        phrases = [s["label"] for s in signals if s["kind"] == "phrase"]
        assert phrases == EXPECTED.get(skill_id, []), skill_id
        assert all(s["weight"] == 2 for s in signals if s["kind"] == "phrase")


# Codex review (2026-10-10): validation must compare phrases the way the router
# matches them — unordered, plural-folded word sets — not as literal text.
def test_phrase_matching_own_slug_after_plural_folding_is_rejected():
    with pytest.raises(build.BuildError, match="repeats the skill's own tag slug"):
        build.parse_router_phrases({"phrases": ["SEO audits"]}, {"seo-audit"}, "x/SKILL.md")


def test_reordered_phrase_is_a_duplicate():
    with pytest.raises(build.BuildError, match="duplicate router phrase"):
        build.parse_router_phrases({"phrases": ["web clipping", "clipping web"]}, set(), "x/SKILL.md")


def test_plural_variant_phrase_is_a_duplicate():
    with pytest.raises(build.BuildError, match="duplicate router phrase"):
        build.parse_router_phrases({"phrases": ["web clipping", "web clippings"]}, set(), "x/SKILL.md")
