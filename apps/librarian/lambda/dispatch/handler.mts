import { processDispatchStream } from '../shared/dispatch-worker.mjs';
import { logEvent } from '../shared/logging.mjs';
import type { DynamoDBStreamEvent } from 'aws-lambda';

interface DispatchContext {
  awsRequestId?: string;
}

export async function handler(event: DynamoDBStreamEvent = { Records: [] }, context: DispatchContext = {}) {
  const start = performance.now();
  const tableName = process.env.TABLE_NAME;
  if (!tableName) throw new Error('TABLE_NAME is required');
  const result = await processDispatchStream({ event, tableName });
  const payload = {
    ok: result.failed === 0,
    ...result,
    stream_record_count: Array.isArray(event.Records) ? event.Records.length : 0,
    request_id: context.awsRequestId || '',
    duration_ms: Math.round(performance.now() - start)
  };
  logEvent('info', 'dispatch_worker_completed', payload, 'weekly-thing-librarian-dispatch');
  return payload;
}
