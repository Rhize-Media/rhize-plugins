import assert from 'node:assert/strict';
import test from 'node:test';

import {nextCarryover} from '../../service/src/planner/carryover.mjs';
import {classifyTask} from '../../service/src/planner/eligibility.mjs';
import {estimateTask} from '../../service/src/planner/estimates.mjs';
import {materializeWorkingIntervals, overlaps} from '../../service/src/planner/intervals.mjs';
import {planDay} from '../../service/src/planner/planning.mjs';
import {compareCodePoint, rankTasks} from '../../service/src/planner/priority.mjs';

const now = '2026-08-17T08:00:00.000Z';
const planningDate = '2026-08-17';
const profile = {
  schemaVersion: 1,
  identity: {name: 'Tom', timezone: 'UTC', locale: 'en-US'},
  jira: {accountId: 'tom', baseUrl: 'https://rhize.atlassian.net', projects: ['RHIZE'], issueTypes: ['Task', 'Bug', 'Story', 'Epic'], excludedIssueTypes: ['Sub-task'], projectImportance: {RHIZE: 5}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: [{name: 'marketing', confidence: 0.9, excluded: false}, {name: 'ops', confidence: 0.8, excluded: false}]},
  calendar: {readCalendarIds: ['primary'], focusCalendarId: 'focus', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true},
  reminders: {awarenessLists: [], tasksListId: 'tasks', tasksListName: 'Rhize Tasks'},
  workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [{dayOfWeek: 1, start: '12:00', end: '12:30'}],
  capacity: {bufferPercent: 20, maxDailyMinutes: 480}, planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 30},
  routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'}, approval: {setupComplete: true, firstPlanApproved: true, automationPaused: false}, privacy: {showOutsideTitles: false},
};

function task(overrides = {}) {
  return {schemaVersion: 1, id: 'task-1', sourceType: 'jira', lane: 'owned', title: 'Audit', projectKey: 'RHIZE', issueType: 'Task', assigneeAccountId: 'tom', priority: 'high', dueDate: '2026-08-18', status: 'Open', terminal: false, blocked: false, dependencyRisk: 1, remainingMinutes: 60, explicitEstimateMinutes: null, competencies: ['marketing'], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T09:00:00.000Z', reserved: false, sourceRevision: '1', jiraKey: 'RHIZE-1', ...overrides};
}

test('owned deadline risk precedes an urgent opportunity', () => {
  const dueOwned = task({id: 'owned', dueDate: '2026-08-17'});
  const urgentOpportunity = task({id: 'opportunity', assigneeAccountId: null, priority: 'urgent', dueDate: null, remainingMinutes: 30});
  const ranked = rankTasks([urgentOpportunity, dueOwned], profile, now);
  assert.equal(ranked[0].task.id, dueOwned.id);
  assert.equal(ranked[0].lane, 'owned');
  assert.deepEqual(ranked[0].factors.map(({name}) => name), ['lane', 'due', 'priority', 'blocked_dependencies', 'project_importance', 'effort_fit', 'competency_confidence', 'context', 'age']);
});

test('classifies only eligible assigned work and unapproved opportunities', () => {
  assert.deepEqual(classifyTask(task(), profile), {lane: 'owned', schedulable: true});
  assert.deepEqual(classifyTask(task({assigneeAccountId: null, priority: 'high'}), profile), {lane: 'opportunity', schedulable: false});
  assert.equal(classifyTask(task({assigneeAccountId: null, reserved: true}), profile), null);
  assert.equal(classifyTask(task({projectKey: 'OTHER'}), profile), null);
  assert.equal(classifyTask(task({issueType: 'Sub-task'}), profile), null);
});

test('uses the defined estimate hierarchy without overwriting source estimates', () => {
  assert.deepEqual(estimateTask(task({remainingMinutes: 45}), [], profile), {minutes: 45, source: 'jira_remaining', confidence: 'high', rationale: 'Jira remaining estimate', requiresApproval: false});
  assert.equal(estimateTask(task({remainingMinutes: null, explicitEstimateMinutes: 50}), [], profile).source, 'explicit');
  const history = [40, 60, 80].map((actualMinutes, index) => ({projectKey: 'RHIZE', issueType: 'Task', competencies: ['marketing'], actualMinutes, completedAt: `2026-08-0${index + 1}T10:00:00.000Z`}));
  assert.deepEqual(estimateTask(task({remainingMinutes: null}), history, profile), {minutes: 60, source: 'history', confidence: 'medium', rationale: 'Median of 3 similar completed tasks', requiresApproval: false});
  assert.deepEqual(estimateTask(task({remainingMinutes: null, issueType: 'Bug'}), [], profile), {minutes: 90, source: 'inferred', confidence: 'low', rationale: 'Deterministic Bug scope rule', requiresApproval: true});
  const assisted = estimateTask(task({remainingMinutes: null, estimate: {minutes: 70, source: 'agent_assisted', confidence: 'high', rationale: 'Model analysis', confirmedAt: null, requiresApproval: false}}), [], profile);
  assert.equal(assisted.requiresApproval, false);
});

test('materializes recurring work in profile timezone and rejects invalid dates', () => {
  assert.deepEqual(materializeWorkingIntervals(profile, planningDate), [{start: '2026-08-17T09:00:00.000Z', end: '2026-08-17T17:00:00.000Z'}]);
  const eastern = {...profile, identity: {...profile.identity, timezone: 'America/New_York'}};
  assert.deepEqual(materializeWorkingIntervals(eastern, planningDate), [{start: '2026-08-17T13:00:00.000Z', end: '2026-08-17T21:00:00.000Z'}]);
  assert.throws(() => materializeWorkingIntervals(eastern, '2026-03-08', [{dayOfWeek: 7, start: '02:00', end: '03:00'}]), RangeError);
});

test('preserves buffer and protected intervals while splitting only inside blocks', () => {
  const protectedIntervals = [{id: 'meeting', start: '2026-08-17T10:00:00.000Z', end: '2026-08-17T11:00:00.000Z', kind: 'fixed', sourceSystem: 'calendar', mutable: false}];
  const plan = planDay({tasks: [task({remainingMinutes: 150})], protectedIntervals, profile, planningDate, now, planRevision: 1});
  assert.equal(plan.status, 'preview');
  assert.ok(plan.usedMinutes <= plan.capacityMinutes);
  assert.equal(plan.availableMinutes, 390);
  assert.equal(plan.capacityMinutes, 312);
  assert.ok(plan.blocks.every(block => protectedIntervals.every(interval => !overlaps(block, interval))));
  assert.ok(plan.blocks.every(block => block.minutes >= profile.planning.minimumBlockMinutes));
  assert.deepEqual(plan.protectedIntervals, protectedIntervals);
});

test('merges overlapping recurring work windows without double-counting or block collisions', () => {
  const overlapping = {...profile, workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '12:00'}, {dayOfWeek: 1, start: '10:00', end: '13:00'}], breaks: [], capacity: {bufferPercent: 0, maxDailyMinutes: 480}};
  const plan = planDay({tasks: [task({remainingMinutes: 180})], protectedIntervals: [], profile: overlapping, planningDate, now, planRevision: 4});
  assert.equal(plan.availableMinutes, 240);
  assert.equal(plan.usedMinutes, 180);
  assert.ok(plan.blocks.every((block, index) => plan.blocks.slice(index + 1).every(other => !overlaps(block, other))));
});

test('does not cross a sub-minute protected boundary', () => {
  const limited = {...profile, workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '11:00'}], breaks: [], capacity: {bufferPercent: 0, maxDailyMinutes: 480}};
  const protectedIntervals = [{id: 'fractional', start: '2026-08-17T09:29:31.000Z', end: '2026-08-17T10:00:00.000Z', kind: 'fixed', sourceSystem: 'calendar', mutable: false}];
  const plan = planDay({tasks: [task({remainingMinutes: 30})], protectedIntervals, profile: limited, planningDate, now, planRevision: 5});
  assert.deepEqual(plan.blocks.map(block => [block.start, block.end]), [['2026-08-17T10:00:00.000Z', '2026-08-17T10:30:00.000Z']]);
  assert.ok(plan.blocks.every(block => protectedIntervals.every(interval => !overlaps(block, interval))));
});

test('applies meeting buffer on both sides of fixed meetings only', () => {
  const buffered = {...profile, workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '12:00'}], breaks: [], capacity: {bufferPercent: 0, maxDailyMinutes: 480}, planning: {...profile.planning, meetingBufferMinutes: 15}};
  const protectedIntervals = [{id: 'meeting', start: '2026-08-17T10:00:00.000Z', end: '2026-08-17T11:00:00.000Z', kind: 'fixed', sourceSystem: 'calendar', mutable: false}];
  const plan = planDay({tasks: [task({remainingMinutes: 60})], protectedIntervals, profile: buffered, planningDate, now, planRevision: 6});
  const bufferedMeeting = {start: '2026-08-17T09:45:00.000Z', end: '2026-08-17T11:15:00.000Z'};
  assert.equal(plan.availableMinutes, 90);
  assert.ok(plan.blocks.every(block => !overlaps(block, bufferedMeeting)));
  assert.deepEqual(plan.protectedIntervals, protectedIntervals);
});

test('finds a feasible 70 plus 30 minute partition under focus block rules', () => {
  const splitProfile = {...profile, workingIntervals: [{dayOfWeek: 1, start: '09:00', end: '11:00'}], breaks: [], capacity: {bufferPercent: 0, maxDailyMinutes: 480}};
  const plan = planDay({tasks: [task({remainingMinutes: 100})], protectedIntervals: [], profile: splitProfile, planningDate, now, planRevision: 7});
  assert.deepEqual(plan.blocks.map(block => block.minutes), [70, 30]);
});

test('rejects malformed protected intervals before copying them into a plan', () => {
  const valid = {id: 'protected', start: '2026-08-17T10:00:00.000Z', end: '2026-08-17T11:00:00.000Z', kind: 'outside', sourceSystem: 'calendar', mutable: false};
  assert.throws(() => planDay({tasks: [], protectedIntervals: [{...valid, title: 'private'}], profile, planningDate, now, planRevision: 8}), TypeError);
  const {id, ...missing} = valid;
  assert.throws(() => planDay({tasks: [], protectedIntervals: [missing], profile, planningDate, now, planRevision: 8}), TypeError);
  assert.throws(() => planDay({tasks: [], protectedIntervals: [{...valid, mutable: true}], profile, planningDate, now, planRevision: 8}), TypeError);
});

test('uses code-point ordering without ambient locale comparison', () => {
  const original = String.prototype.localeCompare;
  String.prototype.localeCompare = () => { throw new Error('locale comparison must not run'); };
  try {
    assert.ok(compareCodePoint('a', 'ä') < 0);
    assert.deepEqual(rankTasks([task({id: 'ä'}), task({id: 'a'})], profile, now).map(item => item.task.id), ['a', 'ä']);
  } finally { String.prototype.localeCompare = original; }
});

test('shares canonical non-BMP context ordering between ranking and blocks', () => {
  const plan = planDay({tasks: [task({competencies: ['😀', '\uE000'], remainingMinutes: 60})], protectedIntervals: [], profile, planningDate, now, planRevision: 9});
  const rankedContext = plan.ranked[0].factors.find(factor => factor.name === 'context').value;
  assert.equal(rankedContext, '\uE000|😀');
  assert.ok(plan.blocks.every(block => block.contextKey === rankedContext));
});

test('does not schedule blocked, locked, provisional, reserved, or opportunities', () => {
  const tasks = [task({id: 'blocked', blocked: true}), task({id: 'locked', manualLock: true}), task({id: 'provisional', lane: 'provisional'}), task({id: 'reserved', assigneeAccountId: null, reserved: true}), task({id: 'opp', assigneeAccountId: null, priority: 'urgent'})];
  const plan = planDay({tasks, protectedIntervals: [], profile, planningDate, now, planRevision: 2});
  assert.equal(plan.blocks.length, 0);
  assert.deepEqual(Object.fromEntries(plan.unscheduled.map(item => [item.taskId, item.reason])), {blocked: 'blocked', locked: 'manual_lock', provisional: 'provisional', reserved: 'reserved', opp: 'opportunity_unapproved'});
});

test('uses confirmed history estimates when deciding automatic placement', () => {
  const history = [45, 60, 75].map((actualMinutes, index) => ({projectKey: 'RHIZE', issueType: 'Task', competencies: ['marketing'], actualMinutes, completedAt: `2026-08-0${index + 1}T10:00:00.000Z`}));
  const plan = planDay({tasks: [task({remainingMinutes: null})], protectedIntervals: [], profile, history, planningDate, now, planRevision: 3});
  assert.equal(plan.ranked[0].estimate.source, 'history');
  assert.equal(plan.usedMinutes, 60);
});

test('escalates carryover deterministically', () => {
  assert.deepEqual(nextCarryover(task({carryoverCount: 0})), {state: 'reschedule_once', choices: []});
  assert.deepEqual(nextCarryover(task({carryoverCount: 1})), {state: 'needs_diagnosis', choices: ['blocked', 'underestimated', 'not_important']});
  assert.deepEqual(nextCarryover(task({carryoverCount: 2})), {state: 'decision_required', choices: ['split', 'delegate', 'defer', 'renegotiate']});
});
