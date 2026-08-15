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
  const reconcileCreate = async (connector, create, lookup) => {
    const existing = await connector.findByExternalId(lookup);
    if (existing) return connector.applyOperation(create);
    try { return await connector.applyOperation(create); } catch (error) {
      if (error?.ambiguous !== true) throw error;
      const found = await connector.findByExternalId(lookup);
      if (!found) throw new ApiError('reconciliation_required', 409);
      return connector.applyOperation(create);
    }
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
      let reminderId = pending.exact.reminderExternalId; let calendarId = null; let failure = null;
      try {
        await reconcileCreate(reminders, pending.reminder, reminderId); if (!await reminders.findByExternalId(reminderId)) throw new Error('reminder_probe_unverified');
        const calendarResult = await reconcileCreate(calendar, pending.calendar, pending.exact.calendarOperationKey); calendarId = calendarResult?.externalId;
        if (typeof calendarId !== 'string' || !calendarId || !await calendar.findByExternalId(calendarId)) throw new Error('calendar_probe_unverified');
      } catch (error) { failure = error; }
      try {
        if (calendarId) { const value = operation({revision: pending.calendar.planRevision, kind: 'calendar_delete', targetSystem: 'calendar', targetId: calendarId, payload: {}, now: now().toISOString()}); await calendar.applyOperation(value); if (await calendar.findByExternalId(calendarId)) throw new Error('calendar_probe_cleanup_unverified'); }
        if (reminderId && await reminders.findByExternalId(reminderId)) { const value = operation({revision: pending.reminder.planRevision, kind: 'reminder_delete', targetSystem: 'reminders', targetId: reminderId, payload: {}, now: now().toISOString()}); await reminders.applyOperation(value); if (await reminders.findByExternalId(reminderId)) throw new Error('reminder_probe_cleanup_unverified'); }
      } catch (error) { failure = failure ?? error; }
      if (failure) { const reconciliation = failure?.message === 'reconciliation_required' || failure?.status === 409; preferences.set('pending_setup_probe', {...pending, state: reconciliation ? 'reconciliation_required' : 'failed'}); audit.append(reconciliation ? 'setup_probe_reconciliation_required' : 'setup_probe_failed', 'setup_probe', probeId, {actor, cleanupAttempted: true}); throw new ApiError(reconciliation ? 'reconciliation_required' : 'setup_probe_failed', reconciliation ? 409 : 503); }
      preferences.delete('pending_setup_probe'); audit.append('setup_probe_completed', 'setup_probe', probeId, {actor, verified: {reminders: true, calendar: true}});
      return {probeId, verified: {reminders: true, calendar: true}};
    },
  };
}
