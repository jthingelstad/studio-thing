const EVAL_QUESTION_PROMPT_CHARS = 1800;
const EVAL_ANSWER_PROMPT_CHARS = 12000;

interface EvalCitation {
  issue_number?: number | string;
  subject?: string;
  url?: string;
  source_kind?: string;
}

interface EvalTurn {
  question?: unknown;
  answer?: unknown;
  citations?: EvalCitation[];
  preflight?: {
    category?: string;
    action?: string;
  };
  tool_names?: string[];
  feedback_reaction?: string;
  feedback_comment?: string;
  stop_reason?: string;
  duration_ms?: number;
}

function transcriptText(value: unknown, max = 800) {
  const text = String(value || '')
    .trim()
    .replace(/\s+/g, ' ');
  if (text.length <= max) return text;
  const omitted = text.length - max;
  return `${text.slice(0, max).trimEnd()}\n\n[Evaluator transcript note: ${omitted} characters omitted from this field; do not treat this as reader-visible truncation.]`;
}

function citationLabel(citation: EvalCitation = {}) {
  if (citation.issue_number) return `WT${citation.issue_number}`;
  return citation.subject || citation.url || citation.source_kind || '';
}

export function turnForPrompt(turn: EvalTurn, index: number) {
  const citations = (turn.citations || []).map(citationLabel).filter(Boolean).join(', ');
  const preflight =
    turn.preflight?.category || turn.preflight?.action
      ? `${turn.preflight.category || ''}/${turn.preflight.action || ''}`
      : '';
  const tools = (turn.tool_names || []).join(', ');
  const feedback = turn.feedback_reaction
    ? `${turn.feedback_reaction}${turn.feedback_comment ? ` — ${turn.feedback_comment}` : ''}`
    : '';
  const runtime = [
    turn.stop_reason ? `stop_reason=${turn.stop_reason}` : '',
    turn.duration_ms ? `duration_ms=${turn.duration_ms}` : ''
  ]
    .filter(Boolean)
    .join(', ');
  return [
    `### Turn ${index + 1}`,
    `Reader: ${transcriptText(turn.question, EVAL_QUESTION_PROMPT_CHARS)}`,
    '',
    `Thingy: ${transcriptText(turn.answer, EVAL_ANSWER_PROMPT_CHARS)}`,
    runtime ? `Runtime: ${runtime}` : '',
    citations ? `Citations: ${citations}` : '',
    preflight ? `Preflight: ${preflight}` : '',
    tools ? `Tools: ${tools}` : '',
    feedback ? `Reader feedback: ${feedback}` : ''
  ]
    .filter(Boolean)
    .join('\n');
}
