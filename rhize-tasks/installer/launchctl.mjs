export function isKnownNotLoaded(result) {
  if (!result || result.code === 0) return false;
  const message = `${result.stderr ?? ''}\n${result.stdout ?? ''}`.trim();
  return result.code === 3 && /(?:Could not find specified service|No such process|service is not loaded|Could not find service)/i.test(message);
}

export async function getLaunchAgentState({run, domain, label}) {
  let result;
  try {
    result = await run('/bin/launchctl', ['print', `${domain}/${label}`], {timeoutMs: 15_000, maxOutputBytes: 64_000});
  } catch {
    throw new Error('launchctl_state_failed');
  }
  if (result?.code === 0) return {loaded: true};
  if (isKnownNotLoaded(result)) return {loaded: false};
  throw new Error('launchctl_state_failed');
}

export async function bootoutIfLoaded({run, domain, plistPath}) {
  let result;
  try {
    result = await run('/bin/launchctl', ['bootout', domain, plistPath], {timeoutMs: 15_000, maxOutputBytes: 64_000});
  } catch {
    throw new Error('launchctl_bootout_failed');
  }
  if (result?.code === 0 || isKnownNotLoaded(result)) return {notLoaded: result.code !== 0};
  throw new Error('launchctl_bootout_failed');
}
