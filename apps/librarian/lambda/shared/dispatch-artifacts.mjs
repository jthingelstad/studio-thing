import { GetObjectCommand, PutObjectCommand } from '@aws-sdk/client-s3';
import { s3 } from './aws-clients.mjs';

const DEFAULT_PREFIX = 'artifacts/dispatches';

function dispatchArtifactBucket() {
  const bucket = String(process.env.DISPATCH_ARTIFACT_BUCKET || process.env.CORPUS_BUCKET || '').trim();
  if (!bucket) throw new Error('DISPATCH_ARTIFACT_BUCKET or CORPUS_BUCKET is required for Dispatch artifacts.');
  return bucket;
}

function dispatchArtifactPrefix() {
  return String(process.env.DISPATCH_ARTIFACT_PREFIX || DEFAULT_PREFIX).replace(/^\/+|\/+$/g, '') || DEFAULT_PREFIX;
}

function safeKeyPart(value) {
  return String(value || 'unknown').replace(/[^A-Za-z0-9_.:-]/g, '_').slice(0, 120) || 'unknown';
}

export function dispatchContentArtifactKey({ subscriberHash, dispatchId }) {
  return [
    dispatchArtifactPrefix(),
    safeKeyPart(subscriberHash),
    `${safeKeyPart(dispatchId)}.json`
  ].join('/');
}

export async function putDispatchContentArtifact({ subscriberHash, dispatchId, result }) {
  const bucket = dispatchArtifactBucket();
  const key = dispatchContentArtifactKey({ subscriberHash, dispatchId });
  const payload = {
    version: 1,
    dispatch_id: String(dispatchId || ''),
    created_at: new Date().toISOString(),
    subject: String(result?.subject || ''),
    title: String(result?.title || ''),
    preview: String(result?.preview || ''),
    text: String(result?.text || ''),
    html: String(result?.html || '')
  };
  await s3.send(new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: JSON.stringify(payload),
    ContentType: 'application/json; charset=utf-8'
  }));
  return { bucket, key };
}

export async function getDispatchContentArtifact({ bucket, key }) {
  if (!bucket || !key) return {};
  const response = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
  const raw = await response.Body.transformToString();
  const parsed = JSON.parse(raw);
  return {
    text: String(parsed.text || ''),
    html: String(parsed.html || '')
  };
}
