import { GetItemCommand, PutItemCommand, QueryCommand, UpdateItemCommand } from '@aws-sdk/client-dynamodb';
import {
  artifactDynamoString,
  citationDynamoItem,
  conversationPreview,
  conversationSk,
  conversationSummaryFromItem,
  conversationTitle,
  conversationTurnFromItem,
  dynamoList,
  dynamoNumber,
  dynamoString,
  historyFromTurns,
  messagesFromTurns,
  preflightDynamoItem,
  toolTraceDynamoString,
  turnSk,
  turnSkPrefix,
  userConversationPk,
  validConversationId
} from './user-conversations.mjs';

function noopLog() {}

function logger(logEvent) {
  return typeof logEvent === 'function' ? logEvent : noopLog;
}

function tableReady({ tableName, subscriberHash }) {
  return Boolean(tableName && subscriberHash);
}

function boundedList(values = [], limit = 12, chars = 80) {
  const seen = new Set();
  const out = [];
  for (const value of values || []) {
    const text = String(value || '').trim().replace(/\s+/g, ' ').slice(0, chars);
    const key = text.toLowerCase();
    if (!text || seen.has(key)) continue;
    seen.add(key);
    out.push(text);
    if (out.length >= limit) break;
  }
  return out;
}

function dynamoStringList(values = [], limit = 12, chars = 80) {
  return dynamoList(boundedList(values, limit, chars), dynamoString);
}

export async function loadUserConversationHistory({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  logEvent
}) {
  const log = logger(logEvent);
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return [];
  try {
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
      ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
      ExpressionAttributeValues: {
        ':pk': dynamoString(userConversationPk(subscriberHash)),
        ':prefix': dynamoString(turnSkPrefix(validId))
      },
      ScanIndexForward: false,
      Limit: 8
    }));
    return historyFromTurns((response.Items || []).map(conversationTurnFromItem));
  } catch (error) {
    log('warning', 'user_conversation_history_load_failed', {
      subscriber_hash: subscriberHash,
      conversation_id: validId,
      error_type: error.constructor?.name || 'Error'
    });
    return [];
  }
}

export async function loadUserConversationSummaries({
  dynamodb,
  tableName,
  subscriberHash,
  limit = 8,
  logEvent
}) {
  const log = logger(logEvent);
  if (!tableReady({ tableName, subscriberHash })) return [];
  try {
    const response = await dynamodb.send(new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
      ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
      ExpressionAttributeValues: {
        ':pk': dynamoString(userConversationPk(subscriberHash)),
        ':prefix': dynamoString('conversation#')
      }
    }));
    return (response.Items || [])
      .map(conversationSummaryFromItem)
      .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
      .slice(0, Math.max(1, Math.min(Number(limit) || 8, 20)));
  } catch (error) {
    log('warning', 'user_conversation_summaries_load_failed', {
      subscriber_hash: subscriberHash,
      error_type: error.constructor?.name || 'Error'
    });
    return [];
  }
}

export async function getUserConversationMetadata({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId
}) {
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  const response = await dynamodb.send(new GetItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(conversationSk(validId))
    }
  }));
  return response.Item ? conversationSummaryFromItem(response.Item) : null;
}

export async function loadUserConversationMessages({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  limit = 80
}) {
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return [];
  const response = await dynamodb.send(new QueryCommand({
    TableName: tableName,
    KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
    ExpressionAttributeNames: { '#pk': 'pk', '#sk': 'sk' },
    ExpressionAttributeValues: {
      ':pk': dynamoString(userConversationPk(subscriberHash)),
      ':prefix': dynamoString(turnSkPrefix(validId))
    },
    ScanIndexForward: false,
    Limit: Math.max(1, Math.min(Number(limit) || 80, 80))
  }));
  const turns = (response.Items || [])
    .map(conversationTurnFromItem)
    .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  return messagesFromTurns(turns);
}

export async function getUserConversation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  limit = 80
}) {
  const conversation = await getUserConversationMetadata({ dynamodb, tableName, subscriberHash, conversationId });
  if (!conversation) return null;
  const messages = await loadUserConversationMessages({ dynamodb, tableName, subscriberHash, conversationId, limit });
  return { conversation, messages };
}

export async function createUserConversation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  title,
  preview,
  scope,
  now = new Date().toISOString()
}) {
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  await dynamodb.send(new PutItemCommand({
    TableName: tableName,
    Item: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(conversationSk(validId)),
      item_type: dynamoString('conversation'),
      conversation_id: dynamoString(validId),
      title: dynamoString(conversationTitle(title || '')),
      title_source: dynamoString('user'),
      preview: dynamoString(conversationPreview(preview || title || '')),
      scope: dynamoString(scope || 'all'),
      created_at: dynamoString(now),
      updated_at: dynamoString(now),
      last_message_at: dynamoString(''),
      turn_count: dynamoNumber(0)
    },
    ConditionExpression: 'attribute_not_exists(pk)'
  }));
  return await getUserConversationMetadata({ dynamodb, tableName, subscriberHash, conversationId: validId });
}

export async function renameUserConversation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  title,
  now = new Date().toISOString()
}) {
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(conversationSk(validId))
    },
    UpdateExpression: 'SET #title = :title, #title_source = :title_source, #updated_at = :updated_at',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeNames: {
      '#title': 'title',
      '#title_source': 'title_source',
      '#updated_at': 'updated_at'
    },
    ExpressionAttributeValues: {
      ':title': dynamoString(conversationTitle(title)),
      ':title_source': dynamoString('user'),
      ':updated_at': dynamoString(now)
    }
  }));
  return await getUserConversationMetadata({ dynamodb, tableName, subscriberHash, conversationId: validId });
}

async function putTurn({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  requestId,
  createdAt,
  scope,
  question = '',
  answer = '',
  citations = [],
  preflight = null,
  artifact = null,
  toolTrace = null,
  metrics = {}
}) {
  const citationItems = (citations || []).slice(0, 24).map(citationDynamoItem);
  const toolNames = boundedList((toolTrace?.calls || []).map((call) => call?.name), 20, 80);
  const item = {
    pk: dynamoString(userConversationPk(subscriberHash)),
    sk: dynamoString(turnSk(conversationId, createdAt, requestId)),
    item_type: dynamoString('turn'),
    conversation_id: dynamoString(conversationId),
    request_id: dynamoString(requestId),
    created_at: dynamoString(createdAt),
    scope: dynamoString(scope || 'all'),
    question: dynamoString(String(question || '').slice(0, 4000)),
    answer: dynamoString(String(answer || '').slice(0, 12000)),
    question_chars: dynamoNumber(String(question || '').length),
    answer_chars: dynamoNumber(String(answer || '').length),
    citation_count: dynamoNumber((citations || []).length),
    citations: dynamoList(citationItems, (value) => value),
    preflight: preflightDynamoItem(preflight),
    model: dynamoString(metrics.model),
    duration_ms: dynamoNumber(metrics.duration_ms),
    output_tokens: dynamoNumber(metrics.output_tokens),
    stop_reason: dynamoString(metrics.stop_reason),
    tool_count: dynamoNumber(toolNames.length),
    tool_names: dynamoStringList(toolNames, 20, 80),
    tool_trace_json: toolTraceDynamoString(toolTrace)
  };
  if (artifact) {
    item.artifact_kind = dynamoString(artifact.kind || 'artifact');
    item.artifact_version = dynamoNumber(artifact.artifact_version || artifact.version || 1);
    item.artifact_json = artifactDynamoString(artifact);
  }
  await dynamodb.send(new PutItemCommand({ TableName: tableName, Item: item }));
}

async function upsertConversation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  title,
  preview,
  scope,
  requestId,
  now,
  lastQuestion,
  incrementTurns,
  preservePreview = false,
  preserveLastQuestion = false
}) {
  const response = await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(conversationSk(conversationId))
    },
    UpdateExpression: [
      'SET #item_type = :item_type',
      '#conversation_id = :conversation_id',
      '#title = if_not_exists(#title, :title)',
      '#title_source = if_not_exists(#title_source, :title_source)',
      preservePreview ? '#preview = if_not_exists(#preview, :preview)' : '#preview = :preview',
      '#scope = :scope',
      '#created_at = if_not_exists(#created_at, :now)',
      '#updated_at = :now',
      '#last_message_at = :now',
      '#last_request_id = :request_id',
      preserveLastQuestion ? '#last_question = if_not_exists(#last_question, :question)' : '#last_question = :question',
      '#turn_count = if_not_exists(#turn_count, :zero) + :turn_increment'
    ].join(', '),
    ExpressionAttributeNames: {
      '#item_type': 'item_type',
      '#conversation_id': 'conversation_id',
      '#title': 'title',
      '#title_source': 'title_source',
      '#preview': 'preview',
      '#scope': 'scope',
      '#created_at': 'created_at',
      '#updated_at': 'updated_at',
      '#last_message_at': 'last_message_at',
      '#last_request_id': 'last_request_id',
      '#last_question': 'last_question',
      '#turn_count': 'turn_count'
    },
    ExpressionAttributeValues: {
      ':item_type': dynamoString('conversation'),
      ':conversation_id': dynamoString(conversationId),
      ':title': dynamoString(title),
      ':title_source': dynamoString('auto'),
      ':preview': dynamoString(preview),
      ':scope': dynamoString(scope || 'all'),
      ':now': dynamoString(now),
      ':request_id': dynamoString(requestId),
      ':question': dynamoString(String(lastQuestion || '').slice(0, 500)),
      ':zero': dynamoNumber(0),
      ':turn_increment': dynamoNumber(incrementTurns ? 1 : 0)
    },
    ReturnValues: 'ALL_NEW'
  }));
  return response.Attributes ? conversationSummaryFromItem(response.Attributes) : null;
}

export async function recordUserConversationTurn({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  question,
  answer,
  scope,
  requestId,
  citations,
  preflight,
  toolTrace,
  metrics,
  logEvent
}) {
  const log = logger(logEvent);
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  const now = new Date().toISOString();
  try {
    await putTurn({
      dynamodb,
      tableName,
      subscriberHash,
      conversationId: validId,
      requestId,
      createdAt: now,
      scope,
      question,
      answer,
      citations,
      preflight,
      toolTrace,
      metrics
    });
    return await upsertConversation({
      dynamodb,
      tableName,
      subscriberHash,
      conversationId: validId,
      title: conversationTitle(question),
      preview: conversationPreview(question),
      scope,
      requestId,
      now,
      lastQuestion: question,
      incrementTurns: true
    });
  } catch (error) {
    log('warning', 'user_conversation_turn_record_failed', {
      subscriber_hash: subscriberHash,
      conversation_id: validId,
      request_id: requestId,
      error_type: error.constructor?.name || 'Error'
    });
    return null;
  }
}

export async function recordUserConversationFeedback({
  dynamodb,
  tableName,
  subscriberHash,
  requestId,
  reaction,
  comment = '',
  feedbackAt = new Date().toISOString(),
  logEvent
}) {
  const log = logger(logEvent);
  if (!tableReady({ tableName, subscriberHash }) || !requestId || !reaction) return { found: false };
  try {
    const items = [];
    let exclusiveStartKey;
    do {
      const response = await dynamodb.send(new QueryCommand({
        TableName: tableName,
        KeyConditionExpression: '#pk = :pk AND begins_with(#sk, :prefix)',
        FilterExpression: '#request_id = :request_id',
        ExpressionAttributeNames: {
          '#pk': 'pk',
          '#sk': 'sk',
          '#request_id': 'request_id'
        },
        ExpressionAttributeValues: {
          ':pk': dynamoString(userConversationPk(subscriberHash)),
          ':prefix': dynamoString('turn#'),
          ':request_id': dynamoString(requestId)
        },
        ExclusiveStartKey: exclusiveStartKey
      }));
      items.push(...(response.Items || []));
      exclusiveStartKey = response.LastEvaluatedKey;
    } while (exclusiveStartKey && items.length === 0);
    if (!items.length) return { found: false };
    for (const item of items) {
      await dynamodb.send(new UpdateItemCommand({
        TableName: tableName,
        Key: { pk: item.pk, sk: item.sk },
        UpdateExpression: 'SET #feedback_reaction = :reaction, #feedback_at = :feedback_at, #feedback_comment = :feedback_comment ADD #feedback_revision :one',
        ExpressionAttributeNames: {
          '#feedback_reaction': 'feedback_reaction',
          '#feedback_at': 'feedback_at',
          '#feedback_comment': 'feedback_comment',
          '#feedback_revision': 'feedback_revision'
        },
        ExpressionAttributeValues: {
          ':reaction': dynamoString(reaction),
          ':feedback_at': dynamoString(feedbackAt),
          ':feedback_comment': dynamoString(String(comment || '').slice(0, 1000)),
          ':one': dynamoNumber(1)
        }
      }));
    }
    return { found: true, updated: items.length };
  } catch (error) {
    log('warning', 'user_conversation_feedback_record_failed', {
      subscriber_hash: subscriberHash,
      request_id: requestId,
      error_type: error.constructor?.name || 'Error'
    });
    throw error;
  }
}

export async function updateUserConversationEvaluation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  summary = {},
  assessment = {},
  model = '',
  evaluator = 'thingy_eval',
  lastRequestId = '',
  now = new Date().toISOString(),
  logEvent
}) {
  const log = logger(logEvent);
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  const quality = String(assessment.quality || '').trim().toLowerCase();
  const safeQuality = ['clean', 'watch', 'problem'].includes(quality) ? quality : 'watch';
  try {
    const response = await dynamodb.send(new UpdateItemCommand({
      TableName: tableName,
      Key: {
        pk: dynamoString(userConversationPk(subscriberHash)),
        sk: dynamoString(conversationSk(validId))
      },
      UpdateExpression: [
        'SET #summary = :summary',
        '#topic = :topic',
        '#tags = :tags',
        '#preview = :preview',
        '#title = if_not_exists(#title, :title)',
        '#title_source = if_not_exists(#title_source, :title_source)',
        '#eval_status = :eval_status',
        '#eval_quality = :eval_quality',
        '#eval_flags = :eval_flags',
        '#eval_improvements = :eval_improvements',
        '#eval_assessed_at = :eval_assessed_at',
        '#eval_model = :eval_model',
        '#eval_last_request_id = :eval_last_request_id',
        '#eval_evaluator = :eval_evaluator',
        '#eval_topic = :eval_topic',
        '#eval_reader = :eval_reader',
        '#eval_thingy = :eval_thingy',
        '#eval_takeaway = :eval_takeaway',
        '#updated_at = :updated_at'
      ].join(', '),
      ConditionExpression: 'attribute_exists(pk)',
      ExpressionAttributeNames: {
        '#summary': 'summary',
        '#topic': 'topic',
        '#tags': 'tags',
        '#preview': 'preview',
        '#title': 'title',
        '#title_source': 'title_source',
        '#eval_status': 'eval_status',
        '#eval_quality': 'eval_quality',
        '#eval_flags': 'eval_flags',
        '#eval_improvements': 'eval_improvements',
        '#eval_assessed_at': 'eval_assessed_at',
        '#eval_model': 'eval_model',
        '#eval_last_request_id': 'eval_last_request_id',
        '#eval_evaluator': 'eval_evaluator',
        '#eval_topic': 'eval_topic',
        '#eval_reader': 'eval_reader',
        '#eval_thingy': 'eval_thingy',
        '#eval_takeaway': 'eval_takeaway',
        '#updated_at': 'updated_at'
      },
      ExpressionAttributeValues: {
        ':summary': dynamoString(String(summary.summary || '').slice(0, 1000)),
        ':topic': dynamoString(String(summary.topic || assessment.topic || '').slice(0, 120)),
        ':tags': dynamoStringList(summary.tags, 8, 40),
        ':preview': dynamoString(conversationPreview(summary.preview || summary.summary || assessment.takeaway || '')),
        ':title': dynamoString(conversationTitle(summary.title || summary.topic || assessment.topic || '')),
        ':title_source': dynamoString('auto'),
        ':eval_status': dynamoString('reviewed'),
        ':eval_quality': dynamoString(safeQuality),
        ':eval_flags': dynamoStringList(assessment.flags, 10, 80),
        ':eval_improvements': dynamoStringList(assessment.improvements, 6, 180),
        ':eval_assessed_at': dynamoString(now),
        ':eval_model': dynamoString(model),
        ':eval_last_request_id': dynamoString(lastRequestId),
        ':eval_evaluator': dynamoString(evaluator),
        ':eval_topic': dynamoString(String(assessment.topic || summary.topic || '').slice(0, 120)),
        ':eval_reader': dynamoString(String(assessment.reader || '').slice(0, 1000)),
        ':eval_thingy': dynamoString(String(assessment.thingy || '').slice(0, 1000)),
        ':eval_takeaway': dynamoString(String(assessment.takeaway || '').slice(0, 600)),
        ':updated_at': dynamoString(now)
      },
      ReturnValues: 'ALL_NEW'
    }));
    return response.Attributes ? conversationSummaryFromItem(response.Attributes) : null;
  } catch (error) {
    log('warning', 'user_conversation_evaluation_update_failed', {
      subscriber_hash: subscriberHash,
      conversation_id: validId,
      error_type: error.constructor?.name || 'Error'
    });
    return null;
  }
}

export async function markUserConversationEvalPosted({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  postedAt = new Date().toISOString()
}) {
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId) return null;
  const response = await dynamodb.send(new UpdateItemCommand({
    TableName: tableName,
    Key: {
      pk: dynamoString(userConversationPk(subscriberHash)),
      sk: dynamoString(conversationSk(validId))
    },
    UpdateExpression: 'SET #eval_posted_to_chatter_at = :posted_at, #updated_at = :updated_at',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeNames: {
      '#eval_posted_to_chatter_at': 'eval_posted_to_chatter_at',
      '#updated_at': 'updated_at'
    },
    ExpressionAttributeValues: {
      ':posted_at': dynamoString(postedAt),
      ':updated_at': dynamoString(postedAt)
    },
    ReturnValues: 'ALL_NEW'
  }));
  return response.Attributes ? conversationSummaryFromItem(response.Attributes) : null;
}

export async function recordUserArtifactConversation({
  dynamodb,
  tableName,
  subscriberHash,
  conversationId,
  artifact,
  scope,
  requestId,
  title,
  preview,
  logEvent,
  preserveConversationSummary = false
}) {
  const log = logger(logEvent);
  const validId = validConversationId(conversationId);
  if (!tableReady({ tableName, subscriberHash }) || !validId || !artifact) return null;
  const now = new Date().toISOString();
  try {
    await putTurn({
      dynamodb,
      tableName,
      subscriberHash,
      conversationId: validId,
      requestId,
      createdAt: now,
      scope,
      artifact
    });
    return await upsertConversation({
      dynamodb,
      tableName,
      subscriberHash,
      conversationId: validId,
      title: conversationTitle(title || artifact.title || 'Artifact'),
      preview: conversationPreview(preview || artifact.prompt || artifact.title || 'Artifact'),
      scope,
      requestId,
      now,
      lastQuestion: '',
      incrementTurns: false,
      preservePreview: preserveConversationSummary,
      preserveLastQuestion: preserveConversationSummary
    });
  } catch (error) {
    log('warning', 'user_artifact_conversation_record_failed', {
      subscriber_hash: subscriberHash,
      conversation_id: validId,
      request_id: requestId,
      artifact_kind: artifact?.kind,
      error_type: error.constructor?.name || 'Error'
    });
    return null;
  }
}
