import {randomUUID} from 'node:crypto';
import {operationKey} from '../domain.mjs';
import {ApiError} from './auth.mjs';

function operation({revision, kind, targetSystem, targetId, payload, now}) {
  const key = operationKey(revision, kind, targetId, payload);
  return {schemaVersion: 1, id: `setup-probe:${kind}:${key.slice(0, 20)}`, planRevision: revision, kind, targetSystem, targetId, payload, idempotencyKey: key, approval: 'approved', preconditionRevision: null, retryState: 'pending', createdAt: now};
}

export function createSetupProbeAuthority({preferences, audit, connectorRegistry, now = () => new Date()}) {
  return {
    preview({planRevision, remindersListId, focusCalendarId}) {
      if (typeof remindersListId !== 'string' || !remindersListId || typeof focusCalendarId !== 'string' || !focusCalendarId) throw new ApiError('invalid_setup_probe');
      const probeId = randomUUID(); const revision = Math.max(1, planRevision + 1); const externalId = `access-probe:${probeId}`; const instant = now(); const start = new Date(instant.getTime() + 5 * 60_000).toISOString(); const end = new Date(instant.getTime() + 20 * 60_000).toISOString();
      const reminderPayload = {listId: remindersListId, title: 'Rhize Tasks access check', dueAt: null, notes: 'Created and removed by the approved setup access check.', externalId};
      const calendarPayload = {calendarId: focusCalendarId, title: 'Rhize Tasks access check', start, end, description: 'Created and removed by the approved setup access check.', externalId};
      const exact = {remindersListId, focusCalendarId, reminderExternalId: externalId, calendarOperationKey: operationKey(revision, 'calendar_upsert', null, calendarPayload)};
      preferences.set('pending_setup_probe', {probeId, planRevision, reminder: operation({revision, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: externalId, payload: reminderPayload, now: instant.toISOString()}), calendar: operation({revision, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: null, payload: calendarPayload, now: instant.toISOString()}), exact});
      audit.append('setup_probe_previewed', 'setup_probe', probeId, {planRevision, exact});
      return {planRevision, probeId, approvalRequired: true, exact};
    },
    async apply({probeId, actor}) {
      const pending = preferences.get('pending_setup_probe');
      if (!pending || pending.probeId !== probeId) throw new ApiError('setup_probe_not_found', 404);
      preferences.delete('pending_setup_probe');
      const registry = await connectorRegistry.getSetupProbe(pending.exact); const reminders = registry?.reminders; const calendar = registry?.calendar;
      if (!reminders?.applyOperation || !reminders?.findByExternalId || !calendar?.applyOperation || !calendar?.findByExternalId) throw new ApiError('connector_unavailable', 503);
      let reminderId = null; let calendarId = null; let failure = null;
      try {
        reminderId = pending.exact.reminderExternalId; const reminderResult = await reminders.applyOperation(pending.reminder);
        if (reminderId !== pending.exact.reminderExternalId || !await reminders.findByExternalId(reminderId)) throw new Error('reminder_probe_unverified');
        const calendarResult = await calendar.applyOperation(pending.calendar); calendarId = calendarResult?.externalId;
        if (typeof calendarId !== 'string' || !calendarId || !await calendar.findByExternalId(calendarId)) throw new Error('calendar_probe_unverified');
      } catch (error) { failure = error; }
      try {
        if (calendarId) { const value = operation({revision: pending.calendar.planRevision, kind: 'calendar_delete', targetSystem: 'calendar', targetId: calendarId, payload: {}, now: now().toISOString()}); await calendar.applyOperation(value); if (await calendar.findByExternalId(calendarId)) throw new Error('calendar_probe_cleanup_unverified'); }
        if (reminderId) { const value = operation({revision: pending.reminder.planRevision, kind: 'reminder_delete', targetSystem: 'reminders', targetId: reminderId, payload: {}, now: now().toISOString()}); await reminders.applyOperation(value); if (await reminders.findByExternalId(reminderId)) throw new Error('reminder_probe_cleanup_unverified'); }
      } catch (error) { failure = failure ?? error; }
      if (failure) { audit.append('setup_probe_failed', 'setup_probe', probeId, {actor, cleanupAttempted: true}); throw new ApiError('setup_probe_failed', 503); }
      audit.append('setup_probe_completed', 'setup_probe', probeId, {actor, verified: {reminders: true, calendar: true}});
      return {probeId, verified: {reminders: true, calendar: true}};
    },
  };
}
