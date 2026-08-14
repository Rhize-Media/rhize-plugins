import {isoDateTime, realDate} from '../domain.mjs';
import {classifyTask} from './eligibility.mjs';
import {estimateTask} from './estimates.mjs';
import {assertProtectedIntervals, materializeWorkingIntervals, subtractIntervals, totalMinutes, withMeetingBuffers} from './intervals.mjs';
import {canonicalContextKey, rankTasks} from './priority.mjs';

const MINUTE = 60000;
const availableMinutes = window => Math.floor((Date.parse(window.end) - Date.parse(window.start)) / MINUTE);

function localDate(instant, timeZone) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone, year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(new Date(instant)).filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function reasonFor(task, classification, estimate) {
  if (task.manualLock) return 'manual_lock';
  if (task.blocked) return 'blocked';
  if (task.lane === 'provisional' || classification?.lane === 'provisional') return 'provisional';
  if (task.reserved) return 'reserved';
  if (classification?.lane === 'opportunity') return 'opportunity_unapproved';
  if (!classification) return 'ineligible';
  if (estimate.confidence === 'low' || estimate.requiresApproval) return 'low_confidence';
  return null;
}

function trimBefore(windows, cutoff) {
  return windows.flatMap(window => Date.parse(window.end) <= cutoff ? [] : [{start: Date.parse(window.start) < cutoff ? new Date(cutoff).toISOString() : window.start, end: window.end}]);
}

function block(task, planRevision, sessionIndex, start, minutes) {
  return {id: `${planRevision}:${task.id}:${sessionIndex}`, taskId: task.id, start, end: new Date(Date.parse(start) + minutes * MINUTE).toISOString(), minutes, sessionIndex, contextKey: canonicalContextKey(task.competencies), locked: false};
}

function feasiblePart(remaining, window, profile) {
  const maximum = Math.min(remaining, availableMinutes(window), profile.planning.focusBlockMinutes);
  if (maximum < profile.planning.minimumBlockMinutes) return 0;
  if (remaining === maximum) return maximum;
  const remainder = remaining - maximum;
  if (remainder >= profile.planning.minimumBlockMinutes) return maximum;
  const reduced = maximum - (profile.planning.minimumBlockMinutes - remainder);
  return reduced >= profile.planning.minimumBlockMinutes ? reduced : 0;
}

function place(task, estimate, windows, profile, planRevision, blocks) {
  const windowSnapshot = windows.map(window => ({...window}));
  const blockCount = blocks.length;
  if (!profile.planning.allowSplitting) {
    const index = windows.findIndex(window => estimate.minutes <= profile.planning.focusBlockMinutes && estimate.minutes <= availableMinutes(window));
    if (index < 0) return false;
    const placed = block(task, planRevision, 1, windows[index].start, estimate.minutes);
    blocks.push(placed); windows[index] = {start: placed.end, end: windows[index].end};
    return true;
  }
  let remaining = estimate.minutes; let sessionIndex = 0;
  for (let index = 0; index < windows.length && remaining > 0; index += 1) {
    while (remaining > 0) {
      const minutes = feasiblePart(remaining, windows[index], profile);
      if (minutes === 0) break;
      sessionIndex += 1;
      const placed = block(task, planRevision, sessionIndex, windows[index].start, minutes);
      blocks.push(placed); windows[index] = {start: placed.end, end: windows[index].end};
      remaining -= minutes;
    }
  }
  if (remaining === 0) return true;
  windows.splice(0, windows.length, ...windowSnapshot);
  blocks.splice(blockCount);
  return false;
}

export function planDay({tasks, protectedIntervals, profile, history = [], planningDate, now, planRevision}) {
  realDate(planningDate, 'planningDate'); isoDateTime(now, 'now');
  if (!Number.isInteger(planRevision) || planRevision < 1) throw new RangeError('planRevision must be an integer >= 1');
  assertProtectedIntervals(protectedIntervals);
  const today = localDate(now, profile.identity.timezone);
  if (planningDate < today) throw new RangeError('planningDate must not be in the past');
  const protectedCopy = structuredClone(protectedIntervals);
  const recurringBreaks = materializeWorkingIntervals(profile, planningDate, profile.breaks);
  let windows = subtractIntervals(materializeWorkingIntervals(profile, planningDate), [...withMeetingBuffers(protectedCopy, profile.planning.meetingBufferMinutes), ...recurringBreaks]);
  const beforeFreeze = totalMinutes(windows);
  if (planningDate === today) windows = trimBefore(windows, Date.parse(now) + profile.planning.freezeWindowMinutes * MINUTE);
  const available = totalMinutes(windows);
  const capacityMinutes = Math.min(profile.capacity.maxDailyMinutes, Math.floor(available * (1 - profile.capacity.bufferPercent / 100)));
  const bufferMinutes = available - capacityMinutes;
  const ranking = rankTasks(tasks.map(task => ({...task, estimate: estimateTask(task, history, profile)})), profile, now);
  const blocks = []; const unscheduled = []; let remainingCapacity = capacityMinutes;
  for (const item of ranking) {
    const reason = reasonFor(item.task, classifyTask(item.task, profile), item.estimate);
    if (reason) { unscheduled.push({taskId: item.task.id, reason}); continue; }
    if (item.estimate.minutes > remainingCapacity || !place(item.task, item.estimate, windows, profile, planRevision, blocks)) {
      unscheduled.push({taskId: item.task.id, reason: beforeFreeze > available && item.estimate.minutes <= beforeFreeze ? 'freeze_window' : 'no_capacity'});
      continue;
    }
    remainingCapacity -= item.estimate.minutes;
  }
  const usedMinutes = blocks.reduce((total, item) => total + item.minutes, 0);
  return {schemaVersion: 1, planRevision, planningDate, generatedAt: now, status: 'preview', availableMinutes: available, capacityMinutes, usedMinutes, bufferMinutes, ranked: ranking.map(item => ({taskId: item.task.id, lane: item.lane, schedulable: item.schedulable, factors: item.factors, estimate: item.estimate})), blocks, unscheduled, protectedIntervals: protectedCopy};
}
