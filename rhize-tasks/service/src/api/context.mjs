import {randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';

import {createGoogleCalendarConnector} from '../connectors/google-calendar.mjs';
import {createHttpTransport} from '../connectors/http.mjs';
import {createJiraConnector} from '../connectors/jira.mjs';
import {createKeychain} from '../connectors/keychain.mjs';
import {runProcess} from '../connectors/process-runner.mjs';
import {createRemindersConnector} from '../connectors/reminders.mjs';
import {createSlackConnector} from '../connectors/slack.mjs';
import {assertOperation, isAutomationActive, operationKey, validateProfile} from '../domain.mjs';
import {planDay} from '../planner/planning.mjs';
import {applyApprovedOperations, previewOperations} from '../reconciliation/operations.mjs';
import {openDatabase, operationRepository, planRepository, taskRepository} from '../storage/database.mjs';
import {applicationSupportDirectory} from '../storage/paths.mjs';
import {protectedForMidday} from '../scheduler/bounded-routines.mjs';
import {evaluateCatchUp} from '../scheduler/catch-up.mjs';
import {projectTodayView} from '../views/today-view.mjs';
import {ApiError, sanitize} from './auth.mjs';
import {cleanupPluginItems} from './cleanup.mjs';

const VERSION = '0.0.0';
const systems = ['jira', 'calendar', 'reminders', 'slack'];
const autoKinds = new Set(['calendar_upsert', 'calendar_delete', 'reminder_upsert', 'reminder_complete', 'reminder_delete']);

function json(value) { return JSON.stringify(value); }
function parse(value, fallback = null) { try { return JSON.parse(value); } catch { return fallback; } }
function localDate(now, timezone) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts(now).filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

function preferenceStore(db, now) {
  return {
    get(key) { const row = db.prepare('select value_json from preferences where key = ?').get(key); return row ? parse(row.value_json) : null; },
    set(key, value) { db.prepare('insert into preferences (key, value_json, updated_at) values (?, ?, ?) on conflict(key) do update set value_json = excluded.value_json, updated_at = excluded.updated_at').run(key, json(value), now().toISOString()); return structuredClone(value); },
    entries() { return db.prepare('select key, value_json from preferences order by key').all().map(row => [row.key, parse(row.value_json)]); },
  };
}

function auditStore(db, now) {
  return {
    append(event, entityType, entityId, data = {}) { db.prepare('insert into audit_log (occurred_at, event, entity_type, entity_id, data_json) values (?, ?, ?, ?, ?)').run(now().toISOString(), event, entityType, String(entityId), json(sanitize(data))); },
    list(limit = 100) { const bounded = Number.isInteger(limit) ? Math.min(Math.max(limit, 1), 500) : 100; return db.prepare('select id, occurred_at, event, entity_type, entity_id, data_json from audit_log order by id desc limit ?').all(bounded).map(row => sanitize({id: row.id, occurredAt: row.occurred_at, event: row.event, entityType: row.entity_type, entityId: row.entity_id, data: parse(row.data_json, {})})); },
  };
}

function routineStore(db, now) {
  return {
    async evaluate(kind, instant) {
      if (kind !== 'catch-up') {
        const row = db.prepare("select completed_at from routine_runs where routine = ? and state = 'completed' order by completed_at desc limit 1").get(kind);
        return row?.completed_at?.slice(0, 10) === instant.toISOString().slice(0, 10) ? {shouldRun: false, catchUp: false} : {shouldRun: true, catchUp: false};
      }
      const row = db.prepare("select completed_at from routine_runs where state = 'completed' order by completed_at desc limit 1").get();
      return evaluateCatchUp({lastCompletedAt: row?.completed_at ?? null, now: instant.toISOString(), intervalMinutes: 15});
    },
    async begin(kind, instant, due) { const id = randomUUID(); db.prepare('insert into routine_runs (id, routine, state, started_at, completed_at, data_json) values (?, ?, ?, ?, null, ?)').run(id, kind, 'running', instant.toISOString(), json({catchUp: due.catchUp === true})); return id; },
    async complete(id, state, data) { db.prepare('update routine_runs set state = ?, completed_at = ?, data_json = ? where id = ?').run(state, now().toISOString(), json(sanitize(data)), id); },
  };
}

function delegationTask(item, now) {
  return {schemaVersion: 1, id: `delegation:${item.delegationId}`, sourceType: 'delegation', lane: 'provisional', title: item.title, projectKey: 'unlinked', issueType: 'Delegation', assigneeAccountId: null, priority: item.priority, dueDate: item.dueDate, status: 'Needs Jira', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: null, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: now().toISOString(), reserved: false, sourceRevision: item.delegationId, delegationId: item.delegationId};
}

function defaultRegistry({preferences, keychain, transport, now}) {
  let cachedProfile; let cachedConfig; let cached;
  return {
    async get() {
      const profile = preferences.get('profile'); const config = preferences.get('connector_config') ?? {};
      if (!profile) return {};
      const signature = json([profile, config]);
      if (signature === cachedProfile && cached) return cached;
      cachedProfile = signature; cachedConfig = config;
      cached = {
        jira: createJiraConnector({baseUrl: profile.jira.baseUrl, accountId: profile.jira.accountId, projectKeys: profile.jira.projects, issueTypes: profile.jira.issueTypes, credentials: keychain, transport}),
        calendar: createGoogleCalendarConnector({readCalendarIds: profile.calendar.readCalendarIds, focusCalendarId: profile.calendar.focusCalendarId, credentials: keychain, transport, now, redactOutsideTitles: profile.calendar.redactOutsideTitles}),
        reminders: createRemindersConnector({helperPath: config.remindersHelperPath ?? fileURLToPath(new URL('../../../native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper', import.meta.url)), tasksListId: profile.reminders.tasksListId}),
      };
      if (config.slack?.workspaceId && config.slack?.channelId && Array.isArray(config.slack.senderIds)) cached.slack = createSlackConnector({...config.slack, credentials: keychain, transport});
      return cached;
    },
  };
}

async function googleCalendarCleanup({keys, profile, keychain, transport}) {
  if (keys.length === 0) return 0;
  const [client_id, client_secret, refresh_token] = await Promise.all(['client-id', 'client-secret', 'refresh-token'].map(account => keychain.get('media.rhize.tasks.google', account)));
  const tokenResponse = await transport({url: 'https://oauth2.googleapis.com/token', method: 'POST', headers: {'content-type': 'application/x-www-form-urlencoded'}, body: new URLSearchParams({client_id, client_secret, refresh_token, grant_type: 'refresh_token'}).toString()});
  if (tokenResponse?.status < 200 || tokenResponse?.status >= 300 || typeof tokenResponse?.body?.access_token !== 'string') throw new Error('cleanup_unavailable');
  const headers = {authorization: `Bearer ${tokenResponse.body.access_token}`};
  const findMatches = async key => {
    let pageToken = ''; const seen = new Set(); const matches = new Set();
    for (let page = 0; page < 100; page += 1) {
      const query = new URLSearchParams({privateExtendedProperty: `rhizeOperationKey=${key}`, singleEvents: 'true', maxResults: '250', ...(pageToken ? {pageToken} : {})});
      const response = await transport({url: `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(profile.calendar.focusCalendarId)}/events?${query}`, method: 'GET', headers});
      if (response?.status < 200 || response?.status >= 300 || !Array.isArray(response?.body?.items)) throw new Error('cleanup_unavailable');
      for (const event of response.body.items) if (event?.extendedProperties?.private?.rhizeOperationKey === key && typeof event.id === 'string' && event.id) matches.add(event.id); else throw new Error('cleanup_unverified');
      pageToken = response.body.nextPageToken ?? '';
      if (!pageToken) break;
      if (typeof pageToken !== 'string' || seen.has(pageToken)) throw new Error('cleanup_unverified'); seen.add(pageToken);
      if (page === 99) throw new Error('cleanup_unverified');
    }
    return [...matches];
  };
  let deleted = 0;
  for (const key of keys) {
    const matches = await findMatches(key);
    for (const id of matches) {
      const response = await transport({url: `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(profile.calendar.focusCalendarId)}/events/${encodeURIComponent(id)}`, method: 'DELETE', headers, expectJson: false});
      if (response?.status < 200 || response?.status >= 300) throw new Error('cleanup_unavailable'); deleted += 1;
    }
    if ((await findMatches(key)).length !== 0) throw new Error('cleanup_unverified');
  }
  return deleted;
}

function generatedOperations(plan, profile, freshness, now) {
  const healthy = system => freshness[system]?.status === 'healthy'; const values = [];
  for (const block of plan.blocks) {
    const payload = {calendarId: profile.calendar.focusCalendarId, title: 'Rhize Focus', start: block.start, end: block.end, description: `Rhize task ${block.taskId}`, externalId: block.id};
    const key = operationKey(plan.planRevision, 'calendar_upsert', block.id, payload);
    values.push({schemaVersion: 1, id: `calendar:${key.slice(0, 24)}`, planRevision: plan.planRevision, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: block.id, payload, idempotencyKey: key, approval: healthy('calendar') ? 'approved' : 'required', preconditionRevision: null, retryState: 'pending', createdAt: now});
  }
  for (const taskId of new Set(plan.blocks.map(block => block.taskId))) {
    const task = plan.__tasks.find(item => item.id === taskId); const payload = {listId: profile.reminders.tasksListId, title: task.title, dueAt: null, notes: '', externalId: task.id};
    const key = operationKey(plan.planRevision, 'reminder_upsert', task.id, payload);
    values.push({schemaVersion: 1, id: `reminder:${key.slice(0, 24)}`, planRevision: plan.planRevision, kind: 'reminder_upsert', targetSystem: 'reminders', targetId: task.id, payload, idempotencyKey: key, approval: healthy('reminders') ? 'approved' : 'required', preconditionRevision: null, retryState: 'pending', createdAt: now});
  }
  return values;
}

export async function createServiceContext({databasePath, database, keychain, connectors, connectorFactory, transport = createHttpTransport(), now = () => new Date(), host = '127.0.0.1', port = 43179, lockPath} = {}) {
  const db = database ?? openDatabase(databasePath);
  const preferences = preferenceStore(db, now); const audit = auditStore(db, now);
  const repositories = {tasks: taskRepository(db), plans: planRepository(db), operations: operationRepository(db), preferences, audit};
  const credentialStore = keychain ?? createKeychain({spawnFile: runProcess});
  const injectedRegistry = connectors ? {async get() { return connectors; }} : connectorFactory ? {async get() { return connectorFactory(preferences.get('profile')); }} : defaultRegistry({preferences, keychain: credentialStore, transport, now});
  const activation = {async canActivate() { const value = preferences.get('profile'); return Boolean(value && isAutomationActive(value) && Number.isInteger(preferences.get('approved_plan_revision'))); }};
  const pause = {async isPaused() { return preferences.get('profile')?.approval?.automationPaused === true || preferences.get('paused') === true; }};
  const sync = {async readAll() {
    const registry = await injectedRegistry.get(); const previous = preferences.get('connector_freshness') ?? {}; const freshness = {}; const offlineSystems = []; let protectedIntervals = preferences.get('last_protected_intervals') ?? [];
    for (const system of systems) {
      const connector = registry[system];
      if (!connector || typeof connector.readSnapshot !== 'function') { freshness[system] = {status: 'offline', freshAt: previous[system]?.freshAt ?? null}; offlineSystems.push(system); continue; }
      try {
        const snapshot = await connector.readSnapshot(); const instant = now().toISOString(); freshness[system] = {status: 'healthy', freshAt: instant};
        if (system === 'jira') for (const item of snapshot) repositories.tasks.upsert(item);
        if (system === 'slack') for (const item of snapshot) repositories.tasks.upsert(delegationTask(item, now));
        if (system === 'calendar') { protectedIntervals = snapshot.map(item => ({id: item.id, start: item.start, end: item.end, kind: item.calendarId === preferences.get('profile')?.calendar?.focusCalendarId ? 'fixed' : 'outside', sourceSystem: 'calendar', mutable: false})); preferences.set('last_protected_intervals', protectedIntervals); }
      } catch (error) { const status = error?.kind === 'authorization' ? 'revoked' : 'offline'; freshness[system] = {status, freshAt: previous[system]?.freshAt ?? null}; offlineSystems.push(system); }
    }
    preferences.set('connector_freshness', freshness);
    return {tasks: repositories.tasks.list(), protectedIntervals, freshness, offlineSystems};
  }};

  async function persistPreview({baseRevision, planningDate, sourceRevision, proposedOperations, snapshot, kind = 'preview'}) {
    const latest = repositories.plans.latest(); const current = latest?.planRevision ?? 0;
    if (baseRevision !== current) throw new RangeError('plan revision conflict');
    const profile = preferences.get('profile'); if (!profile) throw new ApiError('preferences_required', 409); validateProfile(profile);
    const source = snapshot ?? await sync.readAll();
    const preserved = kind === 'midday' && latest ? protectedForMidday(latest, preferences.get('block_states') ?? {}, now().toISOString(), profile.planning.freezeWindowMinutes) : [];
    const plan = planDay({tasks: source.tasks, protectedIntervals: [...source.protectedIntervals, ...preserved], profile, planningDate, now: now().toISOString(), planRevision: current + 1});
    Object.defineProperty(plan, '__tasks', {value: source.tasks, configurable: true});
    let candidates = proposedOperations;
    if (candidates === undefined) candidates = generatedOperations(plan, profile, source.freshness, now().toISOString());
    const active = await activation.canActivate();
    candidates = candidates.map(candidate => { assertOperation(candidate); const approval = !active || !autoKinds.has(candidate.kind) || source.offlineSystems.includes(candidate.targetSystem) ? 'required' : candidate.approval; return {...candidate, approval}; });
    const preview = previewOperations(plan, {sourceRevision, proposedOperations: candidates});
    delete plan.__tasks; repositories.plans.save(plan); for (const operation of preview.operations) repositories.operations.save(operation);
    audit.append('plan_previewed', 'plan', plan.planRevision, {sourceRevision, operationIds: preview.operations.map(item => item.id), kind});
    return {...plan, operations: preview.operations, approvalsRequired: preview.approvalsRequired, freshness: source.freshness};
  }

  async function approvePlan(revision, actor, apply) {
    const plan = repositories.plans.latest(); if (!plan || plan.planRevision !== revision) throw new RangeError('plan revision conflict');
    const already = preferences.get('approved_plan_revision') === revision;
    const operations = repositories.operations.listForPlan(revision);
    if (!already) {
      for (const operation of operations) if (operation.approval === 'required') repositories.operations.setApproval(operation.id, 'approved', actor);
      const profile = preferences.get('profile'); preferences.set('profile', {...profile, approval: {...profile.approval, firstPlanApproved: true}}); preferences.set('approved_plan_revision', revision); audit.append('plan_approved', 'plan', revision, {actor, operationIds: operations.map(item => item.id)});
    }
    let results = [];
    if (apply && !await pause.isPaused()) results = await applyApprovedOperations({repository: repositories.operations, connectors: await injectedRegistry.get(), currentRevision: revision}, repositories.operations.listForPlan(revision));
    return {planRevision: revision, approved: true, results};
  }

  const plans = {
    preview: persistPreview,
    approve: approvePlan,
    async reconcileAndPlan({kind, snapshot, now: instant}) {
      const profile = preferences.get('profile'); const planningDate = localDate(instant, profile.identity.timezone); const latest = repositories.plans.latest();
      const result = await persistPreview({baseRevision: latest?.planRevision ?? 0, planningDate, sourceRevision: `${kind}:${instant.toISOString()}`, proposedOperations: undefined, snapshot, kind});
      const applicable = result.operations.filter(operation => operation.approval === 'approved' && !snapshot.offlineSystems.includes(operation.targetSystem));
      const writes = applicable.length ? await applyApprovedOperations({repository: repositories.operations, connectors: await injectedRegistry.get(), currentRevision: result.planRevision}, applicable) : [];
      return {state: 'planned', planRevision: result.planRevision, writes, writesPausedFor: snapshot.offlineSystems};
    },
  };
  const routineState = routineStore(db, now);
  return {
    version: VERSION, host, port, db, repositories, keychain: credentialStore, connectorRegistry: injectedRegistry, activation, pause, sync, plans, routineState, lockPath: lockPath ?? `${applicationSupportDirectory()}/routine.lock`, now,
    auth: {getToken: () => credentialStore.get('media.rhize.tasks.api', 'bearer')},
    close() { db.close(); },
    async today() { const plan = repositories.plans.latest(); if (!plan) throw new ApiError('plan_not_found', 404); return projectTodayView({plan, tasks: repositories.tasks.list(), operations: repositories.operations.listForPlan(plan.planRevision), profile: preferences.get('profile'), freshness: preferences.get('connector_freshness') ?? {}, approvedOutsideLabels: preferences.get('outside_labels') ?? {}, now: now().toISOString()}); },
    async doctor() { const registry = await injectedRegistry.get(); const connectorStatus = {}; for (const system of systems) { try { connectorStatus[system] = registry[system] && await registry[system].health() ? 'healthy' : 'offline'; } catch (error) { connectorStatus[system] = error?.kind === 'authorization' ? 'revoked' : 'offline'; } } return {version: VERSION, database: 'ready', activation: await activation.canActivate(), paused: await pause.isPaused(), connectors: connectorStatus}; },
    async cleanup(request) { const profile = preferences.get('profile'); const records = db.prepare('select data_json, attempt_count from operations order by id').all().map(row => ({...parse(row.data_json), attemptCount: row.attempt_count})); const registry = await injectedRegistry.get(); return cleanupPluginItems({request, profile, operations: records, connectors: registry, calendarCleanup: keys => googleCalendarCleanup({keys, profile, keychain: credentialStore, transport})}); },
  };
}
