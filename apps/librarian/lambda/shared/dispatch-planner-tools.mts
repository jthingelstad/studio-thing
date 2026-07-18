// Tools for the Dispatch planner conversation mode on the chat runtime.
//
// Dispatch planning is a goal-directed chat conversation: the model talks
// the reader toward a locked Dispatch brief. These tools keep that
// conversation honest and visible:
//
//   - check_dispatch_fit  — deterministic archive-coverage evidence for a
//     working topic, from the same fit analyzer Dispatch generation uses.
//   - update_dispatch_brief — the model publishes the current brief; the
//     runtime mirrors it to the client over SSE so the reader watches the
//     package form and ultimately locks it.
//
// The brief never queues generation from here. Locking and queueing stay on
// the auth Lambda's /dispatch route, triggered by the reader.

import { analyzeDispatchSourceFit, loadDispatchCorpus } from './dispatch-generator.mjs';

const BRIEF_STATUSES = new Set(['draft', 'ready']);
const COVERAGE_STATUSES = new Set(['thin', 'focused', 'broad', 'ambiguous']);
const MAX_READY_SOURCES = 6;

type PlannerInput = Record<string, unknown>;

interface PlannerSource extends PlannerInput {
  id?: unknown;
  label?: unknown;
  title?: unknown;
  url?: unknown;
  source_kind?: unknown;
  publish_date?: unknown;
  why?: unknown;
  excerpt?: unknown;
  text?: unknown;
}

function asPlannerInput(value: unknown): PlannerInput {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as PlannerInput) : {};
}

function cleanText(value: unknown, max = 500) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, max);
}

function textArray(value: unknown, max = 8, itemMax = 180) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => cleanText(item, itemMax))
    .filter(Boolean)
    .slice(0, max);
}

function normalizeBriefSource(value: unknown, index = 0) {
  const source = asPlannerInput(value) as PlannerSource;
  return {
    id: cleanText(source.id, 24) || `S${index + 1}`,
    label: cleanText(source.label, 80),
    title: cleanText(source.title, 180),
    url: cleanText(source.url, 500),
    source_kind: cleanText(source.source_kind, 40),
    publish_date: cleanText(source.publish_date, 40),
    why: cleanText(source.why, 220)
  };
}

export function normalizePlannerBrief(input: PlannerInput = {}) {
  const sources = Array.isArray(input.selected_sources) ? input.selected_sources : [];
  const coverage = String(input.coverage_status || '')
    .trim()
    .toLowerCase();
  const status = String(input.status || '')
    .trim()
    .toLowerCase();
  return {
    user_goal: cleanText(input.user_goal, 500),
    working_angle: cleanText(input.working_angle, 700),
    coverage_status: COVERAGE_STATUSES.has(coverage) ? coverage : 'ambiguous',
    selected_sources: sources
      .slice(0, 10)
      .map(normalizeBriefSource)
      .filter((source) => source.title || source.url),
    excluded_scope: textArray(input.excluded_scope, 8, 180),
    generation_instructions: cleanText(input.generation_instructions, 1200),
    preheader_basis: cleanText(input.preheader_basis, 240),
    status: BRIEF_STATUSES.has(status) ? status : 'draft'
  };
}

function fitPacketForModel(value: unknown, index = 0) {
  const source = asPlannerInput(value) as PlannerSource;
  return {
    id: String(source.id || `S${index + 1}`),
    label: cleanText(source.label, 80),
    title: cleanText(source.title, 180),
    url: cleanText(source.url, 500),
    source_kind: cleanText(source.source_kind, 40),
    publish_date: cleanText(source.publish_date, 40),
    excerpt: cleanText(source.excerpt || source.text, 420)
  };
}

async function toolCheckDispatchFit(input: PlannerInput = {}) {
  const query = cleanText(input.query || input.topic || input.prompt, 1200);
  if (!query) return { error: 'check_dispatch_fit needs a query.' };
  const chunks = await loadDispatchCorpus();
  const fit = analyzeDispatchSourceFit(chunks, query);
  return {
    query,
    coverage_status: fit.coverage_status,
    candidate_count: fit.candidate_count,
    source_kinds: fit.source_kinds || {},
    selected_sources: (fit.selected_sources || []).slice(0, 10).map(fitPacketForModel)
  };
}

async function toolUpdateDispatchBrief(input: PlannerInput = {}) {
  const brief = normalizePlannerBrief(input);
  if (!brief.user_goal && !brief.working_angle) {
    return { error: 'update_dispatch_brief needs at least a user_goal or working_angle.' };
  }
  if (brief.status === 'ready') {
    const curatedBroadFit =
      brief.coverage_status === 'broad' &&
      brief.selected_sources.length > 0 &&
      brief.selected_sources.length <= MAX_READY_SOURCES;
    if (brief.coverage_status !== 'focused' && !curatedBroadFit) {
      return {
        error:
          'A ready brief needs focused coverage or a curated packet of no more than six sources from a broad fit. Keep status "draft" or narrow the angle first.',
        brief
      };
    }
    if (!brief.selected_sources.length) {
      return {
        error: 'A ready brief needs at least one selected source.',
        brief
      };
    }
    // The fit tool describes the size of the raw archive result. Once the
    // reader has confirmed a small, explicit packet, the brief itself is
    // focused even when that raw result was broad.
    if (curatedBroadFit) brief.coverage_status = 'focused';
  }
  return { ok: true, brief, status: brief.status };
}

export const DISPATCH_PLANNER_TOOLS = {
  check_dispatch_fit: toolCheckDispatchFit,
  update_dispatch_brief: toolUpdateDispatchBrief
};

export function dispatchPlannerToolSpecs() {
  return [
    {
      toolSpec: {
        name: 'check_dispatch_fit',
        description:
          "Check how well Jamie's published archive supports a working Dispatch topic. Returns a coverage status (thin, focused, broad, ambiguous), the candidate match count, the source-kind balance, and the strongest source packets. Call this before making any claim about archive coverage, and again whenever the working angle changes.",
        inputSchema: {
          json: {
            type: 'object',
            properties: {
              query: {
                type: 'string',
                description: 'The working Dispatch topic or angle to check against the archive.'
              }
            },
            required: ['query']
          }
        }
      }
    },
    {
      toolSpec: {
        name: 'update_dispatch_brief',
        description:
          'Publish the current Dispatch brief so the reader can see the package forming. Call this whenever the plan changes meaningfully, and always once the plan is ready. Set status "ready" only when coverage is focused, sources are selected, and the direction is confirmed with the reader.',
        inputSchema: {
          json: {
            type: 'object',
            properties: {
              user_goal: {
                type: 'string',
                description: 'What the reader wants this Dispatch to do, in one or two sentences.'
              },
              working_angle: { type: 'string', description: 'The confirmed angle the Dispatch will take.' },
              coverage_status: {
                type: 'string',
                enum: ['thin', 'focused', 'broad', 'ambiguous'],
                description: 'Archive coverage for this angle, from check_dispatch_fit evidence.'
              },
              selected_sources: {
                type: 'array',
                description: 'Sources the Dispatch should draw from, taken from check_dispatch_fit packets.',
                items: {
                  type: 'object',
                  properties: {
                    id: { type: 'string' },
                    label: { type: 'string' },
                    title: { type: 'string' },
                    url: { type: 'string' },
                    source_kind: { type: 'string' },
                    publish_date: { type: 'string' },
                    why: { type: 'string', description: 'Why this source belongs in the Dispatch.' }
                  }
                }
              },
              excluded_scope: {
                type: 'array',
                items: { type: 'string' },
                description: 'Angles or material deliberately left out of this Dispatch.'
              },
              generation_instructions: {
                type: 'string',
                description: 'Instructions for the Dispatch writer: angle, emphasis, tone, and how to use the sources.'
              },
              preheader_basis: { type: 'string', description: 'One line the email preheader can be built from.' },
              status: {
                type: 'string',
                enum: ['draft', 'ready'],
                description: '"draft" while the plan is still moving; "ready" when the reader can lock and generate.'
              }
            },
            required: ['user_goal', 'working_angle', 'coverage_status', 'generation_instructions']
          }
        }
      }
    }
  ];
}
