import {randomUUID} from 'node:crypto';
import {open, readFile, unlink} from 'node:fs/promises';

const running = pid => { try { process.kill(pid, 0); return true; } catch (error) { return error.code === 'EPERM'; } };

async function reclaim(lockPath, now, staleMs) {
  let value;
  try { value = JSON.parse(await readFile(lockPath, 'utf8')); } catch { return false; }
  const stale = typeof value.startedAt === 'string' && now().getTime() - Date.parse(value.startedAt) > staleMs;
  if (!stale || !Number.isInteger(value.pid) || running(value.pid)) return false;
  try { await unlink(lockPath); return true; } catch { return false; }
}

export async function withSingleInstance(lockPath, action, {now = () => new Date(), staleMs = 30 * 60_000} = {}) {
  if (typeof lockPath !== 'string' || !lockPath || typeof action !== 'function') throw new TypeError('invalid single-instance arguments');
  const token = randomUUID(); let handle;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try { handle = await open(lockPath, 'wx', 0o600); break; } catch (error) {
      if (error.code !== 'EEXIST' || attempt > 0 || !await reclaim(lockPath, now, staleMs)) throw Object.assign(new Error('already_running'), {kind: 'already_running'});
    }
  }
  await handle.writeFile(JSON.stringify({pid: process.pid, token, startedAt: now().toISOString()}));
  try { return await action(); } finally {
    await handle.close();
    try { const current = JSON.parse(await readFile(lockPath, 'utf8')); if (current.token === token) await unlink(lockPath); } catch {}
  }
}
