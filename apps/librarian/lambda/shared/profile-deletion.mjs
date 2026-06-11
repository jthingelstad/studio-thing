import { BatchWriteItemCommand, GetItemCommand, PutItemCommand, QueryCommand } from '@aws-sdk/client-dynamodb';
import { DeleteObjectCommand } from '@aws-sdk/client-s3';
import { dynamodb, s3 } from './aws-clients.mjs';
import { errorFields, logEvent } from './logging.mjs';
import { dynamoNumber, dynamoString, fromDynamoAttr } from './user-conversations.mjs';

const PROFILE_DELETION_SK = 'profile-deleted';
const EMAIL_HASH_INDEX = 'EmailHashIndex';
const SUBSCRIBER_HASH_INDEX = 'SubscriberHashIndex';

function deletionKey(sub) {
  return { pk: dynamoString(`user#${sub}`), sk: dynamoString(PROFILE_DELETION_SK) };
}

function itemKey(item = {}) {
  const pk = item.pk?.S || '';
  const sk = item.sk?.S || '';
  return pk && sk ? { pk: dynamoString(pk), sk: dynamoString(sk) } : null;
}

function sameKey(a = {}, b = {}) {
  return a.pk?.S === b.pk?.S && a.sk?.S === b.sk?.S;
}

function deletedMarkerFromItem(item = {}) {
  if (!item?.pk) return null;
  const deletedAtMs = Number(item.deleted_at_ms?.N || 0);
  const deletedAt = item.deleted_at?.S || '';
  if (!deletedAt && !deletedAtMs) return null;
  return {
    deleted_at: deletedAt,
    deleted_at_ms: deletedAtMs,
    deleted_at_seconds: Number(item.deleted_at_seconds?.N || Math.floor(deletedAtMs / 1000) || 0)
  };
}

async function queryUserItems(tableName, sub) {
  const items = [];
  let ExclusiveStartKey;
  do {
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: '#pk = :pk',
      ExpressionAttributeNames: { '#pk': 'pk' },
      ExpressionAttributeValues: { ':pk': dynamoString(`user#${sub}`) },
      ExclusiveStartKey
    }));
    items.push(...(response.Items || []));
    ExclusiveStartKey = response.LastEvaluatedKey;
  } while (ExclusiveStartKey);
  return items;
}

async function queryLinkedIndex(tableName, indexName, attributeName, sub) {
  const items = [];
  let ExclusiveStartKey;
  do {
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      IndexName: indexName,
      ProjectionExpression: '#pk, #sk',
      KeyConditionExpression: '#hash = :sub',
      ExpressionAttributeNames: {
        '#pk': 'pk',
        '#sk': 'sk',
        '#hash': attributeName
      },
      ExpressionAttributeValues: { ':sub': dynamoString(sub) },
      ExclusiveStartKey
    }));
    items.push(...(response.Items || []));
    ExclusiveStartKey = response.LastEvaluatedKey;
  } while (ExclusiveStartKey);
  return items;
}

async function queryLinkedItems(tableName, sub) {
  const [emailItems, subscriberItems] = await Promise.all([
    queryLinkedIndex(tableName, EMAIL_HASH_INDEX, 'email_hash', sub),
    queryLinkedIndex(tableName, SUBSCRIBER_HASH_INDEX, 'subscriber_hash', sub)
  ]);
  return [...emailItems, ...subscriberItems];
}

async function batchDeleteKeys(tableName, keys = []) {
  let deleted = 0;
  for (let index = 0; index < keys.length; index += 25) {
    let requests = keys.slice(index, index + 25).map((Key) => ({ DeleteRequest: { Key } }));
    for (let attempt = 1; requests.length && attempt <= 5; attempt += 1) {
      const response = await dynamodb.send(new BatchWriteItemCommand({
        RequestItems: { [tableName]: requests }
      }));
      const unprocessed = response.UnprocessedItems?.[tableName] || [];
      deleted += requests.length - unprocessed.length;
      requests = unprocessed;
      if (requests.length && attempt < 5) {
        await new Promise((resolve) => setTimeout(resolve, 50 * (2 ** (attempt - 1))));
      }
    }
    if (requests.length) throw new Error(`DynamoDB left ${requests.length} profile delete request(s) unprocessed`);
  }
  return deleted;
}

async function deleteDispatchArtifacts(items = []) {
  let deleted = 0;
  for (const item of items) {
    const row = Object.fromEntries(Object.entries(item || {}).map(([key, value]) => [key, fromDynamoAttr(value)]));
    const bucket = String(row.content_artifact_bucket || '').trim();
    const key = String(row.content_artifact_key || '').trim();
    if (!bucket || !key) continue;
    try {
      await s3.send(new DeleteObjectCommand({ Bucket: bucket, Key: key }));
      deleted += 1;
    } catch (error) {
      logEvent('warning', 'thingy_profile_dispatch_artifact_delete_failed', errorFields(error, {
        bucket,
        key
      }));
      throw error;
    }
  }
  return deleted;
}

export async function getThingyProfileDeletion(sub, options = {}) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return null;
  const response = await dynamodb.send(new GetItemCommand({
    TableName: tableName,
    Key: deletionKey(sub),
    ConsistentRead: Boolean(options.consistent)
  }));
  return deletedMarkerFromItem(response.Item);
}

export function tokenIssuedAfterProfileDeletion(payload = {}, marker = null) {
  if (!marker) return true;
  const issuedAtMs = Number(payload.iat_ms || 0);
  if (issuedAtMs) return issuedAtMs > Number(marker.deleted_at_ms || 0);
  const issuedAt = Number(payload.iat || 0);
  if (issuedAt) return issuedAt > Number(marker.deleted_at_seconds || 0);
  return false;
}

export async function sessionAllowedForThingyProfile(payload) {
  const sub = String(payload?.sub || '');
  if (!sub) return false;
  const marker = await getThingyProfileDeletion(sub);
  return tokenIssuedAfterProfileDeletion(payload, marker);
}

export async function deleteThingyProfile(sub) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName || !sub) return { ok: false, error: 'Thingy profile deletion is unavailable.' };
  const nowMs = Date.now();
  const nowSeconds = Math.floor(nowMs / 1000);
  const nowIso = new Date(nowMs).toISOString();
  const markerKey = deletionKey(sub);
  const userItems = await queryUserItems(tableName, sub);
  const linkedItems = await queryLinkedItems(tableName, sub);
  const keyed = new Map();
  for (const item of [...userItems, ...linkedItems]) {
    const key = itemKey(item);
    if (!key || sameKey(key, markerKey)) continue;
    keyed.set(`${key.pk.S}\0${key.sk.S}`, key);
  }
  const deletedArtifacts = await deleteDispatchArtifacts(userItems);
  const deletedItems = await batchDeleteKeys(tableName, Array.from(keyed.values()));
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      ...markerKey,
      item_type: dynamoString('profile_deletion'),
      deleted_at: dynamoString(nowIso),
      deleted_at_ms: dynamoNumber(nowMs),
      deleted_at_seconds: dynamoNumber(nowSeconds)
    }
  }));
  logEvent('info', 'thingy_profile_deleted', {
    subscriber_hash: sub,
    deleted_items: deletedItems,
    deleted_artifacts: deletedArtifacts
  });
  return {
    ok: true,
    deleted_at: nowIso,
    deleted_items: deletedItems,
    deleted_artifacts: deletedArtifacts
  };
}
