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
    UpdateExpression: 'SET #title = :title, #updated_at = :updated_at',
    ConditionExpression: 'attribute_exists(pk)',
    ExpressionAttributeNames: {
      '#title': 'title',
      '#updated_at': 'updated_at'
    },
    ExpressionAttributeValues: {
      ':title': dynamoString(conversationTitle(title)),
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
  artifact = null
}) {
  const citationItems = (citations || []).slice(0, 24).map(citationDynamoItem);
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
    preflight: preflightDynamoItem(preflight)
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
      preflight
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
