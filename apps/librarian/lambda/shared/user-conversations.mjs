import { fromDynamoAttr } from './conversations.mjs';

export const USER_CONVERSATION_LIMIT = 50;
export const USER_CONVERSATION_TURN_LIMIT = 80;
export const MAX_HISTORY_MESSAGES = 8;
export const MAX_HISTORY_CHARS = 4000;

const CONVERSATION_ID_RE = /^[A-Za-z0-9_.:-]{1,96}$/;

export function userConversationPk(subscriberHash) {
  return `user#${subscriberHash}`;
}

export function conversationSk(conversationId) {
  return `conversation#${conversationId}`;
}

export function turnSkPrefix(conversationId) {
  return `turn#${conversationId}#`;
}

export function turnSk(conversationId, createdAt, requestId) {
  return `${turnSkPrefix(conversationId)}${createdAt}#${requestId}`;
}

export function validConversationId(value) {
  const text = String(value || '').trim();
  return CONVERSATION_ID_RE.test(text) ? text : '';
}

export function conversationTitle(question) {
  const text = String(question || '').replace(/\s+/g, ' ').trim();
  return text ? text.slice(0, 80) : 'Untitled chat';
}

export function conversationPreview(question) {
  return String(question || '').replace(/\s+/g, ' ').trim().slice(0, 160);
}

export function dynamoString(value) {
  return { S: String(value || '') };
}

export function dynamoNumber(value) {
  return { N: String(Number(value || 0)) };
}

export function dynamoList(values, mapper = dynamoString) {
  return { L: (values || []).map(mapper) };
}

export function preflightDynamoItem(preflight) {
  const value = preflight && typeof preflight === 'object' ? preflight : {};
  return {
    M: {
      action: dynamoString(value.action),
      category: dynamoString(value.category),
      original_question: dynamoString(String(value.original_question || '').slice(0, 1200)),
      rewritten_question: dynamoString(String(value.rewritten_question || '').slice(0, 1200)),
      direct_answer: dynamoString(String(value.direct_answer || '').slice(0, 2000)),
      rationale: dynamoString(String(value.rationale || '').slice(0, 500)),
      answer_guidance: dynamoString(String(value.answer_guidance || '').slice(0, 700))
    }
  };
}

export function citationDynamoItem(citation) {
  return {
    M: {
      issue_number: dynamoString(citation.issue_number),
      source_kind: dynamoString(citation.source_kind),
      subject: dynamoString(citation.subject),
      publish_date: dynamoString(citation.publish_date),
      section: dynamoString(citation.section),
      url: dynamoString(citation.url)
    }
  };
}

function itemObject(item) {
  return Object.fromEntries(Object.entries(item || {}).map(([key, value]) => [key, fromDynamoAttr(value)]));
}

export function conversationSummaryFromItem(item) {
  const o = itemObject(item);
  const id = o.conversation_id || String(o.sk || '').replace(/^conversation#/, '');
  return {
    id,
    conversation_id: id,
    title: o.title || 'Untitled chat',
    preview: o.preview || '',
    scope: o.scope || 'all',
    created_at: o.created_at || '',
    updated_at: o.updated_at || o.created_at || '',
    last_message_at: o.last_message_at || o.updated_at || '',
    last_request_id: o.last_request_id || '',
    turn_count: Number(o.turn_count || 0)
  };
}

export function conversationTurnFromItem(item) {
  const o = itemObject(item);
  return {
    conversation_id: o.conversation_id || '',
    request_id: o.request_id || '',
    created_at: o.created_at || '',
    scope: o.scope || 'all',
    question: o.question || '',
    answer: o.answer || '',
    question_chars: Number(o.question_chars || 0),
    answer_chars: Number(o.answer_chars || 0),
    citation_count: Number(o.citation_count || 0),
    citations: Array.isArray(o.citations) ? o.citations : [],
    preflight: o.preflight && typeof o.preflight === 'object' ? o.preflight : null
  };
}

export function messagesFromTurns(turns = []) {
  const messages = [];
  for (const turn of [...turns].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))) {
    if (turn.question) {
      messages.push({
        role: 'user',
        content: turn.question,
        scope: turn.scope,
        created_at: turn.created_at,
        request_id: turn.request_id
      });
    }
    if (turn.answer) {
      messages.push({
        role: 'assistant',
        content: turn.answer,
        citations: turn.citations || [],
        created_at: turn.created_at,
        request_id: turn.request_id
      });
    }
  }
  return messages;
}

export function historyFromTurns(turns = [], options = {}) {
  const maxMessages = Number(options.maxMessages || MAX_HISTORY_MESSAGES);
  const maxChars = Number(options.maxChars || MAX_HISTORY_CHARS);
  const messages = messagesFromTurns(turns);
  let chars = 0;
  const result = [];
  for (const item of messages.slice(-maxMessages).reverse()) {
    const role = item.role === 'assistant' ? 'assistant' : item.role === 'user' ? 'user' : '';
    const content = String(item.content || '').trim().replace(/\s+/g, ' ').slice(0, 700);
    if (!role || !content) continue;
    chars += content.length;
    if (chars > maxChars) break;
    result.unshift({ role, content });
  }
  return result;
}
