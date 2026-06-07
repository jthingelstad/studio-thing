import crypto from 'node:crypto';

export const DEFAULT_CONVERSATION_MODE = 'thingy';

const MODE_DEFINITIONS = {
  thingy: {
    id: 'thingy',
    label: 'Thingy',
    description: 'Explore Jamie Thingelstad\'s published archive with the default archive agent.',
    required_entitlement: 'reader'
  },
  research_guide: {
    id: 'research_guide',
    label: 'Research Guide',
    description: 'Deeper synthesis, timelines, and reading paths for supporting members.',
    required_entitlement: 'supporting_member'
  },
  thought_partner: {
    id: 'thought_partner',
    label: 'Thought Partner',
    description: 'A more reflective mode for Jamie to interrogate patterns in his published work.',
    required_entitlement: 'owner'
  },
  trusted_circle: {
    id: 'trusted_circle',
    label: 'Trusted Circle',
    description: 'A warmer, closer-reader posture for explicitly invited people.',
    required_entitlement: 'trusted_circle'
  }
};

const DEFAULT_OWNER_EMAIL = 'jamie@thingelstad.com';

function normalizeEmail(value) {
  return String(value || '').trim().toLowerCase();
}

function emailHash(value) {
  return crypto.createHash('sha256').update(normalizeEmail(value)).digest('hex');
}

function csv(value) {
  return String(value || '')
    .split(/[,\s]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function subscriberTagNames(subscriber) {
  const tags = Array.isArray(subscriber?.tags) ? subscriber.tags : [];
  const names = [];
  for (const tag of tags) {
    const name = typeof tag === 'string' ? tag : tag?.name;
    const clean = String(name || '').trim().toLowerCase();
    if (clean && !names.includes(clean)) names.push(clean);
  }
  return names;
}

export function ownerEmailHashes() {
  const emails = csv(process.env.THINGY_OWNER_EMAILS || DEFAULT_OWNER_EMAIL).map(emailHash);
  const hashes = csv(process.env.THINGY_OWNER_EMAIL_HASHES);
  return Array.from(new Set([...emails, ...hashes].map((value) => value.toLowerCase())));
}

export function isOwnerEmail(email) {
  return ownerEmailHashes().includes(emailHash(email));
}

export function isOwnerSubscriberHash(subscriberHash) {
  return ownerEmailHashes().includes(String(subscriberHash || '').trim().toLowerCase());
}

export function entitlementsForSubscriber({ email = '', subscriber = null, status = '' } = {}) {
  const normalizedStatus = String(status || subscriber?.type || '').trim().toLowerCase();
  const tags = subscriberTagNames(subscriber);
  const entitlements = new Set(['reader']);

  if (normalizedStatus === 'premium' || tags.includes('thingy-supporting-member')) {
    entitlements.add('supporting_member');
  }
  if (tags.some((tag) => ['thingy-trusted-circle', 'thingy-family', 'thingy-close-friends'].includes(tag))) {
    entitlements.add('trusted_circle');
  }
  if (isOwnerEmail(email) || tags.includes('thingy-owner')) {
    entitlements.add('owner');
    entitlements.add('supporting_member');
    entitlements.add('trusted_circle');
  }

  return Array.from(entitlements);
}

export function normalizeConversationMode(value) {
  const key = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return MODE_DEFINITIONS[key] ? key : DEFAULT_CONVERSATION_MODE;
}

export function canUseConversationMode(mode, entitlements = []) {
  const normalized = normalizeConversationMode(mode);
  const required = MODE_DEFINITIONS[normalized]?.required_entitlement || 'reader';
  return new Set(entitlements || []).has(required);
}

export function resolveConversationMode(value, entitlements = []) {
  const normalized = normalizeConversationMode(value);
  return canUseConversationMode(normalized, entitlements) ? normalized : DEFAULT_CONVERSATION_MODE;
}

export function conversationModeDefinition(mode) {
  return MODE_DEFINITIONS[normalizeConversationMode(mode)] || MODE_DEFINITIONS[DEFAULT_CONVERSATION_MODE];
}

export function availableConversationModes(entitlements = []) {
  return Object.values(MODE_DEFINITIONS)
    .filter((mode) => canUseConversationMode(mode.id, entitlements))
    .map((mode) => ({ ...mode }));
}

export function entitlementContext(entitlements = []) {
  const values = Array.from(new Set((entitlements || []).map((item) => String(item || '').trim()).filter(Boolean)));
  return values.length ? values : ['reader'];
}

export function conversationModePrompt(mode) {
  const normalized = normalizeConversationMode(mode);
  if (normalized === 'thought_partner') {
    return [
      'Conversation mode: Thought Partner.',
      'This mode is for Jamie, the author of the archive, using the published archive only.',
      'Respond as a candid, constructive thought partner rather than a docent for a general reader.',
      'Use the archive to reflect patterns back to Jamie, identify tensions or changes over time, name assumptions, and ask sharper follow-up questions when useful.',
      'Push back gently when the evidence supports it, but stay grounded in retrieved sources and do not pretend to know unpublished motives or private context.',
      'Do not introduce private-draft or hidden-corpus claims; this mode changes posture, not archive scope.'
    ].join('\n');
  }
  if (normalized === 'research_guide') {
    return [
      'Conversation mode: Research Guide.',
      'Favor deeper synthesis, timelines, comparisons, and guided reading paths through the published archive.',
      'Still stay grounded in retrieved evidence and avoid general-purpose answers outside the archive.'
    ].join('\n');
  }
  if (normalized === 'trusted_circle') {
    return [
      'Conversation mode: Trusted Circle.',
      'Use a warmer closer-reader tone while staying grounded in Jamie\'s published archive.',
      'Do not assume private facts or privileged access.'
    ].join('\n');
  }
  return [
    'Conversation mode: Thingy.',
    'Use the default public archive-agent posture for an authenticated reader.'
  ].join('\n');
}
