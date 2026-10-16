'use strict';
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const workflow = require('../../rhize-context-manager/hooks/credential-workflow.js');
const { callChoice } = require('../../rhize-context-manager/hooks/lib/laya-client.js');
const catalog = require('../../rhize-context-manager/catalog/credential-workflows.json');

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'credential-workflow-test-'));
const secret = 'PRIVATE_FIXTURE_VALUE_never_send_or_record';
const event = { hook_event_name: 'PreToolUse', session_id: 'fixture-only', tool_name: 'Bash',
  tool_input: { command: `security find-generic-password -s fixture -w # ${secret}` } };
const config = { mode: 'cosign', deployablePolicy: 'credential-cli-v1', endpoint: 'http://127.0.0.1:8000',
  model: 'typed-decisions', latencyBudgetMs: 800, registryRevision: 3 };

async function main() {
  let receipt;
  let called = 0;
  const options = { root, env: { CLAUDE_CODE_ENTRYPOINT: 'cli' }, readConfig: () => config,
    writeReceipt: (_root, value) => { receipt = value; },
    call: async (request) => {
      called += 1;
      assert(!JSON.stringify(request.request).includes(secret));
      assert(!JSON.stringify(request.request).includes('fixture'));
      assert.deepStrictEqual(request.request.state, { credentialStep:
        { event: 'PreToolUse', toolClass: 'execution', operation: 'lookup' } });
      assert(request.deadlineAt > performance.now());
      return { status: 'ok', choice: 'keychain_lookup' };
    } };
  const output = await workflow.run(event, options);
  assert(output.hookSpecificOutput.additionalContext.includes(catalog.procedures.keychain_lookup));
  assert.strictEqual(receipt.selected, 'keychain_lookup');
  assert.strictEqual(receipt.action, 'emit_fixed_guidance');
  assert(!JSON.stringify(receipt).includes(secret));
  assert(!('permissionDecision' in output.hookSpecificOutput));
  assert.strictEqual(called, 1);

  for (const hostEnv of [{ PLUGIN_ROOT: '/fixture/plugin' }, { CLAUDE_CODE_ENTRYPOINT: 'cli' }]) {
    const out = await workflow.run(event, { ...options, env: hostEnv });
    assert(out.hookSpecificOutput.additionalContext.includes('keychain_lookup'));
  }
  for (const env of [{}, { PLUGIN_ROOT: 'x', CLAUDE_CODE_ENTRYPOINT: 'cli' }]) {
    assert.strictEqual(await workflow.run(event, { ...options, env }), null);
    assert.strictEqual(receipt.mode, 'shadow');
  }
  assert.strictEqual(await workflow.run(event, { ...options, readConfig: () => ({ ...config, mode: 'shadow' }) }), null);
  assert.strictEqual(receipt.selected, null);
  const beforeOff = called;
  assert.strictEqual(await workflow.run(event, { ...options, readConfig: () => ({ ...config, mode: 'off' }) }), null);
  assert.strictEqual(called, beforeOff);

  for (const bad of [{ status: 'timeout' }, { status: 'invalid' }, { status: 'ok', choice: 'none' },
    { status: 'ok', choice: 'keychain_store' }, { status: 'ok', choice: secret }]) {
    const fallback = await workflow.run(event, { ...options, call: async () => bad });
    assert(fallback.hookSpecificOutput.additionalContext.includes('service_cli'));
    assert(!JSON.stringify(fallback).includes(secret));
  }
  const failedAudit = await workflow.run(event, { ...options, writeReceipt: () => { throw new Error(secret); } });
  assert(failedAudit.hookSpecificOutput.additionalContext.includes('service_cli'));
  assert(!JSON.stringify(failedAudit).includes(secret));

  const store = { ...event, tool_input: { command: 'security add-generic-password -s fixture' } };
  const stored = await workflow.run(store, { ...options, call: async (args) => {
    assert.deepStrictEqual(Object.values(args.keyMap), ['keychain_store', 'clarify']);
    return { status: 'ok', choice: 'keychain_store' };
  } });
  assert(stored.hookSpecificOutput.additionalContext.includes(catalog.procedures.keychain_store));
  const clarify = await workflow.run(store, { ...options, call: async () => ({ status: 'unavailable' }) });
  assert(clarify.hookSpecificOutput.additionalContext.includes('clarify'));

  const prompt = { hook_event_name: 'UserPromptSubmit', prompt: 'Use stored Keychain credentials', session_id: 'fixture' };
  assert((await workflow.run(prompt, { ...options, call: async () => ({ status: 'ok', choice: 'clarify' }) }))
    .hookSpecificOutput.additionalContext.includes(catalog.procedures.clarify));
  for (const input of [
    { ...event, tool_name: 'Read', tool_input: { input: 'Keychain Access' } },
    { ...event, tool_name: 'functions.exec', tool_input: { input: 'Keychain Access' } },
    { ...event, tool_input: { command: 'cat docs/keychain.md' } },
    { ...event, tool_input: { command: 'git status' } },
    { ...event, tool_input: { body: 'Open Keychain Access' } },
    { ...prompt, prompt: 'Keychain'.repeat(160000) },
  ]) assert.strictEqual(workflow.signalFor(input), null);

  // Actual shared transport/decoder path, with an inert in-memory HTTP adapter.
  const transported = await workflow.run(event, { ...options, call: (args) => callChoice({ ...args,
    healthCachePath: null, fetchImpl: async (url, init) => {
      if (url.endsWith('/health')) return new Response(JSON.stringify({ loaded: ['typed-decisions'] }));
      const request = JSON.parse(init.body);
      assert(!init.body.includes(secret));
      const keys = Object.keys(request.questions.skill.criteria);
      return new Response(JSON.stringify({ routing: { model: 'typed-decisions' }, answers: {
        skill: { type: 'choice', choice: 's1', probabilities: Object.fromEntries(keys.map(k => [k, k === 's1' ? 1 : 0])) },
      } }));
    } }) });
  assert(transported.hookSpecificOutput.additionalContext.includes('keychain_lookup'));
  workflow.writeReceipt(root, receipt);
  const files = fs.readdirSync(path.join(root, 'workflow-fit', 'receipts'));
  assert.strictEqual(files.length, 1);
  assert.strictEqual(fs.statSync(path.join(root, 'workflow-fit', 'receipts', files[0])).mode & 0o777, 0o600);
  const linked = path.join(root, 'linked');
  fs.symlinkSync(root, linked);
  assert.throws(() => workflow.writeReceipt(linked, receipt));
  console.log('PASS credential workflow: active instructions, both hosts, legal candidates, privacy, modes, failures, shared transport and private receipts');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => fs.rmSync(root, { recursive: true, force: true }));
