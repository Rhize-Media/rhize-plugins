import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';

import {assertTask, operationKey, validateProfile} from '../../service/src/domain.mjs';

const profile = {
  schemaVersion: 1,
  identity: {name: 'Tom Cassidy', timezone: 'America/New_York', locale: 'en-US'},
  jira: {
    accountId: 'tom-1', baseUrl: 'https://rhize.atlassian.net', projects: ['RHIZE'],
    issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {RHIZE: 5},
    opportunityUrgencyThreshold: 'high', maxDailySuggestions: 3,
    competencies: [{name: 'marketing', confidence: 0.9, excluded: false}],
  },
  calendar: {readCalendarIds: ['primary'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
  reminders: {awarenessLists: [{id: 'personal', protectedDurationMinutes: 30, showTitles: false}], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
  workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}],
  breaks: [],
  capacity: {bufferPercent: 20, maxDailyMinutes: 480},
  planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 15, freezeWindowMinutes: 30},
  routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'},
  approval: {setupComplete: true, firstPlanApproved: true, automationPaused: false},
  privacy: {showOutsideTitles: false},
};

const task = {
  schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Audit paid search',
  projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: 'tom-1', priority: 'high',
  dueDate: '2026-08-17', status: 'Open', terminal: false, blocked: false, dependencyRisk: 1,
  remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['marketing'], manualLock: false,
  carryoverCount: 0, sourceRevision: '42', jiraKey: 'RHIZE-42',
  estimate: {minutes: 60, source: 'jira_remaining', confidence: 'high', rationale: 'Jira estimate', confirmedAt: '2026-08-14T12:00:00.000Z', requiresApproval: false},
};

test('validates the complete v1 profile and task contracts', () => {
  assert.equal(validateProfile(profile), profile);
  assert.equal(assertTask(task), task);
});

test('rejects unknown properties, invalid enums, impossible dates, unsafe URLs, negative durations, and unsupported versions', () => {
  assert.throws(() => validateProfile({...profile, extra: true}), TypeError);
  assert.throws(() => validateProfile({...profile, jira: {...profile.jira, opportunityUrgencyThreshold: 'now'}}), TypeError);
  assert.throws(() => validateProfile({...profile, jira: {...profile.jira, baseUrl: 'http://rhize.atlassian.net'}}), TypeError);
  assert.throws(() => validateProfile({...profile, workingIntervals: [{dayOfWeek: 1, start: '17:00', end: '09:00'}]}), TypeError);
  assert.throws(() => validateProfile({...profile, schemaVersion: 2}), TypeError);
  assert.throws(() => assertTask({...task, dueDate: '2026-02-30'}), TypeError);
  assert.throws(() => assertTask({...task, remainingMinutes: -1}), TypeError);
  assert.throws(() => assertTask({...task, jiraUrl: 'javascript:alert(1)'}), TypeError);
});

test('enforces task source cross-fields and JSON-only operation keys', () => {
  assert.throws(() => assertTask({...task, jiraKey: undefined, jiraUrl: undefined}), TypeError);
  assert.throws(() => assertTask({...task, sourceType: 'delegation', delegationId: undefined}), TypeError);
  assert.equal(operationKey(4, 'reminder_upsert', 'task-1', {title: 'Audit', tags: ['paid']}), operationKey(4, 'reminder_upsert', 'task-1', {tags: ['paid'], title: 'Audit'}));
  assert.throws(() => operationKey(4, 'reminder_upsert', 'task-1', {bad: undefined}), TypeError);
  const cyclic = {}; cyclic.self = cyclic;
  assert.throws(() => operationKey(4, 'reminder_upsert', 'task-1', cyclic), TypeError);
});

test('schema files are strict v1 JSON schemas', async () => {
  for (const name of ['profile', 'task', 'today-view', 'operation', 'delegation-v1']) {
    const schema = JSON.parse(await readFile(new URL(`../../schemas/${name}.schema.json`, import.meta.url), 'utf8'));
    assert.equal(schema.additionalProperties, false);
    assert.equal(schema.properties.schemaVersion.const, 1);
  }
});
