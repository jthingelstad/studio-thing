import {
  DeleteItemCommand,
  GetItemCommand,
  PutItemCommand,
  QueryCommand,
  UpdateItemCommand
} from '@aws-sdk/client-dynamodb';
import type { AttributeValue, DynamoDBClient } from '@aws-sdk/client-dynamodb';
import crypto from 'node:crypto';
import {
  boundedJsonForStorage,
  dynamoList,
  dynamoNumber,
  dynamoString,
  fromDynamoAttr,
  userConversationPk
} from './user-conversations.mjs';
import { dispatchDraftTtlSeconds, dispatchHistoryTtlSeconds } from './retention.mjs';

const DISPATCH_ID_RE = /^[A-Za-z0-9_.:-]{1,96}$/;
const ACTIVE_STATUSES = new Set(['queued', 'generating', 'ready_to_send', 'sending']);
const DRAFT_STATUSES = new Set(['draft', 'shaping', 'needs_clarification', 'ready']);
const DEFAULT_COOLDOWN_SECONDS = 24 * 60 * 60;
const DEFAULT_QUEUE_STALE_SECONDS = 15 * 60;
const DEFAULT_GENERATION_LEASE_SECONDS = 14 * 60;
const DEFAULT_SEND_LEASE_SECONDS = 5 * 60;
const DEFAULT_SHAPING_STALE_SECONDS = 30;

type JsonRecord = Record<string, unknown>;
type DynamoItem = Record<string, AttributeValue>;

export interface DispatchRecord extends JsonRecord {
  id: string;
  dispatch_id: string;
  status: string;
  topic: string;
  prompt: string;
  direction: string;
  clarification_question: string;
  clarification_answer: string;
  conversation_id: string;
  email_hash: string;
  to_email: string;
  subject: string;
  title: string;
  preview: string;
  error: string;
  created_at: string;
  updated_at: string;
  queued_at: string;
  started_at: string;
  lease_expires_at: string;
  worker_run_id: string;
  ready_at: string;
  send_started_at: string;
  send_attempt_id: string;
  sent_at: string;
  failed_at: string;
  ttl: number;
  template_test: boolean;
  brief: JsonRecord;
  brief_json: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  source_count: number;
  sources: unknown[];
  messages: unknown[];
  content_artifact_bucket: string;
  content_artifact_key: string;
  content_text: string;
  content_html: string;
}

interface StoreContext {
  dynamodb: DynamoDBClient;
  tableName: string;
  subscriberHash: string;
}

interface DispatchContext extends StoreContext {
  dispatch: DispatchRecord;
}

function objectValue(value: unknown): JsonRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as JsonRecord) : {};
}

function cleanDispatchText(value: unknown, max = 500) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);
}

function compactDispatchBriefSource(value: unknown) {
  const source = objectValue(value);
  return {
    id: cleanDispatchText(source.id, 40),
    label: cleanDispatchText(source.label, 80),
    title: cleanDispatchText(source.title, 180),
    url: cleanDispatchText(source.url, 500),
    source_kind: cleanDispatchText(source.source_kind, 40),
    publish_date: cleanDispatchText(source.publish_date, 40),
    why: cleanDispatchText(source.why, 220)
  };
}

function compactDispatchBrief(value: unknown = {}) {
  const brief = objectValue(value);
  if (!brief || typeof brief !== 'object' || Array.isArray(brief)) return null;
  return {
    user_goal: cleanDispatchText(brief.user_goal, 500),
    working_angle: cleanDispatchText(brief.working_angle, 700),
    coverage_status: cleanDispatchText(brief.coverage_status, 40),
    generation_instructions: cleanDispatchText(brief.generation_instructions, 1200),
    preheader_basis: cleanDispatchText(brief.preheader_basis, 240),
    excluded_scope: Array.isArray(brief.excluded_scope)
      ? brief.excluded_scope
          .map((item) => cleanDispatchText(item, 180))
          .filter(Boolean)
          .slice(0, 8)
      : [],
    selected_sources: Array.isArray(brief.selected_sources)
      ? brief.selected_sources
          .map(compactDispatchBriefSource)
          .filter((source) => source.title || source.url)
          .slice(0, 12)
      : []
  };
}

function dispatchBriefJson(brief: unknown = {}) {
  const compact = compactDispatchBrief(brief);
  return compact ? boundedJsonForStorage(compact, 12000) : '';
}

function dispatchBriefFromRow(row: JsonRecord = {}) {
  if (row.brief && typeof row.brief === 'object' && !Array.isArray(row.brief))
    return compactDispatchBrief(row.brief) || {};
  const raw = String(row.brief_json || '');
  if (!raw) return {};
  try {
    return compactDispatchBrief(JSON.parse(raw)) || {};
  } catch {
    return {};
  }
}

export function dispatchSk(createdAt: unknown, dispatchId: unknown) {
  return `dispatch#${createdAt}#${dispatchId}`;
}

function dispatchLookupSk(dispatchId: unknown) {
  return `dispatch-id#${dispatchId}`;
}

export function validDispatchId(value: unknown) {
  const text = String(value || '').trim();
  return DISPATCH_ID_RE.test(text) ? text : '';
}

export function dispatchFromItem(item: DynamoItem = {}): DispatchRecord {
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
    conversation_id: String(row.conversation_id || ''),
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
    ttl: Number(row.ttl || 0),
    template_test: Boolean(row.template_test),
    brief: dispatchBriefFromRow(row),
    brief_json: String(row.brief_json || ''),
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

function publicDispatch(row: DispatchRecord) {
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
    brief: row.brief || {},
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

export function dispatchForClient(row: DispatchRecord | DynamoItem) {
  const record = row as JsonRecord;
  const normalized = typeof record.id === 'string' || typeof record.dispatch_id === 'string';
  return publicDispatch(normalized ? (row as DispatchRecord) : dispatchFromItem(row as DynamoItem));
}

function isoAfter(seconds: unknown, now = new Date()) {
  return new Date(now.getTime() + Math.max(1, Number(seconds) || 1) * 1000).toISOString();
}

function dispatchLeaseExpired(row: DispatchRecord, nowSeconds = Math.floor(Date.now() / 1000)) {
  const expiresAt = Date.parse(row.lease_expires_at || '');
  return Number.isFinite(expiresAt) && Math.floor(expiresAt / 1000) <= nowSeconds;
}

function dispatchQueuedStale(row: DispatchRecord, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (row.status !== 'queued') return false;
  const queuedAt = Date.parse(row.queued_at || row.updated_at || row.created_at || '');
  if (!Number.isFinite(queuedAt)) return false;
  const staleSeconds = Math.max(
    60,
    Number(process.env.DISPATCH_QUEUE_STALE_SECONDS || DEFAULT_QUEUE_STALE_SECONDS) || DEFAULT_QUEUE_STALE_SECONDS
  );
  return Math.floor(queuedAt / 1000) + staleSeconds <= nowSeconds;
}

function dispatchShapingStale(row: DispatchRecord, nowSeconds = Math.floor(Date.now() / 1000)) {
  if (row.status !== 'shaping') return false;
  const updatedAt = Date.parse(row.updated_at || row.created_at || '');
  if (!Number.isFinite(updatedAt)) return false;
  const staleSeconds = Math.max(
    10,
    Number(process.env.DISPATCH_SHAPING_STALE_SECONDS || DEFAULT_SHAPING_STALE_SECONDS) || DEFAULT_SHAPING_STALE_SECONDS
  );
  return Math.floor(updatedAt / 1000) + staleSeconds <= nowSeconds;
}

function recoveredDraftStatus(row: DispatchRecord) {
  if (row.clarification_question) return 'needs_clarification';
  const direction = String(row.direction || '').trim();
  const prompt = String(row.prompt || row.topic || '').trim();
  if (direction && direction !== prompt) return 'ready';
  return 'draft';
}

function recoverableActiveStatus(status: unknown) {
  return status === 'generating' || status === 'ready_to_send';
}

export function dispatchIsActive(row: DispatchRecord, { nowSeconds = Math.floor(Date.now() / 1000) } = {}) {
  if (!ACTIVE_STATUSES.has(row.status)) return false;
  if (dispatchQueuedStale(row, nowSeconds)) return false;
  if (recoverableActiveStatus(row.status) && dispatchLeaseExpired(row, nowSeconds)) return false;
  if (row.status === 'sending' && dispatchLeaseExpired(row, nowSeconds)) return false;
  return true;
}

export async function listUserDispatches({
  dynamodb,
  tableName,
  subscriberHash,
  limit = 12
}: StoreContext & { limit?: number }) {
  const response = await dynamodb.send(
    new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
      ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
      ExpressionAttributeValues: {
        ':pk': dynamoString(userConversationPk(subscriberHash)),
        ':prefix': dynamoString('dispatch#')
      },
      ScanIndexForward: false,
      Limit: Math.max(1, Math.min(Number(limit) || 12, 50))
    })
  );
  return (response.Items || []).map(dispatchFromItem);
}

export async function getUserDispatch({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId
}: StoreContext & { dispatchId: unknown }) {
  const id = validDispatchId(dispatchId);
  if (!id) return null;
  const lookup = await dynamodb.send(
    new GetItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchLookupSk(id))
      }
    })
  );
  const createdAt = fromDynamoAttr(lookup.Item?.created_at);
  const dispatchSortKey = String(
    fromDynamoAttr(lookup.Item?.dispatch_sk) || (createdAt ? dispatchSk(createdAt, id) : '')
  );
  if (!dispatchSortKey) return null;
  const response = await dynamodb.send(
    new GetItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSortKey)
      }
    })
  );
  return response.Item ? dispatchFromItem(response.Item) : null;
}

async function putDispatchLookup({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId,
  createdAt,
  now = createdAt,
  ttl = 0
}: StoreContext & { dispatchId: string; createdAt: string; now?: string; ttl?: number }) {
  const item: DynamoItem = {
    pk: dynamoString(userConversationPk(subscriberHash)),
    sk: dynamoString(dispatchLookupSk(dispatchId)),
    item_type: dynamoString('dispatch_lookup'),
    dispatch_id: dynamoString(dispatchId),
    dispatch_sk: dynamoString(dispatchSk(createdAt, dispatchId)),
    created_at: dynamoString(createdAt),
    updated_at: dynamoString(now)
  };
  if (Number(ttl) > 0) item.ttl = dynamoNumber(ttl);
  await dynamodb.send(
    new PutItemCommand({
      TableName: tableName,
      Item: item
    })
  );
}

async function updateDispatchLookupTtl({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId,
  now,
  ttl = 0
}: StoreContext & { dispatchId: string; now: string; ttl?: number }) {
  const setTtl = Number(ttl) > 0;
  try {
    await dynamodb.send(
      new UpdateItemCommand({
        TableName: tableName,
        Key: {
          pk: dynamoString(userConversationPk(subscriberHash)),
          sk: dynamoString(dispatchLookupSk(dispatchId))
        },
        UpdateExpression: setTtl ? 'SET #updated_at = :now, #ttl = :ttl' : 'SET #updated_at = :now REMOVE #ttl',
        ConditionExpression: 'attribute_exists(pk)',
        ExpressionAttributeNames: {
          '#updated_at': 'updated_at',
          '#ttl': 'ttl'
        },
        ExpressionAttributeValues: setTtl
          ? {
              ':now': dynamoString(now),
              ':ttl': dynamoNumber(ttl)
            }
          : {
              ':now': dynamoString(now)
            }
      })
    );
  } catch (error) {
    if (!(error instanceof Error) || error.name !== 'ConditionalCheckFailedException') throw error;
  }
}

export async function deleteUserDispatch({
  dynamodb,
  tableName,
  subscriberHash,
  dispatchId
}: StoreContext & { dispatchId: unknown }) {
  const dispatch = await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId });
  if (!dispatch) return null;
  await dynamodb.send(
    new DeleteItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      }
    })
  );
  await dynamodb.send(
    new DeleteItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchLookupSk(dispatch.id))
      }
    })
  );
  return dispatch;
}

export function dispatchAvailabilityFromRows(
  rows: DispatchRecord[] = [],
  { nowSeconds = Math.floor(Date.now() / 1000), cooldownSeconds = DEFAULT_COOLDOWN_SECONDS, owner = false } = {}
) {
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

export async function dispatchAvailability({
  dynamodb,
  tableName,
  subscriberHash,
  owner = false
}: StoreContext & { owner?: boolean }) {
  let rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 20 });
  const recovered = await recoverStaleDispatches({ dynamodb, tableName, subscriberHash, rows });
  if (recovered) rows = await listUserDispatches({ dynamodb, tableName, subscriberHash, limit: 20 });
  return dispatchAvailabilityFromRows(rows, { owner });
}

function draftStatus(value: unknown) {
  const status = String(value || 'draft')
    .trim()
    .toLowerCase();
  if (status === 'upgrade') return 'ready';
  return DRAFT_STATUSES.has(status) ? status : 'draft';
}

function dispatchMessageDynamoItem(value: unknown): AttributeValue {
  const message = objectValue(value);
  const role = String(message.role || 'assistant')
    .trim()
    .toLowerCase();
  return {
    M: {
      id: dynamoString(String(message.id || '').slice(0, 120)),
      role: dynamoString(['user', 'assistant', 'system'].includes(role) ? role : 'assistant'),
      text: dynamoString(String(message.text || '').slice(0, 2400)),
      time: dynamoString(String(message.time || '').slice(0, 60)),
      kind: dynamoString(String(message.kind || '').slice(0, 80)),
      status: dynamoString(String(message.status || '').slice(0, 40))
    }
  };
}

function compactMessages(messages: unknown = []): AttributeValue[] {
  return Array.isArray(messages) ? messages.slice(-24).map(dispatchMessageDynamoItem) : [];
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
  conversationId = '',
  clarificationQuestion = '',
  clarificationAnswer = '',
  brief = null,
  title = '',
  messages = [],
  now = new Date().toISOString()
}: StoreContext & {
  dispatchId?: unknown;
  status?: unknown;
  topic?: unknown;
  prompt?: unknown;
  direction?: unknown;
  conversationId?: unknown;
  clarificationQuestion?: unknown;
  clarificationAnswer?: unknown;
  brief?: unknown;
  title?: unknown;
  messages?: unknown[];
  now?: string;
}) {
  const id = validDispatchId(dispatchId) || crypto.randomUUID();
  const existing = dispatchId ? await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id }) : null;
  const normalizedStatus = draftStatus(status);
  const ttl = dispatchDraftTtlSeconds(now);
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
    conversation_id: dynamoString(String(conversationId || '').slice(0, 80)),
    clarification_question: dynamoString(String(clarificationQuestion || '').slice(0, 800)),
    clarification_answer: dynamoString(String(clarificationAnswer || '').slice(0, 1200)),
    brief_json: dynamoString(dispatchBriefJson(brief)),
    title: dynamoString(
      String(title || topic || prompt || 'Dispatch')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 120)
    ),
    messages: dynamoList(messages, dispatchMessageDynamoItem),
    created_at: dynamoString(now),
    updated_at: dynamoString(now),
    ttl: dynamoNumber(ttl)
  };
  if (!existing) {
    await dynamodb.send(
      new PutItemCommand({
        TableName: tableName,
        Item: item,
        ConditionExpression: 'attribute_not_exists(pk)'
      })
    );
    await putDispatchLookup({ dynamodb, tableName, subscriberHash, dispatchId: id, createdAt: now, now, ttl });
    return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
  }

  await dynamodb.send(
    new UpdateItemCommand({
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
        '#conversation_id = :conversation_id',
        '#clarification_question = :clarification_question',
        '#clarification_answer = :clarification_answer',
        '#brief_json = :brief_json',
        '#title = :title',
        '#messages = :messages',
        '#updated_at = :now',
        '#ttl = :ttl'
      ].join(', '),
      ConditionExpression: '#status IN (:draft, :shaping, :needs_clarification, :ready)',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#topic': 'topic',
        '#prompt': 'prompt',
        '#direction': 'direction',
        '#conversation_id': 'conversation_id',
        '#clarification_question': 'clarification_question',
        '#clarification_answer': 'clarification_answer',
        '#brief_json': 'brief_json',
        '#title': 'title',
        '#messages': 'messages',
        '#updated_at': 'updated_at',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':status': dynamoString(normalizedStatus),
        ':topic': dynamoString(String(topic || prompt || title || existing.topic || '').slice(0, 300)),
        ':prompt': dynamoString(String(prompt || existing.prompt || '').slice(0, 1400)),
        ':direction': dynamoString(String(direction || prompt || topic || existing.direction || '').slice(0, 1800)),
        ':conversation_id': dynamoString(String(conversationId || existing.conversation_id || '').slice(0, 80)),
        ':clarification_question': dynamoString(String(clarificationQuestion || '').slice(0, 800)),
        ':clarification_answer': dynamoString(
          String(clarificationAnswer || existing.clarification_answer || '').slice(0, 1200)
        ),
        ':brief_json': dynamoString(dispatchBriefJson(brief) || existing.brief_json || ''),
        ':title': dynamoString(
          String(title || topic || prompt || existing.title || 'Dispatch')
            .replace(/\s+/g, ' ')
            .trim()
            .slice(0, 120)
        ),
        ':messages': { L: compactMessages(messages) },
        ':now': dynamoString(now),
        ':ttl': dynamoNumber(ttl),
        ':draft': dynamoString('draft'),
        ':shaping': dynamoString('shaping'),
        ':needs_clarification': dynamoString('needs_clarification'),
        ':ready': dynamoString('ready')
      }
    })
  );
  await updateDispatchLookupTtl({ dynamodb, tableName, subscriberHash, dispatchId: id, now, ttl });
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
  brief = null,
  templateTest = false,
  now = new Date().toISOString(),
  dispatchId = crypto.randomUUID()
}: StoreContext & {
  emailHash: string;
  toEmail: string;
  topic: unknown;
  prompt: unknown;
  direction: unknown;
  clarificationQuestion?: unknown;
  clarificationAnswer?: unknown;
  brief?: unknown;
  templateTest?: boolean;
  now?: string;
  dispatchId?: unknown;
}) {
  const id = validDispatchId(dispatchId);
  if (!id) throw new Error('dispatchId is invalid');
  await dynamodb.send(
    new PutItemCommand({
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
        brief_json: dynamoString(dispatchBriefJson(brief)),
        template_test: { BOOL: Boolean(templateTest) },
        created_at: dynamoString(now),
        updated_at: dynamoString(now),
        queued_at: dynamoString(now)
      },
      ConditionExpression: 'attribute_not_exists(pk)'
    })
  );
  await putDispatchLookup({ dynamodb, tableName, subscriberHash, dispatchId: id, createdAt: now });
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
  brief = null,
  templateTest = false
}: StoreContext & {
  dispatchId: unknown;
  emailHash: string;
  toEmail: string;
  topic: unknown;
  prompt: unknown;
  direction: unknown;
  clarificationQuestion?: unknown;
  clarificationAnswer?: unknown;
  brief?: unknown;
  templateTest?: boolean;
}) {
  const id = validDispatchId(dispatchId);
  if (!id) throw new Error('dispatchId is invalid');
  const existing = await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
  if (!existing) throw new Error('dispatch draft not found');
  const now = new Date().toISOString();
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(existing.created_at, existing.id))
      },
      UpdateExpression:
        [
          'SET #status = :queued',
          '#email_hash = :email_hash',
          '#to_email = :to_email',
          '#topic = :topic',
          '#prompt = :prompt',
          '#direction = :direction',
          '#clarification_question = :clarification_question',
          '#clarification_answer = :clarification_answer',
          '#brief_json = :brief_json',
          '#template_test = :template_test',
          '#updated_at = :now',
          '#queued_at = :now'
        ].join(', ') + ' REMOVE #ttl',
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
        '#brief_json': 'brief_json',
        '#template_test': 'template_test',
        '#updated_at': 'updated_at',
        '#queued_at': 'queued_at',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':queued': dynamoString('queued'),
        ':email_hash': dynamoString(emailHash || subscriberHash),
        ':to_email': dynamoString(toEmail),
        ':topic': dynamoString(String(topic || prompt || existing.topic || '').slice(0, 300)),
        ':prompt': dynamoString(String(prompt || existing.prompt || '').slice(0, 1400)),
        ':direction': dynamoString(String(direction || prompt || topic || existing.direction || '').slice(0, 1800)),
        ':clarification_question': dynamoString(
          String(clarificationQuestion || existing.clarification_question || '').slice(0, 800)
        ),
        ':clarification_answer': dynamoString(
          String(clarificationAnswer || existing.clarification_answer || '').slice(0, 1200)
        ),
        ':brief_json': dynamoString(dispatchBriefJson(brief) || existing.brief_json || ''),
        ':template_test': { BOOL: Boolean(templateTest) },
        ':now': dynamoString(now),
        ':draft': dynamoString('draft'),
        ':shaping': dynamoString('shaping'),
        ':needs_clarification': dynamoString('needs_clarification'),
        ':ready': dynamoString('ready')
      }
    })
  );
  await updateDispatchLookupTtl({ dynamodb, tableName, subscriberHash, dispatchId: id, now, ttl: 0 });
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: id });
}

export async function claimQueuedDispatch({ dynamodb, tableName, subscriberHash, dispatch }: DispatchContext) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const workerRunId = crypto.randomUUID();
  const leaseExpiresAt = isoAfter(
    process.env.DISPATCH_GENERATION_LEASE_SECONDS || DEFAULT_GENERATION_LEASE_SECONDS,
    nowDate
  );
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression:
        'SET #status = :generating, #updated_at = :now, #started_at = :now, #lease_expires_at = :lease_expires_at, #worker_run_id = :worker_run_id REMOVE #ttl',
      ConditionExpression: '#status = :queued',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#updated_at': 'updated_at',
        '#started_at': 'started_at',
        '#lease_expires_at': 'lease_expires_at',
        '#worker_run_id': 'worker_run_id',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':queued': dynamoString('queued'),
        ':generating': dynamoString('generating'),
        ':now': dynamoString(now),
        ':lease_expires_at': dynamoString(leaseExpiresAt),
        ':worker_run_id': dynamoString(workerRunId)
      }
    })
  );
  return {
    ...dispatch,
    status: 'generating',
    updated_at: now,
    started_at: now,
    lease_expires_at: leaseExpiresAt,
    worker_run_id: workerRunId
  };
}

function sourceDynamoItem(value: unknown): AttributeValue {
  const source = objectValue(value);
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

export async function markDispatchReadyToSend({
  dynamodb,
  tableName,
  subscriberHash,
  dispatch,
  result,
  artifact
}: DispatchContext & { result: JsonRecord; artifact?: JsonRecord | null }) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const sources = Array.isArray(result.sources) ? result.sources : [];
  const leaseExpiresAt = isoAfter(process.env.DISPATCH_SEND_LEASE_SECONDS || DEFAULT_SEND_LEASE_SECONDS, nowDate);
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression:
        [
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
          '#content_artifact_key = :content_artifact_key',
          '#lease_expires_at = :lease_expires_at'
        ].join(', ') + ' REMOVE #ttl',
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
        '#content_artifact_key': 'content_artifact_key',
        '#lease_expires_at': 'lease_expires_at',
        '#ttl': 'ttl'
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
        ':input_tokens': dynamoNumber(
          objectValue(result.usage).inputTokens || objectValue(result.usage).input_tokens || 0
        ),
        ':output_tokens': dynamoNumber(
          objectValue(result.usage).outputTokens || objectValue(result.usage).output_tokens || 0
        ),
        ':source_count': dynamoNumber(sources.length),
        ':sources': dynamoList(sources, sourceDynamoItem),
        ':content_artifact_bucket': dynamoString(artifact?.bucket || ''),
        ':content_artifact_key': dynamoString(artifact?.key || ''),
        ':lease_expires_at': dynamoString(leaseExpiresAt)
      }
    })
  );
  return await getUserDispatch({ dynamodb, tableName, subscriberHash, dispatchId: dispatch.id });
}

export async function claimReadyToSendDispatch({ dynamodb, tableName, subscriberHash, dispatch }: DispatchContext) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const sendAttemptId = crypto.randomUUID();
  const leaseExpiresAt = isoAfter(process.env.DISPATCH_SEND_LEASE_SECONDS || DEFAULT_SEND_LEASE_SECONDS, nowDate);
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression:
        'SET #status = :sending, #updated_at = :now, #send_started_at = :now, #lease_expires_at = :lease_expires_at, #send_attempt_id = :send_attempt_id REMOVE #ttl',
      ConditionExpression: '#status = :ready_to_send AND attribute_not_exists(#submission_id)',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#updated_at': 'updated_at',
        '#send_started_at': 'send_started_at',
        '#lease_expires_at': 'lease_expires_at',
        '#send_attempt_id': 'send_attempt_id',
        '#submission_id': 'submission_id',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':ready_to_send': dynamoString('ready_to_send'),
        ':sending': dynamoString('sending'),
        ':now': dynamoString(now),
        ':lease_expires_at': dynamoString(leaseExpiresAt),
        ':send_attempt_id': dynamoString(sendAttemptId)
      }
    })
  );
  return {
    ...dispatch,
    status: 'sending',
    updated_at: now,
    send_started_at: now,
    lease_expires_at: leaseExpiresAt,
    send_attempt_id: sendAttemptId
  };
}

export async function markDispatchSent({
  dynamodb,
  tableName,
  subscriberHash,
  dispatch,
  submissionId
}: DispatchContext & { submissionId: unknown }) {
  const now = new Date().toISOString();
  const ttl = dispatchHistoryTtlSeconds(now);
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression: [
        'SET #status = :sent',
        '#updated_at = :now',
        '#sent_at = :now',
        '#submission_id = :submission_id',
        '#ttl = :ttl'
      ].join(', '),
      ConditionExpression:
        '#status = :sending AND #send_attempt_id = :send_attempt_id AND attribute_not_exists(#submission_id)',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#send_attempt_id': 'send_attempt_id',
        '#updated_at': 'updated_at',
        '#sent_at': 'sent_at',
        '#submission_id': 'submission_id',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':sending': dynamoString('sending'),
        ':send_attempt_id': dynamoString(dispatch.send_attempt_id),
        ':sent': dynamoString('sent'),
        ':now': dynamoString(now),
        ':submission_id': dynamoString(submissionId),
        ':ttl': dynamoNumber(ttl)
      }
    })
  );
  await updateDispatchLookupTtl({ dynamodb, tableName, subscriberHash, dispatchId: dispatch.id, now, ttl });
}

export async function markDispatchReadyToRetry({
  dynamodb,
  tableName,
  subscriberHash,
  dispatch,
  error
}: DispatchContext & { error: unknown }) {
  const nowDate = new Date();
  const now = nowDate.toISOString();
  const leaseExpiresAt = isoAfter(process.env.DISPATCH_SEND_LEASE_SECONDS || DEFAULT_SEND_LEASE_SECONDS, nowDate);
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression:
        [
          'SET #status = :ready_to_send',
          '#updated_at = :now',
          '#lease_expires_at = :lease_expires_at',
          '#error = :error'
        ].join(', ') + ' REMOVE #ttl',
      ConditionExpression:
        '#status = :sending AND #send_attempt_id = :send_attempt_id AND attribute_not_exists(#submission_id)',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#send_attempt_id': 'send_attempt_id',
        '#submission_id': 'submission_id',
        '#updated_at': 'updated_at',
        '#lease_expires_at': 'lease_expires_at',
        '#error': 'error',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':sending': dynamoString('sending'),
        ':ready_to_send': dynamoString('ready_to_send'),
        ':send_attempt_id': dynamoString(dispatch.send_attempt_id),
        ':now': dynamoString(now),
        ':lease_expires_at': dynamoString(leaseExpiresAt),
        ':error': dynamoString(
          String((error instanceof Error ? error.message : error) || 'Dispatch delivery will retry.').slice(0, 1000)
        )
      }
    })
  );
}

export async function markDispatchFailed({
  dynamodb,
  tableName,
  subscriberHash,
  dispatch,
  error
}: DispatchContext & { error: unknown }) {
  const now = new Date().toISOString();
  const ttl = dispatchHistoryTtlSeconds(now);
  await dynamodb.send(
    new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(dispatchSk(dispatch.created_at, dispatch.id))
      },
      UpdateExpression: 'SET #status = :failed, #updated_at = :now, #failed_at = :now, #error = :error, #ttl = :ttl',
      ConditionExpression: '#status <> :sent',
      ExpressionAttributeNames: {
        '#status': 'status',
        '#updated_at': 'updated_at',
        '#failed_at': 'failed_at',
        '#error': 'error',
        '#ttl': 'ttl'
      },
      ExpressionAttributeValues: {
        ':failed': dynamoString('failed'),
        ':sent': dynamoString('sent'),
        ':now': dynamoString(now),
        ':error': dynamoString(
          String((error instanceof Error ? error.message : error) || 'Dispatch failed.').slice(0, 1000)
        ),
        ':ttl': dynamoNumber(ttl)
      }
    })
  );
  await updateDispatchLookupTtl({ dynamodb, tableName, subscriberHash, dispatchId: dispatch.id, now, ttl });
}

export async function recoverStaleDispatches({
  dynamodb,
  tableName,
  subscriberHash,
  rows = []
}: StoreContext & { rows?: DispatchRecord[] }) {
  const nowSeconds = Math.floor(Date.now() / 1000);
  let recovered = 0;
  for (const row of rows) {
    if (row.status === 'queued' && dispatchQueuedStale(row, nowSeconds)) {
      await markDispatchFailed({
        dynamodb,
        tableName,
        subscriberHash,
        dispatch: row,
        error: 'Dispatch was queued but not claimed by the worker in time. Please generate it again.'
      })
        .then(() => {
          recovered += 1;
        })
        .catch(() => {});
    } else if (row.status === 'shaping' && dispatchShapingStale(row, nowSeconds)) {
      const now = new Date().toISOString();
      const status = recoveredDraftStatus(row);
      await dynamodb
        .send(
          new UpdateItemCommand({
            TableName: tableName,
            Key: {
              pk: dynamoString(userConversationPk(subscriberHash)),
              sk: dynamoString(dispatchSk(row.created_at, row.id))
            },
            UpdateExpression: 'SET #status = :status, #updated_at = :now',
            ConditionExpression: '#status = :shaping',
            ExpressionAttributeNames: {
              '#status': 'status',
              '#updated_at': 'updated_at'
            },
            ExpressionAttributeValues: {
              ':shaping': dynamoString('shaping'),
              ':status': dynamoString(status),
              ':now': dynamoString(now)
            }
          })
        )
        .then(() => {
          recovered += 1;
        })
        .catch(() => {});
    } else if (!dispatchLeaseExpired(row, nowSeconds)) {
      continue;
    } else if (row.status === 'generating') {
      const now = new Date().toISOString();
      await dynamodb
        .send(
          new UpdateItemCommand({
            TableName: tableName,
            Key: {
              pk: dynamoString(userConversationPk(subscriberHash)),
              sk: dynamoString(dispatchSk(row.created_at, row.id))
            },
            UpdateExpression: 'SET #status = :queued, #updated_at = :now, #queued_at = :now REMOVE #ttl',
            ConditionExpression: '#status = :generating AND #lease_expires_at = :lease_expires_at',
            ExpressionAttributeNames: {
              '#status': 'status',
              '#updated_at': 'updated_at',
              '#queued_at': 'queued_at',
              '#lease_expires_at': 'lease_expires_at',
              '#ttl': 'ttl'
            },
            ExpressionAttributeValues: {
              ':generating': dynamoString('generating'),
              ':queued': dynamoString('queued'),
              ':now': dynamoString(now),
              ':lease_expires_at': dynamoString(row.lease_expires_at)
            }
          })
        )
        .then(() => {
          recovered += 1;
        })
        .catch(() => {});
    } else if (row.status === 'ready_to_send') {
      const nowDate = new Date();
      const now = nowDate.toISOString();
      const leaseExpiresAt = isoAfter(process.env.DISPATCH_SEND_LEASE_SECONDS || DEFAULT_SEND_LEASE_SECONDS, nowDate);
      await dynamodb
        .send(
          new UpdateItemCommand({
            TableName: tableName,
            Key: {
              pk: dynamoString(userConversationPk(subscriberHash)),
              sk: dynamoString(dispatchSk(row.created_at, row.id))
            },
            UpdateExpression: 'SET #updated_at = :now, #lease_expires_at = :lease_expires_at REMOVE #ttl',
            ConditionExpression: '#status = :ready_to_send AND #lease_expires_at = :old_lease_expires_at',
            ExpressionAttributeNames: {
              '#status': 'status',
              '#updated_at': 'updated_at',
              '#lease_expires_at': 'lease_expires_at',
              '#ttl': 'ttl'
            },
            ExpressionAttributeValues: {
              ':ready_to_send': dynamoString('ready_to_send'),
              ':now': dynamoString(now),
              ':lease_expires_at': dynamoString(leaseExpiresAt),
              ':old_lease_expires_at': dynamoString(row.lease_expires_at)
            }
          })
        )
        .then(() => {
          recovered += 1;
        })
        .catch(() => {});
    } else if (row.status === 'sending') {
      await markDispatchFailed({
        dynamodb,
        tableName,
        subscriberHash,
        dispatch: row,
        error: 'Dispatch delivery could not be confirmed. It was not retried to avoid sending a duplicate email.'
      })
        .then(() => {
          recovered += 1;
        })
        .catch(() => {});
    }
  }
  return recovered;
}
