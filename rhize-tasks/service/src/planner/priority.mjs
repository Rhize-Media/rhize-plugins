import {classifyTask, PRIORITY, taskCompetencyFit} from './eligibility.mjs';
import {estimateTask} from './estimates.mjs';

const dayDistance = (dueDate, now) => Math.round((Date.parse(`${dueDate}T00:00:00.000Z`) - Date.parse(`${now.slice(0, 10)}T00:00:00.000Z`)) / 86400000);
const ageDays = (createdAt, now) => Math.max(0, Math.floor((Date.parse(now) - Date.parse(createdAt)) / 86400000));

export function compareCodePoint(left, right) {
  const a = String(left); const b = String(right);
  let aIndex = 0; let bIndex = 0;
  while (aIndex < a.length && bIndex < b.length) {
    const aPoint = a.codePointAt(aIndex); const bPoint = b.codePointAt(bIndex);
    if (aPoint !== bPoint) return aPoint - bPoint;
    aIndex += aPoint > 0xffff ? 2 : 1;
    bIndex += bPoint > 0xffff ? 2 : 1;
  }
  return a.length - b.length;
}

function compareValue(left, right) { return typeof left === 'number' ? right - left : compareCodePoint(left, right); }

export function rankTasks(tasks, profile, now) {
  return tasks.map(task => {
    const classification = classifyTask(task, profile);
    const lane = classification?.lane ?? task.lane;
    const estimate = estimateTask(task, [], profile);
    const contextKey = task.competencies.map(name => name.toLowerCase()).sort(compareCodePoint).join('|') || '~';
    const competency = taskCompetencyFit(task, profile);
    const age = ageDays(task.createdAt, now);
    return {
      task, lane, schedulable: Boolean(classification?.schedulable), estimate,
      factors: [
        {name: 'lane', value: lane === 'owned' ? 2 : lane === 'opportunity' ? 1 : 0, explanation: lane === 'owned' ? 'Assigned owned work precedes opportunities' : 'Unassigned work is advisory'},
        {name: 'due', value: task.dueDate ? 10000 - dayDistance(task.dueDate, now) : -1, explanation: task.dueDate ? `Due ${task.dueDate}` : 'No due date'},
        {name: 'priority', value: PRIORITY[task.priority], explanation: `${task.priority} priority`},
        {name: 'blocked_dependencies', value: task.blocked ? -100 : task.dependencyRisk, explanation: task.blocked ? 'Blocked work cannot be placed' : `Dependency/downstream risk ${task.dependencyRisk}`},
        {name: 'project_importance', value: profile.jira.projectImportance[task.projectKey] ?? 0, explanation: `Project importance ${profile.jira.projectImportance[task.projectKey] ?? 0}`},
        {name: 'effort_fit', value: estimate.minutes <= profile.planning.focusBlockMinutes ? 1 : 0, explanation: estimate.minutes <= profile.planning.focusBlockMinutes ? 'Fits one focus block' : 'Requires permitted splitting'},
        {name: 'competency_confidence', value: competency, explanation: `Competency fit ${competency}`},
        {name: 'context', value: contextKey, explanation: contextKey === '~' ? 'No context tag' : `Context ${contextKey}`},
        {name: 'age', value: age, explanation: `${age} days open`},
      ],
    };
  }).sort((left, right) => {
    for (let index = 0; index < left.factors.length; index += 1) {
      const result = compareValue(left.factors[index].value, right.factors[index].value);
      if (result !== 0) return result;
    }
    return compareCodePoint(left.task.id, right.task.id);
  });
}
