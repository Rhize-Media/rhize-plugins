function output(result) {
  return `${result?.stderr ?? ''}\n${result?.stdout ?? ''}`.trim();
}

export function isKnownPrintNotLoaded(result, {domain, label} = {}) {
  if (![3, 113].includes(result?.code) || typeof domain !== 'string' || typeof label !== 'string') return false;
  const domainMatch = /^gui\/(\d+)$/.exec(domain);
  if (!domainMatch) return false;
  const expected = `Could not find service "${label}" in domain for user gui: ${domainMatch[1]}`;
  const message = output(result);
  return message === expected || message === `Bad request.\n${expected}`;
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

export async function getLaunchAgentState({run, domain, label}) {
  let result;
  try {
    result = await run('/bin/launchctl', ['print', `${domain}/${label}`], {timeoutMs: 15_000, maxOutputBytes: 64_000});
  } catch {
    throw new Error('launchctl_state_failed');
  }
  if (result?.code === 0) return {loaded: true, configurationPath: configurationPath(result.stdout)};
  if (isKnownPrintNotLoaded(result, {domain, label})) return {loaded: false, configurationPath: null};
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

export function bootoutIfLoaded({run, domain, plistPath}) {
  return bootout(run, ['bootout', domain, plistPath]);
}

export function bootoutServiceIfLoaded({run, domain, label}) {
  return bootout(run, ['bootout', `${domain}/${label}`]);
}
