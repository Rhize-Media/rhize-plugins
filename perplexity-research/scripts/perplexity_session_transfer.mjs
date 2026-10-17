// Host-side browser adapter. Never run in a page or return cookie values to the caller.
import * as crypto from 'node:crypto';
import * as fs from 'node:fs/promises';
import path from 'node:path';

export async function transferSession(descriptor, send) {
  let temporary;
  let stage = 'descriptor';
  try {
    if (descriptor.status !== 'waiting' || descriptor.origin !== 'https://www.perplexity.ai' ||
        !/^[0-9a-f-]{36}$/.test(descriptor.transfer_id) ||
        !(descriptor.expires_at > Date.now() / 1000 && descriptor.expires_at <= Date.now() / 1000 + 305) ||
        !path.isAbsolute(descriptor.payload_path) || path.basename(descriptor.payload_path) !== 'payload.json') throw Error();
    const directory = path.dirname(descriptor.payload_path);
    const owner = (await fs.lstat(directory)).uid;
    for (let p = directory; ; p = path.dirname(p)) {
      const info = await fs.lstat(p);
      if (!info.isDirectory() || info.isSymbolicLink() ||
          (p === directory && (info.mode & 0o077))) throw Error();
      if (p === path.dirname(p)) break;
    }
    const current = async () => {
      const filename = path.join(directory, 'session.json');
      const info = await fs.lstat(filename);
      if (!info.isFile() || info.isSymbolicLink() || info.uid !== owner ||
          info.mode & 0o077 || info.nlink !== 1 || info.size > 8192) throw Error();
      const state = JSON.parse(await fs.readFile(filename, 'utf8'));
      if (state.status !== 'waiting' || state.transfer_id !== descriptor.transfer_id ||
          state.public_key !== descriptor.public_key || state.payload_path !== descriptor.payload_path ||
          state.expires_at !== descriptor.expires_at) throw Error();
    };
    await current();
    stage = 'browser_access';
    const response = await send('Network.getCookies', {urls: ['https://www.perplexity.ai/']});
    stage = 'cookie_selection';
    const scoped = response.cookies.filter(c => ['perplexity.ai', '.perplexity.ai', 'www.perplexity.ai'].includes(c.domain) &&
      c.secure && c.path === '/' && (c.expires === -1 || c.expires > Date.now() / 1000));
    const accounts = scoped.filter(c => c.name === '__Host-pplx-last-active-account');
    if (accounts.length > 1) throw Error();
    const account = accounts[0]?.value ?? '';
    const names = new Set(['__Host-pplx-last-active-account', `__Secure-pplx.session.${account}`,
      'next-auth.session-token', '__Secure-next-auth.session-token', 'next-auth.csrf-token', '__Host-next-auth.csrf-token']);
    const cookies = Object.create(null);
    for (const cookie of scoped.filter(c => names.has(c.name))) {
      if (Object.hasOwn(cookies, cookie.name) || !/^[\x21-\x7e]+$/.test(cookie.value) || cookie.value.includes(';')) throw Error();
      cookies[cookie.name] = cookie.value;
    }
    if (!Object.keys(cookies).some(name => name.includes('session'))) throw Error();
    stage = 'encryption';
    const key = crypto.randomBytes(32), iv = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    cipher.setAAD(Buffer.from(descriptor.transfer_id));
    const ciphertext = Buffer.concat([cipher.update(JSON.stringify(cookies), 'utf8'), cipher.final(), cipher.getAuthTag()]);
    const envelope = JSON.stringify({transfer_id: descriptor.transfer_id, iv: iv.toString('base64'),
      key: crypto.publicEncrypt({key: descriptor.public_key, oaepHash: 'sha256', padding: crypto.constants.RSA_PKCS1_OAEP_PADDING}, key).toString('base64'),
      ciphertext: ciphertext.toString('base64')});
    key.fill(0);
    if (envelope.length > 131072 || descriptor.expires_at <= Date.now() / 1000) throw Error();
    stage = 'publication';
    temporary = path.join(directory, `.encrypted-${crypto.randomUUID()}`);
    await fs.writeFile(temporary, envelope, {mode: 0o600, flag: 'wx'});
    await current();
    try { await fs.lstat(descriptor.payload_path); throw new Error('exists'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await fs.rename(temporary, descriptor.payload_path);
    temporary = undefined;
    return {status: 'encrypted_handoff_sent'};
  } catch (error) {
    const code = ['EPERM', 'EACCES'].includes(error?.code) ? `_${error.code}` : '';
    throw new Error(`perplexity_session_${stage}_failed${code}`);
  } finally {
    if (temporary) await fs.unlink(temporary).catch(() => {});
  }
}
