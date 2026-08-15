import {withSingleInstance} from './single-instance.mjs';

const kinds = new Set(['morning', 'midday', 'evening', 'catch-up']);

export function protectedForMidday(plan, states = {}, now = new Date().toISOString(), freezeWindowMinutes = 30) {
  const cutoff = Date.parse(now) + freezeWindowMinutes * 60000;
  return (plan?.blocks ?? []).filter(block => block.locked === true || ['active', 'completed', 'manual'].includes(states[block.id]) || Date.parse(block.start) <= cutoff).map(block => ({id: `preserved:${block.id}`, start: block.start, end: block.end, kind: block.locked || states[block.id] === 'manual' ? 'manual_lock' : 'freeze', sourceSystem: 'local', mutable: false}));
}

export async function runRoutine(kind, context, now = new Date()) {
  if (!kinds.has(kind)) throw new TypeError('unsupported_routine');
  if (!context?.lockPath || !context.activation || !context.routineState || !context.sync || !context.plans) throw new TypeError('invalid_routine_context');
  if (await context.pause?.isPaused?.()) return {state: 'paused'};
  if (!await context.activation.canActivate()) return {state: 'inactive'};
  try {
    return await withSingleInstance(context.lockPath, async () => {
      const due = await context.routineState.evaluate(kind, now);
      if (!due?.shouldRun) return {state: 'not_due'};
      const runId = await context.routineState.begin(kind, now, due);
      try {
        const snapshot = await context.sync.readAll();
        const result = await context.plans.reconcileAndPlan({kind: due.catchUp ? 'catch_up' : kind, snapshot, now});
        await context.routineState.complete(runId, 'completed', result);
        return result;
      } catch (error) {
        await context.routineState.complete(runId, 'failed', {kind: error?.kind ?? 'routine_error'});
        throw error;
      }
    });
  } catch (error) {
    if (error?.kind === 'already_running') return {state: 'already_running'};
    throw error;
  }
}
