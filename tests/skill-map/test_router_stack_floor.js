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
console.log(`${passed} passed`);
