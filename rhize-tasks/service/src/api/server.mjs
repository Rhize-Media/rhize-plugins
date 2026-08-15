import http from 'node:http';
import {createRouter} from './routes.mjs';
import {publicError} from './auth.mjs';

function send(response, status, body) {
  const data = `${JSON.stringify(body)}\n`;
  response.writeHead(status, {'content-type': 'application/json; charset=utf-8', 'content-length': Buffer.byteLength(data), 'cache-control': 'no-store', 'x-content-type-options': 'nosniff'});
  response.end(data);
}

export function createServer(context) {
  if (context?.host !== '127.0.0.1') throw new TypeError('server must bind to loopback 127.0.0.1');
  const route = createRouter(context);
  return http.createServer(async (request, response) => {
    const remote = request.socket.remoteAddress;
    if (remote && !['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(remote)) return send(response, 403, {error: {kind: 'loopback_required', status: 403}});
    try { const result = await route(request); send(response, result.status, result.body); } catch (error) { const result = publicError(error); if (!response.headersSent) send(response, result.status, result.body); else response.destroy(); }
  });
}
