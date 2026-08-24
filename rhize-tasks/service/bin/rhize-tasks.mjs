#!/usr/bin/env node

import {spawn} from 'node:child_process';
import {closeSync, openSync} from 'node:fs';
import {mkdir, rm, writeFile} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {fileURLToPath, pathToFileURL} from 'node:url';

import {writeArtifactFile} from '../../dashboard/artifact.mjs';
import {install, servePidPath} from '../../installer/install.mjs';
import {parseUninstallChoice, uninstall} from '../../installer/uninstall.mjs';
import {createServiceContext} from '../src/api/context.mjs';
import {createServer} from '../src/api/server.mjs';
import {runRoutine} from '../src/scheduler/bounded-routines.mjs';
import {applicationSupportDirectory} from '../src/storage/paths.mjs';

const routineKinds = new Set(['morning', 'midday', 'evening', 'catch-up']);
const MAX_STDIN_BYTES = 64 * 1024;
const HEALTH_PROBE_TIMEOUT_MS = 1_500;
const HEALTH_POLL_INTERVAL_MS = 150;
const HEALTH_POLL_MAX_WAIT_MS = 4_000;

function exactArgs(actual, expected) {
  if (actual.length !== expected.length || actual.some((value, index) => value !== expected[index])) throw new TypeError('invalid_arguments');
}

function writeJson(write, value) {
  write(`${JSON.stringify(value)}\n`);
}

async function readOneJsonLine(input = process.stdin) {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of input) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    bytes += buffer.length;
    if (bytes > MAX_STDIN_BYTES) throw new TypeError('stdin_too_large');
    chunks.push(buffer);
  }
  const text = Buffer.concat(chunks).toString('utf8');
  const lines = text.split(/\r?\n/);
  if (lines.at(-1) === '') lines.pop();
  if (lines.length !== 1 || lines[0].length === 0) throw new TypeError('invalid_json_line');
  try { return JSON.parse(lines[0]); } catch { throw new TypeError('invalid_json_line'); }
}

// Installer errors carry a snake_case identifier as `.message` (sometimes
// with a `:detail` suffix) but historically no `.kind`/`.code`, so every
// install/uninstall failure surfaced here as a uniform "command_failed"
// with no diagnostic value (finding #6). Node's own ERR_* codes are
// uppercase and were rejected outright by the original pattern too — e.g.
// ERR_UNKNOWN_BUILTIN_MODULE from a node:sqlite-incapable Node build
// (finding #25) — so fall back to those, lowercased, before giving up.
export function errorKind(error) {
  for (const candidate of [error?.kind, error?.code]) if (typeof candidate === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(candidate)) return candidate;
  if (typeof error?.code === 'string' && /^[A-Z][A-Z0-9_]{0,63}$/.test(error.code)) return error.code.toLowerCase();
  if (typeof error?.message === 'string') {
    const head = error.message.split(':')[0];
    if (/^[a-z][a-z0-9_]{0,63}$/.test(head)) return head;
  }
  return 'command_failed';
}

async function listen(server, port, host) {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, host, resolve);
  });
}

async function stop(server) {
  if (!server.listening) return;
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}

// `dashboard` spawns `serve` detached with no other way to find it later —
// reinstalling after `dashboard` had run once used to fail outright
// (checkLoopbackPort's new own-server detection), and uninstalling used to
// delete the runtime/database out from under a still-running `serve`
// (finding #1). `serve` writes the pidfile install.mjs/uninstall.mjs read.
async function defaultWriteServePid(pidPath, pid = process.pid) {
  await mkdir(path.dirname(pidPath), {recursive: true, mode: 0o700});
  await writeFile(pidPath, String(pid), {mode: 0o600});
}

async function defaultRemoveServePid(pidPath) {
  await rm(pidPath, {force: true});
}

async function probeHealth(host, port, timeoutMs = HEALTH_PROBE_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`http://${host}:${port}/health`, {signal: controller.signal});
    if (!response.ok) return null;
    const body = await response.json();
    return body?.status === 'ok' ? body : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function waitForHealth(host, port, {maxWaitMs = HEALTH_POLL_MAX_WAIT_MS, intervalMs = HEALTH_POLL_INTERVAL_MS, probe = probeHealth, sleep = ms => new Promise(resolve => setTimeout(resolve, ms))} = {}) {
  const deadline = Date.now() + maxWaitMs;
  do {
    const health = await probe(host, port);
    if (health) return health;
    await sleep(intervalMs);
  } while (Date.now() < deadline);
  return null;
}

// `dashboard` previously only minted a nonce and printed a URL nothing was
// listening on — the LaunchAgent only ever runs `routine catch-up`, which
// exits immediately, so the dashboard was connection-refused on a fresh
// install (finding #1). Ensure a `serve` process is actually up before
// handing back a URL, without adding a second always-on LaunchAgent (which
// would worsen the TCC responsible-process problem in a related finding).
export async function ensureServerRunning(host, port, {
  probe = probeHealth,
  wait = waitForHealth,
  spawnServe = spawn,
  cliPath = fileURLToPath(import.meta.url),
  nodePath = process.execPath,
  logDir = path.join(applicationSupportDirectory(), 'logs'),
  mkdirImpl = mkdir,
  openLogFd = openSync,
  closeLogFd = closeSync,
} = {}) {
  if (await probe(host, port)) return;
  await mkdirImpl(logDir, {recursive: true, mode: 0o700});
  const stdoutFd = openLogFd(path.join(logDir, 'serve.log'), 'a', 0o600);
  const stderrFd = openLogFd(path.join(logDir, 'serve-error.log'), 'a', 0o600);
  try {
    const child = spawnServe(nodePath, [cliPath, 'serve'], {detached: true, stdio: ['ignore', stdoutFd, stderrFd]});
    child.unref();
  } finally {
    closeLogFd(stdoutFd);
    closeLogFd(stderrFd);
  }
  if (!await wait(host, port)) throw Object.assign(new Error('dashboard_server_did_not_start'), {code: 'dashboard_server_did_not_start'});
}

export async function runCli(args, {
  createContext = createServiceContext,
  installLocal = install,
  uninstallLocal = uninstall,
  stdin = process.stdin,
  stdout = value => process.stdout.write(value),
  waitForShutdown,
  ensureServer = ensureServerRunning,
  servePidFilePath = servePidPath(),
  writeServePid = defaultWriteServePid,
  removeServePid = defaultRemoveServePid,
} = {}) {
  if (!Array.isArray(args) || args.some(value => typeof value !== 'string')) throw new TypeError('invalid_arguments');
  const [command, ...rest] = args;
  if (command === 'install') {
    exactArgs(rest, []);
    const result = await installLocal();
    writeJson(stdout, {ok: true, ...result});
    return result;
  }
  if (command === 'uninstall') {
    const choices = parseUninstallChoice(rest);
    const result = await uninstallLocal({choices});
    writeJson(stdout, result);
    return result;
  }
  if (!['serve', 'routine', 'doctor', 'artifact', 'uninstall-items', 'provision-token', 'dashboard'].includes(command)) throw new TypeError('unknown_command');

  const context = await createContext();
  try {
    if (command === 'serve') {
      exactArgs(rest, []);
      // Pidfile written BEFORE listen (finding #1-followup): writing it
      // after left a window where a write failure (disk full, permissions)
      // left a server actually listening with no pidfile to find it by —
      // exactly the state install/uninstall's own-server detection can't
      // recover from. If the write fails, we never even attempt to listen.
      // If listen then fails, the pidfile we already wrote is cleaned up
      // before the error propagates, so a failed `serve` never leaves a
      // stale pidfile behind either.
      await writeServePid(servePidFilePath);
      const server = createServer(context);
      try {
        await listen(server, context.port, context.host);
      } catch (error) {
        await removeServePid(servePidFilePath).catch(() => {});
        throw error;
      }
      writeJson(stdout, {ok: true, status: 'listening', host: context.host, port: context.port});
      try {
        if (waitForShutdown) await waitForShutdown(server);
        else await new Promise(resolve => {
          const close = () => { process.off('SIGINT', close); process.off('SIGTERM', close); stop(server).finally(resolve); };
          process.once('SIGINT', close); process.once('SIGTERM', close);
        });
      } finally {
        await removeServePid(servePidFilePath).catch(() => {});
      }
      await stop(server);
      return {status: 'stopped'};
    }
    if (command === 'routine') {
      if (rest.length !== 1 || !routineKinds.has(rest[0])) throw new TypeError('invalid_routine');
      const result = await runRoutine(rest[0], context, context.now());
      writeJson(stdout, {ok: true, ...result});
      return result;
    }
    if (command === 'doctor') {
      exactArgs(rest, ['--json']);
      const result = await context.doctor();
      writeJson(stdout, {ok: true, ...result});
      return result;
    }
    if (command === 'provision-token') {
      exactArgs(rest, ['--json']);
      const result = {ok: true, provisioned: context.auth.provisioned === true, service: 'media.rhize.tasks.api', account: 'bearer'};
      writeJson(stdout, result);
      return result;
    }
    if (command === 'dashboard') {
      exactArgs(rest, ['--json']);
      await ensureServer(context.host, context.port);
      const issued = context.sessions.issue(); const result = {ok: true, url: `http://${context.host}:${context.port}/session?nonce=${encodeURIComponent(issued.nonce)}`, expiresAt: issued.expiresAt};
      writeJson(stdout, result);
      return result;
    }
    if (command === 'artifact') {
      if (rest.length !== 2 || rest[0] !== '--output') throw new TypeError('invalid_arguments');
      const view = await context.today();
      const output = await writeArtifactFile(rest[1], view);
      const result = {ok: true, output, planRevision: view.planRevision};
      writeJson(stdout, result);
      return result;
    }
    if (command === 'uninstall-items') {
      exactArgs(rest, ['--json']);
      const result = await context.cleanup(await readOneJsonLine(stdin));
      writeJson(stdout, result);
      return result;
    }
  } finally {
    context.close?.();
  }
}

// runChecked (installer/install.mjs) attaches the already-truncated
// stdout/stderr tail, exit code, and command to swift-build/codesign
// failures — but this boundary used to serialize only `kind`, so a
// CLT-only-toolchain build failure (README's top first-install problem)
// still reached the user with no compiler output (finding #6/#11).
export function serializeError(error) {
  const payload = {kind: errorKind(error)};
  if (typeof error?.command === 'string') payload.command = error.command;
  if (Number.isInteger(error?.exitCode)) payload.exitCode = error.exitCode;
  if (typeof error?.stdout === 'string' && error.stdout) payload.stdoutTail = error.stdout;
  if (typeof error?.stderr === 'string' && error.stderr) payload.stderrTail = error.stderr;
  return payload;
}

export async function main(args = process.argv.slice(2), options = {}) {
  try {
    await runCli(args, options);
  } catch (error) {
    writeJson(value => process.stderr.write(value), {ok: false, error: serializeError(error)});
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
