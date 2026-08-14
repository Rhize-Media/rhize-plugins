import {connectorError, normalizeError} from './http.mjs';

export const KEYCHAIN = Object.freeze({api: ['media.rhize.tasks.api', 'bearer'], jira: ['media.rhize.tasks.jira', 'email', 'api-token'], google: ['media.rhize.tasks.google', 'client-id', 'client-secret', 'refresh-token'], slack: ['media.rhize.tasks.slack', 'bot-token']});

function check(service, account) { if (typeof service !== 'string' || !service.startsWith('media.rhize.tasks.') || typeof account !== 'string' || !account) throw connectorError('invalid_credential'); }
function resultValue(result) { return typeof result?.stdout === 'string' ? result.stdout.replace(/\n$/, '') : ''; }

export function createKeychain({spawnFile} = {}) {
  if (typeof spawnFile !== 'function') throw new TypeError('spawnFile must be a function');
  async function call(args, input) {
    try {
      const result = await spawnFile('/usr/bin/security', args, {input, timeoutMs: 10_000, maxOutputBytes: 16_384});
      if (!result || result.code !== 0) throw connectorError('keychain', {retryable: false});
      return result;
    } catch (error) { throw normalizeError(error); }
  }
  return {
    async get(service, account) { check(service, account); return resultValue(await call(['find-generic-password', '-s', service, '-a', account, '-w'])); },
    async set(service, account, value) { check(service, account); if (typeof value !== 'string' || !value) throw connectorError('invalid_credential'); await call(['add-generic-password', '-U', '-s', service, '-a', account, '-w'], value); },
    async delete(service, account) { check(service, account); await call(['delete-generic-password', '-s', service, '-a', account]); },
  };
}
