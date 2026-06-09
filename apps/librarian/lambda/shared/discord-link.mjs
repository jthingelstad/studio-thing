import crypto from 'node:crypto';
import { GetItemCommand, PutItemCommand } from '@aws-sdk/client-dynamodb';
import { dynamodb } from './aws-clients.mjs';
import { entitlementsForSubscriber } from './conversation-modes.mjs';
import { fetchSubscriber, subscriberStatus } from './buttondown.mjs';
import { emailHash, normalizeEmail, stableHash } from './session.mjs';

export const DISCORD_LINK_TTL_SECONDS = 10 * 60;
export const DISCORD_USER_ID_RE = /^[A-Za-z0-9_:.-]{1,64}$/;

export function dynamoString(value) {
  return { S: String(value || '') };
}

export function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

export function discordUserHash(discordUserId) {
  const value = String(discordUserId || '').trim();
  return DISCORD_USER_ID_RE.test(value) ? stableHash(value) : '';
}

export function normalizeDiscordIdentity(input = {}) {
  const username = String(input.username || input.name || '').trim().slice(0, 80);
  const globalName = String(input.global_name || input.globalName || input.display_name || '').trim().slice(0, 80);
  const displayName = String(input.display_name || input.displayName || globalName || username || 'Discord member').trim().slice(0, 80);
  return {
    username,
    global_name: globalName,
    display_name: displayName,
    guild_id: String(input.guild_id || input.guildId || '').trim().slice(0, 80)
  };
}

export function isSupportingEntitlement(entitlements = []) {
  const set = new Set(Array.isArray(entitlements) ? entitlements : []);
  return set.has('supporting_member') || set.has('owner');
}

export function createLinkState() {
  return crypto.randomBytes(18).toString('base64url');
}

export function createLinkCode() {
  let code = '';
  while (code.length < 8) {
    code += crypto.randomBytes(5).toString('base64url').replace(/[-_]/g, '').toUpperCase();
  }
  return code.slice(0, 8);
}

export function linkHash(value) {
  return stableHash(String(value || '').trim());
}

export function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

export function discordStateKey(state) {
  return { pk: dynamoString(`discord_link_state#${linkHash(state)}`), sk: dynamoString('discord_link') };
}

export function discordCodeKey(code) {
  return { pk: dynamoString(`discord_link_code#${linkHash(code)}`), sk: dynamoString('discord_link') };
}

export function discordConnectionKeyFromHash(userHash) {
  return { pk: dynamoString(`discord_user#${userHash}`), sk: dynamoString('connection') };
}

export function discordConnectionKey(discordUserId) {
  const userHash = discordUserHash(discordUserId);
  return userHash ? discordConnectionKeyFromHash(userHash) : null;
}

export function readDiscordConnectionItem(item = {}) {
  if (!item?.pk) return null;
  const entitlements = (() => {
    try {
      const parsed = JSON.parse(item.entitlements_json?.S || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  })();
  return {
    subscriber_hash: item.subscriber_hash?.S || '',
    email: normalizeEmail(item.email?.S || ''),
    email_hash: item.email_hash?.S || '',
    discord_user_hash: item.discord_user_hash?.S || '',
    username: item.username?.S || '',
    global_name: item.global_name?.S || '',
    display_name: item.display_name?.S || item.global_name?.S || item.username?.S || '',
    guild_id: item.guild_id?.S || '',
    connected_at: item.connected_at?.S || '',
    last_verified_at: item.last_verified_at?.S || '',
    entitlements
  };
}

export async function loadDiscordConnection(discordUserId) {
  const tableName = process.env.TABLE_NAME;
  const key = discordConnectionKey(discordUserId);
  if (!tableName || !key) return null;
  const response = await dynamodb.send(new GetItemCommand({
    TableName: tableName,
    Key: key,
    ConsistentRead: true
  }));
  return readDiscordConnectionItem(response?.Item);
}

export async function putDiscordConnection(connection = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) throw new Error('TABLE_NAME is required');
  const userHash = String(connection.discord_user_hash || '').trim();
  if (!userHash) throw new Error('discord_user_hash is required');
  const entitlements = Array.isArray(connection.entitlements) ? connection.entitlements : [];
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      ...discordConnectionKeyFromHash(userHash),
      subscriber_hash: dynamoString(connection.subscriber_hash || ''),
      email: dynamoString(normalizeEmail(connection.email || '')),
      email_hash: dynamoString(connection.email_hash || emailHash(connection.email || '')),
      discord_user_hash: dynamoString(userHash),
      username: dynamoString(connection.username || ''),
      global_name: dynamoString(connection.global_name || ''),
      display_name: dynamoString(connection.display_name || connection.global_name || connection.username || ''),
      guild_id: dynamoString(connection.guild_id || ''),
      connected_at: dynamoString(connection.connected_at || ''),
      last_verified_at: dynamoString(connection.last_verified_at || connection.connected_at || ''),
      entitlements_json: dynamoString(JSON.stringify(entitlements)),
      ttl: dynamoNumber(connection.ttl || nowSeconds() + 365 * 86400)
    }
  }));
}

export async function currentEntitlementsForEmail(email) {
  const normalized = normalizeEmail(email);
  if (!normalized) return { ok: false, status: 'invalid', entitlements: [], subscriber: null };
  const subscriber = await fetchSubscriber(normalized);
  const status = subscriberStatus(subscriber);
  if (!['active', 'premium'].includes(status)) {
    return { ok: false, status, entitlements: [], subscriber };
  }
  const entitlements = entitlementsForSubscriber({ email: normalized, subscriber, status });
  return {
    ok: true,
    status,
    entitlements,
    subscriber,
    supporting_member: isSupportingEntitlement(entitlements)
  };
}
