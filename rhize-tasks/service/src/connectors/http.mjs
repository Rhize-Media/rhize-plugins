const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_MAX_BYTES = 1_000_000;

export function connectorError(kind = 'connector_error', {retryable = false, ambiguous = false, status = null} = {}) {
  return {kind, retryable, ambiguous, status: Number.isInteger(status) ? status : null};
}

export function normalizeError(error, {afterWrite = false} = {}) {
  if (error?.kind) return connectorError(error.kind, error);
  const status = Number.isInteger(error?.status) ? error.status : null;
  if (error?.name === 'AbortError') return connectorError('timeout', {retryable: true, ambiguous: afterWrite, status});
  if (status !== null) return connectorError(status === 401 || status === 403 ? 'authorization' : 'http', {retryable: status >= 500 || status === 429, ambiguous: afterWrite && (status >= 500 || status === 429), status});
  return connectorError('transport', {retryable: true, ambiguous: afterWrite});
}

export function unsupported() { throw connectorError('unsupported'); }

export function createHttpTransport({fetch: fetchImpl = globalThis.fetch, timeoutMs = DEFAULT_TIMEOUT_MS, maxBytes = DEFAULT_MAX_BYTES} = {}) {
  if (typeof fetchImpl !== 'function') throw new TypeError('fetch must be a function');
  return async ({url, method = 'GET', headers = {}, body, signal, expectJson = true}) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort(); signal?.addEventListener?.('abort', abort, {once: true});
    try {
      const response = await fetchImpl(url, {method, headers, body, signal: controller.signal});
      const length = Number(response.headers?.get?.('content-length') ?? 0);
      if (length > maxBytes) throw connectorError('response_too_large', {status: response.status});
      let text = '';
      if (response.body?.getReader) {
        const reader = response.body.getReader(); let bytes = 0; const chunks = [];
        while (true) { const {done, value} = await reader.read(); if (done) break; bytes += value.byteLength; if (bytes > maxBytes) { await reader.cancel(); controller.abort(); throw connectorError('response_too_large', {status: response.status}); } chunks.push(value); }
        text = new TextDecoder().decode(Buffer.concat(chunks));
      } else { text = await response.text(); if (Buffer.byteLength(text) > maxBytes) throw connectorError('response_too_large', {status: response.status}); }
      const contentType = response.headers?.get?.('content-type') ?? '';
      if (!response.ok) throw connectorError(response.status === 401 || response.status === 403 ? 'authorization' : response.status === 429 ? 'rate_limited' : 'http', {retryable: response.status >= 500 || response.status === 429, status: response.status});
      let parsed = text;
      if (expectJson && !/application\/json/i.test(contentType)) throw connectorError('invalid_content_type', {status: response.status});
      if (expectJson && !text) parsed = null;
      else if (expectJson) { try { parsed = JSON.parse(text); } catch { throw connectorError('invalid_json', {status: response.status}); } }
      return {status: response.status, headers: response.headers, body: parsed};
    } catch (error) { throw normalizeError(error, {afterWrite: method !== 'GET' && method !== 'HEAD'}); }
    finally { clearTimeout(timer); signal?.removeEventListener?.('abort', abort); }
  };
}
