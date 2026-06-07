export function logEvent(level, message, fields = {}, service = process.env.LIBRARIAN_SERVICE_NAME || 'weekly-thing-librarian') {
  console.log(JSON.stringify({
    level,
    message,
    service,
    timestamp: Math.floor(Date.now() / 1000),
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined && value !== null))
  }));
}

function sanitizeErrorMessage(message) {
  return String(message || '')
    .replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, '[email]')
    .replace(/https?:\/\/\S+/gi, '[url]')
    .replace(/\b[A-Za-z0-9_-]{32,}\b/g, '[redacted]')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 360);
}

export function errorFields(error, fields = {}) {
  const name = error?.name || error?.constructor?.name || 'Error';
  const code = error?.code || error?.Code || error?.$metadata?.httpStatusCode;
  const message = sanitizeErrorMessage(error?.message);
  return {
    ...fields,
    error_type: error?.constructor?.name || name,
    error_name: name,
    error_code: code,
    error_message: message || undefined
  };
}

export function truthyEnv(name, defaultValue = '0') {
  const value = String(process.env[name] ?? defaultValue).trim().toLowerCase();
  return !['', '0', 'false', 'no', 'off'].includes(value);
}
