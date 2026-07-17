import type {
  ContentBlock,
  ConverseStreamResponse,
  ConversationRole,
  Message,
  TokenUsage
} from '@aws-sdk/client-bedrock-runtime';

type JsonObject = Record<string, unknown>;

interface StreamToolUse {
  toolUseId: string;
  name: string;
  input: string;
}

interface StreamBlock {
  text?: string;
  toolUse?: StreamToolUse;
}

interface ReadConverseStreamOptions {
  onTextDelta?: (text: string) => void;
}

export function parseToolUseInput(value: unknown): JsonObject {
  const text = String(value || '').trim();
  if (!text) return {};
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as JsonObject) : {};
  } catch {
    return {};
  }
}

export async function readConverseStream(
  response: ConverseStreamResponse,
  { onTextDelta }: ReadConverseStreamOptions = {}
) {
  const blocks = new Map<number, StreamBlock>();
  const message: Message = {
    role: 'assistant',
    content: []
  };
  let text = '';
  let stopReason = '';
  let usage: TokenUsage | undefined;
  let trace = {};

  const blockFor = (index: number): StreamBlock => {
    if (!blocks.has(index)) blocks.set(index, { text: '' });
    return blocks.get(index)!;
  };

  for await (const event of response.stream || []) {
    if (event.messageStart?.role) {
      message.role = event.messageStart.role as ConversationRole;
      continue;
    }

    if (event.contentBlockStart) {
      const index = event.contentBlockStart.contentBlockIndex ?? blocks.size;
      const toolUse = event.contentBlockStart.start?.toolUse;
      blocks.set(
        index,
        toolUse
          ? { toolUse: { toolUseId: toolUse.toolUseId ?? '', name: toolUse.name ?? '', input: '' } }
          : { text: '' }
      );
      continue;
    }

    if (event.contentBlockDelta) {
      const index = event.contentBlockDelta.contentBlockIndex ?? blocks.size;
      const delta = (event.contentBlockDelta.delta || {}) as {
        text?: string;
        toolUse?: { input?: string };
      };
      const block = blockFor(index);

      if (delta.text) {
        block.text = `${block.text || ''}${delta.text}`;
        text += delta.text;
        if (onTextDelta) onTextDelta(delta.text);
      }

      if (delta.toolUse?.input) {
        if (!block.toolUse) block.toolUse = { toolUseId: '', name: '', input: '' };
        block.toolUse.input = `${block.toolUse.input || ''}${delta.toolUse.input}`;
      }
      continue;
    }

    if (event.messageStop?.stopReason) {
      stopReason = event.messageStop.stopReason;
      continue;
    }

    if (event.metadata?.usage) usage = event.metadata.usage;
    if (event.metadata?.trace) trace = event.metadata.trace;
  }

  message.content = Array.from(blocks.entries())
    .sort(([left], [right]) => left - right)
    .map(([, block]) => {
      if (block.toolUse) {
        return {
          toolUse: {
            ...block.toolUse,
            input: parseToolUseInput(block.toolUse.input)
          }
        };
      }
      return { text: block.text || '' };
    })
    .filter((block) => block.toolUse || block.text) as ContentBlock[];

  return { message, text: text.trim(), stopReason, usage, trace };
}
