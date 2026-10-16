'use strict';
// Select fixed credential procedure guidance; permission and GUI denies remain independent.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { performance } = require('perf_hooks');
const catalog = require('../catalog/credential-workflows.json');
const { readDecisionConfig } = require('./lib/decision-registry.js');
const { callChoice, commitProbeCache } = require('./lib/laya-client.js');
const { canonicalJson, sha256Hex, instrumentSha256 } = require('./lib/laya-instrument.js');
const { defaultRoot, policySha256 } = require('./lib/typed-decisions.js');

const POLICY = 'credential-cli-v1';
const MAX_INPUT = 1 << 20;
const SOURCE_TOOLS = new Set(['read', 'write', 'edit', 'multiedit', 'notebookedit', 'apply_patch']);
const FIELDS = new Set(['code', 'command', 'cmd', 'script', 'input']);

function signalFor(data) {
  if (!data || typeof data !== 'object') return null;
  const event = data.hook_event_name;
  let text;
  let toolClass = 'request';
  if (event === 'UserPromptSubmit') text = data.prompt;
  else if (event === 'PreToolUse') {
    const tool = data.tool_name;
    if (typeof tool !== 'string' || SOURCE_TOOLS.has(tool.toLowerCase().split('.').pop())
      || ['functions.exec', 'exec'].includes(tool)) return null;
    const gui = /cua|computer|desktop|open_app|launch_app|applescript/i.test(tool);
    toolClass = gui ? 'gui' : 'execution';
    const input = data.tool_input;
    text = typeof input === 'string' ? input : input && typeof input === 'object'
      ? Object.entries(input).filter(([key, value]) => (gui || FIELDS.has(key)) && typeof value === 'string')
        .map(([, value]) => value).join('\n') : null;
    if (tool === 'Bash' && typeof text === 'string' && !/[\r\n]/.test(text)
      && /^(?:rg|grep|cat|head|tail)\s/.test(text) && !/[;&|`()<>]/.test(text)) return null;
  } else return null;
  if (typeof text !== 'string' || Buffer.byteLength(text) > MAX_INPUT) return null;
  text = text.normalize('NFKC').replace(/\p{Cf}/gu, '').replace(/\\ /g, ' ');
  if (!/keychain|com\.apple\.keychainaccess|security\s+(?:find|add)-(?:generic|internet)-password|stored\s+(?:credentials?|passwords?|tokens?)/i.test(text)) return null;
  const store = /\b(?:store|save|add-generic-password|add-internet-password)\b/i.test(text);
  const lookup = /\b(?:retrieve|lookup|find-generic-password|find-internet-password|stored)\b/i.test(text);
  return { event, toolClass, operation: store && !lookup ? 'store' : lookup && !store ? 'lookup' : 'unknown' };
}

function buildRequest(signal) {
  const allowed = signal.operation === 'store' ? ['keychain_store', 'clarify']
    : signal.operation === 'lookup' ? ['service_cli', 'keychain_lookup', 'clarify'] : ['service_cli', 'clarify'];
  const keyMap = Object.fromEntries(allowed.map((id, i) => [`s${i}`, id]));
  const criteria = Object.fromEntries(allowed.map((id, i) => [`s${i}`, catalog.procedures[id]]));
  criteria.none = 'Retain deterministic CLI-first guidance.';
  return { keyMap, request: { model: 'typed-decisions', state: { credentialStep: signal },
    questions: { skill: { type: 'choice', instructions: catalog.question, criteria } } } };
}

function writeReceipt(root, receipt) {
  for (const dir of [root, path.join(root, 'workflow-fit'), path.join(root, 'workflow-fit', 'receipts')]) {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    const stat = fs.lstatSync(dir);
    if (!stat.isDirectory() || stat.isSymbolicLink() || (stat.mode & 0o077)) throw new Error('private receipt directory required');
  }
  const file = path.join(root, 'workflow-fit', 'receipts', `${crypto.randomUUID()}.json`);
  fs.writeFileSync(file, JSON.stringify(receipt) + '\n', { mode: 0o600, flag: 'wx' });
}

async function run(data, options = {}) {
  const started = performance.now();
  const signal = signalFor(data);
  if (!signal) return null;
  const config = (options.readConfig || readDecisionConfig)('workflow-fit');
  if (config.mode === 'off' || config.deployablePolicy !== POLICY) return null;
  const env = options.env || process.env;
  const claude = Boolean(env.CLAUDE_CODE_ENTRYPOINT);
  const codex = Boolean(env.PLUGIN_ROOT);
  const host = claude === codex ? 'unknown' : claude ? 'claude' : 'codex';
  const mode = host === 'unknown' ? 'shadow' : config.mode;
  const root = options.root || defaultRoot();
  const built = buildRequest(signal);
  let result;
  try {
    result = await (options.call || callChoice)({ endpoint: config.endpoint, model: config.model,
      request: built.request, keyMap: built.keyMap, deadlineAt: started + config.latencyBudgetMs,
      healthCachePath: path.join(root, 'workflow-fit', 'health-cache.json') });
  } catch (_) { result = { status: 'unavailable' }; }
  const allowed = Object.values(built.keyMap);
  const validChoice = result && result.status === 'ok' && allowed.includes(result.choice);
  const fallback = signal.operation === 'store' ? 'clarify' : 'service_cli';
  const selected = mode === 'cosign' && validChoice ? result.choice : fallback;
  const status = result && ['ok', 'timeout', 'unavailable', 'invalid', 'identity_failed', 'redirect_refused'].includes(result.status)
    ? result.status : 'invalid';
  try {
    (options.writeReceipt || writeReceipt)(root, {
      schema: 'rhize-credential-workflow-receipt-v1', host, mode, signal, registryRevision: config.registryRevision,
      policySha256: policySha256(POLICY), instrumentSha256: instrumentSha256(POLICY),
      requestSha256: sha256Hex(canonicalJson(built.request)), status,
      modelChoice: validChoice ? result.choice : null, selected: mode === 'cosign' ? selected : null,
      sessionHash: sha256Hex(String(data.session_id || data.thread_id || '')),
      action: mode === 'cosign' ? 'emit_fixed_guidance' : 'observe_only',
    });
    if (!options.call) commitProbeCache(result);
  } catch (_) {
    // Without an audit receipt, retain deterministic guidance rather than a model-selected procedure.
    if (mode !== 'cosign') return null;
    return payload(signal.event, fallback, 'deterministic fallback; receipt unavailable');
  }
  return mode === 'cosign' ? payload(signal.event, selected, validChoice ? 'Laya selection' : 'deterministic fallback') : null;
}

function payload(event, selected, basis) {
  return { hookSpecificOutput: { hookEventName: event, additionalContext:
    `Credential workflow (${basis}): ${selected}. ${catalog.procedures[selected]} `
    + 'Follow rhize-devflow:credential-access. This selects procedure guidance only; existing authorization, OS consent and the credential GUI hard deny remain in force.' } };
}

async function main() {
  const buffer = Buffer.alloc(MAX_INPUT + 1);
  let total = 0;
  while (total < buffer.length) {
    const count = fs.readSync(0, buffer, total, buffer.length - total, null);
    if (!count) break;
    total += count;
  }
  if (total > MAX_INPUT) return;
  const output = await run(JSON.parse(buffer.subarray(0, total).toString('utf8')));
  if (output) process.stdout.write(JSON.stringify(output) + '\n');
}

function entry() {
  return main().catch(() => {
    process.stdout.write(JSON.stringify({ systemMessage: 'Credential workflow selection unavailable; retain CLI-first credential-access guidance and all existing denies.' }) + '\n');
  });
}
if (require.main === module) entry();
module.exports = { signalFor, buildRequest, run, writeReceipt, entry };
