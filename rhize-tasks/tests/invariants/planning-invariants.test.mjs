import assert from 'node:assert/strict';
import test from 'node:test';

import {overlaps} from '../../service/src/planner/intervals.mjs';
import {planDay} from '../../service/src/planner/planning.mjs';

function random(seed) { let state = seed >>> 0; return () => ((state = (state * 1664525 + 1013904223) >>> 0) / 2 ** 32); }
function profile(overlapping) { return {schemaVersion: 1, identity: {name: 'T', timezone: 'UTC', locale: 'en-US'}, jira: {accountId: 'tom', baseUrl: 'https://rhize.atlassian.net', projects: ['R'], issueTypes: ['Task'], excludedIssueTypes: [], projectImportance: {R: 3}, opportunityUrgencyThreshold: 'normal', maxDailySuggestions: 3, competencies: [{name: 'ops', confidence: .9, excluded: false}]}, calendar: {readCalendarIds: ['p'], focusCalendarId: 'f', focusCalendarName: 'Rhize Focus', redactOutsideTitles: true}, reminders: {awarenessLists: [], tasksListId: 't', tasksListName: 'Rhize Tasks'}, workingIntervals: overlapping ? [{dayOfWeek: 1, start: '09:00', end: '12:00'}, {dayOfWeek: 1, start: '10:00', end: '17:00'}] : [{dayOfWeek: 1, start: '09:00', end: '17:00'}], breaks: [], capacity: {bufferPercent: 20, maxDailyMinutes: 480}, planning: {focusBlockMinutes: 90, minimumBlockMinutes: 30, allowSplitting: true, meetingBufferMinutes: 0, freezeWindowMinutes: 0}, routines: {replanningMode: 'bounded', reconciliationMode: 'prompted', morningTime: '09:00', middayTime: '12:00', eveningTime: '17:00'}, approval: {setupComplete: true, firstPlanApproved: true, automationPaused: false}, privacy: {showOutsideTitles: false}}; }
function task(id, changes = {}) { return {schemaVersion: 1, id, sourceType: 'jira', lane: 'owned', title: id, projectKey: 'R', issueType: 'Task', assigneeAccountId: 'tom', priority: 'normal', dueDate: null, status: 'Open', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: 30, explicitEstimateMinutes: null, competencies: ['ops'], manualLock: false, carryoverCount: 0, createdAt: '2026-08-01T00:00:00.000Z', reserved: false, sourceRevision: '1', jiraKey: `R-${id.replace(/\D/g, '') || 1}`, ...changes}; }

test('250 seeded plans preserve exact interval and lane safety invariants', () => {
  for (let seed = 1; seed <= 250; seed += 1) {
    const next = random(seed);
    const owned = Array.from({length: 1 + Math.floor(next() * 8)}, (_, index) => task(`t${index + 1}`, {remainingMinutes: 15 + Math.floor(next() * 180), blocked: next() < .15, manualLock: next() < .15, lane: next() < .12 ? 'provisional' : 'owned'}));
    const opportunity = task(`opp${seed}`, {assigneeAccountId: null, priority: 'urgent', remainingMinutes: 30});
    const tasks = [...owned, opportunity];
    const protectedIntervals = [
      {id: `meeting-${seed}`, start: '2026-08-17T10:29:31.000Z', end: '2026-08-17T11:00:00.000Z', kind: 'fixed', sourceSystem: 'calendar', mutable: false},
      ...(next() < .6 ? [{id: `outside-${seed}`, start: '2026-08-17T13:00:00.000Z', end: '2026-08-17T14:00:00.000Z', kind: 'outside', sourceSystem: 'calendar', mutable: false}] : []),
    ];
    const before = structuredClone({tasks, protectedIntervals});
    const plan = planDay({tasks, protectedIntervals, profile: profile(seed % 2 === 0), planningDate: '2026-08-17', now: '2026-08-17T08:00:00.000Z', planRevision: seed});
    assert.deepEqual({tasks, protectedIntervals}, before, `seed ${seed} mutated input`);
    assert.ok(plan.usedMinutes <= plan.capacityMinutes, `seed ${seed} over capacity`);
    for (const [index, block] of plan.blocks.entries()) {
      assert.ok(protectedIntervals.every(interval => !overlaps(block, interval)), `seed ${seed} overlaps protected`);
      assert.ok(plan.blocks.slice(index + 1).every(other => !overlaps(block, other)), `seed ${seed} has block collision`);
      const source = tasks.find(item => item.id === block.taskId);
      assert.ok(source.assigneeAccountId === 'tom' && source.lane !== 'provisional' && !source.blocked && !source.manualLock, `seed ${seed} scheduled unsafe task`);
    }
    assert.ok(!plan.blocks.some(block => block.taskId === opportunity.id), `seed ${seed} silently scheduled opportunity`);
    assert.ok(plan.unscheduled.some(item => item.taskId === opportunity.id && item.reason === 'opportunity_unapproved'), `seed ${seed} lost eligible opportunity gate`);
    for (const locked of tasks.filter(item => item.manualLock)) assert.ok(plan.unscheduled.some(item => item.taskId === locked.id && item.reason === 'manual_lock'), `seed ${seed} lost manual lock`);
  }
});
