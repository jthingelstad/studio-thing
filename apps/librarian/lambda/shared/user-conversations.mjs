export const USER_CONVERSATION_LIMIT = 50;
export const USER_CONVERSATION_TURN_LIMIT = 80;
export const MAX_HISTORY_MESSAGES = 8;
export const MAX_HISTORY_CHARS = 4000;
export const MAX_ARTIFACT_JSON_CHARS = 20000;
export const MAX_TOOL_TRACE_JSON_CHARS = 16000;

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

export function fromDynamoAttr(av) {
  if (av == null || typeof av !== 'object') return null;
  if ('S' in av) return av.S;
  if ('N' in av) return Number(av.N);
  if ('BOOL' in av) return Boolean(av.BOOL);
  if ('NULL' in av) return null;
  if ('L' in av) return (av.L || []).map(fromDynamoAttr);
  if ('M' in av) return Object.fromEntries(Object.entries(av.M || {}).map(([k, v]) => [k, fromDynamoAttr(v)]));
  return null;
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

function boundedText(value, max = 500) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function compactSourceRef(source) {
  if (!source || typeof source !== 'object') return null;
  return {
    title: boundedText(source.title || source.subject, 160),
    url: boundedText(source.url, 500),
    source_kind: boundedText(source.source_kind || source.kind, 40),
    publish_date: boundedText(source.publish_date, 40),
    reason: boundedText(source.reason, 240)
  };
}

function compactCuriosityMapArtifact(artifact) {
  return {
    kind: 'curiosity_map',
    artifact_version: 1,
    compacted: true,
    title: boundedText(artifact.title, 120),
    scope: boundedText(artifact.scope, 40),
    center: artifact.center && typeof artifact.center === 'object' ? {
      id: boundedText(artifact.center.id, 80),
      label: boundedText(artifact.center.label, 120),
      kind: boundedText(artifact.center.kind, 40),
      prompt: boundedText(artifact.center.prompt, 300),
      why: boundedText(artifact.center.why, 240)
    } : null,
    nodes: Array.isArray(artifact.nodes) ? artifact.nodes.slice(0, 8).map((node) => ({
      id: boundedText(node?.id, 80),
      label: boundedText(node?.label, 120),
      kind: boundedText(node?.kind, 40),
      weight: Number(node?.weight || 0),
      prompt: boundedText(node?.prompt, 300),
      why: boundedText(node?.why, 240),
      source_refs: Array.isArray(node?.source_refs)
        ? node.source_refs.slice(0, 2).map(compactSourceRef).filter(Boolean)
        : []
    })) : [],
    edges: Array.isArray(artifact.edges) ? artifact.edges.slice(0, 12).map((edge) => ({
      from: boundedText(edge?.from, 80),
      to: boundedText(edge?.to, 80),
      why: boundedText(edge?.why, 240)
    })) : [],
    sources: Array.isArray(artifact.sources)
      ? artifact.sources.slice(0, 5).map(compactSourceRef).filter(Boolean)
      : [],
    prompt: boundedText(artifact.prompt, 300)
  };
}

export function compactArtifactForStorage(artifact) {
  if (!artifact || typeof artifact !== 'object' || Array.isArray(artifact)) return null;
  if (artifact.kind === 'curiosity_map') return compactCuriosityMapArtifact(artifact);
  return {
    kind: boundedText(artifact.kind || 'artifact', 80),
    artifact_version: Number(artifact.artifact_version || artifact.version || 1),
    compacted: true,
    title: boundedText(artifact.title, 160),
    summary: boundedText(artifact.summary || artifact.description, 1000)
  };
}

export function artifactJsonForStorage(artifact) {
  if (!artifact || typeof artifact !== 'object' || Array.isArray(artifact)) return '';
  const full = JSON.stringify(artifact);
  if (full.length <= MAX_ARTIFACT_JSON_CHARS) return full;
  const compact = compactArtifactForStorage(artifact);
  const compactJson = JSON.stringify(compact || {});
  if (compactJson.length <= MAX_ARTIFACT_JSON_CHARS) return compactJson;
  return JSON.stringify({
    kind: boundedText(artifact.kind || 'artifact', 80),
    artifact_version: Number(artifact.artifact_version || artifact.version || 1),
    compacted: true,
    title: boundedText(artifact.title, 160),
    omitted: true
  });
}

export function artifactDynamoString(artifact) {
  return dynamoString(artifactJsonForStorage(artifact));
}

export function boundedJsonForStorage(value, maxChars = MAX_TOOL_TRACE_JSON_CHARS) {
  if (value == null) return '';
  try {
    const json = JSON.stringify(value);
    if (json.length <= maxChars) return json;
    return JSON.stringify({
      compacted: true,
      omitted: true,
      original_chars: json.length
    });
  } catch {
    return '';
  }
}

export function toolTraceDynamoString(trace) {
  return dynamoString(boundedJsonForStorage(trace, MAX_TOOL_TRACE_JSON_CHARS));
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
  const tags = Array.isArray(o.tags) ? o.tags : [];
  const evalFlags = Array.isArray(o.eval_flags) ? o.eval_flags : [];
  const evalImprovements = Array.isArray(o.eval_improvements) ? o.eval_improvements : [];
  const titleSource = o.title_source || '';
  const title = titleSource === 'user'
    ? o.title
    : (titleSource === 'eval' ? o.title : (o.eval_topic || o.title));
  return {
    id,
    conversation_id: id,
    title: title || 'Untitled chat',
    title_source: titleSource,
    preview: o.preview || '',
    summary: o.summary || '',
    topic: o.topic || '',
	    tags,
	    scope: o.scope || 'all',
	    mode: o.mode || 'thingy',
	    created_at: o.created_at || '',
    updated_at: o.updated_at || o.created_at || '',
    last_message_at: o.last_message_at || o.updated_at || '',
    last_request_id: o.last_request_id || '',
    turn_count: Number(o.turn_count || 0),
    eval_status: o.eval_status || '',
    eval_quality: o.eval_quality || '',
    eval_flags: evalFlags,
    eval_improvements: evalImprovements,
    eval_assessed_at: o.eval_assessed_at || '',
    eval_model: o.eval_model || '',
    eval_last_request_id: o.eval_last_request_id || '',
    eval_topic: o.eval_topic || '',
    eval_reader: o.eval_reader || '',
    eval_thingy: o.eval_thingy || '',
    eval_takeaway: o.eval_takeaway || '',
    eval_posted_to_chatter_at: o.eval_posted_to_chatter_at || ''
  };
}

export function conversationTurnFromItem(item) {
  const o = itemObject(item);
  let artifact = null;
  if (typeof o.artifact_json === 'string' && o.artifact_json) {
    try {
      const parsed = JSON.parse(o.artifact_json);
      artifact = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
    } catch (error) {
      artifact = null;
    }
  }
  return {
    conversation_id: o.conversation_id || '',
    request_id: o.request_id || '',
    created_at: o.created_at || '',
	    scope: o.scope || 'all',
	    mode: o.mode || 'thingy',
	    question: o.question || '',
    answer: o.answer || '',
    question_chars: Number(o.question_chars || 0),
    answer_chars: Number(o.answer_chars || 0),
    citation_count: Number(o.citation_count || 0),
    citations: Array.isArray(o.citations) ? o.citations : [],
    preflight: o.preflight && typeof o.preflight === 'object' ? o.preflight : null,
    feedback_reaction: o.feedback_reaction || '',
    feedback_at: o.feedback_at || '',
    feedback_comment: o.feedback_comment || '',
    model: o.model || '',
    duration_ms: Number(o.duration_ms || 0),
    output_tokens: Number(o.output_tokens || 0),
    stop_reason: o.stop_reason || '',
    tool_count: Number(o.tool_count || 0),
    tool_names: Array.isArray(o.tool_names) ? o.tool_names : [],
    tool_trace: typeof o.tool_trace_json === 'string' && o.tool_trace_json
      ? (() => {
        try {
          const parsed = JSON.parse(o.tool_trace_json);
          return parsed && typeof parsed === 'object' ? parsed : null;
        } catch {
          return null;
        }
      })()
      : null,
    artifact
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
        request_id: turn.request_id,
        artifact: turn.artifact || null,
        tool_names: turn.tool_names || []
      });
    } else if (turn.artifact) {
      messages.push({
        role: 'assistant',
        content: '',
        citations: [],
        created_at: turn.created_at,
        request_id: turn.request_id,
        artifact: turn.artifact,
        tool_names: turn.tool_names || []
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
