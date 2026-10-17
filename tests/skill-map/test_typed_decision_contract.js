#!/usr/bin/env node
// Typed-decision contract: Node reference vs the shared fixtures (plan §4.2, §4.4).
// The Python half is tests/rhize-context-manager/test_typed_decision_contract.py.
// Run: node tests/skill-map/test_typed_decision_contract.js
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO = path.resolve(__dirname, '..', '..');
const FIX = path.join(REPO, 'tests', 'rhize-context-manager', 'fixtures', 'typed-decisions');
const LIB = path.join(REPO, 'rhize-context-manager', 'hooks', 'lib');
const instrument = require(path.join(LIB, 'laya-instrument.js'));
const td = require(path.join(LIB, 'typed-decisions.js'));
const core = require(path.join(LIB, 'route-core.js'));

const load = (name) => JSON.parse(fs.readFileSync(path.join(FIX, name), 'utf8'));
let passed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
  } catch (err) {
    console.error(`FAIL ${name}: ${err.message}`);
    process.exitCode = 1;
  }
}

const requests = load('laya-choice-requests.json');
for (const c of requests.cases) {
  check(`request ${c.name}`, () => {
    const built = instrument.buildChoiceRequest(c.prompt, c.candidates);
    assert.strictEqual(instrument.canonicalJson(built.request), c.expected.canonicalRequest);
    assert.deepStrictEqual(built.keyMap, c.expected.keyMap);
    assert.strictEqual(built.truncated, c.expected.truncated);
    assert.strictEqual(built.promptLengthBucket, c.expected.promptLengthBucket);
    assert.strictEqual(built.criteriaSha256, c.expected.criteriaSha256);
    assert.strictEqual(built.instrumentSha256, c.expected.instrumentSha256);
  });
}
for (const c of requests.invalid) {
  check(`invalid request ${c.name}`, () => {
    assert.throws(() => instrument.buildChoiceRequest(c.prompt, c.candidates));
  });
}
for (const c of requests.lengthBuckets) {
  check(`length bucket ${c.length}`, () => assert.strictEqual(instrument.lengthBucket(c.prompt), c.bucket));
}

for (const c of load('laya-choice-responses.json').cases) {
  check(`response ${c.name}`, () => {
    if (c.expected) {
      assert.deepStrictEqual(instrument.decodeChoiceResponse(c.response, c.keyMap), c.expected);
    } else {
      assert.throws(() => instrument.decodeChoiceResponse(c.response, c.keyMap), /invalid_response/);
    }
  });
}

const ids = load('identities.json');
check('policy and instrument hashes', () => {
  for (const [policy, digest] of Object.entries(ids.policySha256)) assert.strictEqual(td.policySha256(policy), digest);
  assert.deepStrictEqual(Object.keys(ids.policySha256).sort(), [td.POLICY_ADVISE, td.POLICY_COSIGN].sort());
  assert.strictEqual(instrument.instrumentSha256(), ids.instrumentSha256);
});
for (const c of ids.occurrenceKeys) {
  check(`occurrenceKey ${c.ts}`, () => assert.strictEqual(td.occurrenceKey(c.sessionHash, c.promptHash, c.ts), c.expected));
}
check('arms', () => {
  for (const c of ids.arms) assert.strictEqual(td.armFor(c.sessionHash, c.promptHash, c.holdback), c.expected);
});
check('minuteOf rejects naive timestamps', () => assert.throws(() => td.minuteOf('2026-10-11T17:51:05')));

const shortlist = load('lexical-shortlist.json');
for (const c of shortlist.cases) {
  check(`lexicalShortlist ${c.name}`, () => {
    assert.deepStrictEqual(core.lexicalShortlist(shortlist.index, core.tokenize(c.prompt), c.incumbentId, c.k), c.expected);
  });
}

const records = load('records.json').valid;
check('isDisagreement', () => {
  assert.strictEqual(td.isDisagreement(records['live-shadow-agree']), false);
  assert.strictEqual(td.isDisagreement(records['live-cosign-disagree-suppressed']), true);
  assert.strictEqual(td.isDisagreement(records['live-timeout-emits']), false);
});

if (process.exitCode) {
  console.error(`test_typed_decision_contract.js: failures (passed ${passed})`);
} else {
  console.log(`test_typed_decision_contract.js: ${passed} checks passed`);
}
