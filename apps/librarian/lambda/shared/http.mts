import { LIBRARIAN_CONTRACT_VERSION } from './librarian-contract.mjs';

export interface LibrarianHttpEvent {
  headers?: Record<string, unknown> | null;
  body?: string | null;
  isBase64Encoded?: boolean;
  requestContext?: {
    requestId?: string;
    http?: { method?: string; sourceIp?: string };
    identity?: { sourceIp?: string };
  };
  httpMethod?: string;
  rawPath?: string;
  path?: string;
}

interface LibrarianRequestContext {
  awsRequestId?: string;
}

export interface LibrarianHttpResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: string;
}

export function allowedOrigins() {
  return String(process.env.ALLOWED_ORIGIN || 'https://weekly.thingelstad.com')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
}

export function normalizeHeaders(headers: Record<string, unknown> = {}): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headers || {}).map(([key, value]) => [key.toLowerCase(), String(value ?? '')])
  );
}

export function corsOrigin(event?: LibrarianHttpEvent | null) {
  const origins = allowedOrigins();
  const origin = String(normalizeHeaders(event?.headers || {}).origin || '');
  if (origin && origins.includes(origin)) return origin;
  return origins[0] || 'https://weekly.thingelstad.com';
}

export function jsonResponse(
  statusCode: number,
  payload: unknown,
  event?: LibrarianHttpEvent | null,
  headers: Record<string, string> = {}
): LibrarianHttpResponse {
  return {
    statusCode,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'x-librarian-contract-version': LIBRARIAN_CONTRACT_VERSION,
      'access-control-allow-origin': corsOrigin(event),
      'access-control-allow-headers': 'content-type, authorization, x-librarian-contract-version',
      'access-control-allow-methods': 'GET,OPTIONS,POST',
      'access-control-expose-headers': 'x-librarian-contract-version, x-request-id',
      ...headers
    },
    body: JSON.stringify(payload)
  };
}

export function parseBody(event?: LibrarianHttpEvent | null): Record<string, unknown> {
  const body = event?.body || '{}';
  const text = event?.isBase64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export function methodAndPath(event?: LibrarianHttpEvent | null) {
  const method = (event?.requestContext?.http?.method || event?.httpMethod || 'GET').toUpperCase();
  const path = (event?.rawPath || event?.path || '/').replace(/\/$/, '') || '/';
  return { method, path };
}

export function eventSummary(event?: LibrarianHttpEvent | null, context?: LibrarianRequestContext | null) {
  const { method, path } = methodAndPath(event);
  return {
    request_id: context?.awsRequestId || event?.requestContext?.requestId || '',
    method,
    path,
    origin: normalizeHeaders(event?.headers || {}).origin
  };
}

export function clientSourceIp(event?: LibrarianHttpEvent | null) {
  return event?.requestContext?.http?.sourceIp || event?.requestContext?.identity?.sourceIp || '';
}

export function userAgent(event?: LibrarianHttpEvent | null) {
  return normalizeHeaders(event?.headers || {})['user-agent'] || '';
}
