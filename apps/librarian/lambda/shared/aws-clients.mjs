import { BedrockRuntimeClient } from '@aws-sdk/client-bedrock-runtime';
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { S3Client } from '@aws-sdk/client-s3';

export const bedrock = new BedrockRuntimeClient({});
export const dynamodb = new DynamoDBClient({});
export const s3 = new S3Client({});

export function agentModel() {
  return process.env.BEDROCK_AGENT_MODEL || 'us.anthropic.claude-sonnet-4-6';
}

export function embeddingModel() {
  return process.env.BEDROCK_EMBEDDING_MODEL || 'cohere.embed-english-v3';
}

export function rerankModel() {
  return process.env.BEDROCK_RERANK_MODEL || 'cohere.rerank-v3-5:0';
}
