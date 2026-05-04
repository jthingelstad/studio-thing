export function allowedOrigins() {
  return String(process.env.ALLOWED_ORIGIN || 'https://weekly.thingelstad.com')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

export function normalizeHeaders(headers = {}) {
  return Object.fromEntries(Object.entries(headers || {}).map(([key, value]) => [key.toLowerCase(), value]));
}

export function corsOrigin(event) {
  const origins = allowedOrigins();
  const origin = String(normalizeHeaders(event?.headers || {}).origin || '');
  if (origin && origins.includes(origin)) return origin;
  return origins[0] || 'https://weekly.thingelstad.com';
}

export function jsonResponse(statusCode, payload, event, headers = {}) {
  return {
    statusCode,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': corsOrigin(event),
      'access-control-allow-headers': 'content-type, authorization',
      'access-control-allow-methods': 'GET,OPTIONS,POST',
      ...headers
    },
    body: JSON.stringify(payload)
  };
}

export function parseBody(event) {
  const body = event?.body || '{}';
  const text = event?.isBase64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function methodAndPath(event) {
  const method = (event?.requestContext?.http?.method || event?.httpMethod || 'GET').toUpperCase();
  const path = (event?.rawPath || event?.path || '/').replace(/\/$/, '') || '/';
  return { method, path };
}

export function eventSummary(event, context) {
  const { method, path } = methodAndPath(event);
  return {
    request_id: context?.awsRequestId || event?.requestContext?.requestId || '',
    method,
    path,
    origin: normalizeHeaders(event?.headers || {}).origin
  };
}

export function clientSourceIp(event) {
  return event?.requestContext?.http?.sourceIp || event?.requestContext?.identity?.sourceIp || '';
}

export function userAgent(event) {
  return normalizeHeaders(event?.headers || {})['user-agent'] || '';
}
