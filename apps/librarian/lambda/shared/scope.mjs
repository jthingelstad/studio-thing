/**
 * Source-scope helpers for the Thingy agent.
 *
 * Thingy answers over independent corpora: the Weekly Thing issue archive
 * (`weekly_thing`), Jamie's 20-year thingelstad.com blog (`blog`), and
 * Another Thing podcast transcripts (`podcast`). Scope is enforced by *which
 * corpus the retrieval scans*, not by a post-filter.
 *
 * `both` preserves the original WT+blog behavior. `all` retrieves candidates
 * from every corpus and reranks the union once.
 *
 * Default is `weekly_thing`: it preserves Thingy's historical identity and
 * means the operator `/retrieve` path (workshop_bot) is unaffected when it
 * sends no scope.
 */

export const SCOPES = ['weekly_thing', 'blog', 'podcast', 'both', 'all'];
export const DEFAULT_SCOPE = 'weekly_thing';

/** Coerce arbitrary input into one of SCOPES, defaulting to weekly_thing. */
export function normalizeScope(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (raw === 'weekly_thing' || raw === 'wt' || raw === 'weeklything' || raw === 'issues' || raw === 'archive') {
    return 'weekly_thing';
  }
  if (raw === 'blog' || raw === 'thingelstad' || raw === 'thingelstad_com') return 'blog';
  if (raw === 'podcast' || raw === 'podcasts' || raw === 'another_thing' || raw === 'anotherthing' || raw === 'another') return 'podcast';
  if (raw === 'both') return 'both';
  if (raw === 'all' || raw === 'everything') return 'all';
  return DEFAULT_SCOPE;
}

/** Corpus kinds a scope scans, in retrieval order (WT first for mixed scopes). */
export function scopeKinds(scope) {
  const normalized = normalizeScope(scope);
  if (normalized === 'blog') return ['blog'];
  if (normalized === 'podcast') return ['podcast'];
  if (normalized === 'both') return ['weekly_thing', 'blog'];
  if (normalized === 'all') return ['weekly_thing', 'blog', 'podcast'];
  return ['weekly_thing'];
}

/**
 * One-line, per-turn system instruction telling the agent which corpus it
 * may speak from. Injected as a system block after the cached static
 * prompt, so it varies per request without busting the prompt cache.
 */
export function scopePromptLine(scope) {
  switch (normalizeScope(scope)) {
    case 'blog':
      return 'Active source scope: **thingelstad.com blog only**. Answer from Jamie\'s personal blog posts (his 20-year blog), not the Weekly Thing newsletter. Blog sources have no WT issue number — cite them by title and link, not by WT<N>.';
    case 'podcast':
      return 'Active source scope: **Another Thing podcast only**. Answer from podcast episode transcripts and show notes, not the Weekly Thing newsletter or Jamie\'s blog. Podcast sources have no WT issue number — cite them by episode title and link, not by WT<N>.';
    case 'both':
      return 'Active source scope: **Weekly Thing archive + thingelstad.com blog**. Draw on both. Cite Weekly Thing issues as WT<N> and blog posts by title and link. When a source carries `also_in_issues`, the blog post was also featured in those Weekly Thing issue(s) — you may note the cross-reference (e.g. "Jamie also featured this in WT###").';
    case 'all':
      return 'Active source scope: **Weekly Thing archive + thingelstad.com blog + Another Thing podcast**. Draw on all selected sources. Cite Weekly Thing issues as WT<N>; cite blog posts by title/link; cite podcast sources by episode title/link. Blog and podcast sources have no WT issue number.';
    default:
      return 'Active source scope: **Weekly Thing archive only**. Answer from Weekly Thing issues and the site/FAQ pages. If the reader explicitly asks about Jamie\'s personal blog or Another Thing podcast, tell them that source scope is available but not currently selected.';
  }
}
