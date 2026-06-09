import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { bedrock, dynamodb, fastModel } from '../shared/aws-clients.mjs';
import { jsonResponse } from '../shared/http.mjs';
import { emailHash, extractBearer, normalizeEmail, verifyToken } from '../shared/session.mjs';
import { isOwnerSubscriberHash } from '../shared/conversation-modes.mjs';
import { errorFields, logEvent } from '../shared/logging.mjs';
import {
  createQueuedDispatch,
  deleteUserDispatch,
  dispatchForClient,
  dispatchAvailability,
  getUserDispatch,
  listUserDispatches,
  queueDraftDispatch,
  recoverStaleDispatches,
  upsertDispatchDraft
} from '../shared/dispatch-store.mjs';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function entitlementsForSessionPayload(payload) {
  const entitlements = new Set(Array.isArray(payload?.entitlements) ? payload.entitlements : ['reader']);
  if (isOwnerSubscriberHash(payload?.sub)) {
    entitlements.add('owner');
    entitlements.add('supporting_member');
    entitlements.add('trusted_circle');
  }
  if (!entitlements.size) entitlements.add('reader');
  return Array.from(entitlements);
}

function dispatchAuth(event, body) {
  const payload = verifyToken(extractBearer(event, body));
  return payload || null;
}

function normalizeDispatchText(value, max = 1400) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max);
}

function isMeaningfulDispatchPrompt(value) {
  const text = normalizeDispatchText(value, 1200);
  if (text.length >= 8) return true;
  return /[a-z0-9]{2,}/i.test(text);
}

function dispatchConversationLines(messages = []) {
  if (!Array.isArray(messages)) return [];
  return messages
    .slice(-10)
    .map((message) => {
      const role = message?.role === 'user' ? 'Reader' : 'Thingy';
      const text = normalizeDispatchText(message?.text, 500);
      return text ? `${role}: ${text}` : '';
    })
    .filter(Boolean);
}

function terseDispatchSeed(value) {
  const text = normalizeDispatchText(value, 1200);
  if (/[?!.]/.test(text)) return false;
  return text.length > 0 && text.length <= 28 && text.split(/\s+/).filter(Boolean).length <= 3;
}

function readyMessageClaimsStarted(value) {
  return /\b(?:generating now|generate now|drafting now|sending now|emailing now)\b/i.test(String(value || ''));
}

function bedrockMessageText(message) {
  return (message?.content || []).map((part) => part.text || '').filter(Boolean).join('\n').trim();
}

function dispatchProfile(payload) {
  const entitlements = entitlementsForSessionPayload(payload);
  const owner = entitlements.includes('owner') || isOwnerSubscriberHash(payload?.sub);
  return {
    subscriberHash: String(payload?.sub || ''),
    entitlements,
    supportingMember: entitlements.includes('supporting_member'),
    owner
  };
}

async function clarifyDispatch({ prompt, priorQuestion = '', priorAnswer = '', messages = [] }) {
  const model = fastModel();
  const transcript = dispatchConversationLines(messages);
  const response = await bedrock.send(new ConverseCommand({
    modelId: model,
    system: [{
      text: [
        'You are Thingy, Jamie Thingelstad\'s archive sidekick.',
        'A reader is shaping a one-off Thingy Dispatch from Jamie\'s published archive.',
        'This is a conversational drafting surface, not a form validator.',
        'Terse archive concepts like "RSS", "AI", "POSSE", or "IndieWeb" are valid Dispatch seeds.',
        'For a terse or broad first seed, ask one concrete clarification that offers useful archive angles.',
        'When the reader answers a prior clarification, fold that answer into the confirmed direction instead of asking the same thing again.',
        'When the reader adjusts a ready direction, revise the direction and briefly acknowledge the change.',
        'Ask at most one useful clarification question before expensive generation.',
        'If the request is already specific enough, do not ask a question.',
        'Return only compact JSON: {"needs_clarification":true|false,"question":"...","direction":"confirmed generation direction","message":"Thingy response to show the reader"}'
      ].join('\n')
    }],
    messages: [{
      role: 'user',
      content: [{
        text: [
          `Reader prompt: ${prompt}`,
          priorQuestion ? `Prior clarification question: ${priorQuestion}` : '',
          priorAnswer ? `Reader answer: ${priorAnswer}` : '',
          transcript.length ? `Recent Dispatch conversation:\n${transcript.join('\n')}` : ''
        ].filter(Boolean).join('\n')
      }]
    }],
    inferenceConfig: {
      maxTokens: 420,
      temperature: 0.2
    }
  }));
  const text = bedrockMessageText(response.output?.message || {});
  const raw = text.match(/\{[\s\S]*\}/)?.[0] || text;
  let parsed = {};
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = {};
  }
  const question = normalizeDispatchText(parsed.question, 260);
  const direction = normalizeDispatchText(parsed.direction || prompt, 1000);
  const alreadyAnswered = Boolean(priorQuestion && priorAnswer);
  const shouldClarifyTerseSeed = terseDispatchSeed(prompt) && !priorQuestion && !priorAnswer;
  const needsClarification = Boolean((parsed.needs_clarification || shouldClarifyTerseSeed) && !alreadyAnswered);
  const fallbackQuestion = question || `Good seed. What angle should this Dispatch take on ${normalizeDispatchText(prompt, 80)}?`;
  let message = normalizeDispatchText(parsed.message, 700) || (
    needsClarification
      ? fallbackQuestion
      : `I have enough to shape this Dispatch around: ${direction || prompt}`
  );
  if (!needsClarification && (message.includes('?') || readyMessageClaimsStarted(message))) {
    message = `I have enough to shape this Dispatch around: ${direction || prompt}`;
  }
  return {
    needs_clarification: needsClarification,
    question: needsClarification ? fallbackQuestion : '',
    direction: direction || prompt,
    message
  };
}

export async function handleDispatch(event, body, start = performance.now()) {
  const payload = dispatchAuth(event, body);
  const profile = payload ? dispatchProfile(payload) : null;
  if (!profile?.subscriberHash) {
    return jsonResponse(401, { error: 'Please sign in to use Dispatch.' }, event);
  }
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Dispatch is unavailable right now.' }, event);

  const action = String(body.action || 'list').trim().toLowerCase();
  try {
    if (action === 'clarify') {
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      if (!isMeaningfulDispatchPrompt(prompt)) return jsonResponse(400, { error: 'Dispatch needs a topic or question.' }, event);
      const clarification = await clarifyDispatch({
        prompt,
        priorQuestion: body.clarification_question,
        priorAnswer: body.clarification_answer,
        messages: body.messages
      });
      logEvent('info', 'dispatch_clarified', {
        subscriber_hash: profile.subscriberHash,
        needs_clarification: clarification.needs_clarification,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        ...clarification,
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'save_draft') {
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      const direction = normalizeDispatchText(body.direction || prompt, 1600);
      const title = normalizeDispatchText(body.title || body.topic || prompt || 'Dispatch', 120);
      const dispatch = await upsertDispatchDraft({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id,
        status: body.status || body.stage || 'draft',
        topic: body.topic || prompt || title,
        prompt,
        direction,
        clarificationQuestion: body.clarification_question,
        clarificationAnswer: body.clarification_answer,
        title,
        messages: Array.isArray(body.messages) ? body.messages : []
      });
      logEvent('info', 'dispatch_draft_saved', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        status: dispatch.status,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        dispatch: dispatchForClient(dispatch),
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'list') {
      const availability = await dispatchAvailability({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        owner: profile.owner
      });
      const dispatches = await listUserDispatches({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        limit: body.limit || 12
      });
      return jsonResponse(200, {
        dispatches: dispatches.map(dispatchForClient),
        availability,
        entitlements: profile.entitlements,
        supporting_member: profile.supportingMember,
        owner: profile.owner
      }, event);
    }

    if (action === 'status') {
      let dispatch = await getUserDispatch({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id
      });
      if (!dispatch) return jsonResponse(404, { error: 'Dispatch not found.' }, event);
      const recovered = await recoverStaleDispatches({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        rows: [dispatch]
      });
      if (recovered) {
        dispatch = await getUserDispatch({
          dynamodb,
          tableName,
          subscriberHash: profile.subscriberHash,
          dispatchId: body.dispatch_id || body.id
        }) || dispatch;
      }
      return jsonResponse(200, {
        dispatch: dispatchForClient(dispatch)
      }, event);
    }

    if (action === 'delete') {
      const dispatch = await deleteUserDispatch({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        dispatchId: body.dispatch_id || body.id
      });
      if (!dispatch) return jsonResponse(404, { error: 'Dispatch not found.' }, event);
      logEvent('info', 'dispatch_deleted', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        status: dispatch.status,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(200, {
        status: 'deleted',
        dispatch_id: dispatch.id
      }, event);
    }

    if (action === 'create') {
      if (!profile.supportingMember && !profile.owner) {
        return jsonResponse(403, {
          error: 'Dispatch is available to Weekly Thing Supporting Members.',
          status: 'supporting_member_required',
          message: 'You can shape the Dispatch here. Sending it requires a Supporting Membership.'
        }, event);
      }
      const prompt = normalizeDispatchText(body.prompt || body.topic, 1200);
      const direction = normalizeDispatchText(body.direction || prompt, 1600);
      const toEmail = normalizeEmail(body.email || body.to_email);
      const templateTest = Boolean(body.template_test || body.templateTest || body.test_mode === 'template');
      if (templateTest && !profile.owner) {
        return jsonResponse(403, { error: 'Dispatch template tests are owner-only.' }, event);
      }
      if (!prompt || !direction) return jsonResponse(400, { error: 'Dispatch needs a confirmed direction.' }, event);
      if (!EMAIL_RE.test(toEmail) || emailHash(toEmail) !== profile.subscriberHash) {
        return jsonResponse(403, { error: 'Dispatch can only be sent to your signed-in email address.' }, event);
      }
      const availability = await dispatchAvailability({
        dynamodb,
        tableName,
        subscriberHash: profile.subscriberHash,
        owner: profile.owner
      });
      if (!availability.allowed) {
        return jsonResponse(429, { error: availability.message || 'Dispatch is rate limited.', availability }, event);
      }
      const existingDispatchId = body.dispatch_id || body.id;
      const dispatch = existingDispatchId
        ? await queueDraftDispatch({
          dynamodb,
          tableName,
          subscriberHash: profile.subscriberHash,
          dispatchId: existingDispatchId,
          emailHash: profile.subscriberHash,
          toEmail,
          topic: body.topic || prompt,
          prompt,
          direction,
          clarificationQuestion: body.clarification_question,
          clarificationAnswer: body.clarification_answer,
          templateTest
        })
        : await createQueuedDispatch({
          dynamodb,
          tableName,
          subscriberHash: profile.subscriberHash,
          emailHash: profile.subscriberHash,
          toEmail,
          topic: body.topic || prompt,
          prompt,
          direction,
          clarificationQuestion: body.clarification_question,
          clarificationAnswer: body.clarification_answer,
          templateTest
        });
      logEvent('info', 'dispatch_queued', {
        subscriber_hash: profile.subscriberHash,
        dispatch_id: dispatch.id,
        template_test: templateTest,
        owner: profile.owner,
        duration_ms: Math.round(performance.now() - start)
      });
      return jsonResponse(202, {
        dispatch: dispatchForClient(dispatch)
      }, event);
    }
  } catch (error) {
    logEvent('error', 'dispatch_action_failed', {
      subscriber_hash: profile.subscriberHash,
      action,
      ...errorFields(error)
    });
    return jsonResponse(502, { error: 'Dispatch is unavailable right now.' }, event);
  }

  return jsonResponse(400, { error: 'Unsupported Dispatch action.' }, event);
}
