import {readFileSync} from 'node:fs';
import {open, rename, rm} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const template = readFileSync(new URL('./artifact-template.html', import.meta.url), 'utf8');

function escapeHtml(value) { return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;'); }
function plain(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype; }
function assertView(view) {
  if (!plain(view) || view.schemaVersion !== 1 || !Number.isInteger(view.planRevision) || view.planRevision < 1 || typeof view.generatedAt !== 'string') throw new TypeError('invalid_today_view');
  for (const key of ['timeline', 'carryovers', 'approvals', 'opportunities', 'warnings']) if (!Array.isArray(view[key])) throw new TypeError('invalid_today_view');
  if (!plain(view.capacity) || !plain(view.connectors) || typeof view.paused !== 'boolean' || typeof view.degraded !== 'boolean') throw new TypeError('invalid_today_view');
}
function list(items, render, empty) { return items.length ? `<ul>${items.map(item => `<li>${render(item)}</li>`).join('')}</ul>` : `<p class="muted">${empty}</p>`; }
function block(item) {
  if (item === null) return '<span class="muted">None</span>';
  const label = item.title ?? (item.redacted ? 'Busy' : item.kind);
  return `<strong>${escapeHtml(label)}</strong><br>${escapeHtml(item.start)}–${escapeHtml(item.end)}${item.redacted ? ' · redacted' : ''}`;
}

export function renderArtifact(view) {
  assertView(view);
  const content = [
    `<section class="card"><h2>Current and next</h2><dl><dt>Current</dt><dd>${block(view.currentBlock)}</dd><dt>Next</dt><dd>${block(view.nextBlock)}</dd></dl></section>`,
    `<section class="card"><h2>Capacity</h2><p>${escapeHtml(view.capacity.plannedMinutes)} planned of ${escapeHtml(view.capacity.availableMinutes)} available minutes · ${escapeHtml(view.capacity.bufferMinutes)} minutes buffered · ${escapeHtml(view.capacity.risk)} risk</p></section>`,
    `<section class="card"><h2>Timeline</h2>${list(view.timeline, item => `<strong>${escapeHtml(item.start)}–${escapeHtml(item.end)}</strong> · ${escapeHtml(item.title ?? (item.redacted ? 'Busy' : item.kind))}`, 'No blocks')}</section>`,
    `<section class="card"><h2>Carryovers</h2>${list(view.carryovers, item => `${escapeHtml(item.title)} — ${escapeHtml(item.reason)} (${escapeHtml(item.resolution)})`, 'None')}</section>`,
    `<section class="card"><h2>Pending decisions</h2>${list(view.approvals, item => `${escapeHtml(item.title)} — ${escapeHtml(item.reason)}`, 'None')}</section>`,
    `<section class="card"><h2>Opportunities</h2>${list(view.opportunities, item => `${escapeHtml(item.title)} — ${escapeHtml(item.rationale)}; impact: ${escapeHtml(item.impact)}`, 'None')}</section>`,
    `<section class="card"><h2>Warnings</h2>${list(view.warnings, item => `${escapeHtml(item.code)} — ${escapeHtml(item.message)}`, 'None')}</section>`,
    `<section class="card"><h2>Connector freshness</h2><dl>${Object.entries(view.connectors).map(([name, connector]) => `<dt>${escapeHtml(name)}</dt><dd>${escapeHtml(connector.status)} · ${escapeHtml(connector.staleMinutes)} minutes stale${connector.freshAt ? ` · refreshed ${escapeHtml(connector.freshAt)}` : ''}</dd>`).join('')}</dl></section>`,
    `<section class="card"><h2>Service state</h2><p>${view.paused ? 'Paused' : 'Running'} · ${view.degraded ? 'Degraded' : 'Healthy'}</p></section>`,
  ].join('');
  return template.replaceAll('{{PLAN_REVISION}}', String(view.planRevision)).replace('{{GENERATED_AT}}', escapeHtml(view.generatedAt)).replace('{{TODAY_CONTENT}}', content).replace('{{TODAY_VIEW_JSON}}', escapeHtml(JSON.stringify(view, null, 2)));
}

export async function writeArtifactFile(target, view) {
  if (typeof target !== 'string' || !target || target.includes('\0')) throw new TypeError('invalid_output_path');
  const resolved = path.resolve(target); const temporary = `${resolved}.writing-${process.pid}`; let handle;
  try {
    handle = await open(temporary, 'wx', 0o600); await handle.writeFile(renderArtifact(view)); await handle.sync(); await handle.close(); handle = undefined; await rename(temporary, resolved);
  } catch (error) {
    await handle?.close().catch(() => {}); await rm(temporary, {force: true}).catch(() => {}); throw error;
  }
  return resolved;
}
