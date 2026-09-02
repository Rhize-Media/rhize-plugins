import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, stat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  createApiRequest,
  planPreviewRequest,
  probeApplyRequest,
  probePreviewRequest,
  profileFromStageData,
  profileToStageData,
  reconciliationRequest,
  resumeSetupStages,
  setupConnectorRequest,
  submitCredentials,
} from '../../dashboard/app.js';
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
    carryovers: [], approvals: [], reconciliation: [], opportunities: [], warnings: [],
    connectors: Object.fromEntries(['jira', 'calendar', 'reminders', 'slack'].map(name => [name, {status: 'healthy', freshAt: '2026-08-14T13:00:00Z', staleMinutes: 0}])),
    paused: false, degraded: false,
    ...overrides,
  };
}

function profile() {
  return {
    schemaVersion: 1,
    identity: {name: 'Tom', timezone: 'America/New_York', locale: 'en-US'},
    jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: ['Epic'], projectImportance: {R: 5}, opportunityUrgencyThreshold: 'high', maxDailySuggestions: 3, competencies: [{name: 'ads', confidence: .95, excluded: false}, {name: 'development', confidence: .2, excluded: true}]},
    calendar: {readCalendarIds: ['outside', 'focus', 'personal'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
    reminders: {awarenessLists: [{id: 'personal', protectedDurationMinutes: 30, showTitles: false}], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
    workingIntervals: [{dayOfWeek: 1, start: '08:30', end: '12:00'}, {dayOfWeek: 1, start: '13:00', end: '17:30'}, {dayOfWeek: 3, start: '10:00', end: '16:00'}],
    breaks: [{dayOfWeek: 1, start: '12:00', end: '13:00'}, {dayOfWeek: 3, start: '12:30', end: '13:15'}],
    capacity: {bufferPercent: 20, maxDailyMinutes: 480},
    planning: {focusBlockMinutes: 60, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 15, freezeWindowMinutes: 30},
    routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
    approval: {setupComplete: true, firstPlanApproved: true, automationPaused: false},
    privacy: {showOutsideTitles: false},
  };
}

test('dashboard has one heading, labeled navigation, seven resumable stages, and accessible controls', async () => {
  const [html, css] = await Promise.all([asset('index.html'), asset('styles.css')]);
  assert.equal((html.match(/<h1\b/gi) ?? []).length, 1);
  assert.match(html, /<nav[^>]+aria-label="Primary"/i);
  assert.equal((html.match(/<section[^>]+data-stage="[1-7]"/gi) ?? []).length, 7);
  assert.match(html, /<label[^>]+for=/i);
  assert.match(html, /id="pause-automation"/);
  assert.match(html, /id="reconciliation-heading"/); assert.match(html, /id="reconciliation"/); assert.match(html, /Nothing retries automatically/);
  assert.match(html, /aria-live="polite"/);
  for (const id of ['assignee-name', 'jira-base-url', 'jira-projects', 'competency-rows', 'add-competency', 'slack-channel-id', 'calendar-read-ids', 'calendar-scope-explanation', 'awareness-lists', 'working-interval-rows', 'add-working-interval', 'break-interval-rows', 'add-break-interval', 'morning-time']) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /Exclude a category/); assert.match(html, /focus calendar is automatically included once/i);
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
  assert.match(javascript, /probePreviewRequest\(state\.planRevision, time\)/);
  assert.match(javascript, /probeApplyRequest\(state\.probe\.planRevision, state\.probe\.probeId, 'dashboard'\)/);
  assert.match(javascript, /verified\?\.reminders.*verified\?\.calendar/);
  assert.match(javascript, /connector:\s*'slack'.*scope:\s*config\.slack.*apply:\s*true/);
  assert.doesNotMatch(javascript, /operationKey|crypto\.subtle|reminder_upsert|calendar_upsert/);
  assert.match(javascript, /\/v1\/plans\/preview.*planPreviewRequest\(state\.planRevision, planningDate\(\)\)/);
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
  assert.match(javascript, /typeof document !== 'undefined'/);
  assert.match(javascript, /troubleshooting bearer was cleared/i);
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

test('profile setup state round-trips ordered intervals, per-day breaks, and excluded competencies exactly', () => {
  const original = profile(); const stages = profileToStageData(original, {slack: {workspaceId: 'W', channelId: 'C', senderIds: ['B']}});
  assert.deepEqual(stages[5].workingIntervals, original.workingIntervals);
  assert.deepEqual(stages[5].breaks, original.breaks);
  assert.deepEqual(stages[3].competencies, original.jira.competencies);
  assert.deepEqual(profileFromStageData(stages, {setupComplete: true, firstPlanApproved: true, automationPaused: false}), original);
});

test('request helpers preserve scope boundaries and use only lifecycle-owned request shapes', () => {
  const stages = profileToStageData(profile(), {slack: {workspaceId: 'W', channelId: 'C', senderIds: ['B']}}); stages[4].readCalendarIds = ['outside', 'outside'];
  assert.deepEqual(setupConnectorRequest(4, 'calendar', stages), {planRevision: 4, connector: 'calendar', scope: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}});
  assert.deepEqual(probePreviewRequest(4, stages[4]), {planRevision: 4, mode: 'preview', remindersListId: 'tasks', focusCalendarId: 'focus'});
  assert.deepEqual(probeApplyRequest(4, 'probe-1', 'dashboard'), {planRevision: 4, mode: 'apply', probeId: 'probe-1', actor: 'dashboard'});
  assert.deepEqual(planPreviewRequest(4, '2026-08-17'), {planRevision: 4, planningDate: '2026-08-17'});
  assert.deepEqual(reconciliationRequest(4, 'operation-1', 'tom'), {planRevision: 4, operationIds: ['operation-1'], actor: 'tom'});
});

test('seven-stage resume state is deterministic and retains saved data', () => {
  const result = resumeSetupStages({1: {complete: true, data: {safetyConfirmed: true}}, 4: {complete: false, data: {tasksListId: 'tasks'}}});
  assert.equal(result.length, 7); assert.deepEqual(result[0], {number: 1, complete: true, data: {safetyConfirmed: true}}); assert.deepEqual(result[3], {number: 4, complete: false, data: {tasksListId: 'tasks'}}); assert.equal(result[6].complete, false);
});

test('credentials clear before a failed request and any 401 clears the troubleshooting bearer', async () => {
  const fields = {email: {value: 'tom@example.com'}, 'api-token': {value: 'secret'}};
  await assert.rejects(submitCredentials({connector: 'jira', fields, planRevision: 2, request: async () => { throw new Error('offline'); }}), /offline/);
  assert.deepEqual(Object.values(fields).map(field => field.value), ['', '']);
  const authState = {token: 'temporary-bearer'}; let disconnected = false;
  const request = createApiRequest({authState, fetchImpl: async () => ({status: 401, ok: false, async json() { return {error: {kind: 'unauthorized'}}; }}), onUnauthorized() { disconnected = true; }});
  await assert.rejects(request('/v1/today'), /unauthorized/); assert.equal(authState.token, ''); assert.equal(disconnected, true);
});

test('dashboard application is importable without a browser and delegates state/request rules to pure helpers', async () => {
  const application = await import('../../dashboard/app.js');
  assert.equal(typeof application.bootDashboard, 'function');
  const javascript = await asset('app.js');
  for (const helper of ['profileToStageData', 'profileFromStageData', 'resumeSetupStages', 'setupConnectorRequest', 'submitCredentials']) assert.match(javascript, new RegExp(`${helper}\\(`));
  assert.match(javascript, /renderIntervalRows\('working-interval-rows'/); assert.match(javascript, /renderCompetencyRows/); assert.match(javascript, /data\.competencies/);
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
    // Claude Code substitutes `$ARGUMENTS`/`$1`-`$9`, not `$skill-name` — that's Codex syntax
    // (see the `agents/openai.yaml` assertion above). The Claude-side command must name the
    // skill directly and carry `Skill` in its allowed-tools or invocation can silently no-op.
    assert.match(command, new RegExp(`rhize-tasks:${name}`), name);
    assert.match(command, /allowed-tools:\s*\[[^\]]*\bSkill\b/, name);
    assert.match(command, /Never ask for secrets in chat/i, name);
  }

  const [reconcile, wrapper] = await Promise.all([readFile(new URL('../../skills/reconcile-rhize-tasks/SKILL.md', import.meta.url), 'utf8'), readFile(new URL('../../commands/reconcile.md', import.meta.url), 'utf8')]);
  assert.match(reconcile, /installation\.json/); assert.match(reconcile, /absolute child of `runtimePath`/); assert.match(reconcile, /POST \/v1\/reconcile/); assert.match(reconcile, /\{planRevision, operationIds, actor\}/); assert.doesNotMatch(reconcile, /request a reconciliation preview/i); assert.doesNotMatch(reconcile, /node <cliPath> reconcile/);
  assert.match(wrapper, /TodayView `reconciliation` array/); assert.match(wrapper, /actor name/); assert.match(wrapper, /\/v1\/reconcile/);
});
