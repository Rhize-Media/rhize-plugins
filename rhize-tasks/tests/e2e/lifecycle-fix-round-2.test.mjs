import assert from 'node:assert/strict';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {createServiceContext} from '../../service/src/api/context.mjs';
import {createGoogleCalendarConnector} from '../../service/src/connectors/google-calendar.mjs';

const instant = '2026-08-17T08:00:00.000Z';
const token = 'x'.repeat(43);
const profile = () => ({schemaVersion: 1, identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'}, jira: {accountId: 'tom', baseUrl: 'https://jira.example', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {R: 3}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: []}, calendar: {readCalendarIds: ['focus'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true}, reminders: {awarenessLists: [], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'}, workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [], capacity: {bufferPercent: 20, maxDailyMinutes: 480}, planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 0}, routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'}, approval: {setupComplete: true, firstPlanApproved: false, automationPaused: false}, privacy: {showOutsideTitles: false}});
const task = () => ({schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Audit', projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: 'r1', jiraKey: 'R-1'});

async function fixture(t, connectors) { const directory = await mkdtemp(path.join(tmpdir(), 'rhize-fix2-')); const context = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain: {async get() { return token; }, async set() {}, async delete() {}}, connectors, now: () => new Date(instant)}); t.after(() => { context.close(); return rm(directory, {recursive: true, force: true}); }); return context; }

test('focus snapshot exposes only complete Rhize ownership and planner updates/deletes exact owned events', async t => {
  const events = [{id: 'owned', calendarId: 'focus', revision: 'e1', start: '2026-08-17T09:00:00.000Z', end: '2026-08-17T10:00:00.000Z', owned: true, operationKey: 'a'.repeat(64), taskId: 'task-1', blockSlot: 'task-1:1'}, {id: 'orphan', calendarId: 'focus', revision: 'e2', start: '2026-08-17T15:00:00.000Z', end: '2026-08-17T16:00:00.000Z', owned: true, operationKey: 'b'.repeat(64), taskId: 'old', blockSlot: 'old:1'}, {id: 'user', calendarId: 'focus', revision: 'e3', start: '2026-08-17T12:00:00.000Z', end: '2026-08-17T13:00:00.000Z'}];
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }};
  const context = await fixture(t, {jira: {...empty, async readSnapshot() { return [task()]; }}, calendar: {...empty, async readSnapshot() { return events; }}, reminders: empty, slack: empty}); context.repositories.preferences.set('profile', profile());
  const preview = await context.plans.preview({baseRevision: 0, planningDate: '2026-08-17'}); const calendar = preview.operations.filter(value => value.targetSystem === 'calendar');
  assert.equal(calendar.find(value => value.kind === 'calendar_upsert').targetId, 'owned'); assert.equal(calendar.find(value => value.kind === 'calendar_upsert').payload.blockSlot, 'task-1:1'); assert.equal(calendar.find(value => value.kind === 'calendar_delete').targetId, 'orphan'); assert.ok(preview.protectedIntervals.some(value => value.id === 'user')); assert.ok(!preview.protectedIntervals.some(value => value.id === 'owned'));
});

test('Google focus events round-trip stable private ownership while user focus events stay unowned', async () => {
  const requests = []; let eventLists = 0; const stable = 'c'.repeat(64); const transport = async request => { requests.push(request); if (request.url.includes('oauth2')) return {status: 200, body: {access_token: 'access'}}; if (request.method === 'GET') { eventLists += 1; return {status: 200, body: {items: eventLists === 1 ? [{id: 'owned', etag: 'e1', start: {dateTime: '2026-08-17T09:00:00Z'}, end: {dateTime: '2026-08-17T10:00:00Z'}, extendedProperties: {private: {rhizeOperationKey: stable, rhizeTaskId: 'task-1', rhizeBlockSlot: 'task-1:1'}}}, {id: 'user', etag: 'e2', start: {dateTime: '2026-08-17T11:00:00Z'}, end: {dateTime: '2026-08-17T12:00:00Z'}}] : []}}; } return {status: 200, body: {id: 'created', etag: 'e3'}}; };
  const connector = createGoogleCalendarConnector({readCalendarIds: ['focus'], focusCalendarId: 'focus', credentials: {async get() { return 'credential'; }}, transport, now: () => new Date(instant)}); const snapshot = await connector.readSnapshot(); assert.equal(snapshot[0].owned, true); assert.equal(snapshot[1].owned, undefined);
  const payload = {calendarId: 'focus', title: 'Rhize Focus', start: '2026-08-17T09:00:00Z', end: '2026-08-17T10:00:00Z', description: '', externalId: '1:task-1:1', operationKey: stable, taskId: 'task-1', blockSlot: 'task-1:1'}; await connector.applyOperation({kind: 'calendar_upsert', targetId: null, idempotencyKey: 'd'.repeat(64), payload});
  const body = JSON.parse(requests.find(value => value.method === 'POST' && value.url.includes('/events')).body); assert.deepEqual(body.extendedProperties.private, {rhizeOperationKey: stable, rhizeTaskId: 'task-1', rhizeBlockSlot: 'task-1:1'});
});

test('catch-up completion covers the backlog so the next wake is not due', async t => {
  const empty = {async readSnapshot() { return []; }, async health() { return {ok: true}; }}; const context = await fixture(t, {jira: empty, calendar: empty, reminders: empty, slack: empty}); context.repositories.preferences.set('profile', profile());
  const now = new Date(instant); const due = await context.routineState.evaluate('catch-up', now); assert.equal(due.phase, 'evening'); assert.ok(due.missedCount > 1); const id = await context.routineState.begin(due.phase, now, due); await context.routineState.complete(id, 'completed', {state: 'planned'}); assert.equal((await context.routineState.evaluate('catch-up', now)).shouldRun, false);
});

test('production registry exposes a pre-profile discovery-only connector', async t => {
  let discoveryMode = false; const connector = {async health() { return {ok: true}; }, async discover() { return [{id: 'focus'}]; }};
  const directory = await mkdtemp(path.join(tmpdir(), 'rhize-discovery-')); t.after(() => rm(directory, {recursive: true, force: true})); const value = await createServiceContext({databasePath: path.join(directory, 'state.sqlite'), keychain: {async get() { return token; }, async set() {}, async delete() {}}, connectorFactory: async (_profile, setup) => { discoveryMode = setup?.discoveryOnly === true; return {calendar: connector}; }}); t.after(() => value.close());
  assert.deepEqual(await (await value.connectorRegistry.getDiscovery('calendar')).discover(), [{id: 'focus'}]); assert.equal(discoveryMode, true);
});
