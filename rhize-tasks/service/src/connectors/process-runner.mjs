import {spawn} from 'node:child_process';

export function runProcess(file, args = [], {input = '', timeoutMs = 15_000, maxOutputBytes = 1_000_000, env = process.env} = {}) {
  if (typeof file !== 'string' || file.length === 0 || !Array.isArray(args)) throw new TypeError('invalid process invocation');
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, {env, stdio: ['pipe', 'pipe', 'pipe']});
    const stdout = [];
    const stderr = [];
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let timedOut = false;
    let outputExceeded = false;
    let settled = false;
    let timer;

    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const collect = (target, chunk, stream) => {
      if (outputExceeded) return;
      const bytes = Buffer.byteLength(chunk);
      if (stream === 'stdout') stdoutBytes += bytes;
      else stderrBytes += bytes;
      if (stdoutBytes + stderrBytes > maxOutputBytes) {
        outputExceeded = true;
        child.kill('SIGKILL');
        return;
      }
      target.push(Buffer.from(chunk));
    };
    child.stdout.on('data', chunk => collect(stdout, chunk, 'stdout'));
    child.stderr.on('data', chunk => collect(stderr, chunk, 'stderr'));
    child.on('error', reject);
    child.on('close', (code, signal) => finish({
      code: outputExceeded ? 1 : code,
      signal,
      timedOut,
      outputExceeded,
      stdout: Buffer.concat(stdout).toString('utf8'),
      stderr: Buffer.concat(stderr).toString('utf8'),
    }));
    child.stdin.on('error', error => {
      if (error.code !== 'EPIPE') reject(error);
    });
    child.stdin.end(input);
    timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGKILL');
    }, timeoutMs);
    timer.unref?.();
  });
}
