const INFERENCE = Object.freeze({Bug: 90, Task: 120, Story: 180, Epic: 480});
const clamp = minutes => Math.max(15, Math.min(10080, minutes));
function median(values) { const sorted = [...values].sort((left, right) => left - right); const middle = Math.floor(sorted.length / 2); return sorted.length % 2 ? sorted[middle] : Math.floor((sorted[middle - 1] + sorted[middle]) / 2); }
export function estimateTask(task, history, profile) {
  void profile;
  if (task.remainingMinutes !== null) return {minutes: clamp(task.remainingMinutes), source: 'jira_remaining', confidence: 'high', rationale: 'Jira remaining estimate', requiresApproval: false};
  if (task.explicitEstimateMinutes !== null) return {minutes: clamp(task.explicitEstimateMinutes), source: 'explicit', confidence: 'high', rationale: 'Explicit local estimate', requiresApproval: false};
  if (task.estimate?.source === 'agent_assisted') return {minutes: clamp(task.estimate.minutes), source: 'agent_assisted', confidence: task.estimate.confidence, rationale: task.estimate.rationale, requiresApproval: !(task.estimate.confidence === 'high' && task.estimate.requiresApproval === false)};
  if (task.estimate) return {minutes: clamp(task.estimate.minutes), source: task.estimate.source, confidence: task.estimate.confidence, rationale: task.estimate.rationale, requiresApproval: task.estimate.requiresApproval};
  const records = history.filter(record => record.issueType === task.issueType && (record.projectKey === task.projectKey || record.competencies.some(name => task.competencies.includes(name)))).map(record => record.actualMinutes);
  if (records.length >= 3) return {minutes: clamp(median(records)), source: 'history', confidence: 'medium', rationale: `Median of ${records.length} similar completed tasks`, requiresApproval: false};
  const minutes = clamp(INFERENCE[task.issueType] ?? 60);
  return {minutes, source: 'inferred', confidence: 'low', rationale: `Deterministic ${INFERENCE[task.issueType] ? task.issueType : 'fallback'} scope rule`, requiresApproval: true};
}
