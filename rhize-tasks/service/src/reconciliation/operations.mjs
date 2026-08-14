import {assertOperation} from '../domain.mjs';

const SAFE_RETRY_KINDS = new Set(['reminder_upsert', 'reminder_complete', 'reminder_delete', 'calendar_upsert', 'calendar_delete', 'jira_assign', 'provisional_link', 'urgent_displacement', 'scope_expand']);

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
  const ids = new Set();
  const keys = new Set();
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
  return {
    kind: typeof error.kind === 'string' && error.kind.length > 0 ? error.kind : 'connector_error',
    retryable: error.retryable === true,
    ambiguous: error.ambiguous === true,
    status: Number.isInteger(error.status) ? error.status : null,
  };
}

function saveIfNeeded(repository, operation) {
  const existing = repository.get(operation.id);
  return existing ?? repository.save(operation);
}

function failure(repository, operation, error, state = 'failed') {
  repository.markState(operation.id, state, {error});
  return {operationId: operation.id, state, error};
}

function drift(repository, operation, observedRevision) {
  repository.lockTarget?.(operation.targetId, 'external_revision_drift');
  repository.markState(operation.id, 'reconciliation_required', {expectedRevision: operation.preconditionRevision, observedRevision});
  repository.appendAudit({event: 'external_revision_drift', entityType: 'operation', entityId: operation.id, data: {targetId: operation.targetId, expectedRevision: operation.preconditionRevision, observedRevision}});
  return {operationId: operation.id, state: 'reconciliation_required', reason: 'revision_drift'};
}

async function precondition(repository, connector, operation) {
  if (operation.preconditionRevision === null) return null;
  let current;
  try { current = await connector.findByExternalId(operation.targetId); } catch (error) { return failure(repository, operation, normalizedError(error)); }
  if (current === null || !current || typeof current.revision !== 'string' || current.revision !== operation.preconditionRevision) return drift(repository, operation, current?.revision ?? null);
  return null;
}

async function applyOne(repository, connector, operation) {
  const preconditionResult = await precondition(repository, connector, operation);
  if (preconditionResult) return preconditionResult;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    repository.appendAudit({event: 'operation_attempted', entityType: 'operation', entityId: operation.id, data: {attempt: attempt + 1}});
    try {
      const result = await connector.applyOperation(operation);
      if (!result || typeof result.externalId !== 'string' || result.externalId.length === 0 || typeof result.revision !== 'string' || result.revision.length === 0) return failure(repository, operation, {kind: 'invalid_connector_result', retryable: false, ambiguous: false, status: null});
      repository.markState(operation.id, 'applied', {externalId: result.externalId, revision: result.revision, result: result.result ?? null});
      return {operationId: operation.id, state: 'applied', externalId: result.externalId, revision: result.revision};
    } catch (error) {
      const normalized = normalizedError(error);
      if (normalized.ambiguous) return failure(repository, operation, normalized, 'reconciliation_required');
      if (attempt === 0 && normalized.retryable && SAFE_RETRY_KINDS.has(operation.kind)) {
        repository.markState(operation.id, 'safe_retry', {error: normalized});
        continue;
      }
      return failure(repository, operation, normalized);
    }
  }
  throw new Error('unreachable operation retry state');
}

export async function applyApprovedOperations({repository, connectors, currentRevision}, operations) {
  if (!repository || typeof repository.get !== 'function' || typeof repository.save !== 'function' || typeof repository.markState !== 'function' || typeof repository.wasApplied !== 'function' || typeof repository.appendAudit !== 'function') throw new TypeError('repository does not implement the operation repository contract');
  if (!Number.isInteger(currentRevision) || currentRevision < 1) throw new RangeError('currentRevision must be an integer >= 1');
  if (!Array.isArray(operations)) throw new TypeError('operations must be an array');
  const results = [];
  for (const operation of operations) {
    assertOperation(operation);
    if (operation.planRevision !== currentRevision) throw new RangeError(`operation ${operation.id} plan revision does not match current revision`);
    saveIfNeeded(repository, operation);
    if (operation.approval !== 'approved') {
      repository.appendAudit({event: 'operation_skipped_unapproved', entityType: 'operation', entityId: operation.id, data: {approval: operation.approval}});
      results.push({operationId: operation.id, state: 'skipped_unapproved'});
      continue;
    }
    if (repository.wasApplied(operation.idempotencyKey)) {
      repository.appendAudit({event: 'operation_skipped_applied', entityType: 'operation', entityId: operation.id, data: {idempotencyKey: operation.idempotencyKey}});
      results.push({operationId: operation.id, state: 'skipped_applied'});
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
