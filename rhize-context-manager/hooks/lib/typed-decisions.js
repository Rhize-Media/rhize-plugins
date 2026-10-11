'use strict';
// Typed-decision contract helpers for hooks (Node mirror of the identity and
// policy parts of scripts/typed_decisions/contract.py). Coordinator-owned:
// lanes import these and never redefine them. Parity is pinned by
// tests/rhize-context-manager/fixtures/typed-decisions/identities.json.
const { canonicalJson, sha256Hex } = require('./laya-instrument.js');

const RECORD_SCHEMA = 'rhize-typed-decision-record-v1';
const POLICY_COSIGN = 'cosign-v1';
const POLICIES = {
  [POLICY_COSIGN]: 'emit the incumbent router suggestion iff laya.status == "ok" and laya.choice '
    + '== incumbent.skillId; otherwise emit no router suggestion',
};
const HEX64 = /^[0-9a-f]{64}$/;

function policySha256(policy = POLICY_COSIGN) {
  if (!Object.prototype.hasOwnProperty.call(POLICIES, policy)) throw new Error('unknown policy');
  return sha256Hex(canonicalJson({ policy, rule: POLICIES[policy] }));
}

// UTC 'YYYY-MM-DDTHH:MM' for an ISO-8601 timestamp that carries Z or an offset.
function minuteOf(ts) {
  if (typeof ts !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(ts)) throw new Error('invalid timestamp');
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) throw new Error('invalid timestamp');
  return date.toISOString().slice(0, 16);
}

function requireHex64(value, field) {
  if (typeof value !== 'string' || !HEX64.test(value)) throw new Error(`invalid ${field}`);
}

// Stable identity of one router-hook run (plan §4.4).
function occurrenceKey(sessionHash, promptHash, ts) {
  requireHex64(sessionHash, 'sessionHash');
  requireHex64(promptHash, 'promptHash');
  return sha256Hex(`${sessionHash}:${promptHash}:${minuteOf(ts)}`);
}

// Deterministic arm: 'holdback' when the hash bucket falls below holdback x 10000.
function armFor(sessionHash, promptHash, holdback) {
  requireHex64(sessionHash, 'sessionHash');
  requireHex64(promptHash, 'promptHash');
  if (typeof holdback !== 'number' || !Number.isFinite(holdback) || holdback < 0 || holdback > 0.5) {
    throw new Error('invalid holdback');
  }
  const bucket = parseInt(sha256Hex(`${sessionHash}:${promptHash}`).slice(0, 8), 16) % 10000;
  // Python's round() is banker's rounding; holdback*10000 is integral for every
  // registry value with at most 4 decimals, so Math.round agrees there.
  return bucket < Math.round(holdback * 10000) ? 'holdback' : 'treatment';
}

// Storage layout shared with scripts/typed_decisions/records.py:
//   <root>/<decision>/records/<YYYY-MM-DD>.jsonl (UTC day of record.ts)
// <root> defaults to ~/.local/share/rhize/typed-decisions; RHIZE_TYPED_DECISIONS_ROOT overrides it.
function defaultRoot(env = process.env, homedir = require('os').homedir()) {
  if (env.RHIZE_TYPED_DECISIONS_ROOT) return env.RHIZE_TYPED_DECISIONS_ROOT;
  return require('path').join(homedir, '.local', 'share', 'rhize', 'typed-decisions');
}

function recordsPath(root, decision, ts) {
  return require('path').join(root, decision, 'records', `${minuteOf(ts).slice(0, 10)}.jsonl`);
}

function isDisagreement(record) {
  const incumbent = record && record.incumbent;
  const laya = (record && record.laya) || {};
  return Boolean(incumbent) && laya.status === 'ok' && laya.choice !== incumbent.skillId;
}

module.exports = {
  RECORD_SCHEMA, POLICY_COSIGN, POLICIES, policySha256, minuteOf, occurrenceKey, armFor, isDisagreement,
  defaultRoot, recordsPath,
};
