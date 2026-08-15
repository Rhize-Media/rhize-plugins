import {createHash} from 'node:crypto';
import {nextCarryover} from '../planner/carryover.mjs';

const systems = ['jira', 'calendar', 'reminders', 'slack'];
const reconciliationReasons = new Set(['ambiguous_apply', 'ambiguous_precondition', 'interrupted_attempt', 'invalid_retry_history', 'malformed_success', 'retry_state_persistence_failed', 'revision_drift', 'success_persistence_failed', 'unexpected_retry_state']);
const opaque = value => `busy-${createHash('sha256').update(String(value)).digest('hex').slice(0, 16)}`;
const clone = value => structuredClone(value);

function connectorState(value, now) {
  const status = ['healthy', 'degraded', 'offline', 'revoked'].includes(value?.status) ? value.status : 'offline';
  const freshAt = typeof value?.freshAt === 'string' ? value.freshAt : null;
  const staleMinutes = freshAt === null ? 0 : Math.max(0, Math.floor((Date.parse(now) - Date.parse(freshAt)) / 60000));
  return {status, freshAt, staleMinutes: Number.isFinite(staleMinutes) ? staleMinutes : 0};
}

function reconciliationReason(result) {
  const value = result?.reason;
  return reconciliationReasons.has(value) ? value : 'reconciliation_required';
}

function timeline(plan, tasks, profile, approvedLabels) {
  const byId = new Map(tasks.map(task => [task.id, task]));
  const focus = (plan.blocks ?? []).map(block => ({id: block.id, kind: 'focus', start: block.start, end: block.end, title: byId.get(block.taskId)?.title ?? 'Rhize focus', redacted: false, taskId: block.taskId}));
  const protectedItems = (plan.protectedIntervals ?? []).map(interval => {
    const outside = interval.kind === 'outside';
    const item = {id: outside ? opaque(interval.id) : interval.id, kind: ['fixed', 'outside', 'break'].includes(interval.kind) ? interval.kind : 'fixed', start: interval.start, end: interval.end, redacted: outside};
    const approved = approvedLabels?.[interval.id];
    if (outside && profile?.privacy?.showOutsideTitles === true && typeof approved === 'string' && approved.trim()) item.title = approved.trim();
    return item;
  });
  return [...focus, ...protectedItems].sort((left, right) => Date.parse(left.start) - Date.parse(right.start) || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
}

export function projectTodayView({plan, tasks = [], operations = [], profile, freshness = {}, now = new Date().toISOString(), approvedOutsideLabels = {}}) {
  if (!plan || !Number.isInteger(plan.planRevision) || plan.planRevision < 1) throw new TypeError('TodayView requires a persisted plan');
  const items = timeline(plan, tasks, profile, approvedOutsideLabels);
  const instant = Date.parse(now);
  const focusItems = items.filter(item => item.kind === 'focus');
  const currentBlock = focusItems.find(item => Date.parse(item.start) <= instant && instant < Date.parse(item.end)) ?? null;
  const nextBlock = focusItems.find(item => Date.parse(item.start) > instant) ?? null;
  const carryovers = tasks.filter(task => task.carryoverCount > 0).map(task => { const state = nextCarryover(task).state; return {taskId: task.id, title: task.title, missCount: task.carryoverCount, reason: state, resolution: state === 'reschedule_once' ? 'rescheduled' : state}; });
  const approvals = operations.filter(operation => operation.approval === 'required' && operation.retryState !== 'reconciliation_required').map(operation => ({operationId: operation.id, kind: operation.kind, title: tasks.find(task => task.id === operation.targetId || task.jiraKey === operation.targetId)?.title ?? operation.kind, reason: 'approval_required'}));
  const reconciliation = operations.filter(operation => operation.retryState === 'reconciliation_required').map(operation => ({operationId: operation.id, kind: operation.kind, targetSystem: operation.targetSystem, reason: reconciliationReason(operation.reconciliationResult)}));
  const opportunities = tasks.filter(task => task.lane === 'opportunity').map(task => ({taskId: task.id, title: task.title, priority: task.priority, fit: 0, estimateMinutes: task.remainingMinutes ?? task.explicitEstimateMinutes ?? 90, rationale: 'Allowlisted unassigned work requires review', impact: 'Does not displace owned work without approval'}));
  const warnings = (plan.ranked ?? []).filter(item => item.estimate?.confidence === 'low' || item.estimate?.requiresApproval).map(item => ({code: 'estimate_approval_required', message: 'Low-confidence estimate requires approval', taskId: item.taskId}));
  for (const task of tasks.filter(item => item.lane === 'provisional')) warnings.push({code: 'missing_jira', message: 'Delegation requires Jira linking before scheduling', taskId: task.id});
  const connectors = Object.fromEntries(systems.map(system => [system, connectorState(freshness[system], now)]));
  const paused = profile?.approval?.automationPaused === true;
  return clone({schemaVersion: 1, planRevision: plan.planRevision, generatedAt: plan.generatedAt ?? now, timeline: items, currentBlock, nextBlock, capacity: {availableMinutes: plan.availableMinutes ?? 0, plannedMinutes: plan.usedMinutes ?? 0, bufferMinutes: plan.bufferMinutes ?? 0, risk: (plan.usedMinutes ?? 0) > (plan.capacityMinutes ?? 0) ? 'over' : (plan.capacityMinutes ?? 0) - (plan.usedMinutes ?? 0) < (plan.bufferMinutes ?? 0) ? 'tight' : 'normal'}, carryovers, approvals, reconciliation, opportunities, warnings, connectors, paused, degraded: systems.some(system => connectors[system].status !== 'healthy')});
}
