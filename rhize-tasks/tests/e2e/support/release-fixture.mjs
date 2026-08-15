import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';

import {uninstallCleanupRequest} from '../../../service/src/api/cleanup.mjs';
import {createServiceContext} from '../../../service/src/api/context.mjs';
import {createServer} from '../../../service/src/api/server.mjs';
import {runRoutine} from '../../../service/src/scheduler/bounded-routines.mjs';

const apiToken = 'release-fixture-api-token-that-is-long-enough';
const exactDelegationId = '550e8400-e29b-41d4-a716-446655440000';
const needsJiraId = '650e8400-e29b-41d4-a716-446655440000';

function profile() {
  return {
    schemaVersion: 1,
    identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'},
    jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: ['Epic'], projectImportance: {R: 5}, opportunityUrgencyThreshold: 'high', maxDailySuggestions: 3, competencies: [{name: 'ads', confidence: .95, excluded: false}, {name: 'development', confidence: .2, excluded: true}]},
    calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
    reminders: {awarenessLists: [{id: 'personal', protectedDurationMinutes: 30, showTitles: false}], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
    workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}, {dayOfWeek: 2, start: '09:00', end: '17:00'}],
    breaks: [{dayOfWeek: 1, start: '12:00', end: '13:00'}, {dayOfWeek: 2, start: '12:00', end: '13:00'}],
    capacity: {bufferPercent: 20, maxDailyMinutes: 480},
    planning: {focusBlockMinutes: 60, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 0},
    routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
    approval: {setupComplete: true, firstPlanApproved: false, automationPaused: false},
    privacy: {showOutsideTitles: false},
  };
}

function jiraTask(overrides = {}) {
  return {
    schemaVersion: 1, id: 'jira-1', sourceType: 'jira', lane: 'owned', title: 'Audit campaign', projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['ads'], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: 'jira-r1', jiraKey: 'R-1', jiraUrl: 'https://jira.example/browse/R-1', description: `Campaign notes\nrhize-delegation:v1:${exactDelegationId}`,
    ...overrides,
  };
}

function delegation(delegationId, jira) {
  return {schemaVersion: 1, workspaceId: 'W', channelId: 'C', senderId: 'B', delegationId, ingestionKey: `W:C:${delegationId}`, title: `Delegation ${delegationId[0]}`, dueDate: '2026-08-20', priority: 'normal', jira, state: jira.kind === 'needs_jira' ? 'needs_jira' : 'jira_linked', planningLane: 'provisional', approval: 'required', schedulable: false};
}

function makeFakeSystems() {
  const outsideCalendar = {id: 'outside-calendar-event', calendarId: 'outside', revision: 'outside-r1', start: '2026-08-17T14:00:00.000Z', end: '2026-08-17T15:00:00.000Z', title: 'Personal appointment', description: 'private'};
  const outsideReminder = {id: 'outside-reminder', listId: 'personal', title: 'Private errand', dueAt: '2026-08-17T16:00:00.000Z', notes: null, completed: false, revision: 'outside-reminder-r1'};
  const outsideBytes = Buffer.from(JSON.stringify({outsideCalendar, outsideReminder}));
  const calendars = new Map(); const reminders = new Map(); const cleanupKeys = new Map(); const jiraAttempts = []; let serial = 0; let ambiguousJiraWrite = true;
  const tasks = [
    jiraTask(),
    jiraTask({id: 'jira-2', title: 'Review lead quality', priority: 'normal', sourceRevision: 'jira-r2', jiraKey: 'R-2', jiraUrl: 'https://jira.example/browse/R-2', description: 'Review', competencies: ['marketing']}),
    jiraTask({id: 'jira-3', title: 'Optional urgent ad check', lane: 'opportunity', assigneeAccountId: null, priority: 'urgent', sourceRevision: 'jira-r3', jiraKey: 'R-3', jiraUrl: 'https://jira.example/browse/R-3', description: 'Unassigned', competencies: ['ads']}),
  ];
  const nextRevision = prefix => `${prefix}-${++serial}`;
  const remindersConnector = {
    async discover() { return {lists: [{id: 'tasks', name: 'Rhize Tasks'}, {id: 'personal', name: 'Personal'}]}; },
    async health() { return {ok: true}; },
    async readSnapshot() { return [structuredClone(outsideReminder), ...[...reminders.values()].map(item => structuredClone(item))]; },
    async findByExternalId(id) { const value = reminders.get(id); return value ? {externalId: value.id, revision: value.revision} : null; },
    async applyOperation(operation) {
      if (operation.kind === 'reminder_delete') { reminders.delete(operation.targetId); return {externalId: operation.targetId, revision: nextRevision('reminder-deleted')}; }
      assert.equal(operation.kind, 'reminder_upsert'); const id = operation.payload.externalId; const value = {id, listId: operation.payload.listId, title: operation.payload.title, dueAt: operation.payload.dueAt, notes: operation.payload.notes, completed: false, revision: nextRevision('reminder')}; reminders.set(id, value); return {externalId: id, revision: value.revision};
    },
  };
  const calendarConnector = {
    async discover() { return [{id: 'outside', name: 'Awareness'}, {id: 'focus', name: 'Rhize Focus'}]; },
    async health() { return {ok: true}; },
    async readSnapshot() { return [structuredClone(outsideCalendar), ...[...calendars.values()].map(item => structuredClone(item))]; },
    async findByExternalId(id) { const value = calendars.get(id) ?? [...calendars.values()].find(item => item.operationKey === id); return value ? {externalId: value.id, revision: value.revision} : null; },
    async applyOperation(operation) {
      if (operation.kind === 'calendar_delete') { calendars.delete(operation.targetId); return {externalId: operation.targetId, revision: nextRevision('calendar-deleted')}; }
      assert.equal(operation.kind, 'calendar_upsert'); const existing = operation.targetId ? calendars.get(operation.targetId) : [...calendars.values()].find(item => item.operationKey === operation.payload.operationKey); const id = existing?.id ?? `calendar-owned-${serial + 1}`;
      const value = {id, calendarId: operation.payload.calendarId, revision: nextRevision('calendar'), start: operation.payload.start, end: operation.payload.end, title: operation.payload.title, description: operation.payload.description, owned: true, operationKey: operation.payload.operationKey, taskId: operation.payload.taskId, blockSlot: operation.payload.blockSlot}; calendars.set(id, value); cleanupKeys.set(operation.payload.operationKey, id); return {externalId: id, revision: value.revision};
    },
  };
  const connectors = {
    jira: {async discover() { return {projects: [{id: '1', key: 'R', name: 'Rhize'}], issueTypes: [{id: '1', name: 'Task'}]}; }, async health() { return {ok: true}; }, async readSnapshot() { return tasks.map(item => structuredClone(item)); }, async findByExternalId(id) { const value = tasks.find(item => item.jiraKey === id); return value ? {externalId: id, revision: value.sourceRevision} : null; }, async applyOperation(operation) { jiraAttempts.push({id: operation.id, idempotencyKey: operation.idempotencyKey, kind: operation.kind}); if (ambiguousJiraWrite) { ambiguousJiraWrite = false; throw Object.assign(new Error('ambiguous'), {kind: 'timeout', ambiguous: true}); } return {externalId: operation.targetId, revision: 'jira-r2'}; }},
    calendar: calendarConnector,
    reminders: remindersConnector,
    slack: {async discover() { return {workspaceId: 'W', channelId: 'C', senderIds: ['B']}; }, async health() { return {ok: true}; }, async readSnapshot() { return [delegation(exactDelegationId, {kind: 'key', value: 'R-1'}), delegation(needsJiraId, {kind: 'needs_jira', value: null})]; }},
  };
  const transport = async request => {
    if (request.url === 'https://oauth2.googleapis.com/token') return {status: 200, body: {access_token: 'fake-access'}};
    const url = new URL(request.url); const directId = /\/events\/([^/?]+)$/.exec(url.pathname)?.[1];
    if (request.method === 'GET') { const key = url.searchParams.get('privateExtendedProperty')?.replace(/^rhizeOperationKey=/, ''); const id = cleanupKeys.get(key); const item = id && calendars.has(id) ? {id, extendedProperties: {private: {rhizeOperationKey: key}}} : null; return {status: 200, body: {items: item ? [item] : []}}; }
    if (request.method === 'DELETE' && directId) { calendars.delete(decodeURIComponent(directId)); return {status: 204, body: ''}; }
    throw new Error('unexpected_fake_transport_call');
  };
  return {
    connectors, transport, calendars, reminders, jiraAttempts,
    outsideUnchanged() { return outsideBytes.equals(Buffer.from(JSON.stringify({outsideCalendar, outsideReminder}))); },
  };
}

async function startHttp(context) {
  const server = createServer(context); await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); }); const base = `http://127.0.0.1:${server.address().port}`;
  const request = async (pathname, {method = 'GET', body} = {}) => { const response = await fetch(`${base}${pathname}`, {method, headers: {authorization: `Bearer ${apiToken}`, ...(body === undefined ? {} : {'content-type': 'application/json'})}, body: body === undefined ? undefined : JSON.stringify(body)}); const text = await response.text(); return {status: response.status, body: text ? JSON.parse(text) : null}; };
  return {server, request, async close() { await new Promise(resolve => server.close(resolve)); }};
}

export async function runFakeReleaseAcceptance() {
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-tasks-release-')); const databasePath = path.join(directory, 'state.sqlite'); const lockPath = path.join(directory, 'routine.lock'); const systems = makeFakeSystems(); let current = new Date('2026-08-17T08:00:00.000Z'); let tokenAvailable = true; let context; let http;
  const keychain = {async get(service) { if (service === 'media.rhize.tasks.api') { if (!tokenAvailable) throw Object.assign(new Error('not_found'), {kind: 'not_found'}); return apiToken; } return 'fake-connector-credential'; }, async set() {}, async delete(service) { if (service === 'media.rhize.tasks.api') tokenAvailable = false; }};
  const createContext = () => createServiceContext({databasePath, keychain, connectors: systems.connectors, transport: systems.transport, now: () => new Date(current), lockPath});
  try {
    context = await createContext(); http = await startHttp(context); const {request} = http;
    for (let stage = 1; stage <= 6; stage += 1) { const saved = await request(`/v1/setup/stages/${stage}`, {method: 'PUT', body: {planRevision: 0, complete: true, data: stage === 2 ? {name: 'Tom', jiraBaseUrl: 'https://jira.example', jiraAccountId: 'tom', slackWorkspaceId: 'W', slackChannelId: 'C', slackSenderIds: ['B']} : {confirmed: true}}}); assert.equal(saved.status, 200); }
    const scopes = {jira: {projectKeys: ['R'], issueTypes: ['Task']}, calendar: {readCalendarIds: ['outside', 'focus'], focusCalendarId: 'focus'}, reminders: {awarenessListIds: ['personal'], tasksListId: 'tasks'}, slack: {workspaceId: 'W', channelId: 'C', senderIds: ['B']}};
    for (const [connector, scope] of Object.entries(scopes)) { const preview = await request('/v1/setup/connectors', {method: 'POST', body: {planRevision: 0, connector, scope}}); assert.equal(preview.status, 201); assert.deepEqual(preview.body.scope, scope); const approved = await request(`/v1/operations/${encodeURIComponent(preview.body.operation.id)}/approve`, {method: 'POST', body: {planRevision: 0, actor: 'Tom'}}); assert.equal(approved.body.state, 'approved_setup_scope'); }
    const probe = await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 0, mode: 'preview', remindersListId: 'tasks', focusCalendarId: 'focus'}}); assert.equal(probe.status, 201); const probeApplied = await request('/v1/setup/probe', {method: 'POST', body: {planRevision: 0, mode: 'apply', probeId: probe.body.probeId, actor: 'Tom'}}); assert.deepEqual(probeApplied.body.verified, {reminders: true, calendar: true}); assert.equal(systems.reminders.size, 0); assert.equal(systems.calendars.size, 0);
    assert.equal((await request('/v1/preferences', {method: 'PUT', body: {planRevision: 0, profile: profile()}})).status, 200); assert.equal((await request('/v1/setup/connectors', {method: 'PUT', body: {planRevision: 0, connector: 'slack', scope: scopes.slack, apply: true}})).status, 200);
    const first = await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 0, planningDate: '2026-08-17'}}); assert.equal(first.status, 201); assert.ok(first.body.blocks.length >= 1); assert.ok(first.body.operations.some(item => item.kind === 'calendar_upsert')); assert.ok(first.body.operations.some(item => item.kind === 'reminder_upsert'));
    const approvedFirst = await request('/v1/plans/1/approve', {method: 'POST', body: {actor: 'Tom', apply: true}}); assert.equal(approvedFirst.status, 200); assert.ok(approvedFirst.body.results.every(item => item.state === 'applied')); assert.ok(systems.calendars.size > 0); assert.equal(systems.reminders.size, 2);
    assert.equal((await request('/v1/setup/stages/7', {method: 'PUT', body: {planRevision: 1, complete: true, data: {dryRunReviewed: true}}})).status, 200); const setup = await request('/v1/setup/status'); assert.equal(Object.values(setup.body.stages).filter(item => item.complete).length, 7);
    const canonical = context.repositories.tasks.get('jira-1'); assert.equal(canonical.delegationId, exactDelegationId); assert.equal(context.repositories.tasks.get(`delegation:${exactDelegationId}`), null); assert.equal(context.repositories.tasks.get(`delegation:${needsJiraId}`).status, 'Needs Jira'); assert.ok((await request('/v1/today')).body.opportunities.some(item => item.taskId === 'jira-3'));
    const calendarIds = [...systems.calendars.keys()]; const reminderIds = [...systems.reminders.keys()]; const moved = [...systems.calendars.values()].find(item => item.taskId === 'jira-1'); moved.start = '2026-08-17T15:00:00.000Z'; moved.end = '2026-08-17T16:00:00.000Z'; moved.revision = 'calendar-manual-r2';
    const second = await request('/v1/plans/preview', {method: 'POST', body: {planRevision: 1, planningDate: '2026-08-17'}}); assert.equal(second.status, 201); assert.ok(second.body.protectedIntervals.some(item => item.id === moved.id && item.kind === 'manual_lock')); assert.equal(second.body.operations.some(item => item.targetId === moved.id), false); assert.equal((await request('/v1/plans/2/approve', {method: 'POST', body: {actor: 'Tom', apply: true}})).status, 200); assert.deepEqual([...systems.calendars.keys()], calendarIds); assert.deepEqual([...systems.reminders.keys()], reminderIds);
    const completedReminder = systems.reminders.get('jira-1'); completedReminder.completed = true; completedReminder.revision = 'reminder-completed-r2'; await context.sync.readAll(); const completionView = await request('/v1/today'); const completionApproval = completionView.body.approvals.find(item => item.kind === 'jira_comment'); assert.ok(completionApproval); const ambiguous = await request(`/v1/operations/${encodeURIComponent(completionApproval.operationId)}/approve`, {method: 'POST', body: {planRevision: 2, actor: 'Tom'}}); assert.equal(ambiguous.body.state, 'reconciliation_required'); const reconciliationView = await request('/v1/today'); assert.deepEqual(reconciliationView.body.reconciliation.map(item => item.operationId), [completionApproval.operationId]); const reconciled = await request('/v1/reconcile', {method: 'POST', body: {planRevision: 2, operationIds: [completionApproval.operationId], actor: 'Tom'}}); assert.equal(reconciled.body.results[0].state, 'applied'); assert.equal(new Set(systems.jiraAttempts.map(item => `${item.id}:${item.idempotencyKey}`)).size, 1);
    assert.equal((await request('/v1/pause', {method: 'POST', body: {planRevision: 2, paused: true}})).body.paused, true); assert.deepEqual(await runRoutine('catch-up', context, current), {state: 'paused'}); assert.equal((await request('/v1/pause', {method: 'POST', body: {planRevision: 2, paused: false}})).body.paused, false);
    await http.close(); http = null; context.close(); context = null; current = new Date('2026-08-18T18:30:00.000Z'); context = await createContext(); assert.equal(Object.values(context.repositories.preferences.get('setup_stages')).filter(item => item.complete).length, 7); const catchUp = await runRoutine('catch-up', context, current); assert.equal(catchUp.phase, 'evening'); assert.equal(catchUp.reconciliation, 'prompted'); assert.ok(catchUp.missedCount > 0); assert.equal(context.repositories.tasks.get('jira-1').carryoverCount, 0); assert.equal(context.repositories.tasks.get('jira-2').carryoverCount, 1); assert.ok((await context.today()).carryovers.some(item => item.taskId === 'jira-2'));
    const cleanup = await context.cleanup(uninstallCleanupRequest); assert.equal(cleanup.ok, true); assert.equal(cleanup.reminders.verified, true); assert.equal(cleanup.calendar.verified, true); assert.equal(systems.reminders.size, 0); assert.equal(systems.calendars.size, 0);
    await keychain.delete('media.rhize.tasks.api', 'bearer'); context.close(); context = null; await assert.rejects(createContext(), error => error.kind === 'api_token_missing');
    return {stagesCompleted: 7, firstPlanApproved: true, noDuplicateOwnedItems: true, carryoverPrompted: true, delegationMergedExactly: true, reconciliationPrompted: true, pauseRestartCatchUpSafe: true, revocationFailsClosed: true, uninstallCleanupVerified: true, outsideRecordsUnchanged: systems.outsideUnchanged()};
  } finally {
    await http?.close().catch(() => {}); context?.close(); await rm(directory, {recursive: true, force: true});
  }
}
