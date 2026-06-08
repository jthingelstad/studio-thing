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

