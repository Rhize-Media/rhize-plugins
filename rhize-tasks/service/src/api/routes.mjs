import {operationKey, validateProfile} from '../domain.mjs';
import {applyApprovedOperations} from '../reconciliation/operations.mjs';
import {ApiError, exactObject, readJson, requireBearer, sanitize} from './auth.mjs';

const accounts = Object.freeze({api: ['bearer'], jira: ['email', 'api-token'], google: ['client-id', 'client-secret', 'refresh-token'], slack: ['bot-token']});
const services = Object.freeze({api: 'media.rhize.tasks.api', jira: 'media.rhize.tasks.jira', google: 'media.rhize.tasks.google', slack: 'media.rhize.tasks.slack'});
const mutation = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

function response(status, body) { return {status, body}; }
function currentRevision(context) { return context.repositories.plans.latest()?.planRevision ?? 0; }
function revision(value, context) { if (!Number.isInteger(value) || value < 0 || value !== currentRevision(context)) throw new ApiError('revision_conflict', 409); }
function actor(value) { if (typeof value !== 'string' || !value.trim()) throw new ApiError('invalid_actor'); return value; }
function planningDate(value) { if (value === undefined) return undefined; const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value); if (!match) throw new ApiError('invalid_planning_date'); const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]))); if (date.getUTCFullYear() !== Number(match[1]) || date.getUTCMonth() !== Number(match[2]) - 1 || date.getUTCDate() !== Number(match[3])) throw new ApiError('invalid_planning_date'); return value; }
function discoveryResources(connector, value) { if (connector === 'reminders') return {lists: (value?.lists ?? []).filter(item => typeof item?.id === 'string' && item.id).map(item => ({id: item.id, name: typeof item.name === 'string' ? item.name : typeof item.title === 'string' ? item.title : ''}))}; return value; }
function safeSetupData(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new ApiError('invalid_setup_data');
  if (Object.keys(value).some(key => /token|secret|password|credential|authorization/i.test(key))) throw new ApiError('credential_field_not_allowed');
  return sanitize(value);
}

async function jsonBody(request, keys, options) { return exactObject(await readJson(request), keys, options); }

export function createRouter(context) {
  if (!context?.auth?.getToken || !context.repositories || !context.plans) throw new TypeError('invalid_server_context');
  return async request => {
    const url = new URL(request.url, 'http://127.0.0.1'); const pathname = url.pathname; const method = request.method ?? 'GET';
    if (pathname === '/health') {
      if (method !== 'GET') throw new ApiError('method_not_allowed', 405);
      return response(200, {version: context.version, status: 'ok'});
    }
    if (pathname === '/session') {
      if (method !== 'GET' || [...url.searchParams.keys()].some(key => key !== 'nonce') || url.searchParams.getAll('nonce').length !== 1) throw new ApiError('invalid_session_nonce', 401);
      const cookie = context.sessions.exchange(url.searchParams.get('nonce'));
      return {status: 303, body: {ok: true}, headers: {'set-cookie': cookie, location: '/'}};
    }
    if (!pathname.startsWith('/v1/')) throw new ApiError('not_found', 404);
    if (!context.sessions?.authenticate(request)) await requireBearer(request, context.auth.getToken);
    if (!['GET', 'POST', 'PUT'].includes(method)) throw new ApiError('method_not_allowed', 405);

    if (method === 'GET' && pathname === '/v1/today') return response(200, await context.today());
    if (method === 'GET' && pathname === '/v1/preferences') return response(200, {planRevision: currentRevision(context), profile: context.repositories.preferences.get('profile'), connectorConfig: context.repositories.preferences.get('connector_config')});
    if (method === 'GET' && pathname === '/v1/audit') return response(200, {entries: context.repositories.audit.list(Number(url.searchParams.get('limit') ?? 100))});
    if (method === 'GET' && pathname === '/v1/doctor') return response(200, await context.doctor());
    if (method === 'GET' && pathname === '/v1/setup/status') return response(200, {planRevision: currentRevision(context), stages: context.repositories.preferences.get('setup_stages') ?? {}, scopePreviews: Object.values(context.repositories.preferences.get('setup_scope_previews') ?? {}).map(item => ({operation: item.operation, scope: item.scope})), approvedScopes: context.repositories.preferences.get('approved_setup_scopes') ?? {}});
    if (method === 'GET' && pathname === '/v1/opportunities') return response(200, {planRevision: currentRevision(context), opportunities: (await context.today()).opportunities});

    const discover = /^\/v1\/setup\/discover\/(jira|calendar|reminders|slack)$/.exec(pathname);
    if (method === 'GET' && discover) { const connector = await context.connectorRegistry.getDiscovery(discover[1]); if (!connector?.discover) throw new ApiError('connector_unavailable', 503); return response(200, {connector: discover[1], resources: discoveryResources(discover[1], await connector.discover())}); }

    if (method === 'PUT' && pathname === '/v1/preferences') {
      const body = await jsonBody(request, ['planRevision', 'profile']); revision(body.planRevision, context); validateProfile(body.profile);
      const result = await context.settings.proposeProfile(body.profile);
      return response(result.status === 'approval_required' ? 202 : 200, {planRevision: body.planRevision, saved: result.status === 'saved', approvalRequired: result.status === 'approval_required', operationIds: result.operations.map(operation => operation.id), activationReady: await context.activation.canActivate()});
    }

    if (method === 'POST' && pathname === '/v1/setup/connectors') {
      const body = await jsonBody(request, ['planRevision', 'connector', 'scope']); revision(body.planRevision, context);
      const result = await context.settings.previewSetupScope(body); return response(201, result);
    }

    if (method === 'PUT' && pathname === '/v1/setup/connectors') {
      const body = await jsonBody(request, ['planRevision', 'connector', 'scope', 'apply']); revision(body.planRevision, context);
      if (body.connector !== 'slack' || body.apply !== true) throw new ApiError('invalid_connector_config');
      const result = await context.settings.proposeConnectorConfig({slack: body.scope});
      return response(200, {planRevision: body.planRevision, saved: result.status === 'saved', connector: 'slack', scope: body.scope});
    }

    if (method === 'POST' && pathname === '/v1/setup/probe') {
      const body = await readJson(request); exactObject(body, body?.mode === 'preview' ? ['planRevision', 'mode', 'remindersListId', 'focusCalendarId'] : ['planRevision', 'mode', 'probeId', 'actor']); revision(body.planRevision, context);
      if (body.mode === 'preview') return response(201, context.setupProbe.preview(body));
      if (body.mode === 'apply') return response(200, await context.setupProbe.apply({planRevision: body.planRevision, probeId: body.probeId, actor: actor(body.actor)}));
      throw new ApiError('invalid_setup_probe');
    }

    if (method === 'POST' && pathname === '/v1/plans/preview') {
      const body = await jsonBody(request, ['planRevision', 'planningDate'], {required: ['planRevision']}); revision(body.planRevision, context);
      const plan = await context.plans.preview({baseRevision: body.planRevision, planningDate: planningDate(body.planningDate)}); return response(201, plan);
    }

    const planApproval = /^\/v1\/plans\/([1-9][0-9]*)\/approve$/.exec(pathname);
    if (method === 'POST' && planApproval) {
      const body = await jsonBody(request, ['actor', 'apply']); exactObject(body, ['actor', 'apply']); if (typeof body.apply !== 'boolean') throw new ApiError('invalid_apply');
      return response(200, await context.plans.approve(Number(planApproval[1]), actor(body.actor), body.apply));
    }

    const operationApproval = /^\/v1\/operations\/([^/]+)\/approve$/.exec(pathname);
    if (method === 'POST' && operationApproval) {
      const body = await jsonBody(request, ['planRevision', 'actor']); revision(body.planRevision, context); const approvedBy = actor(body.actor); const id = decodeURIComponent(operationApproval[1]); let operation = context.repositories.operations.get(id); if (!operation) { const setup = await context.settings.approveSetupScope(id, approvedBy); if (setup) return response(200, setup); throw new ApiError('operation_not_found', 404); }
      if (operation.kind === 'scope_expand') return response(200, await context.settings.approveScope(id, approvedBy));
      if (operation.approval === 'required') operation = context.repositories.operations.setApproval(id, 'approved', approvedBy);
      context.repositories.audit.append('operation_approved_via_api', 'operation', id, {actor: body.actor, planRevision: body.planRevision});
      if (await context.pause.isPaused()) return response(202, {operationId: id, state: 'approved_deferred', reason: 'paused'});
      const freshness = context.repositories.preferences.get('connector_freshness') ?? {}; if (freshness[operation.targetSystem]?.status && freshness[operation.targetSystem].status !== 'healthy') return response(202, {operationId: id, state: 'approved_deferred', reason: 'connector_unavailable'});
      const {applyApprovedOperations} = await import('../reconciliation/operations.mjs'); const [result] = await applyApprovedOperations({repository: context.repositories.operations, connectors: await context.connectorRegistry.get(), currentRevision: body.planRevision}, [operation]); return response(200, result);
    }

    if (method === 'POST' && pathname === '/v1/reconcile') {
      const body = await jsonBody(request, ['planRevision', 'operationIds', 'actor']); revision(body.planRevision, context); const requestedBy = actor(body.actor);
      if (!Array.isArray(body.operationIds) || body.operationIds.length === 0 || body.operationIds.some(id => typeof id !== 'string' || id.length === 0) || new Set(body.operationIds).size !== body.operationIds.length) throw new ApiError('invalid_operation_ids');
      if (await context.pause.isPaused()) throw new ApiError('automation_paused', 409);
      const operations = body.operationIds.map(id => context.repositories.operations.get(id));
      if (operations.some(value => !value)) throw new ApiError('operation_not_found', 404);
      if (operations.some(value => value.planRevision !== body.planRevision || value.retryState !== 'reconciliation_required' || value.approval !== 'approved')) throw new ApiError('operation_not_reconcilable', 409);
      const connectors = await context.connectorRegistry.get();
      for (const system of new Set(operations.map(value => value.targetSystem).filter(value => value !== 'local'))) {
        const connector = connectors?.[system];
        if (!connector || typeof connector.health !== 'function') throw new ApiError('connector_unavailable', 503);
        try { const health = await connector.health(); if (health?.ok !== true) throw new Error('unhealthy'); } catch { throw new ApiError('connector_unavailable', 503); }
      }
      let authority;
      try { authority = context.repositories.operations.resumeReconciliations({operations, actor: requestedBy, planRevision: body.planRevision}); }
      catch (error) { if (error?.kind === 'revision_conflict') throw new ApiError('revision_conflict', 409); if (error?.kind === 'automation_paused') throw new ApiError('automation_paused', 409); if (error?.kind === 'operation_not_reconcilable') throw new ApiError('operation_not_reconcilable', 409); throw error; }
      const results = await applyApprovedOperations({repository: context.repositories.operations, connectors, currentRevision: authority.planRevision}, authority.operations); return response(200, {results});
    }

    const claim = /^\/v1\/opportunities\/([^/]+)\/claim$/.exec(pathname);
    if (method === 'POST' && claim) {
      const body = await jsonBody(request, ['planRevision', 'actor', 'accountId']); revision(body.planRevision, context); actor(body.actor); if (typeof body.accountId !== 'string' || !body.accountId) throw new ApiError('invalid_account');
      const task = context.repositories.tasks.get(decodeURIComponent(claim[1])); if (!task || task.lane !== 'opportunity' || !task.jiraKey) throw new ApiError('opportunity_not_found', 404);
      const payload = {accountId: body.accountId}; const key = operationKey(body.planRevision, 'jira_assign', task.jiraKey, payload); const value = {schemaVersion: 1, id: `claim:${key.slice(0, 24)}`, planRevision: body.planRevision, kind: 'jira_assign', targetSystem: 'jira', targetId: task.jiraKey, payload, idempotencyKey: key, approval: 'required', preconditionRevision: task.sourceRevision, retryState: 'pending', createdAt: context.now().toISOString()}; context.repositories.operations.save(value); context.repositories.operations.setApproval(value.id, 'approved', body.actor); context.repositories.audit.append('opportunity_claim_approved', 'task', task.id, {operationId: value.id, actor: body.actor});
      if (await context.pause.isPaused()) return response(202, {operationId: value.id, state: 'approved_deferred'});
      const {applyApprovedOperations} = await import('../reconciliation/operations.mjs'); const [result] = await applyApprovedOperations({repository: context.repositories.operations, connectors: await context.connectorRegistry.get(), currentRevision: body.planRevision}, [{...value, approval: 'approved'}]); return response(200, result);
    }

    if (method === 'POST' && pathname === '/v1/pause') {
      const body = await jsonBody(request, ['planRevision', 'paused']); revision(body.planRevision, context); if (typeof body.paused !== 'boolean') throw new ApiError('invalid_pause'); const profile = context.repositories.preferences.get('profile'); if (profile) context.repositories.preferences.set('profile', {...profile, approval: {...profile.approval, automationPaused: body.paused}}); context.repositories.preferences.set('paused', body.paused); context.repositories.audit.append(body.paused ? 'automation_paused' : 'automation_resumed', 'service', 'local', {planRevision: body.planRevision}); return response(200, {paused: body.paused});
    }

    const stage = /^\/v1\/setup\/stages\/([1-7])$/.exec(pathname);
    if (method === 'PUT' && stage) {
      const body = await jsonBody(request, ['planRevision', 'complete', 'data']); revision(body.planRevision, context); if (typeof body.complete !== 'boolean') throw new ApiError('invalid_stage'); const stages = context.repositories.preferences.get('setup_stages') ?? {}; stages[stage[1]] = {complete: body.complete, data: safeSetupData(body.data)}; context.repositories.preferences.set('setup_stages', stages); context.repositories.audit.append('setup_stage_saved', 'setup', stage[1], {complete: body.complete}); return response(200, {stage: Number(stage[1]), complete: body.complete});
    }

    if (method === 'POST' && pathname === '/v1/setup/credentials') {
      const body = await jsonBody(request, ['planRevision', 'connector', 'values']); revision(body.planRevision, context); if (!accounts[body.connector]) throw new ApiError('invalid_connector'); exactObject(body.values, accounts[body.connector]);
      for (const account of accounts[body.connector]) { const value = body.values[account]; if (typeof value !== 'string' || !value) throw new ApiError('invalid_credential'); await context.keychain.set(services[body.connector], account, value); }
      context.repositories.audit.append('credentials_saved', 'connector', body.connector, {accounts: accounts[body.connector].length}); return response(200, {connector: body.connector, saved: true});
    }

    if (mutation.has(method)) throw new ApiError('not_found', 404);
    throw new ApiError('not_found', 404);
  };
}
