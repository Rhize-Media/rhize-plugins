#!/usr/bin/env node
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { chmodSync, existsSync, lstatSync, mkdirSync, mkdtempSync, openSync, closeSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { homedir, platform } from 'node:os';
import { dirname, join, resolve, basename } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const PLUGIN_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const manifest = JSON.parse(readFileSync(join(PLUGIN_ROOT, 'setup/manifest.json'), 'utf8'));
const runtime = manifest.dependencies.find(item => item.name === 'rhize-outreach runtime');
export const APP_ROOT = join(homedir(), 'Library', 'Application Support', 'Rhize Outreach');
export const DEFAULT_DATA_ROOT = join(APP_ROOT, 'data');
export const DEFAULT_PORT = 8787;
const WIZARD_HTML = join(PLUGIN_ROOT, 'assets', 'setup-wizard.html');

export function compareVersions(a, b) {
  const left = String(a).replace(/^v/, '').split('.').map(Number);
  const right = String(b).replace(/^v/, '').split('.').map(Number);
  for (let i = 0; i < 3; i++) if ((left[i] || 0) !== (right[i] || 0)) return (left[i] || 0) - (right[i] || 0);
  return 0;
}

export function configFor({ dataRoot = DEFAULT_DATA_ROOT, port = DEFAULT_PORT, pgBin = null } = {}) {
  const dataPath = resolve(dataRoot);
  return {
    schema_version: 1,
    runtime_source: runtime.source,
    runtime_commit: runtime.pin,
    source_path: join(APP_ROOT, 'source', runtime.pin),
    data_path: dataPath,
    artifact_path: join(dataPath, 'artifacts'),
    postgres_bin: pgBin ? resolve(pgBin) : null,
    port: Number(port)
  };
}

export function validateConfig(value) {
  if (!value || value.schema_version !== 1 || value.runtime_source !== runtime.source || value.runtime_commit !== runtime.pin) return false;
  if (![value.source_path, value.data_path, value.artifact_path].every(item => typeof item === 'string' && item.length > 0 && resolve(item) === item)) return false;
  if (value.source_path !== join(APP_ROOT, 'source', runtime.pin) || value.artifact_path !== join(value.data_path, 'artifacts')) return false;
  if (!Number.isInteger(value.port) || value.port < 1024 || value.port > 65535) return false;
  return value.postgres_bin === null || (typeof value.postgres_bin === 'string' && resolve(value.postgres_bin) === value.postgres_bin);
}

function command(bin, args, options = {}) {
  const result = spawnSync(bin, args, { encoding: 'utf8', stdio: options.stdio ?? 'pipe', timeout: options.timeout ?? 30000, maxBuffer: 2 * 1024 * 1024, ...options });
  if (result.error) throw new Error(`${basename(bin)} could not run: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${basename(bin)} exited with status ${result.status ?? 'unknown'}`);
  return result;
}

export function findBinary(name) {
  const result = spawnSync('which', [name], { encoding: 'utf8', timeout: 5000 });
  return result.status === 0 ? result.stdout.trim().split('\n')[0] : null;
}

export function inspectPrerequisites() {
  const node = process.version;
  const pg = Object.fromEntries(['initdb', 'pg_ctl', 'createdb'].map(name => [name, findBinary(name)]));
  const pgDirs = new Set(Object.values(pg).filter(Boolean).map(path => dirname(path)));
  let codexInstalled = Boolean(findBinary('codex'));
  let codexSignedIn = false;
  if (codexInstalled) codexSignedIn = spawnSync('codex', ['login', 'status'], { encoding: 'utf8', timeout: 10000, maxBuffer: 1024 * 1024 }).status === 0;
  const checks = {
    platform: { ok: platform() === 'darwin', detail: platform() },
    node: { ok: compareVersions(node, '24.12.0') >= 0, detail: node },
    git: { ok: Boolean(findBinary('git')), detail: findBinary('git') ?? 'not found' },
    npm: { ok: Boolean(findBinary('npm')), detail: findBinary('npm') ?? 'not found' },
    postgresql: { ok: Object.values(pg).every(Boolean) && pgDirs.size === 1, detail: Object.values(pg).every(Boolean) && pgDirs.size === 1 ? [...pgDirs][0] : pg },
    codex: { ok: codexInstalled && codexSignedIn, detail: !codexInstalled ? 'not found' : codexSignedIn ? 'signed in' : 'not signed in' }
  };
  return { checks, pgBin: checks.postgresql.ok ? [...pgDirs][0] : null, ready: Object.values(checks).every(item => item.ok) };
}

export function ensurePrivateDirectory(path) {
  mkdirSync(path, { recursive: true, mode: 0o700 });
  const stat = lstatSync(path);
  if (stat.isSymbolicLink() || !stat.isDirectory() || (typeof process.getuid === 'function' && stat.uid !== process.getuid())) throw new Error(`Refusing unsafe or foreign-owned directory: ${path}`);
  chmodSync(path, 0o700);
}

function readConfig() {
  const path = join(APP_ROOT, 'config.json');
  if (!existsSync(path)) return null;
  const value = JSON.parse(readFileSync(path, 'utf8'));
  if (!validateConfig(value)) throw new Error('Existing config is invalid or references another runtime pin; preserve it and diagnose before changing it.');
  return value;
}

function writePrivateConfig(value) {
  ensurePrivateDirectory(APP_ROOT);
  const target = join(APP_ROOT, 'config.json');
  const temporary = join(APP_ROOT, `.config-${process.pid}-${Date.now()}.tmp`);
  const fd = openSync(temporary, 'wx', 0o600);
  try { writeFileSync(fd, `${JSON.stringify(value, null, 2)}\n`); } finally { closeSync(fd); }
  chmodSync(temporary, 0o600);
  renameSync(temporary, target);
}

function verifyCheckout(sourcePath, { requireClean = true, runtimeSpec = runtime } = {}) {
  if (!existsSync(join(sourcePath, '.git'))) return { ok: false, reason: 'missing' };
  let origin, head, status;
  try {
    origin = command('git', ['-C', sourcePath, 'remote', 'get-url', 'origin']).stdout.trim().replace(/\.git$/, '');
    head = command('git', ['-C', sourcePath, 'rev-parse', 'HEAD']).stdout.trim();
    status = command('git', ['-C', sourcePath, 'status', '--porcelain']).stdout.trim();
  } catch { return { ok: false, reason: 'git check failed' }; }
  if (origin !== runtimeSpec.source.replace(/\.git$/, '') || head !== runtimeSpec.pin) return { ok: false, reason: 'origin or pinned commit mismatch', head, origin };
  if (requireClean && status) return { ok: false, reason: 'tracked or untracked source changes are present' };
  return { ok: true, head };
}

export function installSource({ sourceRoot, installDependencies = true, runtimeSpec = runtime } = {}) {
  const base = resolve(sourceRoot ?? join(APP_ROOT, 'source'));
  ensurePrivateDirectory(base);
  const target = join(base, runtimeSpec.pin);
  if (existsSync(target)) {
    const verified = verifyCheckout(target, { runtimeSpec });
    if (!verified.ok) throw new Error(`Existing pinned source checkout is not safe to reuse: ${verified.reason}. It was left untouched.`);
    if (installDependencies && !existsSync(join(target, 'node_modules'))) command('npm', ['ci'], { cwd: target, stdio: 'inherit', timeout: 600000 });
    return target;
  }
  const stage = mkdtempSync(join(base, '.install-'));
  try {
    command('git', ['clone', '--no-checkout', runtimeSpec.source, stage], { stdio: 'inherit', timeout: 300000 });
    command('git', ['-C', stage, 'checkout', '--detach', runtimeSpec.pin], { stdio: 'inherit', timeout: 120000 });
    const verified = verifyCheckout(stage, { runtimeSpec });
    if (!verified.ok) throw new Error(`Fetched runtime did not match the pinned commit: ${verified.reason}`);
    if (installDependencies) command('npm', ['ci'], { cwd: stage, stdio: 'inherit', timeout: 600000 });
    renameSync(stage, target);
    return target;
  } catch (error) {
    rmSync(stage, { recursive: true, force: true });
    throw error;
  }
}

function printChecks(report, asJson = false) {
  if (asJson) console.log(JSON.stringify(report, null, 2));
  else for (const [name, value] of Object.entries(report.checks ?? {})) console.log(`${value.ok ? 'PASS' : 'BLOCKED'} ${name}: ${typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail)}`);
}

function setup(args) {
  const prereqs = inspectPrerequisites();
  printChecks(prereqs, args.json);
  if (!prereqs.ready) throw new Error('Setup is blocked until every prerequisite is available. No files were changed.');
  const previous = readConfig();
  const next = configFor({ dataRoot: args.dataDir ?? previous?.data_path, port: args.port ?? previous?.port, pgBin: prereqs.pgBin });
  if (args.check || !args.apply) {
    console.log(`Would fetch ${runtime.pin} from ${runtime.source}, keep data in ${next.data_path}, and start local UI on 127.0.0.1:${next.port}.`);
    if (!args.apply) console.log('No files were changed. Run /rhize-outreach:setup for the guided wizard or rerun setup --apply after reviewing this plan.');
    return;
  }
  ensurePrivateDirectory(dirname(next.source_path));
  ensurePrivateDirectory(next.data_path);
  ensurePrivateDirectory(next.artifact_path);
  const installedSource = installSource({ sourceRoot: dirname(next.source_path) });
  next.source_path = installedSource;
  writePrivateConfig(next);
  console.log(`Setup complete. Runtime ${runtime.pin} is installed; local data remains at ${next.data_path}. Run /rhize-outreach:run to start it.`);
  return { status: 'installed', runtimeCommit: runtime.pin, dataPath: next.data_path, port: next.port };
}

function wizard() {
  const token = randomBytes(32).toString('hex');
  let expectedOrigin;
  let installPending = false;
  let installedInSession = false;
  const server = createServer((req, res) => {
    const requestUrl = new URL(req.url ?? '/', 'http://127.0.0.1');
    const origin = req.headers.origin;
    const submitted = Buffer.from(requestUrl.searchParams.get('token') ?? '');
    const expected = Buffer.from(token);
    const authorized = req.headers.host === new URL(expectedOrigin).host && submitted.length === expected.length && timingSafeEqual(submitted, expected);
    const sameOrigin = !origin || origin === expectedOrigin;
    const send = (status, value, type = 'application/json; charset=utf-8') => {
      const body = Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value));
      res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store', 'Content-Length': body.length, 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'" });
      res.end(body);
    };
    if (!authorized || !sameOrigin) return send(403, { error: 'Invalid local setup session.' });
    if (req.method === 'GET' && requestUrl.pathname === '/') return send(200, readFileSync(WIZARD_HTML), 'text/html; charset=utf-8');
    if (req.method === 'GET' && requestUrl.pathname === '/api/status') {
      const report = inspectPrerequisites();
      let configured = false;
      try { configured = Boolean(readConfig()); } catch { configured = false; }
      return send(200, { checks: report.checks, ready: report.ready, configured, runtimeCommit: runtime.pin, defaultDataPath: DEFAULT_DATA_ROOT });
    }
    if (req.method === 'POST' && requestUrl.pathname === '/api/install') {
      if (installPending || installedInSession) return send(409, { error: 'Setup is already running or has completed in this session.' });
      if (!String(req.headers['content-type'] ?? '').startsWith('application/json')) return send(415, { error: 'Send JSON only.' });
      installPending = true;
      let body = '';
      let bodyBytes = 0;
      req.on('data', chunk => { bodyBytes += chunk.length; if (bodyBytes > 4096) { installPending = false; send(413, { error: 'Setup request is too large.' }); req.destroy(); return; } body += chunk.toString('utf8'); });
      req.on('end', () => {
        try {
          const input = JSON.parse(body || '{}');
          const dataDir = typeof input.dataDir === 'string' && input.dataDir.trim() ? input.dataDir.trim() : DEFAULT_DATA_ROOT;
          if (dataDir.length > 1000 || !dataDir.startsWith('/')) throw new Error('Choose an absolute local data directory.');
          const port = input.port === undefined ? DEFAULT_PORT : Number(input.port);
          if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Port must be between 1024 and 65535.');
          const result = setup({ action: 'setup', apply: true, check: false, json: false, dataDir, port });
          installedInSession = true;
          send(200, result);
          server.close();
        } catch (error) { send(400, { error: error instanceof Error ? error.message : String(error) }); }
        finally { installPending = false; }
      });
      return;
    }
    send(404, { error: 'Not found.' });
  });
  server.requestTimeout = 0;
  server.listen(0, '127.0.0.1', () => {
    const address = server.address();
    if (!address || typeof address === 'string') { console.error('Could not bind setup to loopback.'); server.close(); process.exitCode = 1; return; }
    expectedOrigin = `http://127.0.0.1:${address.port}`;
    const opened = spawnSync('open', [`${expectedOrigin}/?token=${token}`], { stdio: 'ignore', timeout: 10000 });
    if (opened.status !== 0) { console.error('Could not open the local setup wizard. No setup files were changed.'); server.close(); process.exitCode = 1; return; }
    console.log('Rhize Outreach setup wizard opened in your default browser. It is available only on this Mac; keep this terminal open until setup finishes.');
  });
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => server.close());
}

async function doctor(asJson = false) {
  const prereqs = inspectPrerequisites();
  const config = readConfig();
  const report = { status: 'blocked', checks: { ...prereqs.checks, config: { ok: Boolean(config), detail: config ? 'valid; contains no secrets' : 'not configured' } } };
  if (config) {
    const checkout = verifyCheckout(config.source_path);
    report.checks.runtime = { ok: checkout.ok, detail: checkout.ok ? checkout.head : checkout.reason };
    report.checks.dependencies = { ok: existsSync(join(config.source_path, 'node_modules')), detail: existsSync(join(config.source_path, 'node_modules')) ? 'installed' : 'not installed' };
    for (const [name, path] of [['data', config.data_path], ['artifacts', config.artifact_path]]) {
      try { const stat = lstatSync(path); report.checks[name] = { ok: stat.isDirectory() && !stat.isSymbolicLink() && (stat.mode & 0o077) === 0, detail: 'private local directory' }; }
      catch { report.checks[name] = { ok: false, detail: 'missing' }; }
    }
    try { const response = await fetch(`http://127.0.0.1:${config.port}/`, { signal: AbortSignal.timeout(1200) }); report.checks.local_service = { ok: response.status === 200, detail: response.status === 200 ? 'operator UI responds on loopback' : `HTTP ${response.status}` }; }
    catch { report.checks.local_service = { ok: false, detail: 'not running (start with /rhize-outreach:run)' }; }
  }
  report.status = Object.values(report.checks).every(item => item.ok) ? 'ready' : 'blocked';
  printChecks(report, asJson);
  if (!asJson) console.log(`Status: ${report.status}. This runtime uses local PostgreSQL and Codex CLI only; email delivery, publishing, shared Supabase, and paid discovery are not configured by setup.`);
  return report.status === 'ready' ? 0 : 1;
}

export function parse(argv) {
  const [action, ...rest] = argv;
  const args = { action, check: false, apply: false, json: false };
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--check') args.check = true;
    else if (rest[i] === '--apply') args.apply = true;
    else if (rest[i] === '--json') args.json = true;
    else if (rest[i] === '--port' && rest[i + 1]) args.port = Number(rest[++i]);
    else if (rest[i] === '--data-dir' && rest[i + 1]) args.dataDir = rest[++i];
    else throw new Error(`Unsupported argument: ${rest[i]}`);
  }
  if (args.check && args.apply) throw new Error('Choose either --check or --apply.');
  if (args.port !== undefined && (!Number.isInteger(args.port) || args.port < 1024 || args.port > 65535)) throw new Error('--port must be a number from 1024 to 65535.');
  if (args.dataDir !== undefined && (!args.dataDir.startsWith('/') || args.dataDir.length > 1000)) throw new Error('--data-dir must be an absolute path of at most 1000 characters on macOS.');
  return args;
}

function start() {
  const config = readConfig();
  if (!config) throw new Error('Run /rhize-outreach:setup first.');
  const checkout = verifyCheckout(config.source_path);
  if (!checkout.ok) throw new Error(`Pinned runtime check failed: ${checkout.reason}. Run doctor; the checkout was not modified.`);
  const env = { ...process.env, PORT: String(config.port), OUTREACH_DATA_DIR: config.data_path, OUTREACH_ARTIFACT_DIR: config.artifact_path, OUTREACH_PG_BIN: config.postgres_bin ?? '' };
  const child = spawn('npm', ['run', 'dev'], { cwd: config.source_path, env, stdio: ['inherit', 'pipe', 'pipe'] });
  let stdout = '';
  const openOnce = line => {
    const match = line.match(/^Operator URL: (http:\/\/127\.0\.0\.1:\d+\/#\S+)$/);
    if (!match) return false;
    const opened = spawnSync('open', [match[1]], { stdio: 'ignore', timeout: 10000 });
    if (opened.status !== 0) { console.error('Could not open the authenticated local UI. The session link was withheld; check the Mac default browser and restart.'); child.kill('SIGTERM'); }
    else console.log('Authenticated local operator UI opened in the default browser. Keep this terminal running; Ctrl-C stops the service.');
    return true;
  };
  child.stdout.on('data', data => {
    stdout += data.toString();
    const lines = stdout.split('\n'); stdout = lines.pop() ?? '';
    for (const line of lines) if (!openOnce(line)) process.stdout.write(`${line}\n`);
  });
  child.stderr.on('data', data => process.stderr.write(data));
  child.on('error', error => { console.error(`Runtime could not start: ${error.message}`); process.exitCode = 1; });
  child.on('exit', code => { if (stdout && !openOnce(stdout)) process.stdout.write(stdout); process.exitCode = code ?? 0; });
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => child.kill(signal));
}

export async function main(argv = process.argv.slice(2)) {
  try {
    const args = parse(argv);
    if (!['setup', 'wizard', 'doctor', 'start'].includes(args.action)) throw new Error('Use setup [--check|--apply], wizard, doctor [--json], or start.');
    if (args.action === 'setup') setup(args);
    if (args.action === 'wizard') wizard();
    if (args.action === 'doctor') return await doctor(args.json);
    if (args.action === 'start') start();
    return 0;
  } catch (error) { console.error(error instanceof Error ? error.message : String(error)); return 1; }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) process.exitCode = await main();
