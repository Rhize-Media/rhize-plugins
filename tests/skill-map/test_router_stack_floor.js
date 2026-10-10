'use strict';
// A router match made only of stack tags ("sanity" + "vercel") must not
// qualify: stacks say what a prompt is built on, not what it asks for.
// Topic tags, names and phrases still qualify alongside a stack tag, and
// signals without a facet (older indexes, inferred tags) behave as before.
const assert = require('assert');
const path = require('path');
const rc = require(path.join(__dirname, '..', '..', 'rhize-context-manager', 'hooks', 'lib', 'route-core.js'));

let passed = 0;
function check(name, fn) { fn(); passed += 1; console.log(`ok - ${name}`); }

const index = {
  signals: {
    'skill:p/data-sync': [
      { kind: 'name', weight: 1, label: 'data-sync' },
      { kind: 'tag', facet: 'stack', weight: 2, label: 'sanity' },
      { kind: 'tag', facet: 'stack', weight: 2, label: 'vercel' },
      { kind: 'tag', facet: 'topic', weight: 2, label: 'data-consistency' },
    ],
  },
  extendsBases: {},
};
const route = (prompt) => rc.routeFromIndex(index, rc.tokenize(prompt), prompt);

check('two stack tags alone do not qualify', () => {
  assert.strictEqual(route('the vercel build for our sanity site fails on a TypeError'), null);
});
check('stack tag plus topic tag qualifies', () => {
  const r = route('sanity writes leave data consistency problems');
  assert.ok(r && r.skillId === 'skill:p/data-sync');
});
check('stack tag plus name qualifies', () => {
  const r = route('run data sync for the sanity dataset');
  assert.ok(r && r.skillId === 'skill:p/data-sync');
});
check('facet-less tag signals keep the old floor', () => {
  const legacy = { signals: { 'skill:p/x': [
    { kind: 'tag', weight: 2, label: 'sanity' },
    { kind: 'tag', weight: 2, label: 'vercel' },
  ] }, extendsBases: {} };
  const r = rc.routeFromIndex(legacy, rc.tokenize('sanity on vercel'), 'sanity on vercel');
  assert.ok(r && r.skillId === 'skill:p/x');
});
check('map-scan route() applies the same floor', () => {
  const doc = {
    nodes: [
      { id: 'skill:p/data-sync', kind: 'skill', name: 'data-sync' },
      { id: 'tag:stack/sanity', kind: 'tag', name: 'sanity' },
      { id: 'tag:stack/vercel', kind: 'tag', name: 'vercel' },
    ],
    edges: [
      { from: 'skill:p/data-sync', to: 'tag:stack/sanity', type: 'stack-tag' },
      { from: 'skill:p/data-sync', to: 'tag:stack/vercel', type: 'stack-tag' },
    ],
  };
  assert.strictEqual(rc.route(doc, rc.tokenize('sanity on vercel'), 'sanity on vercel'), null);
});

// Codex review (2026-10-10): a partial name must not count as task evidence,
// or two stack tags plus a partial name would bypass the stack floor.
check('stack tags plus a partial name do not qualify', () => {
  const idx = { signals: { 'skill:p/nextjs-sanity-seo': [
    { kind: 'name', weight: 1, label: 'nextjs-sanity-seo' },
    { kind: 'tag', facet: 'stack', weight: 2, label: 'nextjs' },
    { kind: 'tag', facet: 'stack', weight: 2, label: 'sanity' },
    { kind: 'tag', facet: 'topic', weight: 2, label: 'content-optimization' },
  ] }, extendsBases: {} };
  const p = 'our nextjs app pulls content from sanity and the build is slow';
  assert.strictEqual(rc.routeFromIndex(idx, rc.tokenize(p), p), null);
});
// Codex review (2026-10-10): the map-scan fallback must see router phrases.
check('route() fallback emits phrase signals like the index', () => {
  const doc = {
    nodes: [
      { id: 'skill:p/clipper', kind: 'skill', name: 'clipper', routerPhrases: ['web clipping'] },
      { id: 'tag:stack/obsidian', kind: 'tag', name: 'obsidian' },
    ],
    edges: [{ from: 'skill:p/clipper', to: 'tag:stack/obsidian', type: 'stack-tag' }],
  };
  const p = 'web clipping into my obsidian vault';
  const viaMap = rc.route(doc, rc.tokenize(p), p);
  const idx = { signals: { 'skill:p/clipper': [
    { kind: 'name', weight: 1, label: 'clipper' },
    { kind: 'phrase', weight: 2, label: 'web clipping' },
    { kind: 'tag', facet: 'stack', weight: 2, label: 'obsidian' },
  ] }, extendsBases: {} };
  const viaIndex = rc.routeFromIndex(idx, rc.tokenize(p), p);
  assert.ok(viaMap && viaIndex && viaMap.skillId === viaIndex.skillId && viaMap.score === viaIndex.score);
});
console.log(`${passed} passed`);
