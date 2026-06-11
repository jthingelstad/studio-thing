import { ConverseCommand } from '@aws-sdk/client-bedrock-runtime';
import { bedrock, dynamodb, fastModel } from '../shared/aws-clients.mjs';
import { jsonResponse } from '../shared/http.mjs';
import { emailHash, extractBearer, normalizeEmail, verifyToken } from '../shared/session.mjs';
import { sessionAllowedForThingyProfile } from '../shared/profile-deletion.mjs';
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
import { analyzeDispatchSourceFit, loadDispatchCorpus } from '../shared/dispatch-generator.mjs';

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

async function dispatchAuth(event, body) {
  const payload = verifyToken(extractBearer(event, body));
  if (!payload || !(await sessionAllowedForThingyProfile(payload))) return null;
  return payload;
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

function sourceKindSummary(sourceKinds = {}) {
  return Object.entries(sourceKinds)
    .filter(([, count]) => Number(count) > 0)
    .map(([kind, count]) => `${count} ${kind.replace(/_/g, ' ')}`)
    .join(', ');
}

function plannerSource(source = {}, index = 0, why = '') {
  return {
    id: String(source.id || `S${index + 1}`),
    label: normalizeDispatchText(source.label, 80),
    title: normalizeDispatchText(source.title, 180),
    url: normalizeDispatchText(source.url, 500),
    source_kind: normalizeDispatchText(source.source_kind, 40),
    publish_date: normalizeDispatchText(source.publish_date, 40),
    why: normalizeDispatchText(why || source.why, 220)
  };
}

function plannerSources(sources = [], reasons = []) {
  return sources
    .slice(0, 10)
    .map((source, index) => plannerSource(source, index, reasons[index]))
    .filter((source) => source.title || source.url);
}

function plannerSourcePackets(sources = []) {
  return sources.slice(0, 10).map((source) => [
    `[${source.id}] ${source.label} · ${source.title}`,
    source.publish_date ? `Date: ${source.publish_date}` : '',
    source.url ? `URL: ${source.url}` : '',
    `Excerpt: ${normalizeDispatchText(source.excerpt, 520)}`
  ].filter(Boolean).join('\n')).join('\n\n');
}

function textArray(value, max = 5, itemMax = 180) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => normalizeDispatchText(item, itemMax)).filter(Boolean).slice(0, max);
}

function validCoverageStatus(value, fallback = 'focused') {
  const status = String(value || '').trim().toLowerCase();
  return ['thin', 'focused', 'broad', 'ambiguous'].includes(status) ? status : fallback;
}

function coverageQuestion(status, prompt, fit, adjacentTopics = []) {
  const topic = normalizeDispatchText(prompt, 80) || 'that';
  if (status === 'thin') {
    const adjacent = adjacentTopics.length
      ? ` I found stronger adjacent material around ${adjacentTopics.slice(0, 3).join(', ')}.`
      : '';
    return `I am not finding enough direct archive support for ${topic}.${adjacent} Want me to redirect the Dispatch toward one of those adjacent threads?`;
  }
  if (status === 'broad') {
    return `There is a lot in Jamie's archive around ${topic}. Which angle should I narrow this toward so the Dispatch does not drown in source material?`;
  }
  if (fit.selected_sources.length < 4) {
    return `I only found ${fit.selected_sources.length} usable archive matches. What adjacent angle should I use?`;
  }
  return `What angle should this Dispatch take on ${topic}?`;
}

function defaultPlannerMessage({ needsClarification, status, direction }) {
  if (needsClarification && status === 'thin') {
    return 'I checked the archive first, and this looks under-supported as stated. I can still help redirect it toward something Jamie has written enough about.';
  }
  if (needsClarification && status === 'broad') {
    return 'I checked the archive first, and this topic is broad enough that I should narrow it before Dispatch generation.';
  }
  if (needsClarification) return 'I checked the archive and need one steering choice before I generate a useful Dispatch.';
  return `I checked the archive and have enough to shape this Dispatch around: ${direction}`;
}

function normalizeDispatchBrief(parsedBrief = {}, { prompt, direction, coverageStatus, sources }) {
  const sourceReasons = Array.isArray(parsedBrief.selected_sources)
    ? parsedBrief.selected_sources.map((source) => source?.why || '')
    : [];
  return {
    user_goal: normalizeDispatchText(parsedBrief.user_goal || prompt, 500),
    working_angle: normalizeDispatchText(parsedBrief.working_angle || direction || prompt, 700),
    coverage_status: coverageStatus,
    selected_sources: plannerSources(sources, sourceReasons),
    excluded_scope: textArray(parsedBrief.excluded_scope, 8, 180),
    generation_instructions: normalizeDispatchText(parsedBrief.generation_instructions || direction || prompt, 1200),
    preheader_basis: normalizeDispatchText(parsedBrief.preheader_basis || direction || prompt, 240)
  };
}

function toolActivityForPlan({ fit, coverageStatus, needsClarification, brief }) {
  const kindSummary = sourceKindSummary(fit.source_kinds || {});
  return [
    {
      id: 'archive-fit',
      label: 'Checked archive coverage',
      status: 'complete',
      summary: `${fit.selected_sources.length} source packets selected from ${fit.candidate_count} candidate matches.`
    },
    {
      id: 'source-balance',
      label: 'Balanced source packet',
      status: 'complete',
      summary: kindSummary ? `Coverage includes ${kindSummary}.` : 'Coverage is concentrated in the strongest available sources.'
    },
    {
      id: 'dispatch-brief',
      label: 'Prepared Dispatch brief',
      status: needsClarification ? 'waiting' : 'complete',
      summary: needsClarification
        ? `Archive fit is ${coverageStatus}; waiting for one steering choice.`
        : `Archive fit is ${coverageStatus}; brief is ready with ${brief.selected_sources.length} planned sources.`
    }
  ];
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
  const fitQuery = [prompt, priorQuestion, priorAnswer, transcript.join(' ')].filter(Boolean).join(' ');
  const chunks = await loadDispatchCorpus();
  const fit = analyzeDispatchSourceFit(chunks, fitQuery);
  const sourcePackets = plannerSourcePackets(fit.selected_sources);
  const response = await bedrock.send(new ConverseCommand({
    modelId: model,
    system: [{
      text: [
        'You are Thingy, Jamie Thingelstad\'s archive sidekick.',
        'A reader is shaping a one-off Thingy Dispatch from Jamie\'s published archive.',
        'This is an agentic planning conversation, not a form validator.',
        'You already checked source-fit against Jamie\'s archive. Use that evidence before deciding whether to ask a question.',
        'Terse archive concepts like "RSS", "AI", "POSSE", or "IndieWeb" are valid Dispatch seeds.',
        'If archive coverage is thin, disclose that clearly and suggest adjacent source-supported directions.',
        'If archive coverage is broad, ask one narrowing question so generation is not flooded with sources.',
        'If archive coverage is focused, create a compact Dispatch brief and let the reader generate.',
        'When the reader answers a prior clarification, fold that answer into the confirmed direction instead of asking the same thing again.',
        'When the reader adjusts a ready direction, revise the direction and briefly acknowledge the change.',
        'Ask one useful clarification question at a time.',
        'If a prior answer still leaves archive coverage thin or broad, ask a different steering question rather than forcing generation.',
        'If the request is already specific enough, do not ask a question.',
        'Never claim generation, drafting, sending, or emailing has started.',
        'Return only compact JSON with this shape:',
        '{"needs_clarification":true|false,"coverage_status":"thin|focused|broad|ambiguous","question":"...","direction":"confirmed generation direction","message":"Thingy response to show the reader","adjacent_topics":["..."],"suggested_narrowing":["..."],"brief":{"user_goal":"...","working_angle":"...","excluded_scope":["..."],"generation_instructions":"...","preheader_basis":"...","selected_sources":[{"id":"S1","why":"why this source belongs"}]}}'
      ].join('\n')
    }],
    messages: [{
      role: 'user',
      content: [{
        text: [
          `Reader prompt: ${prompt}`,
          priorQuestion ? `Prior clarification question: ${priorQuestion}` : '',
          priorAnswer ? `Reader answer: ${priorAnswer}` : '',
          transcript.length ? `Recent Dispatch conversation:\n${transcript.join('\n')}` : '',
          `Archive coverage status: ${fit.coverage_status}`,
          `Archive candidate matches: ${fit.candidate_count}`,
          `Selected source packet count: ${fit.selected_sources.length}`,
          fit.source_kinds ? `Source balance: ${sourceKindSummary(fit.source_kinds) || 'none'}` : '',
          sourcePackets ? `Selected source packets:\n${sourcePackets}` : 'Selected source packets: none'
        ].filter(Boolean).join('\n')
      }]
    }],
    inferenceConfig: {
      maxTokens: 1000,
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
  const parsedStatus = validCoverageStatus(parsed.coverage_status, fit.coverage_status);
  const coverageStatus = validCoverageStatus(fit.coverage_status, parsedStatus);
  const adjacentTopics = textArray(parsed.adjacent_topics, 5, 120);
  const suggestedNarrowing = textArray(parsed.suggested_narrowing, 5, 160);
  const shouldClarifyCoverage = coverageStatus === 'thin' || coverageStatus === 'broad';
  const needsClarification = Boolean(shouldClarifyCoverage || ((parsed.needs_clarification || shouldClarifyTerseSeed) && !alreadyAnswered));
  const fallbackQuestion = question || coverageQuestion(coverageStatus, prompt, fit, adjacentTopics);
  let message = normalizeDispatchText(parsed.message, 700) || (
    defaultPlannerMessage({ needsClarification, status: coverageStatus, direction: direction || prompt })
  );
  if (!needsClarification && (message.includes('?') || readyMessageClaimsStarted(message))) {
    message = defaultPlannerMessage({ needsClarification, status: coverageStatus, direction: direction || prompt });
  }
  const brief = normalizeDispatchBrief(parsed.brief || {}, {
    prompt,
    direction: direction || prompt,
    coverageStatus,
    sources: fit.selected_sources
  });
  return {
    needs_clarification: needsClarification,
    question: needsClarification ? fallbackQuestion : '',
    direction: direction || prompt,
    message,
    coverage_status: coverageStatus,
    selected_sources: brief.selected_sources,
    adjacent_topics: adjacentTopics,
    suggested_narrowing: suggestedNarrowing,
    brief,
    tool_activity: toolActivityForPlan({ fit, coverageStatus, needsClarification, brief })
  };
}

export async function handleDispatch(event, body, start = performance.now()) {
  const payload = await dispatchAuth(event, body);
  const profile = payload ? dispatchProfile(payload) : null;
  if (!profile?.subscriberHash) {
    return jsonResponse(401, { error: 'Please sign in to use Dispatch.' }, event);
  }
  const tableName = process.env.TABLE_NAME;
  if (!tableName) return jsonResponse(500, { error: 'Dispatch is unavailable right now.' }, event);

  const action = String(body.action || 'list').trim().toLowerCase();
  try {
    if (action === 'clarify' || action === 'plan') {
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
        coverage_status: clarification.coverage_status,
        source_count: clarification.selected_sources?.length || 0,
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
        brief: body.brief,
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
          brief: body.brief,
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
          brief: body.brief,
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
