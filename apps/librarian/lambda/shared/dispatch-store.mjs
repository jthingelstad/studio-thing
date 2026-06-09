import { DeleteItemCommand, GetItemCommand, PutItemCommand, QueryCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import crypto from 'node:crypto';
import { dynamoList, dynamoNumber, dynamoString, fromDynamoAttr, userConversationPk } from './user-conversations.mjs';

const DISPATCH_ID_RE = /^[A-Za-z0-9_.:-]{1,96}$/;
const ACTIVE_STATUSES = new Set(['queued', 'generating', 'ready_to_send', 'sending']);
const DRAFT_STATUSES = new Set(['draft', 'shaping', 'needs_clarification', 'ready']);
const DEFAULT_COOLDOWN_SECONDS = 24 * 60 * 60;
const DEFAULT_GENERATION_LEASE_SECONDS = 14 * 60;
const DEFAULT_SEND_LEASE_SECONDS = 5 * 60;

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
    lease_expires_at: String(row.lease_expires_at || ''),
    worker_run_id: String(row.worker_run_id || ''),
    ready_at: String(row.ready_at || ''),
    send_started_at: String(row.send_started_at || ''),
    send_attempt_id: String(row.send_attempt_id || ''),
    sent_at: String(row.sent_at || ''),
    failed_at: String(row.failed_at || ''),
    template_test: Boolean(row.template_test),
    model: String(row.model || ''),
    input_tokens: Number(row.input_tokens || 0),
    output_tokens: Number(row.output_tokens || 0),
    source_count: Number(row.source_count || 0),
    sources: Array.isArray(row.sources) ? row.sources : [],
    messages: Array.isArray(row.messages) ? row.messages : [],
    content_artifact_bucket: String(row.content_artifact_bucket || ''),
    content_artifact_key: String(row.content_artifact_key || ''),
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
    prompt: row.prompt,
    clarification_question: row.clarification_question,
    clarification_answer: row.clarification_answer,
    messages: row.messages,
    created_at: row.created_at,
    updated_at: row.updated_at,
    queued_at: row.queued_at,
    started_at: row.started_at,
    ready_at: row.ready_at,
    send_started_at: row.send_started_at,
    sent_at: row.sent_at,
    failed_at: row.failed_at,
    template_test: Boolean(row.template_test),
    source_count: row.source_count
  };
}

export function dispatchForClient(row) {
  const normalized = typeof row?.id === 'string' || typeof row?.dispatch_id === 'string';
  return publicDispatch(normalized ? row : dispatchFromItem(row));
}

function isoAfter(seconds, now = new Date()) {
  return new Date(now.getTime() + Math.max(1, Number(seconds) || 1) * 1000).toISOString();
}

function dispatchLeaseExpired(row = {}, nowSeconds = Math.floor(Date.now() / 1000)) {
  const expiresAt = Date.parse(row.lease_expires_at || '');
  return Number.isFinite(expiresAt) && Math.floor(expiresAt / 1000) <= nowSeconds;
}

function recoverableActiveStatus(status) {
  return status === 'generating' || status === 'ready_to_send';
}

export function dispatchIsActive(row = {}, {
  nowSeconds = Math.floor(Date.now() / 1000)
} = {}) {
  if (!ACTIVE_STATUSES.has(row.status)) return false;
  if (recoverableActiveStatus(row.status) && dispatchLeaseExpired(row, nowSeconds)) return false;
  if (row.status === 'sending' && dispatchLeaseExpired(row, nowSeconds)) return false;
  return true;
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

export async function deleteUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId }) {
  const dispatch = await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId });
  if (!dispatch) return null;
  await dynamodb.send(new DeleteItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    }
  }));
  return dispatch;
}

export function dispatchAvailabilityFromRows(rows = [], {
  nowSeconds = Math.floor(Date.now() / 1000),
  cooldownSeconds = DEFAULT_COOLDOWN_SECONDS,
  owner = false
} = {}) {
  const latestActive = rows.find((row) => dispatchIsActive(row, { nowSeconds }));
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
  let rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 20 });
  const recovered = await recoverStaleDispatches({ dynamodb, tableName, subscriberHash, rows });
  if (recovered) rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 20 });
  return dispatchAvailabilityFromRows(rows, { owner });
}

function draftStatus(value) {
  const status = String(value || 'draft').trim().toLowerCase();
  if (status === 'upgrade') return 'ready';
  return DRAFT_STATUSES.has(status) ? status : 'draft';
}

function dispatchMessageDynamoItem(message = {}) {
  const role = String(message.role || 'assistant').trim().toLowerCase();
  return {
    M: {
      role: dynamoString(['user', 'assistant', 'system'].includes(role) ? role : 'assistant'),
      text: dynamoString(String(message.text || '').slice(0, 2400)),
      time: dynamoString(String(message.time || '').slice(0, 60)),
      kind: dynamoString(String(message.kind || '').slice(0, 80))
    }
  };
}

function compactMessages(messages = []) {
  return Array.isArray(messages)
    ? messages.slice(-24).map(dispatchMessageDynamoItem)
    : [];
}

export async function upsertDispatchDraft({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId = '',
  status = 'draft',
  topic = '',
  prompt = '',
  direction = '',
  clarificationQuestion = '',
  clarificationAnswer = '',
  title = '',
  messages = [],
  now = new Date().toISOString()
}) {
  const id = validDispatchId(dispatchId) || crypto.randomUUID();
  const existing = dispatchId ? await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id }) : null;
  const normalizedStatus = draftStatus(status);
  const item = {
    pk: dynamoString(userConversationPk(subscriberHash)),
    sk: dynamoString(dispatchSk(now, id)),
    item_type: dynamoString('dispatch'),
    dispatch_id: dynamoString(id),
    status: dynamoString(normalizedStatus),
    email_hash: dynamoString(subscriberHash),
    topic: dynamoString(String(topic || prompt || title || '').slice(0, 300)),
    prompt: dynamoString(String(prompt || '').slice(0, 1400)),
    direction: dynamoString(String(direction || prompt || topic || '').slice(0, 1800)),
    clarification_question: dynamoString(String(clarificationQuestion || '').slice(0, 800)),
    clarification_answer: dynamoString(String(clarificationAnswer || '').slice(0, 1200)),
    title: dynamoString(String(title || topic || prompt || 'Dispatch').replace(/\s+/g, ' ').trim().slice(0, 120)),
    messages: dynamoList(messages, dispatchMessageDynamoItem),
    created_at: dynamoString(now),
    updated_at: dynamoString(now)
  };
  if (!existing) {
    await dynamodb.send(new PutItemCommand({
      TableName: tableName,
      Item: item,
      ConditionExpression: 'attribute_not_exists(pk)'
    }));
    return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
  }

  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(existing.created_at, existing.id))
    },
    UpdateExpression: [
      'SET #status = :status',
      '#topic = :topic',
      '#prompt = :prompt',
      '#direction = :direction',
      '#clarification_question = :clarification_question',
      '#clarification_answer = :clarification_answer',
      '#title = :title',
      '#messages = :messages',
      '#updated_at = :now'
    ].join(', '),
    ConditionExpression: '#status IN (:draft, :shaping, :needs_clarification, :ready)',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#topic': 'topic',
      '#prompt': 'prompt',
      '#direction': 'direction',
      '#clarification_question': 'clarification_question',
      '#clarification_answer': 'clarification_answer',
      '#title': 'title',
      '#messages': 'messages',
      '#updated_at': 'updated_at'
    },
    ExpressionAttributeValues: {
      ':status': dynamoString(normalizedStatus),
      ':topic': dynamoString(String(topic || prompt || title || existing.topic || '').slice(0, 300)),
      ':prompt': dynamoString(String(prompt || existing.prompt || '').slice(0, 1400)),
      ':direction': dynamoString(String(direction || prompt || topic || existing.direction || '').slice(0, 1800)),
      ':clarification_question': dynamoString(String(clarificationQuestion || '').slice(0, 800)),
      ':clarification_answer': dynamoString(String(clarificationAnswer || existing.clarification_answer || '').slice(0, 1200)),
      ':title': dynamoString(String(title || topic || prompt || existing.title || 'Dispatch').replace(/\s+/g, ' ').trim().slice(0, 120)),
      ':messages': { L: compactMessages(messages) },
      ':now': dynamoString(now),
      ':draft': dynamoString('draft'),
      ':shaping': dynamoString('shaping'),
      ':needs_clarification': dynamoString('needs_clarification'),
      ':ready': dynamoString('ready')
    }
  }));
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
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
  templateTest = false,
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
      template_test: { BOOL: Boolean(templateTest) },
      created_at: dynamoString(now),
      updated_at: dynamoString(now),
      queued_at: dynamoString(now)
    },
    ConditionExpression: 'attribute_not_exists(pk)'
  }));
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
}

export async function queueDraftDispatch({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId,
  emailHash,
  toEmail,
  topic,
  prompt,
  direction,
  clarificationQuestion = '',
  clarificationAnswer = '',
  templateTest = false
}) {
  const id = validDispatchId(dispatchId);
  if (!id) throw new Error('dispatchId is invalid');
  const existing = await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
  if (!existing) throw new Error('dispatch draft not found');
  const now = new Date().toISOString();
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(existing.created_at, existing.id))
    },
    UpdateExpression: [
      'SET #status = :queued',
      '#email_hash = :email_hash',
      '#to_email = :to_email',
      '#topic = :topic',
      '#prompt = :prompt',
      '#direction = :direction',
      '#clarification_question = :clarification_question',
      '#clarification_answer = :clarification_answer',
      '#template_test = :template_test',
      '#updated_at = :now',
      '#queued_at = :now'
    ].join(', '),
    ConditionExpression: '#status IN (:draft, :shaping, :needs_clarification, :ready)',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#email_hash': 'email_hash',
      '#to_email': 'to_email',
      '#topic': 'topic',
      '#prompt': 'prompt',
      '#direction': 'direction',
      '#clarification_question': 'clarification_question',
      '#clarification_answer': 'clarification_answer',
      '#template_test': 'template_test',
      '#updated_at': 'updated_at',
      '#queued_at': 'queued_at'
    },
    ExpressionAttributeValues: {
      ':queued': dynamoString('queued'),
      ':email_hash': dynamoString(emailHash || subscriberHash),
      ':to_email': dynamoString(toEmail),
      ':topic': dynamoString(String(topic || prompt || existing.topic || '').slice(0, 300)),
      ':prompt': dynamoString(String(prompt || existing.prompt || '').slice(0, 1400)),
      ':direction': dynamoString(String(direction || prompt || topic || existing.direction || '').slice(0, 1800)),
      ':clarification_question': dynamoString(String(clarificationQuestion || existing.clarification_question || '').slice(0, 800)),
      ':clarification_answer': dynamoString(String(clarificationAnswer || existing.clarification_answer || '').slice(0, 1200)),
      ':template_test': { BOOL: Boolean(templateTest) },
      ':now': dynamoString(now),
      ':draft': dynamoString('draft'),
      ':shaping': dynamoString('shaping'),
      ':needs_clarification': dynamoString('needs_clarification'),
      ':ready': dynamoString('ready')
    }
  }));
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
}

export async function claimQueuedDispatch({ dynamodb, tableName, subscriberHash, dispatch }) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const workerRunId = crypto.randomUUID();
  const leaseExpiresAt = isoAfter(process.env.DISPATCH_GENERATION_LEASE_SECONDS || DEFAULT_GENERATION_LEASE_SECONDS, nowDate);
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: 'SET #status = :generating, #updated_at = :now, #started_at = :now, #lease_expires_at = :lease_expires_at, #worker_run_id = :worker_run_id',
    ConditionExpression: '#status = :queued',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#started_at': 'started_at',
      '#lease_expires_at': 'lease_expires_at',
      '#worker_run_id': 'worker_run_id'
    },
    ExpressionAttributeValues: {
      ':queued': dynamoString('queued'),
      ':generating': dynamoString('generating'),
      ':now': dynamoString(now),
      ':lease_expires_at': dynamoString(leaseExpiresAt),
      ':worker_run_id': dynamoString(workerRunId)
    }
  }));
  return { ...dispatch, status: 'generating', updated_at: now, started_at: now, lease_expires_at: leaseExpiresAt, worker_run_id: workerRunId };
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

export async function markDispatchReadyToSend({ dynamodb, tableName, subscriberHash, dispatch, result, artifact }) {
  const now = new Date().toISOString();
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: [
      'SET #status = :ready_to_send',
      '#updated_at = :now',
      '#ready_at = :now',
      '#subject = :subject',
      '#title = :title',
      '#preview = :preview',
      '#model = :model',
      '#input_tokens = :input_tokens',
      '#output_tokens = :output_tokens',
      '#source_count = :source_count',
      '#sources = :sources',
      '#content_artifact_bucket = :content_artifact_bucket',
      '#content_artifact_key = :content_artifact_key'
    ].join(', '),
    ConditionExpression: '#status = :generating AND #worker_run_id = :worker_run_id',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#worker_run_id': 'worker_run_id',
      '#updated_at': 'updated_at',
      '#ready_at': 'ready_at',
      '#subject': 'subject',
      '#title': 'title',
      '#preview': 'preview',
      '#model': 'model',
      '#input_tokens': 'input_tokens',
      '#output_tokens': 'output_tokens',
      '#source_count': 'source_count',
      '#sources': 'sources',
      '#content_artifact_bucket': 'content_artifact_bucket',
      '#content_artifact_key': 'content_artifact_key'
    },
    ExpressionAttributeValues: {
      ':generating': dynamoString('generating'),
      ':ready_to_send': dynamoString('ready_to_send'),
      ':worker_run_id': dynamoString(dispatch.worker_run_id),
      ':now': dynamoString(now),
      ':subject': dynamoString(result.subject),
      ':title': dynamoString(result.title),
      ':preview': dynamoString(result.preview),
      ':model': dynamoString(result.model),
      ':input_tokens': dynamoNumber(result.usage?.inputTokens || result.usage?.input_tokens || 0),
      ':output_tokens': dynamoNumber(result.usage?.outputTokens || result.usage?.output_tokens || 0),
      ':source_count': dynamoNumber((result.sources || []).length),
      ':sources': dynamoList(result.sources || [], sourceDynamoItem),
      ':content_artifact_bucket': dynamoString(artifact?.bucket || ''),
      ':content_artifact_key': dynamoString(artifact?.key || '')
    }
  }));
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: dispatch.id });
}

export async function claimReadyToSendDispatch({ dynamodb, tableName, subscriberHash, dispatch }) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const sendAttemptId = crypto.randomUUID();
  const leaseExpiresAt = isoAfter(process.env.DISPATCH_SEND_LEASE_SECONDS || DEFAULT_SEND_LEASE_SECONDS, nowDate);
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
    },
    UpdateExpression: 'SET #status = :sending, #updated_at = :now, #send_started_at = :now, #lease_expires_at = :lease_expires_at, #send_attempt_id = :send_attempt_id',
    ConditionExpression: '#status = :ready_to_send AND attribute_not_exists(#submission_id)',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#send_started_at': 'send_started_at',
      '#lease_expires_at': 'lease_expires_at',
      '#send_attempt_id': 'send_attempt_id',
      '#submission_id': 'submission_id'
    },
    ExpressionAttributeValues: {
      ':ready_to_send': dynamoString('ready_to_send'),
      ':sending': dynamoString('sending'),
      ':now': dynamoString(now),
      ':lease_expires_at': dynamoString(leaseExpiresAt),
      ':send_attempt_id': dynamoString(sendAttemptId)
    }
  }));
  return { ...dispatch, status: 'sending', updated_at: now, send_started_at: now, lease_expires_at: leaseExpiresAt, send_attempt_id: sendAttemptId };
}

export async function markDispatchSent({ dynamodb, tableName, subscriberHash, dispatch, submissionId }) {
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
      '#submission_id = :submission_id'
    ].join(', '),
    ConditionExpression: '#status = :sending AND #send_attempt_id = :send_attempt_id AND attribute_not_exists(#submission_id)',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#send_attempt_id': 'send_attempt_id',
      '#updated_at': 'updated_at',
      '#sent_at': 'sent_at',
      '#submission_id': 'submission_id'
    },
    ExpressionAttributeValues: {
      ':sending': dynamoString('sending'),
      ':send_attempt_id': dynamoString(dispatch.send_attempt_id),
      ':sent': dynamoString('sent'),
      ':now': dynamoString(now),
      ':submission_id': dynamoString(submissionId)
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
    ConditionExpression: '#status <> :sent',
    ExpressionAttributeNames: {
      '#status': 'status',
      '#updated_at': 'updated_at',
      '#failed_at': 'failed_at',
      '#error': 'error'
    },
    ExpressionAttributeValues: {
      ':failed': dynamoString('failed'),
      ':sent': dynamoString('sent'),
      ':now': dynamoString(now),
      ':error': dynamoString(String(error?.message || error || 'Dispatch failed.').slice(0, 1000))
    }
  }));
}

export async function recoverStaleDispatches({ dynamodb, tableName, subscriberHash, rows = [] }) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  let recovered = 0;
  for (const row of rows) {
    if (!dispatchLeaseExpired(row, nowSeconds)) continue;
    if (row.status === 'generating') {
      const now = new Date().toISOString();
      await dynamodb.send(new UpdateItemCommand({
        TableName: tableName,
        Key: {
          pk: dynamoString(userConversationPk(subscriberHash)),
          sk: dynamoString(dispatchSk(row.created_at, row.id))
        },
        UpdateExpression: 'SET #status = :queued, #updated_at = :now, #queued_at = :now',
        ConditionExpression: '#status = :generating AND #lease_expires_at = :lease_expires_at',
        ExpressionAttributeNames: {
          '#status': 'status',
          '#updated_at': 'updated_at',
          '#queued_at': 'queued_at',
          '#lease_expires_at': 'lease_expires_at'
        },
        ExpressionAttributeValues: {
          ':generating': dynamoString('generating'),
          ':queued': dynamoString('queued'),
          ':now': dynamoString(now),
          ':lease_expires_at': dynamoString(row.lease_expires_at)
        }
      })).then(() => { recovered += 1; }).catch(() => {});
    } else if (row.status === 'ready_to_send') {
      const now = new Date().toISOString();
      await dynamodb.send(new UpdateItemCommand({
        TableName: tableName,
        Key: {
          pk: dynamoString(userConversationPk(subscriberHash)),
          sk: dynamoString(dispatchSk(row.created_at, row.id))
        },
        UpdateExpression: 'SET #updated_at = :now',
        ConditionExpression: '#status = :ready_to_send',
        ExpressionAttributeNames: {
          '#status': 'status',
          '#updated_at': 'updated_at'
        },
        ExpressionAttributeValues: {
          ':ready_to_send': dynamoString('ready_to_send'),
          ':now': dynamoString(now)
        }
      })).then(() => { recovered += 1; }).catch(() => {});
    } else if (row.status === 'sending') {
      await markDispatchFailed({
        dynamodb,
        tableName,
        subscriberHash,
        dispatch: row,
        error: 'Dispatch delivery could not be confirmed. It was not retried to avoid sending a duplicate email.'
      }).then(() => { recovered += 1; }).catch(() => {});
    }
  }
  return recovered;
}
