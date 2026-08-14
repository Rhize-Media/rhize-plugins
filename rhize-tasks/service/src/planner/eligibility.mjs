const PRIORITY = Object.freeze({urgent: 4, high: 3, normal: 2, low: 1});

function competencyFit(task, profile) {
  const saved = new Map(profile.jira.competencies.filter(item => !item.excluded).map(item => [item.name.toLowerCase(), item.confidence]));
  return Math.max(0, ...task.competencies.map(name => saved.get(name.toLowerCase()) ?? 0));
}

export function opportunityEligible(task, profile) {
  return task.assigneeAccountId === null && !task.terminal && !task.blocked && !task.reserved && profile.jira.projects.includes(task.projectKey) && profile.jira.issueTypes.includes(task.issueType) && !profile.jira.excludedIssueTypes.includes(task.issueType) && PRIORITY[task.priority] > PRIORITY[profile.jira.opportunityUrgencyThreshold] && competencyFit(task, profile) >= 0.7;
}
export function taskCompetencyFit(task, profile) { return competencyFit(task, profile); }
export function classifyTask(task, profile) {
  if (task.lane === 'provisional') return {lane: 'provisional', schedulable: false};
  if (!profile.jira.projects.includes(task.projectKey) || task.terminal || !profile.jira.issueTypes.includes(task.issueType) || profile.jira.excludedIssueTypes.includes(task.issueType)) return null;
  if (task.assigneeAccountId === profile.jira.accountId) return {lane: 'owned', schedulable: true};
  if (opportunityEligible(task, profile)) return {lane: 'opportunity', schedulable: false};
  return null;
}
export {PRIORITY};
