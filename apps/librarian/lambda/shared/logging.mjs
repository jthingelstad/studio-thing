export function logEvent(level, message, fields = {}, service = process.env.LIBRARIAN_SERVICE_NAME || 'weekly-thing-librarian') {
  console.log(JSON.stringify({
    level,
    message,
    service,
    timestamp: Math.floor(Date.now() / 1000),
    ...Object.fromEntries(Object.entries(fields).filter(([, value]) => value !== undefined && value !== null))
  }));
}

export function truthyEnv(name, defaultValue = '0') {
  const value = String(process.env[name] ?? defaultValue).trim().toLowerCase();
  return !['', '0', 'false', 'no', 'off'].includes(value);
}
