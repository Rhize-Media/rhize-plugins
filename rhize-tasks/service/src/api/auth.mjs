import {timingSafeEqual} from 'node:crypto';

export const MAX_JSON_BYTES = 64 * 1024;

export class ApiError extends Error {
  constructor(kind, status = 400) {
    super(kind);
    this.kind = kind;
    this.status = status;
  }
}

function equalSecret(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false;
  const a = Buffer.from(left); const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function requireBearer(request, getToken) {
  if (typeof getToken !== 'function') throw new ApiError('authentication_unavailable', 503);
  const authorization = request.headers.authorization;
  if (typeof authorization !== 'string' || !authorization.startsWith('Bearer ')) throw new ApiError('unauthorized', 401);
  let token;
  try { token = await getToken(); } catch { throw new ApiError('authentication_unavailable', 503); }
  if (typeof token !== 'string' || token.length < 16 || !equalSecret(authorization.slice(7), token)) throw new ApiError('unauthorized', 401);
}

export function exactObject(value, keys, {required = keys} = {}) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new ApiError('invalid_json_object');
  if (Object.keys(value).some(key => !keys.includes(key)) || required.some(key => !Object.hasOwn(value, key))) throw new ApiError('unknown_or_missing_fields');
  return value;
}

export async function readJson(request, {maxBytes = MAX_JSON_BYTES} = {}) {
  if (!/^application\/json(?:\s*;|$)/i.test(request.headers['content-type'] ?? '')) throw new ApiError('content_type_required', 415);
  const chunks = []; let bytes = 0;
  for await (const chunk of request) {
    bytes += chunk.length;
    if (bytes > maxBytes) throw new ApiError('request_too_large', 413);
    chunks.push(chunk);
  }
  if (bytes === 0) throw new ApiError('json_body_required');
  let value;
  try { value = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new ApiError('invalid_json'); }
  return exactObject(value, Object.keys(value));
}

const secretKey = /authorization|token|secret|password|credential|cookie/i;
const secretValue = /(?:Bearer\s+|Basic\s+)[A-Za-z0-9+/=_-]+/gi;

export function sanitize(value, seen = new WeakSet()) {
  if (typeof value === 'string') return value.replace(secretValue, '[redacted]');
  if (value === null || typeof value !== 'object') return value;
  if (seen.has(value)) return '[redacted]';
  seen.add(value);
  const result = Array.isArray(value) ? value.map(item => sanitize(item, seen)) : Object.fromEntries(Object.entries(value).filter(([key]) => !secretKey.test(key)).map(([key, item]) => [key, sanitize(item, seen)]));
  seen.delete(value);
  return result;
}

export function publicError(error) {
  if (error instanceof ApiError) return {status: error.status, body: {error: {kind: error.kind, status: error.status}}};
  if (error instanceof RangeError && /revision/i.test(error.message)) return {status: 409, body: {error: {kind: 'revision_conflict', status: 409}}};
  if (error instanceof TypeError || error instanceof SyntaxError) return {status: 400, body: {error: {kind: 'invalid_request', status: 400}}};
  return {status: 500, body: {error: {kind: 'internal_error', status: 500}}};
}
