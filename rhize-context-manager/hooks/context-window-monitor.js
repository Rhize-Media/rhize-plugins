#!/usr/bin/env node
/**
 * context-window-monitor — Rhize-owned replacement for ECC's suggest-compact.
 *
 * WHY THIS EXISTS
 * ECC's `suggest-compact.js` sizes the context window by sniffing the model id
 * for a literal `[1m]` marker, falling back to 200k. Opus 5 carries a 1M window
 * and no marker, so that hook divided ~195k by 200k and reported **97% when the
 * true figure was 20%** — a false "consider /compact" on every turn. It
 * self-corrects only once usage passes 200k (its `tokens > 200_000 -> assume
 * 1M` fallback), so the error is invisible from the message alone and wrong for
 * the entire run below 200k. Verified against the client UI 2026-07-28.
 *
 * THE FIX: a known-model table. A marker sniff can only detect windows a model
 * id happens to advertise; a table can state what we have actually verified.
 * That is the one thing the upstream design structurally cannot do.
 *
 * Contract (Claude Code PreToolUse hook):
 *   stdin  <- JSON { session_id, transcript_path, ... }
 *   stdout -> JSON { hookSpecificOutput: { hookEventName, additionalContext } }
 *   exit   -> always 0. A monitor must never block a tool call.
 *
 * Self-test:  node context-window-monitor.js --self-test
 */

'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const STANDARD_WINDOW = 200_000;
const LARGE_WINDOW = 1_000_000;

/**
 * Windows we have VERIFIED, longest-prefix wins.
 *
 * Only add an entry you have actually confirmed — against the client's context
 * readout, or vendor documentation. A wrong entry here is worse than no entry,
 * because it outranks the observed-usage evidence below it. An unlisted model
 * degrades to the same heuristics ECC used, which is the current behaviour, not
 * a regression.
 */
const KNOWN_WINDOWS = {
  // Confirmed 2026-07-28: client reported 197.3k / 1.0M for this model id.
  'claude-opus-5': LARGE_WINDOW,
};

const ENV_OVERRIDES = [
  'RHIZE_CONTEXT_WINDOW_TOKENS',
  'ECC_CONTEXT_WINDOW_TOKENS',      // honored so we never disagree with ECC
  'CLAUDE_CODE_AUTO_COMPACT_WINDOW',
];

const WARN_AT_PERCENT = Number(process.env.RHIZE_CONTEXT_WARN_PERCENT) || 75;
const REWARN_EVERY_PERCENT = 10;
const TRANSCRIPT_TAIL_BYTES = 256 * 1024;

/** Resolve the window, strongest signal first. */
function resolveWindowTokens(model, observedTokens, env = process.env) {
  for (const name of ENV_OVERRIDES) {
    const raw = String(env[name] || '').trim();
    if (/^\d+$/.test(raw) && Number(raw) > 0) {
      return { tokens: Number(raw), source: `env:${name}` };
    }
  }

  const id = String(model || '').toLowerCase();

  if (id.includes('[1m]')) {
    return { tokens: LARGE_WINDOW, source: 'model-marker' };
  }

  // Longest prefix wins so "claude-opus-5-mini" cannot match a shorter,
  // less specific entry ahead of its own.
  const hit = Object.keys(KNOWN_WINDOWS)
    .filter((k) => id.startsWith(k))
    .sort((a, b) => b.length - a.length)[0];
  if (hit) {
    return { tokens: KNOWN_WINDOWS[hit], source: `known:${hit}` };
  }

  // Evidence beats assumption: if usage already exceeds the standard window,
  // the window is demonstrably larger than standard.
  if (Number.isFinite(observedTokens) && observedTokens > STANDARD_WINDOW) {
    return { tokens: LARGE_WINDOW, source: 'observed-exceeds-standard' };
  }

  return { tokens: STANDARD_WINDOW, source: 'default' };
}

/** Sum the token fields that actually occupy the window. */
function extractUsageTokens(record) {
  const usage = record && record.message && record.message.usage;
  if (!usage || typeof usage !== 'object') return 0;
  const n = (v) => (Number.isFinite(v) ? v : 0);
  const total =
    n(usage.input_tokens) +
    n(usage.cache_read_input_tokens) +
    n(usage.cache_creation_input_tokens);
  return total > 0 ? total : 0;
}

/** Scan the transcript tail backwards for the most recent usage record. */
function readLatestUsage(transcriptPath) {
  if (!transcriptPath || typeof transcriptPath !== 'string') return null;

  let text;
  let truncated = false;
  try {
    const { size } = fs.statSync(transcriptPath);
    const start = Math.max(0, size - TRANSCRIPT_TAIL_BYTES);
    truncated = start > 0;
    const fd = fs.openSync(transcriptPath, 'r');
    try {
      const buf = Buffer.alloc(size - start);
      fs.readSync(fd, buf, 0, buf.length, start);
      text = buf.toString('utf8');
    } finally {
      fs.closeSync(fd);
    }
  } catch {
    return null;
  }

  const lines = text.split('\n');
  // A truncated tail almost certainly starts mid-record.
  const floor = truncated ? 1 : 0;
  for (let i = lines.length - 1; i >= floor; i--) {
    const line = lines[i].trim();
    if (!line) continue;
    let record;
    try {
      record = JSON.parse(line);
    } catch {
      continue;
    }
    const tokens = extractUsageTokens(record);
    if (tokens > 0) {
      const model =
        record.message && typeof record.message.model === 'string'
          ? record.message.model
          : '';
      return { tokens, model };
    }
  }
  return null;
}

/**
 * Fire at most once per REWARN_EVERY_PERCENT band, so a long session gets a
 * escalating nudge rather than one message per tool call.
 */
function shouldFire(sessionId, percent) {
  if (percent < WARN_AT_PERCENT) return false;
  const band = Math.floor(percent / REWARN_EVERY_PERCENT);
  const stateFile = path.join(
    os.tmpdir(),
    `rhize-ctx-band-${String(sessionId || 'nosession').replace(/[^\w.-]/g, '_')}`
  );
  try {
    if (fs.existsSync(stateFile)) {
      const seen = Number(fs.readFileSync(stateFile, 'utf8').trim());
      if (Number.isFinite(seen) && band <= seen) return false;
    }
    fs.writeFileSync(stateFile, String(band));
  } catch {
    // Statelessness degrades to "fire every call" — noisy but never wrong.
    // Preferable to suppressing a real warning because /tmp was unwritable.
  }
  return true;
}

function formatWindow(tokens) {
  return tokens >= LARGE_WINDOW
    ? `${(tokens / LARGE_WINDOW).toFixed(tokens % LARGE_WINDOW ? 1 : 0)}M`
    : `${Math.round(tokens / 1000)}k`;
}

function buildMessage(used, window, source) {
  const percent = Math.round((used / window) * 100);
  return (
    `[RhizeContext] ~${Math.round(used / 1000)}k of ${formatWindow(window)} ` +
    `(${percent}%, window via ${source}) — consider /compact at the next ` +
    `logical boundary.`
  );
}

function main() {
  let input = {};
  try {
    const raw = fs.readFileSync(0, 'utf8');
    if (raw.trim()) input = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  const usage = readLatestUsage(input.transcript_path);
  if (!usage) process.exit(0);

  const { tokens: window, source } = resolveWindowTokens(usage.model, usage.tokens);
  const percent = (usage.tokens / window) * 100;

  if (!shouldFire(input.session_id, percent)) process.exit(0);

  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        additionalContext: buildMessage(usage.tokens, window, source),
      },
    })
  );
  process.exit(0);
}

// ---------------------------------------------------------------------------

function selfTest() {
  const cases = [
    // [model, observedTokens, env, expectedWindow, expectedSource, note]
    ['claude-opus-5', 197_300, {}, LARGE_WINDOW, 'known:claude-opus-5',
      'THE BUG: ECC reported 97% here; correct is 20%'],
    ['claude-opus-4-8[1m]', 10, {}, LARGE_WINDOW, 'model-marker', 'explicit marker'],
    ['claude-sonnet-4', 10, {}, STANDARD_WINDOW, 'default', 'unlisted -> standard'],
    ['claude-sonnet-4', 250_000, {}, LARGE_WINDOW, 'observed-exceeds-standard',
      'evidence beats assumption'],
    ['claude-opus-5', 10, { ECC_CONTEXT_WINDOW_TOKENS: '1000000' }, LARGE_WINDOW,
      'env:ECC_CONTEXT_WINDOW_TOKENS', 'env outranks table'],
    ['claude-opus-5', 10, { RHIZE_CONTEXT_WINDOW_TOKENS: '400000' }, 400_000,
      'env:RHIZE_CONTEXT_WINDOW_TOKENS', 'rhize var wins over ECC var'],
    ['claude-opus-5', 10, { ECC_CONTEXT_WINDOW_TOKENS: 'garbage' }, LARGE_WINDOW,
      'known:claude-opus-5', 'junk env ignored, not fatal'],
    ['', 10, {}, STANDARD_WINDOW, 'default', 'empty model id'],
  ];

  let pass = 0;
  for (const [model, observed, env, wantTokens, wantSource, note] of cases) {
    const got = resolveWindowTokens(model, observed, env);
    const ok = got.tokens === wantTokens && got.source === wantSource;
    if (ok) pass++;
    console.log(
      `${ok ? 'PASS' : 'FAIL'}  ${(model || '<empty>').padEnd(21)} ` +
        `tok=${String(observed).padEnd(8)} -> ${String(got.tokens).padEnd(9)} ` +
        `${got.source.padEnd(30)} # ${note}`
    );
  }

  // The regression this hook exists to prevent, stated as an assertion.
  const real = resolveWindowTokens('claude-opus-5', 197_300, {});
  const pct = Math.round((197_300 / real.tokens) * 100);
  const pctOk = pct === 20;
  if (pctOk) pass++;
  console.log(
    `${pctOk ? 'PASS' : 'FAIL'}  regression: 197.3k on Opus 5 reads ${pct}% (want 20%, ECC said 97%)`
  );

  const total = cases.length + 1;
  console.log(`\n${pass}/${total} ${pass === total ? 'ALL PASS' : 'FAILURES PRESENT'}`);
  process.exit(pass === total ? 0 : 1);
}

if (process.argv.includes('--self-test')) {
  selfTest();
} else {
  main();
}

module.exports = { resolveWindowTokens, extractUsageTokens, readLatestUsage };
