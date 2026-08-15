import {randomUUID} from 'node:crypto';
import {operationKey} from '../domain.mjs';
import {ApiError} from './auth.mjs';
import {setupScopeCovered} from './preferences.mjs';

function operation({revision, kind, targetSystem, targetId, payload, now}) {
  const key = operationKey(revision, kind, targetId, payload);
  return {schemaVersion: 1, id: `setup-probe:${kind}:${key.slice(0, 20)}`, planRevision: revision, kind, targetSystem, targetId, payload, idempotencyKey: key, approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: now};
}

function approved(preferences, remindersListId, focusCalendarId) {
  const scopes = preferences.get('approved_setup_scopes') ?? {};
  const reminders = {awarenessListIds: [], tasksListId: remindersListId};
  const calendar = {readCalendarIds: [focusCalendarId], focusCalendarId};
  if (!setupScopeCovered('reminders', scopes.reminders, reminders) || !setupScopeCovered('calendar', scopes.calendar, calendar)) throw new ApiError('scope_approval_required', 409);
}

export function createSetupProbeAuthority({preferences, audit, connectorRegistry, currentRevision, now = () => new Date()}) {
  const reconciliationRequired = () => { const error = new ApiError('reconciliation_required', 409); error.ambiguous = true; return error; };
  const reconcileCreate = async (connector, create, lookup) => {
    const existing = await connector.findByExternalId(lookup);
    if (existing) { const externalId = existing.externalId ?? create.targetId; if (!externalId) throw reconciliationRequired(); return {externalId, revision: existing.revision}; }
    try { return await connector.applyOperation(create); } catch (error) {
      if (error?.ambiguous !== true) throw error;
      const found = await connector.findByExternalId(lookup);
      if (!found) throw reconciliationRequired();
      const externalId = found.externalId ?? create.targetId; if (!externalId) throw reconciliationRequired();
      return {externalId, revision: found.revision};
    }
  };
  const exactCalendarProof = async (calendar, operationKey, expectedId) => {
    const found = await calendar.findByExternalId(operationKey);
    if (!found || typeof found.externalId !== 'string' || !found.externalId || (expectedId && found.externalId !== expectedId)) return null;
    return found;
  };
  return {
    preview({planRevision, remindersListId, focusCalendarId}) {
      if (planRevision !== currentRevision() || typeof remindersListId !== 'string' || !remindersListId || typeof focusCalendarId !== 'string' || !focusCalendarId) throw new ApiError('revision_conflict', 409);
      approved(preferences, remindersListId, focusCalendarId);
      const probeId = randomUUID(); const revision = Math.max(1, planRevision + 1); const externalId = `access-probe:${probeId}`; const instant = now(); const start = new Date(instant.getTime() + 5 * 60_000).toISOString(); const end = new Date(instant.getTime() + 20 * 60_000).toISOString();
      const stableCalendarKey = operationKey(1, 'calendar_upsert', probeId, {probeId});
      const reminderPayload = {listId: remindersListId, title: 'Rhize Tasks access check', dueAt: null, notes: 'Created and removed by the approved setup access check.', externalId};
      const calendarPayload = {calendarId: focusCalendarId, title: 'Rhize Tasks access check', start, end, description: 'Created and removed by the approved setup access check.', externalId, operationKey: stableCalendarKey, taskId: `setup-probe:${probeId}`, blockSlot: `setup-probe:${probeId}:1`};
      const exact = {remindersListId, focusCalendarId, reminderExternalId: externalId, calendarOperationKey: stableCalendarKey};
      const pending = {state: 'approval_required', probeId, planRevision, reminder: operation({revision, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: externalId, payload: reminderPayload, now: instant.toISOString()}), calendar: operation({revision, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: null, payload: calendarPayload, now: instant.toISOString()}), exact};
      preferences.set('pending_setup_probe', pending); audit.append('setup_probe_previewed', 'setup_probe', probeId, {planRevision, exact});
      return {planRevision, probeId, approvalRequired: true, exact};
    },
    async apply({planRevision, probeId, actor}) {
      const pending = preferences.get('pending_setup_probe');
      if (!pending || pending.probeId !== probeId) throw new ApiError('setup_probe_not_found', 404);
      if (planRevision !== currentRevision() || pending.planRevision !== planRevision) throw new ApiError('revision_conflict', 409);
      approved(preferences, pending.exact.remindersListId, pending.exact.focusCalendarId);
      preferences.set('pending_setup_probe', {...pending, state: 'approved', actor});
      audit.append('setup_probe_approved', 'setup_probe', probeId, {actor, planRevision, exact: pending.exact});
      const registry = await connectorRegistry.getSetupProbe(pending.exact); const reminders = registry?.reminders; const calendar = registry?.calendar;
      if (!reminders?.applyOperation || !reminders?.findByExternalId || !calendar?.applyOperation || !calendar?.findByExternalId) throw new ApiError('connector_unavailable', 503);
      let reminderId = pending.exact.reminderExternalId; let calendarId = typeof pending.calendarId === 'string' && pending.calendarId ? pending.calendarId : null; let failure = null; let reminderProven = false; let calendarProven = false; let reminderClean = false; let calendarDeleteDispatched = false; let calendarDeleteConfirmed = false; let calendarFinalAbsent = false;
      try {
        await reconcileCreate(reminders, pending.reminder, reminderId); reminderProven = true; if (!await reminders.findByExternalId(reminderId)) throw new Error('reminder_probe_unverified');
        if (!calendarId) { const calendarResult = await reconcileCreate(calendar, pending.calendar, pending.exact.calendarOperationKey); calendarId = calendarResult?.externalId; }
        if (typeof calendarId !== 'string' || !calendarId) throw new Error('calendar_probe_unverified');
        const proof = await exactCalendarProof(calendar, pending.exact.calendarOperationKey, calendarId); if (!proof) throw new Error('calendar_probe_unverified'); calendarProven = true;
      } catch (error) { failure = error; }
      if (!calendarId) try { const proof = await exactCalendarProof(calendar, pending.exact.calendarOperationKey); if (proof) { calendarId = proof.externalId; calendarProven = true; } } catch (error) { failure ??= error; }
      if (calendarId) {
        let deleteError = null;
        try { const value = operation({revision: pending.calendar.planRevision, kind: 'calendar_delete', targetSystem: 'calendar', targetId: calendarId, payload: {}, now: now().toISOString()}); await calendar.applyOperation(value); calendarDeleteDispatched = true; calendarDeleteConfirmed = true; } catch (error) { deleteError = error; }
        try { const [byId, byKey] = await Promise.all([calendar.findByExternalId(calendarId), calendar.findByExternalId(pending.exact.calendarOperationKey)]); calendarFinalAbsent = byId === null && byKey === null; } catch (error) { deleteError ??= error; }
        if (!(calendarProven && calendarDeleteDispatched && calendarDeleteConfirmed && calendarFinalAbsent)) failure ??= deleteError ?? reconciliationRequired();
      }
      try { if (reminderId && await reminders.findByExternalId(reminderId)) { const value = operation({revision: pending.reminder.planRevision, kind: 'reminder_delete', targetSystem: 'reminders', targetId: reminderId, payload: {}, now: now().toISOString()}); await reminders.applyOperation(value); } reminderClean = await reminders.findByExternalId(reminderId) === null; if (!reminderClean) throw new Error('reminder_probe_cleanup_unverified'); } catch (error) { failure ??= error; }
      if (!failure && !(reminderProven && reminderClean && calendarProven && calendarDeleteConfirmed && calendarFinalAbsent)) failure = reconciliationRequired();
      if (failure) { const reconciliation = failure?.ambiguous === true || failure?.message === 'reconciliation_required' || failure?.status === 409 || Boolean(calendarId) || (reminderProven && !reminderClean); const calendarCleanup = {createdOrFound: Boolean(calendarId), provenPositive: calendarProven, deleteDispatched: calendarDeleteDispatched, deleteConfirmed: calendarDeleteConfirmed, finalAbsent: calendarFinalAbsent}; preferences.set('pending_setup_probe', {...pending, state: reconciliation ? 'reconciliation_required' : 'failed', calendarCleanup, ...(calendarId ? {calendarId} : {})}); audit.append(reconciliation ? 'setup_probe_reconciliation_required' : 'setup_probe_failed', 'setup_probe', probeId, {actor, cleanupAttempted: true, calendarCleanup}); const error = new ApiError(reconciliation ? 'reconciliation_required' : 'setup_probe_failed', reconciliation ? 409 : 503); if (reconciliation) error.ambiguous = true; throw error; }
      preferences.delete('pending_setup_probe'); audit.append('setup_probe_completed', 'setup_probe', probeId, {actor, verified: {reminders: true, calendar: true}});
      return {probeId, verified: {reminders: true, calendar: true}};
    },
  };
}
