import { ConditionalCheckFailedException } from '@aws-sdk/client-dynamodb';
import { dynamodb } from './aws-clients.mjs';
import { errorFields, logEvent } from './logging.mjs';
import { generateDispatch } from './dispatch-generator.mjs';
import {
  claimQueuedDispatch,
  dispatchFromItem,
  markDispatchFailed,
  markDispatchSent
} from './dispatch-store.mjs';
import { fromDynamoAttr } from './user-conversations.mjs';

function compactLine(value, max = 240) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length <= max ? text : `${text.slice(0, max - 1).trim()}…`;
}

function sourceLabels(sources = [], limit = 10) {
  const labels = [];
  for (const source of sources || []) {
    const label = [source.label, source.title].filter(Boolean).join(' · ');
    if (label && !labels.includes(label)) labels.push(label);
    if (labels.length >= limit) break;
  }
  return labels;
}

export function discordDispatchCard({ dispatch = {}, result = {} }) {
  const sources = sourceLabels(result.sources || []);
  const subject = compactLine(result.subject || dispatch.subject || result.title || dispatch.title || 'Thingy Dispatch', 180);
  const request = compactLine(dispatch.direction || dispatch.prompt || dispatch.topic || '', 360);
  const lines = [
    `**Thingy Dispatch · \`${dispatch.id || dispatch.dispatch_id || 'unknown'}\`** · sent${dispatch.template_test ? ' · template test' : ''}`,
    `**Subject:** ${subject}`,
    dispatch.to_email ? `**Reader:** ${compactLine(dispatch.to_email, 180)}` : '',
    request ? `**Request:** ${request}` : '',
    result.preview ? `**Preview:** ${compactLine(result.preview, 260)}` : '',
    result.model ? `**Model:** ${result.model}` : '',
    `**Tokens:** in ${result.usage?.inputTokens || result.usage?.input_tokens || 0} / out ${result.usage?.outputTokens || result.usage?.output_tokens || 0}`,
    `**Sources:** ${sources.length ? sources.join(', ') : '—'}`,
    'Use the Thingy Dispatch operator report for full content and source review.'
  ].filter(Boolean);
  const content = lines.join('\n');
  return content.length <= 1900 ? content : `${content.slice(0, 1890).trim()}…`;
}

async function postDiscordDispatchWebhook({ dispatch, result }) {
  const url = String(process.env.DISCORD_CONVERSATION_WEBHOOK_URL || '').trim();
  if (!url) return { skipped: true };
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      content: discordDispatchCard({ dispatch, result }),
      allowed_mentions: { parse: [] }
    })
  });
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Discord webhook HTTP ${response.status}: ${text.slice(0, 200)}`);
  }
  return { posted: true };
}

function subscriberHashFromUserPk(pk) {
  const text = String(pk || '');
  return text.startsWith('user#') ? text.slice('user#'.length) : '';
}

function dispatchRefsFromStream(event = {}) {
  const refs = [];
  const seen = new Set();
  for (const record of event.Records || []) {
    const image = record.dynamodb?.NewImage || null;
    if (!image) continue;
    const itemType = fromDynamoAttr(image.item_type);
    const status = fromDynamoAttr(image.status);
    if (itemType !== 'dispatch' || status !== 'queued') continue;
    const subscriberHash = subscriberHashFromUserPk(fromDynamoAttr(image.pk));
    const dispatch = dispatchFromItem(image);
    if (!subscriberHash || !dispatch.id || !dispatch.created_at) continue;
    const key = `${subscriberHash}\0${dispatch.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    refs.push({ subscriberHash, dispatch });
  }
  return refs;
}

export async function processDispatchStream({ event = {}, tableName }) {
  const refs = dispatchRefsFromStream(event);
  let generated = 0;
  let skipped = 0;
  let failed = 0;
  for (const ref of refs) {
    let claimed;
    try {
      claimed = await claimQueuedDispatch({
        dynamodb,
        tableName,
        subscriberHash: ref.subscriberHash,
        dispatch: ref.dispatch
      });
    } catch (error) {
      if (error instanceof ConditionalCheckFailedException || error.name === 'ConditionalCheckFailedException') {
        skipped += 1;
        continue;
      }
      failed += 1;
      logEvent('warning', 'dispatch_claim_failed', errorFields(error, {
        subscriber_hash: ref.subscriberHash,
        dispatch_id: ref.dispatch.id
      }));
      continue;
    }

    try {
      const result = await generateDispatch(claimed);
      await markDispatchSent({
        dynamodb,
        tableName,
        subscriberHash: ref.subscriberHash,
        dispatch: claimed,
        result
      });
      try {
        const webhookResult = await postDiscordDispatchWebhook({ dispatch: claimed, result });
        if (webhookResult.posted) {
          logEvent('info', 'dispatch_posted_to_discord', {
            subscriber_hash: ref.subscriberHash,
            dispatch_id: claimed.id
          });
        }
      } catch (webhookError) {
        logEvent('warning', 'dispatch_discord_post_failed', errorFields(webhookError, {
          subscriber_hash: ref.subscriberHash,
          dispatch_id: claimed.id
        }));
      }
      generated += 1;
      logEvent('info', 'dispatch_sent', {
        subscriber_hash: ref.subscriberHash,
        dispatch_id: claimed.id,
        source_count: result.sources?.length || 0,
        output_tokens: result.usage?.outputTokens || 0
      });
    } catch (error) {
      failed += 1;
      await markDispatchFailed({
        dynamodb,
        tableName,
        subscriberHash: ref.subscriberHash,
        dispatch: claimed,
        error
      }).catch((markError) => {
        logEvent('warning', 'dispatch_mark_failed_failed', errorFields(markError, {
          subscriber_hash: ref.subscriberHash,
          dispatch_id: claimed.id
        }));
      });
      logEvent('warning', 'dispatch_generation_failed', errorFields(error, {
        subscriber_hash: ref.subscriberHash,
        dispatch_id: claimed.id
      }));
    }
  }
  return {
    candidates: refs.length,
    generated,
    skipped,
    failed
  };
}
