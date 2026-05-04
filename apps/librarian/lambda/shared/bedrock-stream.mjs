export function parseToolUseInput(value) {
  const text = String(value || '').trim();
  if (!text) return {};
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

export async function readConverseStream(response, { onTextDelta } = {}) {
  const blocks = new Map();
  const message = { role: 'assistant', content: [] };
  let text = '';
  let stopReason = '';
  let usage = {};
  let trace = {};

  const blockFor = (index) => {
    if (!blocks.has(index)) blocks.set(index, { text: '' });
    return blocks.get(index);
  };

  for await (const event of response.stream || []) {
    if (event.messageStart?.role) {
      message.role = event.messageStart.role;
      continue;
    }

    if (event.contentBlockStart) {
      const index = event.contentBlockStart.contentBlockIndex ?? blocks.size;
      const toolUse = event.contentBlockStart.start?.toolUse;
      blocks.set(index, toolUse
        ? { toolUse: { toolUseId: toolUse.toolUseId, name: toolUse.name, input: '' } }
        : { text: '' });
      continue;
    }

    if (event.contentBlockDelta) {
      const index = event.contentBlockDelta.contentBlockIndex ?? blocks.size;
      const delta = event.contentBlockDelta.delta || {};
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
    .filter((block) => block.toolUse || block.text);

  return { message, text: text.trim(), stopReason, usage, trace };
}
