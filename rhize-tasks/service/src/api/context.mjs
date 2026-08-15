import {randomBytes, randomUUID} from 'node:crypto';
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
import {localDate as localDateInZone, selectDuePhase} from '../scheduler/catch-up.mjs';
import {projectTodayView} from '../views/today-view.mjs';
import {ApiError, sanitize} from './auth.mjs';
import {cleanupPluginItems} from './cleanup.mjs';
import {connectorScopeChanges, planningMaterialChanged, profileScopeChanges, profileSetupScopes, scopeOperations, scopeResourceIds, setupScopeCovered, validateConnectorConfig, validateDiscoveredScope, validateSetupScope} from './preferences.mjs';
import {createSessionAuthority} from './sessions.mjs';
import {createSetupProbeAuthority} from './setup-probe.mjs';

const VERSION = '0.0.0';
const systems = ['jira', 'calendar', 'reminders', 'slack'];
const autoKinds = new Set(['calendar_upsert', 'calendar_delete', 'reminder_upsert', 'reminder_complete', 'reminder_delete']);

function json(value) { return JSON.stringify(value); }
function parse(value, fallback = null) { try { return JSON.parse(value); } catch { return fallback; } }
function addLocalDays(date, count) { const [year, month, day] = date.split('-').map(Number); const value = new Date(Date.UTC(year, month - 1, day + count)); return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, '0')}-${String(value.getUTCDate()).padStart(2, '0')}`; }

function preferenceStore(db, now) {
  return {
    get(key) { const row = db.prepare('select value_json from preferences where key = ?').get(key); return row ? parse(row.value_json) : null; },
    set(key, value) { db.prepare('insert into preferences (key, value_json, updated_at) values (?, ?, ?) on conflict(key) do update set value_json = excluded.value_json, updated_at = excluded.updated_at').run(key, json(value), now().toISOString()); return structuredClone(value); },
    delete(key) { db.prepare('delete from preferences where key = ?').run(key); },
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
      const profile = db.prepare("select value_json from preferences where key = 'profile'").get(); const value = profile ? parse(profile.value_json) : null;
      const rows = db.prepare("select routine, max(completed_at) as completed_at from routine_runs where state = 'completed' group by routine").all(); const lastRuns = Object.fromEntries(rows.map(row => [row.routine, row.completed_at]));
      if (kind === 'catch-up') return selectDuePhase({profile: value, lastRuns, now: instant});
      const last = lastRuns[kind]; const sameLocalDay = last && localDateInZone(new Date(last), value.identity.timezone) === localDateInZone(instant, value.identity.timezone);
      return {shouldRun: !sameLocalDay, catchUp: false, phase: kind, dueAt: null};
    },
    async begin(kind, instant, due) { const id = randomUUID(); db.prepare('insert into routine_runs (id, routine, state, started_at, completed_at, data_json) values (?, ?, ?, ?, null, ?)').run(id, kind, 'running', instant.toISOString(), json({catchUp: due.catchUp === true})); return id; },
    async complete(id, state, data) { db.prepare('update routine_runs set state = ?, completed_at = ?, data_json = ? where id = ?').run(state, now().toISOString(), json(sanitize(data)), id); },
  };
}

function delegationTask(item, now) {
  const jiraKey = item.jira.kind === 'key' ? item.jira.value : item.jira.kind === 'url' ? /\/browse\/([A-Z][A-Z0-9_]*-[1-9][0-9]*)/.exec(item.jira.value)?.[1] : undefined;
  return {schemaVersion: 1, id: `delegation:${item.delegationId}`, sourceType: 'delegation', lane: 'provisional', title: item.title, projectKey: jiraKey?.split('-')[0] ?? 'unlinked', issueType: 'Delegation', assigneeAccountId: null, priority: item.priority, dueDate: item.dueDate, status: item.state === 'needs_jira' ? 'Needs Jira' : 'Jira Linked', terminal: false, blocked: false, dependencyRisk: 0, remainingMinutes: null, explicitEstimateMinutes: null, competencies: [], manualLock: false, carryoverCount: 0, createdAt: now().toISOString(), reserved: false, sourceRevision: item.delegationId, delegationId: item.delegationId, ...(jiraKey ? {jiraKey} : {}), ...(item.jira.kind === 'url' ? {jiraUrl: item.jira.value} : {})};
}

function exactDelegationMatch(tasks, delegationId) {
  const marker = `rhize-delegation:v1:${delegationId}`;
  const matches = tasks.filter(task => task.sourceType === 'jira' && typeof task.description === 'string' && task.description.split(/\r?\n/).some(line => line === marker));
  return matches.length === 1 ? matches[0] : null;
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
        reminders: createRemindersConnector({helperPath: config.remindersHelperPath ?? fileURLToPath(new URL('../../../native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper', import.meta.url)), tasksListId: profile.reminders.tasksListId, awarenessLists: profile.reminders.awarenessLists}),
      };
      if (config.slack?.workspaceId && config.slack?.channelId && Array.isArray(config.slack.senderIds)) cached.slack = createSlackConnector({...config.slack, credentials: keychain, transport});
      return cached;
    },
    async getSetup(connector, scope) {
      const stages = preferences.get('setup_stages') ?? {}; const identity = stages['2']?.data ?? {};
      if (connector === 'jira') return createJiraConnector({baseUrl: identity.jiraBaseUrl, accountId: identity.jiraAccountId, projectKeys: scope.projectKeys, issueTypes: scope.issueTypes, credentials: keychain, transport});
      if (connector === 'calendar') return createGoogleCalendarConnector({readCalendarIds: scope.readCalendarIds, focusCalendarId: scope.focusCalendarId, credentials: keychain, transport, now});
      if (connector === 'reminders') return createRemindersConnector({helperPath: fileURLToPath(new URL('../../../native/RhizeRemindersHelper.app/Contents/MacOS/RhizeRemindersHelper', import.meta.url)), tasksListId: scope.tasksListId, awarenessListIds: scope.awarenessListIds});
      if (connector === 'slack') return createSlackConnector({...scope, credentials: keychain, transport});
      throw new TypeError('invalid setup connector');
    },
    async getSetupProbe(exact) {
      return {calendar: await this.getSetup('calendar', {readCalendarIds: [exact.focusCalendarId], focusCalendarId: exact.focusCalendarId}), reminders: await this.getSetup('reminders', {awarenessListIds: [], tasksListId: exact.remindersListId})};
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
    const key = operationKey(plan.planRevision, 'calendar_upsert', null, payload);
    values.push({schemaVersion: 1, id: `calendar:${key.slice(0, 24)}`, planRevision: plan.planRevision, kind: 'calendar_upsert', targetSystem: 'calendar', targetId: null, payload, idempotencyKey: key, approval: healthy('calendar') ? 'approved' : 'required', preconditionRevision: null, retryState: 'pending', createdAt: now});
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
  let apiToken; let tokenProvisioned = false;
  try { apiToken = await credentialStore.get('media.rhize.tasks.api', 'bearer'); } catch {}
  if (typeof apiToken !== 'string' || apiToken.length < 32) {
    apiToken = randomBytes(32).toString('base64url');
    await credentialStore.set('media.rhize.tasks.api', 'bearer', apiToken);
    tokenProvisioned = true;
  }
  const injectedRegistry = connectors ? {async get() { return connectors; }, async getSetup(name) { return connectors[name]; }, async getSetupProbe() { return connectors; }} : connectorFactory ? {async get() { return connectorFactory(preferences.get('profile')); }, async getSetup(name, scope) { return (await connectorFactory(null, {name, scope}))[name]; }, async getSetupProbe(exact) { return connectorFactory(null, {probe: exact}); }} : defaultRegistry({preferences, keychain: credentialStore, transport, now});
  const activation = {async canActivate() { const value = preferences.get('profile'); return Boolean(value && isAutomationActive(value) && Number.isInteger(preferences.get('approved_plan_revision')) && !preferences.get('pending_scope_change')); }};
  const sessions = createSessionAuthority({preferences, audit, now, port});
  const setupProbe = createSetupProbeAuthority({preferences, audit, connectorRegistry: injectedRegistry, now});
  const pause = {async isPaused() { return preferences.get('profile')?.approval?.automationPaused === true || preferences.get('paused') === true; }};
  const sync = {async readAll() {
    const registry = await injectedRegistry.get(); const previous = preferences.get('connector_freshness') ?? {}; const freshness = {}; const offlineSystems = []; const protectedBySystem = preferences.get('protected_intervals_by_system') ?? {calendar: preferences.get('last_protected_intervals') ?? [], reminders: []};
    for (const system of systems) {
      const connector = registry[system];
      if (!connector || typeof connector.readSnapshot !== 'function') { freshness[system] = {status: 'offline', freshAt: previous[system]?.freshAt ?? null}; offlineSystems.push(system); continue; }
      try {
        const snapshot = await connector.readSnapshot(); const instant = now().toISOString(); freshness[system] = {status: 'healthy', freshAt: instant};
        if (system === 'jira') for (const item of snapshot) repositories.tasks.upsert(item);
        if (system === 'slack') for (const item of snapshot) { const canonical = exactDelegationMatch(repositories.tasks.list(), item.delegationId); if (canonical) { repositories.tasks.upsert({...canonical, delegationId: item.delegationId}); repositories.tasks.remove(`delegation:${item.delegationId}`); } else repositories.tasks.upsert(delegationTask(item, now)); }
        if (system === 'calendar') protectedBySystem.calendar = snapshot.map(item => ({id: item.id, start: item.start, end: item.end, kind: item.calendarId === preferences.get('profile')?.calendar?.focusCalendarId ? 'fixed' : 'outside', sourceSystem: 'calendar', mutable: false}));
        if (system === 'reminders') { const awareness = new Map((preferences.get('profile')?.reminders?.awarenessLists ?? []).map(item => [item.id, item])); const approvedLabels = preferences.get('outside_labels') ?? {}; protectedBySystem.reminders = snapshot.flatMap(item => { const config = awareness.get(item.listId); const start = item.startAt ?? item.dueAt; if (!config || item.completed === true || typeof start !== 'string' || config.protectedDurationMinutes === 0) return []; const end = new Date(Date.parse(start) + config.protectedDurationMinutes * 60_000); if (Number.isNaN(end.getTime())) return []; const id = `reminder:${item.listId}:${item.id}`; if (config.showTitles === true && typeof item.title === 'string' && item.title.trim()) approvedLabels[id] = item.title.trim(); return [{id, start, end: end.toISOString(), kind: 'outside', sourceSystem: 'reminders', mutable: false}]; }); preferences.set('outside_labels', approvedLabels); }
      } catch (error) { const status = error?.kind === 'authorization' ? 'revoked' : 'offline'; freshness[system] = {status, freshAt: previous[system]?.freshAt ?? null}; offlineSystems.push(system); }
    }
    const protectedIntervals = [...(protectedBySystem.calendar ?? []), ...(protectedBySystem.reminders ?? [])]; preferences.set('protected_intervals_by_system', protectedBySystem); preferences.set('last_protected_intervals', protectedIntervals); preferences.set('connector_freshness', freshness);
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
    async reconcileAndPlan({kind, snapshot, now: instant, scheduledAt = instant}) {
      const profile = preferences.get('profile'); const scheduledDate = localDateInZone(scheduledAt, profile.identity.timezone); const planningDate = kind === 'evening' ? addLocalDays(scheduledDate, 1) : localDateInZone(instant, profile.identity.timezone); const latest = repositories.plans.latest();
      if (kind === 'evening') snapshot = {...snapshot, tasks: snapshot.tasks.map(task => task.terminal ? task : {...task, carryoverCount: task.carryoverCount + 1})};
      if (kind === 'evening') for (const task of snapshot.tasks) repositories.tasks.upsert(task);
      const result = await persistPreview({baseRevision: latest?.planRevision ?? 0, planningDate, sourceRevision: `${kind}:${instant.toISOString()}`, proposedOperations: undefined, snapshot, kind});
      const applicable = result.operations.filter(operation => operation.approval === 'approved' && !snapshot.offlineSystems.includes(operation.targetSystem));
      const writes = applicable.length ? await applyApprovedOperations({repository: repositories.operations, connectors: await injectedRegistry.get(), currentRevision: result.planRevision}, applicable) : [];
      return {state: 'planned', planRevision: result.planRevision, writes, writesPausedFor: snapshot.offlineSystems, reconciliation: kind === 'evening' ? 'prompted' : null};
    },
  };
  function applySettings({profile, connectorConfig, material}) {
    if (profile) preferences.set('profile', material ? {...profile, approval: {...profile.approval, firstPlanApproved: false}} : profile);
    if (connectorConfig) preferences.set('connector_config', connectorConfig);
    if (material) preferences.delete('approved_plan_revision');
  }
  async function proposeSettings({profile, connectorConfig}) {
    if (preferences.get('pending_scope_change')) throw new ApiError('scope_change_pending', 409);
    const beforeProfile = preferences.get('profile'); const beforeConfig = preferences.get('connector_config');
    if (profile) validateProfile(profile); if (connectorConfig) validateConnectorConfig(connectorConfig);
    const approvedSetupScopes = preferences.get('approved_setup_scopes') ?? {};
    if (!beforeProfile && profile) for (const [connector, requested] of Object.entries(profileSetupScopes(profile))) if (!setupScopeCovered(connector, approvedSetupScopes[connector], requested)) throw new ApiError('scope_approval_required', 409);
    if (!beforeConfig && connectorConfig?.slack && !setupScopeCovered('slack', approvedSetupScopes.slack, connectorConfig.slack)) throw new ApiError('scope_approval_required', 409);
    const material = profile ? planningMaterialChanged(beforeProfile, profile) : false;
    const normalizedProfile = profile ? {...profile, approval: {...profile.approval, firstPlanApproved: beforeProfile?.approval?.firstPlanApproved === true}} : null;
    const changes = [...(profile ? profileScopeChanges(beforeProfile, normalizedProfile) : []), ...(connectorConfig ? connectorScopeChanges(beforeConfig, connectorConfig) : [])];
    if (changes.length === 0) {
      applySettings({profile: normalizedProfile, connectorConfig, material});
      if (!beforeProfile && profile) for (const connector of ['jira', 'calendar', 'reminders']) delete approvedSetupScopes[connector];
      if (!beforeConfig && connectorConfig?.slack) delete approvedSetupScopes.slack;
      preferences.set('approved_setup_scopes', approvedSetupScopes);
      audit.append('settings_saved', 'profile', 'v1', {material, narrowedOrUnchanged: true});
      return {status: 'saved', material, operations: []};
    }
    const requested = profile ? profileSetupScopes(normalizedProfile) : {slack: connectorConfig.slack};
    for (const {connector} of changes) if (!setupScopeCovered(connector, approvedSetupScopes[connector], requested[connector])) throw new ApiError('scope_approval_required', 409);
    applySettings({profile: normalizedProfile, connectorConfig, material});
    for (const {connector} of changes) delete approvedSetupScopes[connector]; preferences.set('approved_setup_scopes', approvedSetupScopes);
    audit.append('settings_saved', 'profile', 'v1', {material, approvedScopeConnectors: changes.map(change => change.connector)});
    return {status: 'saved', material, operations: []};
  }
  const settings = {
    proposeProfile: profile => proposeSettings({profile, connectorConfig: null}),
    proposeConnectorConfig: connectorConfig => proposeSettings({profile: null, connectorConfig}),
    async previewSetupScope({connector, scope, planRevision}) {
      const selected = validateSetupScope(connector, scope); const setupConnector = await injectedRegistry.getSetup(connector, selected); if (connector === 'slack') await setupConnector.health(); const discovered = await setupConnector.discover(); validateDiscoveredScope(connector, selected, discovered);
      const resources = scopeResourceIds(connector, selected); const revision = Math.max(1, planRevision + 1); const [operation] = scopeOperations({planRevision: revision, changes: [{connector, resourceIds: resources}], now: now().toISOString()});
      const previews = preferences.get('setup_scope_previews') ?? {}; previews[operation.id] = {connector, scope: selected, operation}; preferences.set('setup_scope_previews', previews); audit.append('setup_scope_previewed', 'operation', operation.id, {planRevision, connector, resourceIds: resources});
      return {planRevision, approvalRequired: true, operation, scope: selected};
    },
    async approveSetupScope(operationId, actor) {
      const previews = preferences.get('setup_scope_previews') ?? {}; const preview = previews[operationId]; if (!preview) return null;
      delete previews[operationId]; preferences.set('setup_scope_previews', previews); const approved = preferences.get('approved_setup_scopes') ?? {}; approved[preview.connector] = preview.scope; preferences.set('approved_setup_scopes', approved); audit.append('setup_scope_approved', 'operation', operationId, {actor, connector: preview.connector, resourceIds: scopeResourceIds(preview.connector, preview.scope)});
      return {operationId, state: 'approved_setup_scope', scope: preview.scope};
    },
    async approveScope(operationId, actor) {
      const pending = preferences.get('pending_scope_change');
      if (!pending?.operationIds?.includes(operationId)) throw new ApiError('scope_change_not_found', 404);
      let operation = repositories.operations.get(operationId); if (!operation || operation.kind !== 'scope_expand') throw new ApiError('scope_change_not_found', 404);
      if (operation.approval === 'required') operation = repositories.operations.setApproval(operationId, 'approved', actor);
      const ready = pending.operationIds.every(id => repositories.operations.get(id)?.approval === 'approved');
      if (!ready) return {operationId, state: 'approved_pending_scope'};
      applySettings(pending);
      for (const id of pending.operationIds) repositories.operations.markState(id, 'applied', {reason: null, appliedLocally: true});
      preferences.delete('pending_scope_change');
      audit.append('scope_change_applied', 'plan', operation.planRevision, {operationIds: pending.operationIds});
      return {operationId, state: 'applied', scopeApplied: true, requiresPlanApproval: pending.material};
    },
  };
  const routineState = routineStore(db, now);
  return {
    version: VERSION, host, port, db, repositories, keychain: credentialStore, connectorRegistry: injectedRegistry, activation, pause, sync, plans, settings, sessions, setupProbe, routineState, lockPath: lockPath ?? `${applicationSupportDirectory()}/routine.lock`, now,
    auth: {getToken: () => credentialStore.get('media.rhize.tasks.api', 'bearer'), provisioned: tokenProvisioned},
    close() { db.close(); },
    async today() { const plan = repositories.plans.latest(); if (!plan) throw new ApiError('plan_not_found', 404); return projectTodayView({plan, tasks: repositories.tasks.list(), operations: repositories.operations.listForPlan(plan.planRevision), profile: preferences.get('profile'), freshness: preferences.get('connector_freshness') ?? {}, approvedOutsideLabels: preferences.get('outside_labels') ?? {}, now: now().toISOString()}); },
    async doctor() { const registry = await injectedRegistry.get(); const connectorStatus = {}; for (const system of systems) { try { connectorStatus[system] = registry[system] && await registry[system].health() ? 'healthy' : 'offline'; } catch (error) { connectorStatus[system] = error?.kind === 'authorization' ? 'revoked' : 'offline'; } } return {version: VERSION, database: 'ready', activation: await activation.canActivate(), paused: await pause.isPaused(), connectors: connectorStatus}; },
    async cleanup(request) { const profile = preferences.get('profile'); const records = db.prepare('select data_json, attempt_count from operations order by id').all().map(row => ({...parse(row.data_json), attemptCount: row.attempt_count})); const registry = await injectedRegistry.get(); return cleanupPluginItems({request, profile, operations: records, connectors: registry, calendarCleanup: keys => googleCalendarCleanup({keys, profile, keychain: credentialStore, transport})}); },
  };
}
