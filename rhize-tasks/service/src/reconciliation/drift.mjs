export function reconcileExternalRevision({repository, taskId, expectedRevision, observedRevision, operation}) {
  if (!repository || typeof repository.reconcileDrift !== 'function') throw new TypeError('repository does not implement reconciliation storage');
  if (typeof taskId !== 'string' || taskId.length === 0 || typeof expectedRevision !== 'string' || expectedRevision.length === 0 || typeof observedRevision !== 'string' || observedRevision.length === 0) throw new TypeError('reconciliation requires taskId and nonempty revisions');
  if (!operation || typeof operation.id !== 'string' || operation.id.length === 0) throw new TypeError('reconciliation requires an operation');
  repository.reconcileDrift({operationId: operation.id, targetId: taskId, expectedRevision, observedRevision});
  return {taskId, state: 'manual_lock', expectedRevision, observedRevision, operationId: operation.id};
}
