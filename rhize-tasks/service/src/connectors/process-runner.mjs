import {spawn} from 'node:child_process';

const STDIO_GRACE_MS = 200;

// detached:true (needed so killGroup below can reach a runaway grandchild —
// see the comment on killGroup) also moves every child into its OWN process
// group, out of the group a plain `kill <ourpid>` SIGTERM would have swept
// them into. That reopened a different hole: launchd stopping this process
// no longer took an in-flight child (e.g. the Reminders EventKit helper)
// down with it (finding #6-followup). Track active groups here so anything
// that owns this process's lifecycle (single-instance's SIGTERM handler) can
// reach them explicitly instead of relying on OS group membership.
const activeGroupPids = new Set();

export function killActiveProcessGroups(signal = 'SIGTERM') {
  for (const pid of activeGroupPids) {
    try { process.kill(-pid, signal); } catch { try { process.kill(pid, signal); } catch {} }
  }
}

export function hasActiveProcessGroups() {
  return activeGroupPids.size > 0;
}

export function runProcess(file, args = [], {input = '', timeoutMs = 15_000, maxOutputBytes = 1_000_000, env = process.env} = {}) {
  if (typeof file !== 'string' || file.length === 0 || !Array.isArray(args)) throw new TypeError('invalid process invocation');
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, {env, stdio: ['pipe', 'pipe', 'pipe'], detached: true});
    if (typeof child.pid === 'number') activeGroupPids.add(child.pid);
    const forgetGroup = () => { if (typeof child.pid === 'number') activeGroupPids.delete(child.pid); };
    const stdout = [];
    const stderr = [];
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let timedOut = false;
    let outputExceeded = false;
    let settled = false;
    let timer;
    let graceTimer;

    // An orphaned grandchild that inherits our stdio pipes can keep them open
    // indefinitely, so a direct child.kill() alone can leave 'close' unfired
    // forever. Killing the whole process group (negative pid) reaches any
    // such descendant too, since detached:true makes this child its leader.
    const killGroup = signal => {
      if (typeof child.pid !== 'number') return;
      try {
        process.kill(-child.pid, signal);
      } catch {
        try { child.kill(signal); } catch {}
      }
    };

    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      clearTimeout(graceTimer);
      forgetGroup();
      resolve(result);
    };
    const collect = (target, chunk, stream) => {
      if (outputExceeded) return;
      const bytes = Buffer.byteLength(chunk);
      if (stream === 'stdout') stdoutBytes += bytes;
      else stderrBytes += bytes;
      if (stdoutBytes + stderrBytes > maxOutputBytes) {
        outputExceeded = true;
        killGroup('SIGKILL');
        return;
      }
      target.push(Buffer.from(chunk));
    };
    child.stdout.on('data', chunk => collect(stdout, chunk, 'stdout'));
    child.stderr.on('data', chunk => collect(stderr, chunk, 'stderr'));
    child.on('error', error => { forgetGroup(); reject(error); });
    child.on('close', (code, signal) => finish({
      code: outputExceeded ? 1 : code,
      signal,
      timedOut,
      outputExceeded,
      stdout: Buffer.concat(stdout).toString('utf8'),
      stderr: Buffer.concat(stderr).toString('utf8'),
    }));
    child.on('exit', (code, signal) => {
      // The process itself has exited, but stdio may still be held open by an
      // orphaned descendant sharing our pipes. Give 'close' a short grace
      // window to fire with complete output; otherwise resolve with whatever
      // was collected so the caller never hangs on a dangling pipe.
      graceTimer = setTimeout(() => finish({
        code: outputExceeded ? 1 : code,
        signal,
        timedOut,
        outputExceeded,
        stdout: Buffer.concat(stdout).toString('utf8'),
        stderr: Buffer.concat(stderr).toString('utf8'),
      }), STDIO_GRACE_MS);
      graceTimer.unref?.();
    });
    child.stdin.on('error', error => {
      if (error.code !== 'EPIPE') reject(error);
    });
    child.stdin.end(input);
    timer = setTimeout(() => {
      timedOut = true;
      killGroup('SIGKILL');
    }, timeoutMs);
    timer.unref?.();
  });
}
