#!/usr/bin/env node

import {open, rename, rm} from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import {pathToFileURL} from 'node:url';

import {install} from '../../installer/install.mjs';
import {parseUninstallChoice, uninstall} from '../../installer/uninstall.mjs';
import {createServiceContext} from '../src/api/context.mjs';
import {createServer} from '../src/api/server.mjs';
import {runRoutine} from '../src/scheduler/bounded-routines.mjs';

const routineKinds = new Set(['morning', 'midday', 'evening', 'catch-up']);
const MAX_STDIN_BYTES = 64 * 1024;

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

async function writeArtifact(target, value) {
  if (typeof target !== 'string' || !target || target.includes('\0')) throw new TypeError('invalid_output_path');
  const resolved = path.resolve(target);
  const temporary = `${resolved}.writing-${process.pid}`;
  let handle;
  try {
    handle = await open(temporary, 'wx', 0o600);
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`);
    await handle.sync();
    await handle.close();
    handle = undefined;
    await rename(temporary, resolved);
  } catch (error) {
    await handle?.close().catch(() => {});
    await rm(temporary, {force: true}).catch(() => {});
    throw error;
  }
  return resolved;
}

function errorKind(error) {
  for (const candidate of [error?.kind, error?.code]) if (typeof candidate === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(candidate)) return candidate;
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

export async function runCli(args, {
  createContext = createServiceContext,
  installLocal = install,
  uninstallLocal = uninstall,
  stdin = process.stdin,
  stdout = value => process.stdout.write(value),
  waitForShutdown,
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
      const server = createServer(context);
      await listen(server, context.port, context.host);
      writeJson(stdout, {ok: true, status: 'listening', host: context.host, port: context.port});
      if (waitForShutdown) await waitForShutdown(server);
      else await new Promise(resolve => {
        const close = () => { process.off('SIGINT', close); process.off('SIGTERM', close); stop(server).finally(resolve); };
        process.once('SIGINT', close); process.once('SIGTERM', close);
      });
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
      const issued = context.sessions.issue(); const result = {ok: true, url: `http://${context.host}:${context.port}/session?nonce=${encodeURIComponent(issued.nonce)}`, expiresAt: issued.expiresAt};
      writeJson(stdout, result);
      return result;
    }
    if (command === 'artifact') {
      if (rest.length !== 2 || rest[0] !== '--output') throw new TypeError('invalid_arguments');
      const view = await context.today();
      const output = await writeArtifact(rest[1], view);
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

export async function main(args = process.argv.slice(2)) {
  try {
    await runCli(args);
  } catch (error) {
    writeJson(value => process.stderr.write(value), {ok: false, error: {kind: errorKind(error)}});
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
