import { GetItemCommand, PutItemCommand, QueryCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import crypto from 'node:crypto';
import { dynamoList, dynamoNumber, dynamoString, fromDynamoAttr, userConversationPk } from './user-conversations.mjs';

const DISPATCH_ID_RE = /^[A-Za-z0-9_.:-]{1,96}$/;
const ACTIVE_STATUSES = new Set(['queued', 'generating']);
const DEFAULT_COOLDOWN_SECONDS = 24 * 60 * 60;

export function dispatchSk(createdAt, dispatchId) {
  return `dispatch#${createdAt}#${dispatchId}`;
}

export function validDispatchId(value) {
  const text = String(value || '').trim();
  return DISPATCH_ID_RE.test(text) ? text : '';
}

export function dispatchFromItem(item = {}) {
  const row = Object.fromEntries(Object.entries(item || {}).map(([key, value]) => [key, fromDynamoAttr(value)]));
  const sk = String(row.sk || '');
  const idFromSk = sk.startsWith('dispatch#') ? sk.split('#').slice(-1)[0] : '';
  return {
    id: String(row.dispatch_id || idFromSk || ''),
    dispatch_id: String(row.dispatch_id || idFromSk || ''),
    status: String(row.status || ''),
    topic: String(row.topic || ''),
    prompt: String(row.prompt || ''),
    direction: String(row.direction || ''),
    clarification_question: String(row.clarification_question || ''),
    clarification_answer: String(row.clarification_answer || ''),
    email_hash: String(row.email_hash || ''),
    to_email: String(row.to_email || ''),
    subject: String(row.subject || ''),
    title: String(row.title || ''),
    preview: String(row.preview || ''),
    error: String(row.error || ''),
    created_at: String(row.created_at || ''),
    updated_at: String(row.updated_at || ''),
    queued_at: String(row.queued_at || ''),
    started_at: String(row.started_at || ''),
    sent_at: String(row.sent_at || ''),
    failed_at: String(row.failed_at || ''),
    model: String(row.model || ''),
    input_tokens: Number(row.input_tokens || 0),
    output_tokens: Number(row.output_tokens || 0),
    source_count: Number(row.source_count || 0),
    sources: Array.isArray(row.sources) ? row.sources : [],
    content_text: String(row.content_text || ''),
    content_html: String(row.content_html || '')
  };
}

function publicDispatch(row) {
  return {
    id: row.id,
    dispatch_id: row.dispatch_id,
    status: row.status,
    topic: row.topic,
    direction: row.direction,
    subject: row.subject,
    title: row.title,
    preview: row.preview,
    error: row.error,
    created_at: row.created_at,
    updated_at: row.updated_at,
    queued_at: row.queued_at,
    started_at: row.started_at,
    sent_at: row.sent_at,
    failed_at: row.failed_at,
    source_count: row.source_count
  };
}

export function dispatchForClient(row) {
  return publicDispatch(dispatchFromItem(row));
}

export async function listUserDispatches({ dynamodb, tableName, subscriberHash, limit = 12 }) {
  const response = await dynamodb.send(new QueryCommand({
    TableName: tableName,
    KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
    ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
    ExpressionAttributeValues: {
      ':pk': dynamoString(userConversationPk(subscriberHash)),
      ':prefix': dynamoString('dispatch#')
    },
    ScanIndexForward: false,
    Limit: Math.max(1, Math.min(Number(limit) || 12, 50))
  }));
  return (response.Items || []).map(dispatchFromItem);
}

export async function getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId }) {
  const id = validDispatchId(dispatchId);
  if (!id) return null;
  const rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 50 });
  return rows.find((row) => row.id === id) || null;
}

export function dispatchAvailabilityFromRows(rows = [], {
  nowSeconds = Math.floor(Date.now() / 1000),
  cooldownSeconds = DEFAULT_COOLDOWN_SECONDS,
  owner = false
} = {}) {
  const latestActive = rows.find((row) => ACTIVE_STATUSES.has(row.status));
  const latestSent = rows.find((row) => row.status === 'sent' && row.sent_at);
  if (latestActive) {
    return {
      allowed: false,
      reason: 'active',
      message: 'A Dispatch is already being prepared. Wait for that one to finish before starting another.',
      active_dispatch_id: latestActive.id
    };
  }
  if (!owner && latestSent) {
    const sentSeconds = Math.floor(Date.parse(latestSent.sent_at) / 1000);
    if (Number.isFinite(sentSeconds)) {
      const remaining = sentSeconds + cooldownSeconds - nowSeconds;
      if (remaining > 0) {
        return {
          allowed: false,
          reason: 'cooldown',
          message: 'Supporting members can send one Dispatch every 24 hours.',
          retry_after_seconds: remaining,
          last_dispatch_id: latestSent.id
        };
      }
    }
  }
  return { allowed: true, reason: 'ok', retry_after_seconds: 0 };
}

export async function dispatchAvailability({ dynamodb, tableName, subscriberHash, owner = false }) {
  const rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 20 });
  return dispatchAvailabilityFromRows(rows, { owner });
}

export async function createQueuedDispatch({
  dynamodb,
  tableName,
  subscriberHash,
  emailHash,
  toEmail,
  topic,
  prompt,
  direction,
  clarificationQuestion = '',
  clarificationAnswer = '',
  now = new Date().toISOString(),
  dispatchId = crypto.randomUUID()
}) {
  const id = validDispatchId(dispatchId);
  if (!id) throw new Error('dispatchId is invalid');
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(now, id)),
      item_type: dynamoString('dispatch'),
      dispatch_id: dynamoString(id),
      status: dynamoString('queued'),
      email_hash: dynamoString(emailHash || subscriberHash),
      to_email: dynamoString(toEmail),
      topic: dynamoString(String(topic || '').slice(0, 300)),
      prompt: dynamoString(String(prompt || '').slice(0, 1400)),
      direction: dynamoString(String(direction || prompt || topic || '').slice(0, 1800)),
      clarification_question: dynamoString(String(clarificationQuestion || '').slice(0, 800)),
      clarification_answer: dynamoString(String(clarificationAnswer || '').slice(0, 1200)),
      created_at: dynamoString(now),
      updated_at: dynamoString(now),
      queued_at: dynamoString(now)
    },
    ConditionExpression: 'attribute_not_exists(pk)'
  }));
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
}

export async function claimQueuedDispatch({ dynamodb, tableName, subscriberHash, dispatch }) {
  const now = new Date().toISOString();
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: 'SET #status = :generating, #updated_at = :now, #started_at = :now',
    ConditionExpression: '#status = :queued',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#started_at': 'started_at'
    },
    ExpressionAttributeValues: {
      ':queued': dynamoString('queued'),
      ':generating': dynamoString('generating'),
      ':now': dynamoString(now)
    }
  }));
  return { ...dispatch, status: 'generating', updated_at: now, started_at: now };
}

function sourceDynamoItem(source = {}) {
  return {
    M: {
      id: dynamoString(source.id),
      label: dynamoString(source.label),
      title: dynamoString(source.title),
      url: dynamoString(source.url),
      source_kind: dynamoString(source.source_kind),
      publish_date: dynamoString(source.publish_date)
    }
  };
}

export async function markDispatchSent({ dynamodb, tableName, subscriberHash, dispatch, result }) {
  const now = new Date().toISOString();
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: [
      'SET #status = :sent',
      '#updated_at = :now',
      '#sent_at = :now',
      '#subject = :subject',
      '#title = :title',
      '#preview = :preview',
      '#model = :model',
      '#input_tokens = :input_tokens',
      '#output_tokens = :output_tokens',
      '#source_count = :source_count',
      '#sources = :sources',
      '#content_text = :content_text',
      '#content_html = :content_html',
      '#submission_id = :submission_id'
    ].join(', '),
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#sent_at': 'sent_at',
      '#subject': 'subject',
      '#title': 'title',
      '#preview': 'preview',
      '#model': 'model',
      '#input_tokens': 'input_tokens',
      '#output_tokens': 'output_tokens',
      '#source_count': 'source_count',
      '#sources': 'sources',
      '#content_text': 'content_text',
      '#content_html': 'content_html',
      '#submission_id': 'submission_id'
    },
    ExpressionAttributeValues: {
      ':sent': dynamoString('sent'),
      ':now': dynamoString(now),
      ':subject': dynamoString(result.subject),
      ':title': dynamoString(result.title),
      ':preview': dynamoString(result.preview),
      ':model': dynamoString(result.model),
      ':input_tokens': dynamoNumber(result.usage?.inputTokens || result.usage?.input_tokens || 0),
      ':output_tokens': dynamoNumber(result.usage?.outputTokens || result.usage?.output_tokens || 0),
      ':source_count': dynamoNumber((result.sources || []).length),
      ':sources': dynamoList(result.sources || [], sourceDynamoItem),
      ':content_text': dynamoString(String(result.text || '').slice(0, 60000)),
      ':content_html': dynamoString(String(result.html || '').slice(0, 120000)),
      ':submission_id': dynamoString(result.submission_id)
    }
  }));
}

export async function markDispatchFailed({ dynamodb, tableName, subscriberHash, dispatch, error }) {
  const now = new Date().toISOString();
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: 'SET #status = :failed, #updated_at = :now, #failed_at = :now, #error = :error',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#failed_at': 'failed_at',
      '#error': 'error'
    },
    ExpressionAttributeValues: {
      ':failed': dynamoString('failed'),
      ':now': dynamoString(now),
      ':error': dynamoString(String(error?.message || error || 'Dispatch failed.').slice(0, 1000))
    }
  }));
}
