import http from 'node:http';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRouter} from './routes.mjs';
import {publicError} from './auth.mjs';

const assets = new Map([['/', ['index.html', 'text/html; charset=utf-8']], ['/app.js', ['app.js', 'text/javascript; charset=utf-8']], ['/styles.css', ['styles.css', 'text/css; charset=utf-8']]]);
const dashboardRoot = fileURLToPath(new URL('../../../dashboard/', import.meta.url));

function send(response, status, body, headers = {}) {
  const data = `${JSON.stringify(body)}\n`;
  response.writeHead(status, {'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(data), 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', ...headers});
  response.end(data);
}

async function sendAsset(response, pathname, root) {
  const [name, contentType] = assets.get(pathname); const data = await readFile(path.join(root, name));
  response.writeHead(200, {'content-type': contentType, 'content-length': data.length, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'content-security-policy': "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"}); response.end(data);
}

export function createServer(context) {
  if (context?.host !== '127.0.0.1') throw new TypeError('server must bind to loopback 127.0.0.1');
  const route = createRouter(context);
  return http.createServer(async (request, response) => {
    const remote = request.socket.remoteAddress;
    // Fail closed: a missing remote address is not proof of a loopback peer, it just means we
    // don't know — the previous `if (remote && ...)` let an unknown remote skip the check.
    if (!remote || !['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(remote)) return send(response, 403, {error: {kind: 'loopback_required', status: 403}});
    // Validate Host against the actual port this connection was accepted on (not a config
    // value) so DNS rebinding or a crafted Host header can't reach the router under a
    // different name, while staying correct for tests that bind an ephemeral port.
    if (request.headers.host !== `127.0.0.1:${request.socket.localPort}`) return send(response, 403, {error: {kind: 'invalid_host', status: 403}});
    try { const rawPath = request.url?.split('?')[0] ?? ''; if (assets.has(rawPath)) { await sendAsset(response, rawPath, context.dashboardRoot ?? dashboardRoot); return; } const result = await route(request); send(response, result.status, result.body, result.headers); } catch (error) { const result = publicError(error); if (!response.headersSent) send(response, result.status, result.body); else response.destroy(); }
  });
}
