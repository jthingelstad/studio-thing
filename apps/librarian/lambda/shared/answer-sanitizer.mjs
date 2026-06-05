const WT_ARCHIVE_URL_RE = /https?:\/\/weekly\.thingelstad\.com\/archive\/(\d+)\/?/gi;
const WT_ARCHIVE_PATH_RE = /`?\/archive\/(\d+)\/`?/gi;
const RAW_URL_RE = /(?<!\]\()https?:\/\/[^\s<>)]+/gi;
const PROCESS_NARRATION_RE = /\b(?:let me\s+(?:pull|look|search|check|find|tell)|i have (?:everything|what) i need|i found enough|i can now answer|i'll\s+(?:pull|look|search|check|find))\b/i;

function cleanSpacing(value) {
  return String(value || '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/ +([,.;:!?])/g, '$1')
    .trim();
}

function stripLeadingProcessNarration(value) {
  const blocks = String(value || '').split(/\n{2,}/);
  while (blocks.length && PROCESS_NARRATION_RE.test(blocks[0])) {
    blocks.shift();
  }
  return blocks.join('\n\n').replace(/^(?:-{3,}|\*{3,}|_{3,})\s*/g, '');
}

export function sanitizeAnswerProse(answer) {
  let text = String(answer || '');
  if (!text) return '';

  text = stripLeadingProcessNarration(text);

  text = text
    .replace(/(?:^|[ \t])(?:The\s+)?(?:archive\s+)?URL\s+is\s+`?\/archive\/\d+\/`?\.?/gim, '')
    .replace(/(?:^|[ \t])(?:The\s+)?(?:archive\s+)?URL\s+is\s+https?:\/\/weekly\.thingelstad\.com\/archive\/\d+\/?\.?/gim, '')
    .replace(WT_ARCHIVE_URL_RE, 'WT$1')
    .replace(WT_ARCHIVE_PATH_RE, 'WT$1')
    .replace(RAW_URL_RE, '');

  return cleanSpacing(text);
}
