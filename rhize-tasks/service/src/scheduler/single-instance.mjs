import {randomUUID} from 'node:crypto';
import {open, readFile, unlink} from 'node:fs/promises';
import {hasActiveProcessGroups, killActiveProcessGroups} from '../connectors/process-runner.mjs';

const SIGTERM_CHILD_GRACE_MS = 2_000;
const SIGTERM_CHILD_POLL_MS = 100;

const running = pid => { try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; } };

// A lock whose pid is no longer running can never be released by its owner,
// so it is always reclaimable regardless of the staleMs age gate — the age
// gate only ever protected a *live* process's lock, and this function never
// reclaims one of those (running(pid) === true short-circuits it below).
async function reclaim(lockPath) {
  let value;
  try { value = JSON.parse(await readFile(lockPath, 'utf8')); } catch { return false; }
  if (!Number.isInteger(value.pid) || running(value.pid)) return false;
  try { await unlink(lockPath); return true; } catch { return false; }
}

export async function withSingleInstance(lockPath, action, {now = () => new Date()} = {}) {
  if (typeof lockPath !== 'string' || !lockPath || typeof action !== 'function') throw new TypeError('invalid single-instance arguments');
  const token = randomUUID(); let handle;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try { handle = await open(lockPath, 'wx', 0o600); break; } catch (error) {
      if (error.code !== 'EEXIST' || attempt > 0 || !await reclaim(lockPath)) throw Object.assign(new Error('already_running'), {kind: 'already_running'});
    }
  }
  await handle.writeFile(JSON.stringify({pid: process.pid, token, startedAt: now().toISOString()}));
  let released = false;
  const release = async () => {
    if (released) return;
    released = true;
    await handle.close().catch(() => {});
    try { const current = JSON.parse(await readFile(lockPath, 'utf8')); if (current.token === token) await unlink(lockPath); } catch {}
  };
  // Node's default SIGTERM disposition terminates immediately, skipping the
  // `finally` below and leaving a stale lock for up to 30 minutes (finding
  // #22). Registering a handler overrides that default, so we must release
  // the lock and exit ourselves.
  //
  // process-runner's children run detached (their own process group, for
  // finding #5's orphan-grandchild kill), so an OS-level SIGTERM to *this*
  // process's group no longer reaches them — a detached EventKit helper
  // could still be mid-write when we release the lock and exit (finding
  // #6-followup). Explicitly stop them first: SIGTERM, a brief grace window
  // to let them exit cleanly, then SIGKILL anything still around.
  const stopChildrenWithGrace = async () => {
    killActiveProcessGroups('SIGTERM');
    const deadline = Date.now() + SIGTERM_CHILD_GRACE_MS;
    while (hasActiveProcessGroups() && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, SIGTERM_CHILD_POLL_MS));
    }
    if (hasActiveProcessGroups()) killActiveProcessGroups('SIGKILL');
  };
  const onSigterm = () => { stopChildrenWithGrace().finally(() => release().finally(() => process.exit(0))); };
  process.once('SIGTERM', onSigterm);
  try {
    return await action();
  } finally {
    process.removeListener('SIGTERM', onSigterm);
    await release();
  }
}
