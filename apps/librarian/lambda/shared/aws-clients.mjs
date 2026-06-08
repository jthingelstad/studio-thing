import { BedrockRuntimeClient } from '@aws-sdk/client-bedrock-runtime';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { S3Client } from '@aws-sdk/client-s3';

export const bedrock = new BedrockRuntimeClient({});
export const dynamodb = new DynamoDBClient({});
export const s3 = new S3Client({});

export const DEFAULT_THINGY_MODEL = 'us.anthropic.claude-sonnet-4-6';
export const FAST_THINGY_MODEL = 'us.anthropic.claude-haiku-4-5-20251001-v1:0';
export const ADVANCED_THINGY_MODEL = 'us.anthropic.claude-sonnet-4-6';

export function thingyDefaultModel() {
  return process.env.THINGY_DEFAULT_MODEL || DEFAULT_THINGY_MODEL;
}

export function fastModel() {
  return process.env.THINGY_FAST_MODEL || FAST_THINGY_MODEL;
}

export function advancedModel() {
  return process.env.THINGY_ADVANCED_MODEL || ADVANCED_THINGY_MODEL;
}

export function agentModel() {
  return thingyDefaultModel();
}

export function embeddingModel() {
  return process.env.BEDROCK_EMBEDDING_MODEL || 'cohere.embed-english-v3';
}

export function rerankModel() {
  return process.env.BEDROCK_RERANK_MODEL || 'cohere.rerank-v3-5:0';
}
