#!/usr/bin/env node
'use strict';

// test_router_matching.js — route-core's shared matcher: plural folding (S1),
// the partial-name signal and its guard (P1), and parity between the
// index-backed routeFromIndex(), the map-scan route() and the Python
// third-party inference tokenizer. Run as `node tests/skill-map/test_router_matching.js`
// (no test runner; same check()/PASS/FAIL harness as test_router.js).
//
// Unit checks require route-core directly; one end-to-end check spawns
// skill-router.js with HOME pointed at a temp dir (never the real ~/.claude)
// to prove display text keeps the original, unfolded labels.
//
// The ROUTER fixture below is a frozen subset of generated/skill-map.indexes.json
// (obsidian-second-brain family plus three rhize-devflow skills, as of
// 2026-10-10) so tag-vocabulary churn elsewhere can't move these assertions.

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const ROUTE_CORE = path.join(REPO_ROOT, 'rhize-context-manager', 'hooks', 'lib', 'route-core.js');
const ROUTER_PATH = path.join(REPO_ROOT, 'rhize-context-manager', 'hooks', 'skill-router.js');
const BUILD_LOCAL = path.join(REPO_ROOT, 'rhize-context-manager', 'scripts', 'build_local_skill_map.py');
const STEM_FIXTURE = path.join(__dirname, 'fixtures', 'stem-parity.json');

const core = require(ROUTE_CORE);

let failures = 0;
function check(name, fn) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (err) {
    failures += 1;
    console.error(`FAIL ${name}`);
    console.error(err && err.stack ? err.stack : err);
  }
}

const W = { name: 1, tag: 2, 'tag-inferred': 0.5 };
function sigs(pairs) {
  return pairs.map(([kind, label]) => ({ kind, weight: W[kind], label }));
}

const ROUTER = {
  signals: {
    'skill:obsidian-second-brain/defuddle': sigs([['name', 'defuddle'], ['tag', 'content-authoring'], ['tag', 'obsidian']]),
    'skill:obsidian-second-brain/json-canvas': sigs([['name', 'json-canvas'], ['tag', 'knowledge-management'], ['tag', 'obsidian'], ['tag', 'visualization']]),
    'skill:obsidian-second-brain/knowledge-compiler': sigs([['name', 'knowledge-compiler'], ['tag', 'knowledge-management'], ['tag', 'obsidian'], ['tag', 'provenance'], ['tag', 'workflow-patterns']]),
    'skill:obsidian-second-brain/obsidian-bases': sigs([['name', 'obsidian-bases'], ['tag', 'content-authoring'], ['tag', 'knowledge-management'], ['tag', 'obsidian']]),
    'skill:obsidian-second-brain/obsidian-cli': sigs([['name', 'obsidian-cli'], ['tag', 'automation'], ['tag', 'content-authoring'], ['tag', 'obsidian']]),
    'skill:obsidian-second-brain/obsidian-markdown': sigs([['name', 'obsidian-markdown'], ['tag', 'content-authoring'], ['tag', 'knowledge-management'], ['tag', 'obsidian']]),
    'skill:obsidian-second-brain/qmd-search': sigs([['name', 'qmd-search'], ['tag', 'knowledge-management'], ['tag', 'obsidian'], ['tag', 'search']]),
    'skill:obsidian-second-brain/second-brain': sigs([['name', 'second-brain'], ['tag', 'knowledge-management'], ['tag', 'obsidian'], ['tag', 'workflow-patterns']]),
    'skill:obsidian-second-brain/vault-alignment': sigs([['name', 'vault-alignment'], ['tag', 'knowledge-management'], ['tag', 'observability'], ['tag', 'obsidian']]),
    'skill:obsidian-second-brain/vault-templates': sigs([['name', 'vault-templates'], ['tag', 'content-authoring'], ['tag', 'knowledge-management'], ['tag', 'obsidian']]),
    'skill:rhize-devflow/data-mutation-consistency': sigs([['name', 'data-mutation-consistency'], ['tag', 'data-consistency'], ['tag', 'nextjs'], ['tag', 'postgresql'], ['tag', 'sanity'], ['tag', 'sentry'], ['tag', 'vercel'], ['tag', 'workflow-patterns']]),
    'skill:rhize-devflow/dev-flow-foundations': sigs([['name', 'dev-flow-foundations'], ['tag', 'project-planning'], ['tag', 'workflow-patterns']]),
    'skill:rhize-devflow/test-evidence': sigs([['name', 'test-evidence'], ['tag', 'evidence'], ['tag', 'review'], ['tag', 'testing']]),
  },
  extendsBases: {
    'skill:obsidian-second-brain/json-canvas': ['skill:obsidian-second-brain/obsidian-markdown'],
    'skill:obsidian-second-brain/obsidian-bases': ['skill:obsidian-second-brain/obsidian-markdown'],
    'skill:obsidian-second-brain/vault-alignment': ['skill:obsidian-second-brain/second-brain'],
    'skill:rhize-devflow/data-mutation-consistency': ['skill:rhize-devflow/dev-flow-foundations'],
    'skill:rhize-devflow/test-evidence': ['skill:rhize-devflow/dev-flow-foundations'],
  },
};

// Equivalent static-map document for the map-scan fallback route(): one tag
// node per distinct tag label, topic-tag edges, extends edges.
function docFromRouter(router) {
  const nodes = [];
  const edges = [];
  const tagIds = new Map();
  for (const [skillId, signals] of Object.entries(router.signals)) {
    const name = signals.find((s) => s.kind === 'name').label;
    nodes.push({ id: skillId, kind: 'skill', name });
    for (const s of signals) {
      if (s.kind !== 'tag') continue;
      if (!tagIds.has(s.label)) {
        tagIds.set(s.label, `tag:topic/${s.label}`);
        nodes.push({ id: `tag:topic/${s.label}`, kind: 'tag', name: s.label });
      }
      edges.push({ from: skillId, to: tagIds.get(s.label), type: 'topic-tag' });
    }
  }
  for (const [extender, bases] of Object.entries(router.extendsBases || {})) {
    for (const base of bases) edges.push({ from: extender, to: base, type: 'extends' });
  }
  return { nodes, edges };
}

function both(router, prompt) {
  const tokens = core.tokenize(prompt);
  return {
    index: core.routeFromIndex(router, tokens, prompt),
    map: core.route(docFromRouter(router), tokens, prompt),
  };
}

function labels(match) {
  return match ? match.signals.map((s) => s.label) : null;
}

// --- S1: stem parity ---------------------------------------------------------

check('[stem] normalizeWord/wordsOf reproduce every stem-parity.json entry', () => {
  const fixture = JSON.parse(fs.readFileSync(STEM_FIXTURE, 'utf8'));
  for (const [word, expected] of Object.entries(fixture.normalizeWord)) {
    assert.strictEqual(core.normalizeWord(word), expected, `normalizeWord(${JSON.stringify(word)})`);
  }
  for (const [text, expected] of Object.entries(fixture.wordsOf)) {
    assert.deepStrictEqual(core.wordsOf(text), expected, `wordsOf(${JSON.stringify(text)})`);
  }
  for (const [word, expected] of Object.entries(fixture.knownCollisions.pairs)) {
    assert.strictEqual(core.normalizeWord(word), expected, `documented collision ${word}`);
  }
  for (const [word, expected] of Object.entries(fixture.knownNonFolds.pairs)) {
    assert.strictEqual(core.normalizeWord(word), expected, `documented non-fold ${word}`);
  }
  // Required edge cases are present in the fixture, not just tested ad hoc.
  for (const w of ['bases', 'notes', 'glass', 'class', 'ss', 'is', 'yes', 'news', 'https', 'nextjs', 'policies', 'ies', 'series', 'analysis', 'status', 'canvas']) {
    assert.ok(Object.prototype.hasOwnProperty.call(fixture.normalizeWord, w), `fixture missing ${w}`);
  }
  assert.ok(Object.prototype.hasOwnProperty.call(fixture.wordsOf, "notes's"), "fixture missing notes's");
  assert.strictEqual(core.normalizeWord('testing'), 'testing', 'no -ing folding');
});

check('[stem] Python _normalize_word/_words_of agree with node on every fixture input', () => {
  const fixture = JSON.parse(fs.readFileSync(STEM_FIXTURE, 'utf8'));
  const words = Object.keys(fixture.normalizeWord);
  const texts = Object.keys(fixture.wordsOf);
  const script = [
    'import importlib.util, json, sys',
    'spec = importlib.util.spec_from_file_location("blsm", sys.argv[1])',
    'm = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)',
    'data = json.load(sys.stdin)',
    'print(json.dumps({"w": {w: m._normalize_word(w) for w in data["w"]}, "t": {t: list(m._words_of(t)) for t in data["t"]}}))',
  ].join('\n');
  const result = spawnSync('python3', ['-c', script, BUILD_LOCAL], {
    input: JSON.stringify({ w: words, t: texts }),
    encoding: 'utf8',
    timeout: 20000,
  });
  assert.strictEqual(result.status, 0, result.stderr);
  const py = JSON.parse(result.stdout);
  for (const w of words) assert.strictEqual(py.w[w], core.normalizeWord(w), `python vs node on ${JSON.stringify(w)}`);
  for (const t of texts) assert.deepStrictEqual(py.t[t], core.wordsOf(t), `python vs node on ${JSON.stringify(t)}`);
});

check('[stem] display labels are untouched: rawWordsOf keeps plurals, formatSignalLabel keeps the label', () => {
  assert.deepStrictEqual(core.rawWordsOf('Obsidian Bases'), ['obsidian', 'bases']);
  assert.strictEqual(core.formatSignalLabel({ kind: 'name', label: 'obsidian-bases' }), 'obsidian-bases');
});

// --- S1: plural flips --------------------------------------------------------

check('[S1] singular "Obsidian Base" prompt now meets the obsidian-bases name (both paths)', () => {
  const prompt = 'I want to build an Obsidian Base that acts as a reading list tracker for my notes';
  const { index, map } = both(ROUTER, prompt);
  assert.ok(index, 'expected a suggestion');
  assert.strictEqual(index.skillId, 'skill:obsidian-second-brain/obsidian-bases');
  assert.deepStrictEqual(labels(index), ['obsidian-bases', 'obsidian']);
  assert.strictEqual(index.score, 3);
  assert.strictEqual(map.skillId, index.skillId);
  assert.strictEqual(map.score, index.score);
});

check('[S1] "meeting notes template ... Obsidian vault" routes to vault-templates (both paths)', () => {
  const prompt = 'make a meeting notes template for my Obsidian vault';
  const { index, map } = both(ROUTER, prompt);
  assert.ok(index, 'expected a suggestion');
  assert.strictEqual(index.skillId, 'skill:obsidian-second-brain/vault-templates');
  assert.deepStrictEqual(labels(index), ['vault-templates', 'obsidian']);
  assert.strictEqual(map.skillId, index.skillId);
  assert.strictEqual(map.score, index.score);
});

check('[S1 e2e] skill-router message keeps the original plural label', () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), 'router-matching-test-'));
  try {
    const dir = path.join(tmpHome, '.claude', 'context-manager');
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, 'skill-map.indexes.json'), JSON.stringify({ router: ROUTER }));
    const result = spawnSync(process.execPath, [ROUTER_PATH], {
      input: JSON.stringify({ prompt: 'build an Obsidian Base for my reading list' }),
      env: { ...process.env, HOME: tmpHome, RHIZE_SUGGESTION_LOG: path.join(tmpHome, 'log.jsonl') },
      encoding: 'utf8',
      timeout: 5000,
    });
    assert.strictEqual(result.status, 0, result.stderr);
    const ctx = JSON.parse(result.stdout.trim()).hookSpecificOutput.additionalContext;
    assert.strictEqual(ctx, 'Consider the obsidian-second-brain:obsidian-bases skill (matches obsidian-bases, obsidian)');
  } finally {
    fs.rmSync(tmpHome, { recursive: true, force: true });
  }
});

// --- P1: partial-name signal --------------------------------------------------

check('[P1] "data mutation ... sanity" routes to data-mutation-consistency via a partial name (both paths)', () => {
  const prompt = 'Our Sanity data mutation leaves stale cache after a write';
  const { index, map } = both(ROUTER, prompt);
  assert.ok(index, 'expected a suggestion');
  assert.strictEqual(index.skillId, 'skill:rhize-devflow/data-mutation-consistency');
  assert.deepStrictEqual(labels(index), ['sanity', 'data-mutation-consistency (partial)']);
  assert.strictEqual(index.score, 2.5);
  const partial = index.signals[1];
  assert.strictEqual(partial.kind, 'name-partial');
  assert.strictEqual(partial.weight, 0.5);
  assert.strictEqual(map.skillId, index.skillId);
  assert.strictEqual(map.score, index.score);
  assert.deepStrictEqual(labels(map), labels(index));
});

check('[P1] no partial for names under 3 words or with 2+ missing words', () => {
  const tokens = core.tokenize('obsidian data');
  assert.strictEqual(core.matchSignals(ROUTER.signals['skill:obsidian-second-brain/obsidian-cli'], tokens).partial, null);
  assert.strictEqual(core.matchSignals(ROUTER.signals['skill:rhize-devflow/data-mutation-consistency'], tokens).partial, null);
});

check('[P1] a partial name never satisfies the full-weight floor on its own', () => {
  // dev-flow-foundations: "dev flow" present, "foundations" missing -> partial,
  // and nothing else matches -> one signal, no suggestion.
  const { index, map } = both(ROUTER, 'walk me through the dev flow');
  assert.strictEqual(index, null);
  assert.strictEqual(map, null);
  // Partial + an inferred tag = two sub-unit signals: still no qualification.
  const router = {
    signals: {
      'skill:mkt/acme/acme-widget-tools': [
        { kind: 'name', weight: 1, label: 'acme-widget-tools' },
        { kind: 'tag-inferred', weight: 0.5, label: 'workflow-patterns' },
      ],
    },
    extendsBases: {},
  };
  const prompt = 'widget tools for my workflow pattern';
  const tokens = core.tokenize(prompt);
  const m = core.matchSignals(router.signals['skill:mkt/acme/acme-widget-tools'], tokens);
  assert.ok(m.partial, 'partial should be eligible');
  assert.deepStrictEqual(m.matched.map((s) => s.label), ['workflow-patterns'], 'plural inferred tag meets singular prompt');
  assert.strictEqual(core.scoreCandidates(Object.entries(router.signals), tokens).size, 0);
  assert.strictEqual(core.routeFromIndex(router, tokens, prompt), null);
});

check('[P1 guard] a full-name match anywhere suppresses every partial (full name beats sibling partial)', () => {
  // review-outreach-businesses (third-party: name + inferred outreach = 1.5)
  // vs review-outreach-email (outreach tag 2 + partial 0.5 = 2.5 without the guard).
  const router = {
    signals: {
      'skill:mkt/outreach-kit/review-outreach-businesses': [
        { kind: 'name', weight: 1, label: 'review-outreach-businesses' },
        { kind: 'tag-inferred', weight: 0.5, label: 'outreach' },
      ],
      'skill:rhize-outreach/review-outreach-email': [
        { kind: 'name', weight: 1, label: 'review-outreach-email' },
        { kind: 'tag', weight: 2, label: 'outreach' },
      ],
    },
    extendsBases: {},
  };
  const prompt = 'review outreach businesses near me';
  const tokens = core.tokenize(prompt);
  // The sibling WOULD get a partial on its own...
  assert.ok(core.matchSignals(router.signals['skill:rhize-outreach/review-outreach-email'], tokens).partial);
  // ...but the guard drops it because review-outreach-businesses' full name matched.
  const best = core.routeFromIndex(router, tokens, prompt);
  assert.ok(best, 'expected a suggestion');
  assert.strictEqual(best.skillId, 'skill:mkt/outreach-kit/review-outreach-businesses');
  assert.strictEqual(best.score, 1.5);
  assert.ok(!best.signals.some((s) => s.kind === 'name-partial'));
  const scored = core.scoreCandidates(Object.entries(router.signals), tokens);
  assert.ok(!scored.has('skill:rhize-outreach/review-outreach-email'), 'sibling must not qualify on a guarded partial');

  // Control: no full name anywhere -> the partial applies, and the third-party
  // skill's own partial + inferred tag still cannot qualify.
  const control = 'review outreach drafts';
  const ctl = core.routeFromIndex(router, core.tokenize(control), control);
  assert.strictEqual(ctl.skillId, 'skill:rhize-outreach/review-outreach-email');
  assert.deepStrictEqual(labels(ctl), ['outreach', 'review-outreach-email (partial)']);
});

check('[P1 guard] map-scan route() applies the same guard', () => {
  const router = {
    signals: {
      'skill:a/review-outreach-businesses': sigs([['name', 'review-outreach-businesses']]),
      'skill:b/review-outreach-email': sigs([['name', 'review-outreach-email'], ['tag', 'outreach']]),
    },
    extendsBases: {},
  };
  // Full name of a (non-qualifying, single-signal) skill matches -> b's partial
  // is suppressed -> b has one signal -> silence on both paths.
  const guarded = both(router, 'review outreach businesses');
  assert.strictEqual(guarded.index, null);
  assert.strictEqual(guarded.map, null);
  const control = both(router, 'review outreach drafts');
  assert.strictEqual(control.index.skillId, 'skill:b/review-outreach-email');
  assert.strictEqual(control.map.skillId, 'skill:b/review-outreach-email');
  assert.strictEqual(control.map.score, control.index.score);
});

// --- Third-party floor under S1 ----------------------------------------------

check('[floor] inferred-only third-party matches still never qualify with folding', () => {
  const router = {
    signals: {
      'skill:mkt/kit/helper': [
        { kind: 'name', weight: 1, label: 'helper' },
        { kind: 'tag-inferred', weight: 0.5, label: 'memory-systems' },
        { kind: 'tag-inferred', weight: 0.5, label: 'workflow-patterns' },
        { kind: 'tag-inferred', weight: 0.5, label: 'backlink-analysis' },
      ],
    },
    extendsBases: {},
  };
  const prompt = 'a memory system workflow pattern for backlink analysis';
  const tokens = core.tokenize(prompt);
  const m = core.matchSignals(router.signals['skill:mkt/kit/helper'], tokens);
  assert.strictEqual(m.matched.length, 3, 'all three inferred tags match through folding');
  assert.strictEqual(core.routeFromIndex(router, tokens, prompt), null);
  // With the name present it qualifies at the documented 2.5 ceiling.
  const named = prompt + ' helper';
  assert.strictEqual(core.routeFromIndex(router, core.tokenize(named), named).score, 2.5);
});

if (failures > 0) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log('\nall checks passed');
