import { UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import { dynamodb } from './aws-clients.mjs';
import { logEvent } from './logging.mjs';

const RATE_LIMIT_WINDOW_SECONDS = 60 * 60;

export async function checkRateLimit(identity: string, maxRequests = Number(process.env.RATE_LIMIT_MAX || '20')) {
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return true;
  const now = Math.floor(Date.now() / 1000);
  const window = Math.floor(now / RATE_LIMIT_WINDOW_SECONDS);
  const key = `rate#${identity}#${window}`;
  const response = await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: { pk: { S: key }, sk: { S: 'rate' } },
    UpdateExpression: 'ADD #count :one SET #ttl = :ttl',
    ExpressionAttributeNames: { '#count': 'count', '#ttl': 'ttl' },
    ExpressionAttributeValues: {
      ':one': { N: '1' },
      ':ttl': { N: String(now + RATE_LIMIT_WINDOW_SECONDS * 2) }
    },
    ReturnValues: 'UPDATED_NEW'
  }));
  const count = Number(response.Attributes?.count?.N || '0');
  logEvent('info', 'rate_limit_checked', { identity_hash: identity, count, limit: maxRequests, allowed: count <= maxRequests });
  return count <= maxRequests;
}
