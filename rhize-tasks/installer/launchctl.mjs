import {access} from 'node:fs/promises';

function output(result) {
  return `${result?.stderr ?? ''}\n${result?.stdout ?? ''}`.trim();
}

export function isKnownBootoutNotLoaded(result) {
  if (result?.code !== 3) return false;
  const message = output(result);
  return message === 'Boot-out failed: 3: No such process' || message === 'Could not find specified service';
}

function configurationPath(stdout) {
  if (typeof stdout !== 'string') return null;
  const match = /(?:^|\n)\s*(?:path|origin)\s*=\s*(.+?)\s*(?:\n|$)/.exec(stdout);
  if (!match) return null;
  const value = match[1].replace(/^"|"$/g, '');
  return value.startsWith('/') ? value : null;
}

const defaultSleep = ms => new Promise(resolve => setTimeout(resolve, ms));

// `launchctl print`'s "not loaded" *message* is not a stable contract — one
// wording change in a macOS point release used to turn a routine not-loaded
// response into launchctl_state_failed on a clean Mac (finding #20). But
// treating literally any non-zero exit as "not loaded" went too far the
// other way (finding #2-followup): a signal-killed, timed-out, or
// spawn-failed `print` tells us nothing, and install() could then swap the
// runtime under a job we never actually confirmed was stopped — recreating
// the exact race finding #21 fixed. So this is tri-state:
//   - exit 0                                  -> loaded
//   - a clean (non-signal, non-timeout) nonzero exit -> not loaded
//   - signal-killed / timed out / spawn error / null exit code -> unknown
// "Unknown" retries briefly (transient launchctl hiccups are common) and
// then throws rather than guessing either way.
export async function getLaunchAgentState({run, domain, label}, {retries = 2, retryDelayMs = 200, sleep = defaultSleep} = {}) {
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    let result;
    try {
      result = await run('/bin/launchctl', ['print', `${domain}/${label}`], {timeoutMs: 15_000, maxOutputBytes: 64_000});
    } catch {
      result = null;
    }
    if (result?.code === 0) return {loaded: true, configurationPath: configurationPath(result.stdout)};
    const uncertain = !result || result.timedOut === true || result.signal != null || result.code === null;
    if (!uncertain) return {loaded: false, configurationPath: null};
    if (attempt < retries) await sleep(retryDelayMs);
  }
  throw new Error('launchctl_state_failed');
}

async function bootout(run, args) {
  let result;
  try {
    result = await run('/bin/launchctl', args, {timeoutMs: 15_000, maxOutputBytes: 64_000});
  } catch {
    throw new Error('launchctl_bootout_failed');
  }
  if (result?.code === 0 || isKnownBootoutNotLoaded(result)) return {notLoaded: result.code !== 0};
  throw new Error('launchctl_bootout_failed');
}

// A bootout against a plist path that no longer exists on disk does not
// reliably return either of isKnownBootoutNotLoaded's recognized messages,
// so it used to hard-fail before any uninstall cleanup ran (finding #19).
// A half-installed/half-removed state is exactly the case uninstall needs
// to recover from — but launchd holds a bootstrapped job in memory
// independent of the plist file that created it, so a missing file is not
// proof the job is gone (finding #3-followup). Fall back to the
// label-addressed form, which needs no file on disk, and treat "no such
// service" as proof there is nothing left to stop.
export async function bootoutIfLoaded({run, domain, plistPath, label}) {
  try {
    await access(plistPath);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    if (typeof label !== 'string' || !label) throw new TypeError('invalid_bootout_label');
    return bootoutServiceIfLoaded({run, domain, label});
  }
  return bootout(run, ['bootout', domain, plistPath]);
}

export function bootoutServiceIfLoaded({run, domain, label}) {
  return bootout(run, ['bootout', `${domain}/${label}`]);
}
