import {assertOperation} from '../domain.mjs';

const SAFE_RETRY_KINDS = new Set(['reminder_upsert', 'reminder_complete', 'reminder_delete', 'calendar_upsert', 'calendar_delete', 'jira_assign', 'provisional_link', 'urgent_displacement', 'scope_expand']);
const TERMINAL_STATES = new Set(['applied', 'reconciliation_required', 'failed']);

function copy(value) { return structuredClone(value); }

function assertPlanRevision(plan) {
  if (plan === null || typeof plan !== 'object' || !Number.isInteger(plan.planRevision) || plan.planRevision < 1) throw new RangeError('plan.planRevision must be an integer >= 1');
  return plan.planRevision;
}

function assertSnapshot(snapshot) {
  if (snapshot === null || typeof snapshot !== 'object' || Array.isArray(snapshot) || Object.getPrototypeOf(snapshot) !== Object.prototype) throw new TypeError('snapshot must be a plain object');
  if (Object.keys(snapshot).length !== 2 || !Object.hasOwn(snapshot, 'sourceRevision') || !Object.hasOwn(snapshot, 'proposedOperations')) throw new TypeError('snapshot must contain only sourceRevision and proposedOperations');
  if (typeof snapshot.sourceRevision !== 'string' || snapshot.sourceRevision.length === 0) throw new TypeError('snapshot.sourceRevision must be a nonempty string');
  if (!Array.isArray(snapshot.proposedOperations)) throw new TypeError('snapshot.proposedOperations must be an array');
}

export function previewOperations(plan, snapshot) {
  const planRevision = assertPlanRevision(plan);
  assertSnapshot(snapshot);
  const ids = new Set(); const keys = new Set();
  for (const operation of snapshot.proposedOperations) {
    assertOperation(operation);
    if (operation.planRevision !== planRevision) throw new RangeError(`operation ${operation.id} plan revision does not match preview plan`);
    if (ids.has(operation.id)) throw new Error(`duplicate operation id ${operation.id}`);
    if (keys.has(operation.idempotencyKey)) throw new Error(`duplicate operation idempotency key ${operation.idempotencyKey}`);
    ids.add(operation.id); keys.add(operation.idempotencyKey);
  }
  const operations = copy(snapshot.proposedOperations);
  return {planRevision, sourceRevision: snapshot.sourceRevision, operations, approvalsRequired: operations.filter(operation => operation.approval === 'required').map(operation => operation.id)};
}

function normalizedError(error) {
  if (!error || typeof error !== 'object') return {kind: 'connector_error', retryable: false, ambiguous: false, status: null};
  return {kind: typeof error.kind === 'string' && error.kind.length > 0 ? error.kind : 'connector_error', retryable: error.retryable === true, ambiguous: error.ambiguous === true, status: Number.isInteger(error.status) ? error.status : null};
}

function terminalResult(operationId, execution) {
  return {operationId, state: execution.operation.retryState, reason: execution.result?.reason ?? null};
}

function failure(repository, operation, error, state = 'failed') {
  repository.markState(operation.id, state, {reason: error.kind, error});
  return {operationId: operation.id, state, error};
}

function reconciliationAfterExternalCall(repository, operation, reason, details = {}) {
  try { repository.markState(operation.id, 'reconciliation_required', {reason, ...details}); } catch (error) {
    if (error instanceof SyntaxError) throw error;
  }
  return {operationId: operation.id, state: 'reconciliation_required', reason};
}

function drift(repository, operation, observedRevision) {
  repository.reconcileDrift({operationId: operation.id, targetId: operation.targetId, expectedRevision: operation.preconditionRevision, observedRevision});
  return {operationId: operation.id, state: 'reconciliation_required', reason: 'revision_drift'};
}

async function precondition(repository, connector, operation) {
  if (operation.preconditionRevision === null) return null;
  if (typeof connector.findByExternalId !== 'function') return failure(repository, operation, {kind: 'missing_find_by_external_id', retryable: false, ambiguous: false, status: null});
  let current;
  try { current = await connector.findByExternalId(operation.targetId); } catch (error) {
    const normalized = normalizedError(error);
    return normalized.ambiguous ? reconciliationAfterExternalCall(repository, operation, 'ambiguous_precondition', {error: normalized}) : failure(repository, operation, normalized);
  }
  if (current === null || !current || typeof current.revision !== 'string' || current.revision !== operation.preconditionRevision) return drift(repository, operation, current?.revision ?? null);
  return null;
}

async function applyOne(repository, connector, operation) {
  const preconditionResult = await precondition(repository, connector, operation);
  if (preconditionResult) return preconditionResult;
  while (true) {
    const execution = repository.execution(operation.id);
    if (TERMINAL_STATES.has(execution.operation.retryState)) {
      repository.appendAudit({event: 'operation_terminal_replay', entityType: 'operation', entityId: operation.id, data: {state: execution.operation.retryState, reason: execution.result?.reason ?? null}});
      return terminalResult(operation.id, execution);
    }
    if (execution.operation.retryState === 'pending' && execution.attemptCount > 0) return reconciliationAfterExternalCall(repository, operation, 'interrupted_attempt');
    if (execution.operation.retryState !== 'pending' && execution.operation.retryState !== 'safe_retry') return reconciliationAfterExternalCall(repository, operation, 'unexpected_retry_state');
    if (execution.operation.retryState === 'safe_retry' && execution.attemptCount >= 2) {
      repository.markState(operation.id, 'failed', {reason: 'retry_exhausted'});
      return {operationId: operation.id, state: 'failed', reason: 'retry_exhausted'};
    }
    if (execution.operation.retryState === 'safe_retry' && execution.attemptCount === 0) return reconciliationAfterExternalCall(repository, operation, 'invalid_retry_history');
    const attempt = repository.beginAttempt(operation.id);
    let result;
    try {
      result = await connector.applyOperation(operation);
    } catch (error) {
      const normalized = normalizedError(error);
      if (normalized.ambiguous) return reconciliationAfterExternalCall(repository, operation, 'ambiguous_apply', {error: normalized});
      if (normalized.retryable && SAFE_RETRY_KINDS.has(operation.kind) && attempt.attemptCount < 2) {
        try { repository.markState(operation.id, 'safe_retry', {reason: 'safe_retry', error: normalized}); } catch (stateError) {
          if (stateError instanceof SyntaxError) throw stateError;
          return reconciliationAfterExternalCall(repository, operation, 'retry_state_persistence_failed', {error: normalized});
        }
        continue;
      }
      return failure(repository, operation, normalized);
    }
    if (!result || typeof result.externalId !== 'string' || result.externalId.length === 0 || typeof result.revision !== 'string' || result.revision.length === 0) return reconciliationAfterExternalCall(repository, operation, 'malformed_success');
    try {
      repository.markState(operation.id, 'applied', {reason: null, externalId: result.externalId, revision: result.revision, result: result.result ?? null});
      return {operationId: operation.id, state: 'applied', externalId: result.externalId, revision: result.revision};
    } catch (persistenceError) {
      if (persistenceError instanceof SyntaxError) throw persistenceError;
      return reconciliationAfterExternalCall(repository, operation, 'success_persistence_failed');
    }
  }
}

export async function applyApprovedOperations({repository, connectors, currentRevision}, operations) {
  if (!repository || typeof repository.get !== 'function' || typeof repository.save !== 'function' || typeof repository.execution !== 'function' || typeof repository.beginAttempt !== 'function' || typeof repository.markState !== 'function' || typeof repository.appendAudit !== 'function' || typeof repository.reconcileDrift !== 'function') throw new TypeError('repository does not implement the operation repository contract');
  if (!Number.isInteger(currentRevision) || currentRevision < 1) throw new RangeError('currentRevision must be an integer >= 1');
  if (!Array.isArray(operations)) throw new TypeError('operations must be an array');
  const results = [];
  for (const candidate of operations) {
    assertOperation(candidate);
    if (candidate.planRevision !== currentRevision) throw new RangeError(`operation ${candidate.id} plan revision does not match current revision`);
    const operation = repository.save(candidate);
    const execution = repository.execution(operation.id);
    if (operation.approval !== 'approved') {
      repository.appendAudit({event: 'operation_skipped_unapproved', entityType: 'operation', entityId: operation.id, data: {approval: operation.approval}});
      results.push({operationId: operation.id, state: 'skipped_unapproved'});
      continue;
    }
    if (TERMINAL_STATES.has(execution.operation.retryState)) {
      repository.appendAudit({event: 'operation_terminal_replay', entityType: 'operation', entityId: operation.id, data: {state: execution.operation.retryState, reason: execution.result?.reason ?? null}});
      results.push(terminalResult(operation.id, execution));
      continue;
    }
    const connector = connectors?.[operation.targetSystem];
    if (!connector || typeof connector.applyOperation !== 'function') {
      results.push(failure(repository, operation, {kind: 'missing_connector', retryable: false, ambiguous: false, status: null}));
      continue;
    }
    results.push(await applyOne(repository, connector, operation));
  }
  return results;
}
