const DEFAULT_THINGY_TINYLYTICS_SITE_UID = 'u5bRAyyJvMXUrz6zbTz5';
const TINYLYTICS_PIXEL_BASE = 'https://tinylytics.app/pixel';

function envValue(...names) {
  for (const name of names) {
    const value = String(process.env[name] || '').trim();
    if (value) return value;
  }
  return '';
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export function tinylyticsEmailSiteUid() {
  return envValue('THINGY_TINYLYTICS_EMAIL_SITE_UID', 'TINYLYTICS_SITE_UID') || DEFAULT_THINGY_TINYLYTICS_SITE_UID;
}

export function tinylyticsPixelUrl(path, { siteUid = tinylyticsEmailSiteUid() } = {}) {
  const uid = String(siteUid || '').trim();
  if (!uid) return '';
  const rawPath = String(path || '').trim() || '/email/thingy';
  const normalizedPath = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
  const params = new URLSearchParams({ path: normalizedPath });
  return `${TINYLYTICS_PIXEL_BASE}/${encodeURIComponent(uid)}.gif?${params.toString()}`;
}

export function tinylyticsPixelHtml(path, options = {}) {
  const url = tinylyticsPixelUrl(path, options);
  if (!url) return '';
  return `<img src="${escapeHtml(url)}" width="1" height="1" alt="" style="display:block;width:1px;height:1px;border:0;outline:0;text-decoration:none;opacity:0;">`;
}
