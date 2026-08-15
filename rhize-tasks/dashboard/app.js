function copyIntervals(values = []) { return values.map(({dayOfWeek, start, end}) => ({dayOfWeek, start, end})); }
function copyCompetencies(values = []) { return values.map(({name, confidence, excluded}) => ({name, confidence, excluded})); }
function copyStrings(values = []) { return [...values]; }

export function unionCalendarIds(readCalendarIds = [], focusCalendarId) {
  const result = []; const seen = new Set();
  for (const value of [...readCalendarIds, focusCalendarId]) if (typeof value === 'string' && value && !seen.has(value)) { seen.add(value); result.push(value); }
  return result;
}
export function profileToStageData(profile, connectorConfig = null) {
  return {
    2: {...profile.identity, jiraBaseUrl: profile.jira.baseUrl, jiraAccountId: profile.jira.accountId, slackWorkspaceId: connectorConfig?.slack?.workspaceId ?? '', slackChannelId: connectorConfig?.slack?.channelId ?? '', slackSenderIds: copyStrings(connectorConfig?.slack?.senderIds)},
    3: {projects: copyStrings(profile.jira.projects), issueTypes: copyStrings(profile.jira.issueTypes), excludedIssueTypes: copyStrings(profile.jira.excludedIssueTypes), projectImportance: {...profile.jira.projectImportance}, opportunityUrgencyThreshold: profile.jira.opportunityUrgencyThreshold, maxDailySuggestions: profile.jira.maxDailySuggestions, competencies: copyCompetencies(profile.jira.competencies)},
    4: {readCalendarIds: copyStrings(profile.calendar.readCalendarIds), focusCalendarId: profile.calendar.focusCalendarId, redactOutsideTitles: profile.calendar.redactOutsideTitles, awarenessLists: profile.reminders.awarenessLists.map(item => ({...item})), tasksListId: profile.reminders.tasksListId, showOutsideTitles: profile.privacy.showOutsideTitles},
    5: {workingIntervals: copyIntervals(profile.workingIntervals), breaks: copyIntervals(profile.breaks), ...profile.capacity, ...profile.planning},
    6: {...profile.routines},
  };
}
export function profileFromStageData(stages, {setupComplete = false, firstPlanApproved = false, automationPaused = false} = {}) {
  const identity = stages[2]; const jira = stages[3]; const time = stages[4]; const work = stages[5]; const routines = stages[6];
  return {
    schemaVersion: 1,
    identity: {name: identity.name, timezone: identity.timezone, locale: identity.locale},
    jira: {accountId: identity.jiraAccountId, baseUrl: identity.jiraBaseUrl, projects: copyStrings(jira.projects), issueTypes: copyStrings(jira.issueTypes), excludedIssueTypes: copyStrings(jira.excludedIssueTypes), projectImportance: {...jira.projectImportance}, opportunityUrgencyThreshold: jira.opportunityUrgencyThreshold, maxDailySuggestions: jira.maxDailySuggestions, competencies: copyCompetencies(jira.competencies)},
    calendar: {readCalendarIds: unionCalendarIds(time.readCalendarIds, time.focusCalendarId), focusCalendarId: time.focusCalendarId, focusCalendarName: 'Rhize Focus', redactOutsideTitles: time.redactOutsideTitles},
    reminders: {awarenessLists: time.awarenessLists.map(item => ({...item})), tasksListId: time.tasksListId, tasksListName: 'Rhize Tasks'},
    workingIntervals: copyIntervals(work.workingIntervals), breaks: copyIntervals(work.breaks),
    capacity: {bufferPercent: work.bufferPercent, maxDailyMinutes: work.maxDailyMinutes},
    planning: {focusBlockMinutes: work.focusBlockMinutes, minimumBlockMinutes: work.minimumBlockMinutes, allowSplitting: work.allowSplitting, meetingBufferMinutes: work.meetingBufferMinutes, freezeWindowMinutes: work.freezeWindowMinutes},
    routines: {...routines}, approval: {setupComplete, firstPlanApproved, automationPaused}, privacy: {showOutsideTitles: time.showOutsideTitles},
  };
}
export function setupConnectorRequest(planRevision, connector, stages) {
  const identity = stages[2]; const jira = stages[3]; const time = stages[4]; let scope;
  if (connector === 'jira') scope = {projectKeys: copyStrings(jira.projects), issueTypes: copyStrings(jira.issueTypes)};
  else if (connector === 'calendar') scope = {readCalendarIds: unionCalendarIds(time.readCalendarIds, time.focusCalendarId), focusCalendarId: time.focusCalendarId};
  else if (connector === 'reminders') scope = {awarenessListIds: time.awarenessLists.map(item => item.id), tasksListId: time.tasksListId};
  else if (connector === 'slack') scope = {workspaceId: identity.slackWorkspaceId, channelId: identity.slackChannelId, senderIds: copyStrings(identity.slackSenderIds)};
  else throw new TypeError('invalid_connector');
  return {planRevision, connector, scope};
}
export function probePreviewRequest(planRevision, time) { return {planRevision, mode: 'preview', remindersListId: time.tasksListId, focusCalendarId: time.focusCalendarId}; }
export function probeApplyRequest(planRevision, probeId, actor) { return {planRevision, mode: 'apply', probeId, actor}; }
export function planPreviewRequest(planRevision, planningDate) { return planningDate ? {planRevision, planningDate} : {planRevision}; }
export function resumeSetupStages(stages = {}) { return Array.from({length: 7}, (_, index) => { const number = index + 1; const saved = stages[number]; return {number, complete: saved?.complete === true, data: saved?.data ?? {}}; }); }
export async function submitCredentials({connector, fields, planRevision, request}) {
  const values = Object.fromEntries(Object.entries(fields).map(([account, field]) => [account, field.value]));
  if (Object.values(values).some(value => typeof value !== 'string' || !value)) throw new Error(`Complete every ${connector} credential field.`);
  for (const field of Object.values(fields)) field.value = '';
  return request('/v1/setup/credentials', {method: 'POST', body: {planRevision, connector, values}});
}
export function createApiRequest({authState, fetchImpl = globalThis.fetch, onUnauthorized = () => {}, onConflict = async () => {}}) {
  return async (path, options = {}) => {
    const headers = {...(authState.token ? {authorization: `Bearer ${authState.token}`} : {}), ...(options.body ? {'content-type': 'application/json'} : {})};
    const response = await fetchImpl(path, {method: options.method ?? 'GET', credentials: 'same-origin', headers, body: options.body ? JSON.stringify(options.body) : undefined});
    if (response.status === 401) { authState.token = ''; onUnauthorized(); }
    let body; try { body = await response.json(); } catch { throw new Error(`Local service returned HTTP ${response.status}.`); }
    if (response.status === 409) { await onConflict(); throw new Error('The plan changed. The current view was refreshed; review it before trying again.'); }
    if (!response.ok) throw new Error(body?.error?.kind ?? `Local service returned HTTP ${response.status}.`);
    return body;
  };
}

const state = {token: '', planRevision: 0, displayedRevision: 0, paused: false, preview: null, setupScope: null, probe: null, profile: null, connectorConfig: null};
const byId = id => document.getElementById(id);
const status = (id, message) => { byId(id).textContent = message; };

const api = createApiRequest({
  authState: state,
  onUnauthorized() {
    if (typeof document === 'undefined') return;
    byId('api-token').value = '';
    status('service-status', 'Disconnected. The troubleshooting bearer was cleared. Run the installed CLI dashboard command for a fresh one-time local session link.');
  },
  async onConflict() {
    state.preview = null; state.setupScope = null; state.probe = null;
    if (typeof document === 'undefined') return;
    for (const id of ['approve-preview', 'approve-scope', 'approve-sample']) byId(id).disabled = true;
    await refreshToday();
  },
});

function itemText(item) { return item?.title ?? (item?.redacted ? 'Busy (title hidden)' : item?.kind ?? 'None'); }
function fillList(id, values, render, empty = 'None') {
  const list = byId(id); list.replaceChildren();
  if (values.length === 0) { const li = document.createElement('li'); li.textContent = empty; list.append(li); return; }
  for (const value of values) { const li = document.createElement('li'); render(li, value); list.append(li); }
}
function text(li, value) { li.textContent = value; }
function addDecision(li, operation) {
  const summary = document.createElement('span'); summary.textContent = `${operation.title} — ${operation.reason} `; li.append(summary);
  const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Confirm'; button.dataset.operationId = operation.operationId;
  button.addEventListener('click', async () => {
    button.disabled = true;
    try { await api(`/v1/operations/${encodeURIComponent(operation.operationId)}/approve`, {method: 'POST', body: {planRevision: state.displayedRevision, actor: 'dashboard'}}); await refreshToday(); }
    catch (error) { status('plan-status', error.message); }
    finally { button.disabled = false; }
  });
  li.append(button);
}
function addOpportunity(li, item) {
  const summary = document.createElement('span'); summary.textContent = `${item.title} · ${item.priority} · fit ${Math.round(item.fit * 100)}% · ${item.estimateMinutes} min · ${item.rationale} · impact: ${item.impact} `; li.append(summary);
  const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Claim with approval';
  button.addEventListener('click', async () => { const accountId = state.profile?.jira?.accountId; if (!accountId) { status('plan-status', 'Save Tom’s Jira account ID before claiming an opportunity.'); return; } button.disabled = true; try { await api(`/v1/opportunities/${encodeURIComponent(item.taskId)}/claim`, {method: 'POST', body: {planRevision: state.displayedRevision, actor: 'dashboard', accountId}}); await refreshToday(); } catch (error) { status('plan-status', error.message); } finally { button.disabled = false; } }); li.append(button);
}

function renderToday(view) {
  state.planRevision = view.planRevision; state.displayedRevision = view.planRevision; state.paused = view.paused;
  status('plan-status', `Plan revision ${view.planRevision}. ${view.paused ? 'Automation is paused.' : view.degraded ? 'Degraded: unaffected work remains available.' : 'All configured systems are current.'}`);
  byId('current-block').textContent = itemText(view.currentBlock); byId('next-block').textContent = itemText(view.nextBlock);
  byId('capacity').textContent = `${view.capacity.plannedMinutes}/${view.capacity.availableMinutes} minutes planned; ${view.capacity.bufferMinutes} buffered; ${view.capacity.risk} risk.`;
  fillList('timeline', view.timeline, (li, item) => text(li, `${item.start}–${item.end} · ${itemText(item)}${item.redacted ? ' · redacted' : ''}`), 'No scheduled blocks');
  fillList('carryovers', view.carryovers, (li, item) => text(li, `${item.title} · miss ${item.missCount} · ${item.reason} · ${item.resolution}`));
  fillList('approvals', view.approvals, addDecision);
  fillList('opportunities', view.opportunities, addOpportunity);
  fillList('warnings', view.warnings, (li, item) => text(li, `${item.code}: ${item.message}`));
  const connectors = byId('connectors'); connectors.replaceChildren();
  for (const [name, connector] of Object.entries(view.connectors)) { const term = document.createElement('dt'); term.textContent = name; const detail = document.createElement('dd'); detail.textContent = `${connector.status}; ${connector.staleMinutes} minutes stale${connector.freshAt ? `; refreshed ${connector.freshAt}` : ''}`; connectors.append(term, detail); }
  const pause = byId('pause-automation'); pause.disabled = false; pause.textContent = view.paused ? 'Resume automation' : 'Pause automation';
}
async function refreshToday() { try { renderToday(await api('/v1/today')); } catch (error) { status('plan-status', error.message); } }

function lines(value) { return value.split(/\r?\n/).map(item => item.trim()).filter(Boolean); }
function assign(id, value) { if (value !== undefined && value !== null) byId(id).value = String(value); }
function check(id, value) { if (typeof value === 'boolean') byId(id).checked = value; }
function pairs(value, {number = false} = {}) {
  return Object.fromEntries(lines(value).map(item => { const at = item.indexOf('='); if (at < 1) throw new Error('Use name=value on every line.'); const key = item.slice(0, at).trim(); const raw = item.slice(at + 1).trim(); const parsed = number ? Number(raw) : raw; if (!key || (number && !Number.isFinite(parsed))) throw new Error('Invalid name=value entry.'); return [key, parsed]; }));
}
function awareness(value) {
  return lines(value).map(item => { const [id, duration, show] = item.split('|').map(part => part.trim()); const protectedDurationMinutes = Number(duration); if (!id || !Number.isInteger(protectedDurationMinutes) || !['true', 'false'].includes(show)) throw new Error('Reminder awareness lines must use ID|minutes|true-or-false.'); return {id, protectedDurationMinutes, showTitles: show === 'true'}; });
}
const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
function labeledControl(labelText, control) {
  const wrapper = document.createElement('div'); const label = document.createElement('label'); label.htmlFor = control.id; label.textContent = labelText; wrapper.append(label, control); return wrapper;
}
function intervalRows(id) {
  return [...byId(id).querySelectorAll('.interval-row')].map(row => ({
    dayOfWeek: Number(row.querySelector('[data-part="day"]').value),
    start: row.querySelector('[data-part="start"]').value,
    end: row.querySelector('[data-part="end"]').value,
  }));
}
function renderIntervalRows(id, values = [], label = 'Working interval') {
  const container = byId(id); container.replaceChildren();
  values.forEach((value, index) => {
    const row = document.createElement('div'); row.className = 'dynamic-row interval-row';
    const key = `${id}-${index}`;
    const day = document.createElement('select'); day.id = `${key}-day`; day.dataset.part = 'day';
    dayNames.forEach((name, dayIndex) => { const option = document.createElement('option'); option.value = String(dayIndex + 1); option.textContent = name; day.append(option); }); day.value = String(value.dayOfWeek);
    const start = document.createElement('input'); start.id = `${key}-start`; start.dataset.part = 'start'; start.type = 'time'; start.value = value.start;
    const end = document.createElement('input'); end.id = `${key}-end`; end.dataset.part = 'end'; end.type = 'time'; end.value = value.end;
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'remove-row'; remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove ${label.toLowerCase()} ${index + 1}`);
    remove.addEventListener('click', () => { const next = intervalRows(id); next.splice(index, 1); renderIntervalRows(id, next, label); });
    row.append(labeledControl(`${label} ${index + 1} day`, day), labeledControl(`${label} ${index + 1} start`, start), labeledControl(`${label} ${index + 1} end`, end), remove); container.append(row);
  });
}
function competencyRows() {
  return [...byId('competency-rows').querySelectorAll('.competency-row')].map(row => ({
    name: row.querySelector('[data-part="name"]').value.trim(),
    confidence: Number(row.querySelector('[data-part="confidence"]').value),
    excluded: row.querySelector('[data-part="excluded"]').checked,
  }));
}
function renderCompetencyRows(values = []) {
  const container = byId('competency-rows'); container.replaceChildren();
  values.forEach((value, index) => {
    const row = document.createElement('div'); row.className = 'dynamic-row competency-row'; const key = `competency-${index}`;
    const name = document.createElement('input'); name.id = `${key}-name`; name.dataset.part = 'name'; name.value = value.name;
    const confidence = document.createElement('input'); confidence.id = `${key}-confidence`; confidence.dataset.part = 'confidence'; confidence.type = 'number'; confidence.min = '0'; confidence.max = '1'; confidence.step = '0.01'; confidence.value = String(value.confidence);
    const excluded = document.createElement('input'); excluded.id = `${key}-excluded`; excluded.dataset.part = 'excluded'; excluded.type = 'checkbox'; excluded.checked = value.excluded === true;
    const excludedLabel = document.createElement('label'); excludedLabel.className = 'checkbox-label'; excludedLabel.htmlFor = excluded.id; excludedLabel.append(excluded, ' Exclude');
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'remove-row'; remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove competency ${index + 1}`);
    remove.addEventListener('click', () => { const next = competencyRows(); next.splice(index, 1); renderCompetencyRows(next); });
    row.append(labeledControl(`Competency ${index + 1} name`, name), labeledControl(`Competency ${index + 1} confidence`, confidence), excludedLabel, remove); container.append(row);
  });
}
function applyStageData(number, data = {}) {
  if (number === 1) check('safety-confirmed', data.safetyConfirmed);
  if (number === 2) { assign('tom-name', data.name); assign('timezone', data.timezone); assign('locale', data.locale); assign('jira-base-url', data.jiraBaseUrl); assign('jira-account-id', data.jiraAccountId); assign('slack-workspace-id', data.slackWorkspaceId); assign('slack-channel-id', data.slackChannelId); assign('slack-sender-ids', data.slackSenderIds?.join('\n')); }
  if (number === 3) { assign('jira-projects', data.projects?.join('\n')); assign('jira-issue-types', data.issueTypes?.join('\n')); assign('jira-excluded-types', data.excludedIssueTypes?.join('\n')); assign('project-importance', data.projectImportance && Object.entries(data.projectImportance).map(([key, value]) => `${key}=${value}`).join('\n')); if (data.competencies) renderCompetencyRows(data.competencies); assign('urgency-threshold', data.opportunityUrgencyThreshold); assign('max-suggestions', data.maxDailySuggestions); assign('scope-connector', data.scopeConnector); }
  if (number === 4) { assign('calendar-read-ids', data.readCalendarIds?.join('\n')); assign('focus-calendar-id', data.focusCalendarId); check('redact-outside-titles', data.redactOutsideTitles); assign('awareness-lists', data.awarenessLists?.map(item => `${item.id}|${item.protectedDurationMinutes}|${item.showTitles}`).join('\n')); assign('sample-list-id', data.tasksListId); check('show-outside-titles', data.showOutsideTitles); }
  if (number === 5) { if (data.workingIntervals) renderIntervalRows('working-interval-rows', data.workingIntervals, 'Working interval'); if (data.breaks) renderIntervalRows('break-interval-rows', data.breaks, 'Break'); assign('buffer-percent', data.bufferPercent); assign('max-daily-minutes', data.maxDailyMinutes); assign('focus-minutes', data.focusBlockMinutes); assign('minimum-block-minutes', data.minimumBlockMinutes); assign('meeting-buffer-minutes', data.meetingBufferMinutes); assign('freeze-window-minutes', data.freezeWindowMinutes); check('allow-splitting', data.allowSplitting); }
  if (number === 6) { assign('replanning-mode', data.replanningMode); assign('reconciliation-mode', data.reconciliationMode); assign('morning-time', data.morningTime); assign('midday-time', data.middayTime); assign('evening-time', data.eveningTime); }
}
function applyProfile(profile, connectorConfig) {
  if (!profile) return;
  const stages = profileToStageData(profile, connectorConfig);
  for (let number = 2; number <= 6; number += 1) applyStageData(number, stages[number]);
}
async function loadSetup() {
  const [setup, preferences] = await Promise.all([api('/v1/setup/status'), api('/v1/preferences')]); state.planRevision = setup.planRevision; state.profile = preferences.profile; state.connectorConfig = preferences.connectorConfig;
  for (const saved of resumeSetupStages(setup.stages)) { document.querySelector(`[data-stage="${saved.number}"]`).dataset.complete = String(saved.complete); applyStageData(saved.number, saved.data); }
  applyProfile(state.profile, state.connectorConfig);
  status('setup-status', `Setup state loaded at plan revision ${state.planRevision}.`);
}
function stageData(number) {
  if (number === 1) return {safetyConfirmed: byId('safety-confirmed').checked};
  if (number === 2) return {credentialStorage: 'macos_keychain', name: byId('tom-name').value.trim(), timezone: byId('timezone').value.trim() || Intl.DateTimeFormat().resolvedOptions().timeZone, locale: byId('locale').value.trim(), jiraBaseUrl: byId('jira-base-url').value.trim(), jiraAccountId: byId('jira-account-id').value.trim(), slackWorkspaceId: byId('slack-workspace-id').value.trim(), slackChannelId: byId('slack-channel-id').value.trim(), slackSenderIds: lines(byId('slack-sender-ids').value)};
  if (number === 3) return {projects: lines(byId('jira-projects').value), issueTypes: lines(byId('jira-issue-types').value), excludedIssueTypes: lines(byId('jira-excluded-types').value), projectImportance: pairs(byId('project-importance').value, {number: true}), competencies: competencyRows(), opportunityUrgencyThreshold: byId('urgency-threshold').value, maxDailySuggestions: Number(byId('max-suggestions').value), scopeConnector: byId('scope-connector').value};
  if (number === 4) return {readCalendarIds: lines(byId('calendar-read-ids').value), focusCalendarId: byId('focus-calendar-id').value.trim(), redactOutsideTitles: byId('redact-outside-titles').checked, awarenessLists: awareness(byId('awareness-lists').value), tasksListId: byId('sample-list-id').value.trim(), showOutsideTitles: byId('show-outside-titles').checked};
  if (number === 5) return {workingIntervals: intervalRows('working-interval-rows'), breaks: intervalRows('break-interval-rows'), bufferPercent: Number(byId('buffer-percent').value), maxDailyMinutes: Number(byId('max-daily-minutes').value), focusBlockMinutes: Number(byId('focus-minutes').value), minimumBlockMinutes: Number(byId('minimum-block-minutes').value), allowSplitting: byId('allow-splitting').checked, meetingBufferMinutes: Number(byId('meeting-buffer-minutes').value), freezeWindowMinutes: Number(byId('freeze-window-minutes').value)};
  if (number === 6) return {replanningMode: byId('replanning-mode').value, reconciliationMode: byId('reconciliation-mode').value, morningTime: byId('morning-time').value, middayTime: byId('midday-time').value, eveningTime: byId('evening-time').value};
  return {dryRunReviewed: state.preview !== null};
}
async function saveStage(number) {
  const data = stageData(number); if (number === 1 && !data.safetyConfirmed) throw new Error('Confirm the safety boundary before saving stage 1.');
  await api(`/v1/setup/stages/${number}`, {method: 'PUT', body: {planRevision: state.planRevision, complete: true, data}}); document.querySelector(`[data-stage="${number}"]`).dataset.complete = 'true'; status('setup-status', `Stage ${number} saved locally.`);
}

async function saveCredentials(connector) {
  const fields = connector === 'jira' ? {email: 'jira-email', 'api-token': 'jira-token'} : connector === 'google' ? {'client-id': 'google-client-id', 'client-secret': 'google-client-secret', 'refresh-token': 'google-refresh-token'} : {'bot-token': 'slack-bot-token'};
  await submitCredentials({connector, fields: Object.fromEntries(Object.entries(fields).map(([account, id]) => [account, byId(id)])), planRevision: state.planRevision, request: api});
  status('setup-status', `${connector} credentials saved to Keychain; values were cleared from the page.`);
}
async function discover(connector) {
  const result = await api(`/v1/setup/discover/${connector}`); const target = connector === 'jira' ? 'jira-discovery' : 'time-discovery'; byId(target).textContent = JSON.stringify(result.resources, null, 2); status('setup-status', `${connector} discovery complete. Confirm exact resources before saving scope.`);
}
function planningDate() { const timeZone = byId('timezone').value.trim() || Intl.DateTimeFormat().resolvedOptions().timeZone; const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {timeZone, year: 'numeric', month: '2-digit', day: '2-digit'}).formatToParts().filter(part => part.type !== 'literal').map(part => [part.type, part.value])); return `${parts.year}-${parts.month}-${parts.day}`; }
function renderPreviewOperation(li, operation) { li.textContent = `${operation.id} · ${operation.kind} · ${operation.targetSystem} · target ${operation.targetId ?? 'new item'} · ${operation.approval} approval · payload ${JSON.stringify(operation.payload)}`; }
async function preview() {
  const result = await api('/v1/plans/preview', {method: 'POST', body: planPreviewRequest(state.planRevision, planningDate())}); if (!Array.isArray(result.operations) || !Array.isArray(result.approvalsRequired)) throw new Error('The local service returned an invalid plan preview.'); state.preview = result; state.planRevision = result.planRevision; state.displayedRevision = result.planRevision; fillList('preview-operations', result.operations, renderPreviewOperation, 'No connector writes proposed'); byId('zero-work-reason').textContent = result.zeroWorkReason ? `No schedulable work: ${result.zeroWorkReason}` : 'Schedulable work was found.'; byId('exact-preview').textContent = JSON.stringify(result, null, 2); byId('approve-preview').disabled = false; status('setup-status', `Exact server-derived revision ${result.planRevision} is ready with ${result.approvalsRequired.length} approval-required operations. Review every operation before confirmation.`);
}
async function previewScope() {
  const connector = byId('scope-connector').value; const stages = {2: stageData(2), 3: stageData(3), 4: stageData(4)};
  const result = await api('/v1/setup/connectors', {method: 'POST', body: setupConnectorRequest(state.planRevision, connector, stages)}); state.setupScope = result; byId('scope-preview').textContent = JSON.stringify({planRevision: result.planRevision, operation: result.operation, scope: result.scope}, null, 2); byId('approve-scope').disabled = false; status('setup-status', `Exact ${connector} scope is ready for approval at revision ${result.planRevision}.`);
}
async function approveScope() { if (!state.setupScope?.operation?.id) throw new Error('Preview exact connector scope first.'); const result = await api(`/v1/operations/${encodeURIComponent(state.setupScope.operation.id)}/approve`, {method: 'POST', body: {planRevision: state.setupScope.planRevision, actor: 'dashboard'}}); if (result.state !== 'approved_setup_scope') throw new Error('The service did not verify setup scope approval.'); byId('approve-scope').disabled = true; status('setup-status', 'Displayed connector scope was approved and recorded locally.'); state.setupScope = null; }
async function previewSample() {
  const time = stageData(4); if (!time.tasksListId || !time.focusCalendarId) throw new Error('Choose the exact Rhize Tasks list and Rhize Focus calendar first.');
  const result = await api('/v1/setup/probe', {method: 'POST', body: probePreviewRequest(state.planRevision, time)}); state.probe = result; byId('probe-preview').textContent = JSON.stringify({planRevision: result.planRevision, probeId: result.probeId, exact: result.exact}, null, 2); byId('approve-sample').disabled = false; status('setup-status', `Exact reversible probe ${result.probeId} is ready for approval.`);
}
async function approveSample() { if (!state.probe?.probeId) throw new Error('Preview the reversible probe first.'); const result = await api('/v1/setup/probe', {method: 'POST', body: probeApplyRequest(state.probe.planRevision, state.probe.probeId, 'dashboard')}); if (result.verified?.reminders !== true || result.verified?.calendar !== true) throw new Error('The service could not verify both reversible probe cleanups.'); byId('approve-sample').disabled = true; status('setup-status', 'Calendar and Reminders probes were created, verified, and removed.'); state.probe = null; }
function required(value, label) { if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} is required.`); return value.trim(); }
function profileFromForm({setupComplete = false} = {}) {
  const identity = stageData(2); const jira = stageData(3); const time = stageData(4); const work = stageData(5); const routines = stageData(6);
  required(identity.name, 'Name'); required(identity.timezone, 'Time zone'); required(identity.locale, 'Locale'); required(identity.jiraAccountId, 'Jira account ID'); required(identity.jiraBaseUrl, 'Jira site URL'); required(time.focusCalendarId, 'Rhize Focus calendar ID'); required(time.tasksListId, 'Rhize Tasks list ID');
  if (!jira.projects.length || !jira.issueTypes.length || !work.workingIntervals.length) throw new Error('Complete the approved Jira scope and at least one working interval before saving preferences.');
  for (const item of [...work.workingIntervals, ...work.breaks]) if (!Number.isInteger(item.dayOfWeek) || item.dayOfWeek < 1 || item.dayOfWeek > 7 || !item.start || !item.end || item.start >= item.end) throw new Error('Every work interval and break needs a valid day, start, and later end time.');
  for (const item of jira.competencies) if (!item.name || !Number.isFinite(item.confidence) || item.confidence < 0 || item.confidence > 1) throw new Error('Every competency needs a name and confidence from 0 to 1.');
  jira.projectImportance = Object.fromEntries(jira.projects.map(project => [project, jira.projectImportance[project] ?? 3]));
  return profileFromStageData({2: identity, 3: jira, 4: time, 5: work, 6: routines}, {setupComplete, firstPlanApproved: state.profile?.approval?.firstPlanApproved === true, automationPaused: state.paused});
}
function connectorConfigFromForm() {
  const setup = stageData(2); const parts = [setup.slackWorkspaceId, setup.slackChannelId, ...setup.slackSenderIds];
  if (parts.every(value => !value)) return {slack: null};
  if (!setup.slackWorkspaceId || !setup.slackChannelId || setup.slackSenderIds.length === 0) throw new Error('Slack fallback needs one workspace, #tom-tasks channel, and at least one recognized sender ID.');
  return {slack: {workspaceId: setup.slackWorkspaceId, channelId: setup.slackChannelId, senderIds: setup.slackSenderIds}};
}
async function savePreferences({setupComplete = false} = {}) {
  const profile = profileFromForm({setupComplete}); const config = connectorConfigFromForm();
  const profileResult = await api('/v1/preferences', {method: 'PUT', body: {planRevision: state.planRevision, profile}}); const profileOperations = profileResult.operationIds ?? [];
  if (profileOperations.length) { byId('exact-preview').textContent = JSON.stringify({planRevision: state.planRevision, operationIds: profileOperations}, null, 2); status('setup-status', 'Profile scope changed. Review and approve the listed operations before continuing.'); await refreshToday(); return false; }
  if (config.slack) await api('/v1/setup/connectors', {method: 'PUT', body: {planRevision: state.planRevision, connector: 'slack', scope: config.slack, apply: true}});
  state.profile = profile; state.connectorConfig = config; status('setup-status', 'Preferences saved. Generating the first no-write plan preview.'); return true;
}
async function previewPlan() { if (await savePreferences({setupComplete: true})) await preview(); }
async function confirmPreview() { if (!state.preview) throw new Error('Generate and review a preview first.'); await api(`/v1/plans/${state.displayedRevision}/approve`, {method: 'POST', body: {actor: 'dashboard', apply: true}}); await saveStage(7); status('setup-status', `Displayed revision ${state.displayedRevision} was confirmed and setup is complete. Refreshing current state.`); state.preview = null; byId('approve-preview').disabled = true; await Promise.all([loadSetup(), refreshToday()]); }

async function loadAuthorized() { await Promise.all([loadSetup(), refreshToday()]); status('service-status', 'Connected to the authenticated loopback service.'); }
async function connect() { state.token = byId('api-token').value; byId('api-token').value = ''; if (!state.token) { status('service-status', 'Enter a temporary bearer only for local troubleshooting.'); return; } try { await loadAuthorized(); } catch (error) { state.token = ''; status('service-status', `${error.message} Disconnected; the troubleshooting bearer was cleared. Run the installed CLI dashboard command for a fresh one-time local session link.`); } }
async function guarded(action) { try { await action(); } catch (error) { status('setup-status', error.message); } }

export function bootDashboard() {
  renderCompetencyRows([{name: 'ads', confidence: .95, excluded: false}, {name: 'marketing', confidence: .95, excluded: false}, {name: 'GHL', confidence: .9, excluded: false}, {name: 'Sanity content', confidence: .75, excluded: false}]);
  renderIntervalRows('working-interval-rows', [1, 2, 3, 4, 5].map(dayOfWeek => ({dayOfWeek, start: '09:00', end: '17:00'})), 'Working interval');
  renderIntervalRows('break-interval-rows', [], 'Break');
  byId('connect').addEventListener('click', connect);
  byId('pause-automation').addEventListener('click', async () => { try { const result = await api('/v1/pause', {method: 'POST', body: {planRevision: state.displayedRevision, paused: !state.paused}}); state.paused = result.paused; await refreshToday(); } catch (error) { status('plan-status', error.message); } });
  byId('add-competency').addEventListener('click', () => renderCompetencyRows([...competencyRows(), {name: '', confidence: .5, excluded: false}]));
  byId('add-working-interval').addEventListener('click', () => renderIntervalRows('working-interval-rows', [...intervalRows('working-interval-rows'), {dayOfWeek: 1, start: '09:00', end: '17:00'}], 'Working interval'));
  byId('add-break-interval').addEventListener('click', () => renderIntervalRows('break-interval-rows', [...intervalRows('break-interval-rows'), {dayOfWeek: 1, start: '12:00', end: '13:00'}], 'Break'));
  document.querySelectorAll('[data-save-stage]').forEach(button => button.addEventListener('click', () => guarded(() => saveStage(Number(button.dataset.saveStage)))));
  document.querySelectorAll('[data-secret]').forEach(button => button.addEventListener('click', () => guarded(() => saveCredentials(button.dataset.secret))));
  document.querySelectorAll('[data-discover]').forEach(button => button.addEventListener('click', () => guarded(() => discover(button.dataset.discover))));
  byId('preview-scope').addEventListener('click', () => guarded(previewScope)); byId('approve-scope').addEventListener('click', () => guarded(approveScope)); byId('preview-sample').addEventListener('click', () => guarded(previewSample)); byId('approve-sample').addEventListener('click', () => guarded(approveSample)); byId('preview-plan').addEventListener('click', () => guarded(previewPlan)); byId('approve-preview').addEventListener('click', () => guarded(confirmPreview));
  loadAuthorized().catch(error => { status('service-status', `${error.message} Open a fresh one-time dashboard link or use the local bearer troubleshooting fallback.`); });
}

if (typeof document !== 'undefined') bootDashboard();
