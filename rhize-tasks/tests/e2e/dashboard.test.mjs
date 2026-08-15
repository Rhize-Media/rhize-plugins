import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {renderArtifact, writeArtifactFile} from '../../dashboard/artifact.mjs';

const dashboard = new URL('../../dashboard/', import.meta.url);

async function asset(name) { return readFile(new URL(name, dashboard), 'utf8'); }

function view(overrides = {}) {
  return {
    schemaVersion: 1,
    planRevision: 42,
    generatedAt: '2026-08-14T13:00:00Z',
    timeline: [{id: 'outside-1', kind: 'outside', start: '2026-08-14T14:00:00Z', end: '2026-08-14T15:00:00Z', title: '<script>alert(1)</script>', redacted: true}],
    currentBlock: null,
    nextBlock: null,
    capacity: {availableMinutes: 360, plannedMinutes: 120, bufferMinutes: 72, risk: 'normal'},
    carryovers: [], approvals: [], opportunities: [], warnings: [],
    connectors: Object.fromEntries(['jira', 'calendar', 'reminders', 'slack'].map(name => [name, {status: 'healthy', freshAt: '2026-08-14T13:00:00Z', staleMinutes: 0}])),
    paused: false, degraded: false,
    ...overrides,
  };
}

test('dashboard has one heading, labeled navigation, seven resumable stages, and accessible controls', async () => {
  const [html, css] = await Promise.all([asset('index.html'), asset('styles.css')]);
  assert.equal((html.match(/<h1\b/gi) ?? []).length, 1);
  assert.match(html, /<nav[^>]+aria-label="Primary"/i);
  assert.equal((html.match(/<section[^>]+data-stage="[1-7]"/gi) ?? []).length, 7);
  assert.match(html, /<label[^>]+for=/i);
  assert.match(html, /id="pause-automation"/);
  assert.match(html, /aria-live="polite"/);
  for (const id of ['tom-name', 'jira-base-url', 'jira-projects', 'competencies', 'slack-channel-id', 'calendar-read-ids', 'awareness-lists', 'working-days', 'morning-time']) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(css, /:focus-visible/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(css, /forced-colors/);
});

test('dashboard uses only the authenticated local API and retains revision-bound approvals', async () => {
  const [html, javascript] = await Promise.all([asset('index.html'), asset('app.js')]);
  for (const route of ['/v1/setup/status', '/v1/setup/credentials', '/v1/setup/discover/', '/v1/plans/preview', '/v1/today', '/v1/pause']) assert.match(javascript, new RegExp(route.replaceAll('/', '\\/')));
  assert.match(javascript, /applyStageData/);
  assert.match(javascript, /\/v1\/preferences/);
  assert.match(javascript, /\/v1\/setup\/connectors/);
  assert.match(javascript, /\/v1\/setup\/probe/);
  assert.match(javascript, /approved_setup_scope/);
  assert.match(javascript, /mode:\s*'preview'.*remindersListId.*focusCalendarId/);
  assert.match(javascript, /mode:\s*'apply'.*probeId.*actor/);
  assert.match(javascript, /verified\?\.reminders.*verified\?\.calendar/);
  assert.match(javascript, /connector:\s*'slack'.*scope:\s*config\.slack.*apply:\s*true/);
  assert.doesNotMatch(javascript, /operationKey|crypto\.subtle|reminder_upsert|calendar_upsert/);
  assert.match(javascript, /\/v1\/plans\/preview.*planRevision:\s*state\.planRevision.*planningDate:\s*planningDate\(\)/);
  assert.match(javascript, /result\.operations/);
  assert.match(javascript, /zeroWorkReason/);
  assert.doesNotMatch(javascript, /proposedOperations|baseRevision|sourceRevision/);
  assert.match(html, /id="preview-operations"/);
  assert.match(html, /id="zero-work-reason"/);
  assert.match(javascript, /\/v1\/operations\/.*\/approve/);
  assert.match(javascript, /\/v1\/opportunities\/.*\/claim/);
  assert.match(javascript, /operationId/);
  assert.match(javascript, /planRevision/);
  assert.match(javascript, /response\.status === 409/);
  assert.match(javascript, /credentials:\s*'same-origin'/);
  assert.doesNotMatch(javascript, /localStorage|sessionStorage|document\.cookie/);
  assert.doesNotMatch(`${html}\n${javascript}`, /nonce/i);
  assert.doesNotMatch(javascript, /atlassian\.net|googleapis\.com|slack\.com/);
});

test('artifact is standalone, escaped, revisioned, and immutably read only', () => {
  const html = renderArtifact(view({
    currentBlock: {id: 'focus-1', kind: 'focus', start: '2026-08-14T13:00:00Z', end: '2026-08-14T14:00:00Z', title: 'Audit campaign', redacted: false, taskId: 'task-1'},
    nextBlock: {id: 'focus-2', kind: 'focus', start: '2026-08-14T15:00:00Z', end: '2026-08-14T16:00:00Z', title: 'Review leads', redacted: false, taskId: 'task-2'},
  }));
  assert.match(html, /Plan revision 42/);
  assert.match(html, /Current and next/);
  assert.match(html, /Audit campaign/);
  assert.match(html, /Review leads/);
  assert.match(html, /Connector freshness/);
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>alert\(1\)<\/script>/);
  assert.doesNotMatch(html, /<form\b|<button\b|fetch\s*\(|XMLHttpRequest|approve|assign|transition/i);
  assert.doesNotMatch(html, /https?:\/\/(?!127\.0\.0\.1)/i);
  assert.match(html, /\/rhize-tasks:today/);
  assert.match(html, /authenticated local dashboard/i);
});

test('artifact template has no network, form, or mutation surface', async () => {
  const template = await asset('artifact-template.html');
  assert.doesNotMatch(template, /<form\b|<button\b|fetch\s*\(|XMLHttpRequest|https?:\/\//i);
  assert.match(template, /\{\{PLAN_REVISION\}\}/);
  assert.match(template, /\{\{TODAY_CONTENT\}\}/);
  assert.match(template, /\{\{TODAY_VIEW_JSON\}\}/);
});

test('artifact export atomically writes one private HTML snapshot', async t => {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-dashboard-')); const output = path.join(directory, 'today.html');
  t.after(() => rm(directory, {recursive: true, force: true}));
  assert.equal(await writeArtifactFile(output, view()), path.resolve(output));
  assert.match(await readFile(output, 'utf8'), /Plan revision 42/);
  assert.equal((await stat(output)).mode & 0o777, 0o600);
});

test('shared skills and Claude commands preserve the local planning boundary', async () => {
  const skills = new Map([
    ['rhize-tasks-setup', 'setup'],
    ['plan-my-day', 'today'],
    ['review-task-opportunities', 'review-opportunities'],
    ['reconcile-rhize-tasks', 'reconcile'],
    ['manage-task-preferences', 'preferences'],
    ['rhize-tasks-doctor', 'doctor'],
  ]);

  for (const [name, commandName] of skills) {
    const [instructions, agent, command] = await Promise.all([
      readFile(new URL(`../../skills/${name}/SKILL.md`, import.meta.url), 'utf8'),
      readFile(new URL(`../../skills/${name}/agents/openai.yaml`, import.meta.url), 'utf8'),
      readFile(new URL(`../../commands/${commandName}.md`, import.meta.url), 'utf8'),
    ]);
    assert.doesNotMatch(instructions, /TODO|placeholder/i, name);
    assert.match(instructions, /local (?:CLI|service|dashboard)/i, name);
    assert.match(instructions, /untrusted/i, name);
    assert.match(instructions, /never (?:ask|request|solicit).*secret/i, name);
    assert.match(instructions, /revision/i, name);
    assert.match(instructions, /approval/i, name);
    assert.match(instructions, /do not call Jira, Google Calendar, Apple Reminders, or Slack directly/i, name);
    assert.match(agent, new RegExp(`default_prompt: "Use \\$${name}`), name);
    assert.match(command, /^---\n[\s\S]+?\n---\n/, name);
    assert.match(command, new RegExp(`\\$${name}`), name);
    assert.match(command, /Never ask for secrets in chat/i, name);
  }
});
