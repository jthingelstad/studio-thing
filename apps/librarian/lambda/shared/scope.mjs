/**
 * Source-scope helpers for the Thingy agent.
 *
 * Thingy answers over two independent corpora: the Weekly Thing issue
 * archive (`weekly_thing`) and Jamie's 20-year thingelstad.com blog
 * (`blog`). Scope is enforced by *which corpus the retrieval scans*, not by
 * a post-filter — so the WT corpus stays byte-identical to today and the
 * (large) blog corpus loads lazily only when a request asks for it.
 *
 * `both` retrieves candidates from each corpus and reranks the union once.
 *
 * Default is `weekly_thing`: it preserves Thingy's historical identity and
 * means the operator `/retrieve` path (workshop_bot) is unaffected when it
 * sends no scope.
 */

export const SCOPES = ['weekly_thing', 'blog', 'both'];
export const DEFAULT_SCOPE = 'weekly_thing';

/** Coerce arbitrary input into one of SCOPES, defaulting to weekly_thing. */
export function normalizeScope(value) {
  const raw = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (raw === 'weekly_thing' || raw === 'wt' || raw === 'weeklything' || raw === 'issues' || raw === 'archive') {
    return 'weekly_thing';
  }
  if (raw === 'blog' || raw === 'thingelstad' || raw === 'thingelstad_com') return 'blog';
  if (raw === 'both' || raw === 'all' || raw === 'everything') return 'both';
  return DEFAULT_SCOPE;
}

/** Corpus kinds a scope scans, in retrieval order (WT first for `both`). */
export function scopeKinds(scope) {
  const normalized = normalizeScope(scope);
  if (normalized === 'blog') return ['blog'];
  if (normalized === 'both') return ['weekly_thing', 'blog'];
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
    case 'both':
      return 'Active source scope: **Weekly Thing archive + thingelstad.com blog**. Draw on both. Cite Weekly Thing issues as WT<N> and blog posts by title and link. When a source carries `also_in_issues`, the blog post was also featured in those Weekly Thing issue(s) — you may note the cross-reference (e.g. "Jamie also featured this in WT###").';
    default:
      return 'Active source scope: **Weekly Thing archive only**. Answer from Weekly Thing issues and the site/FAQ pages. If the reader explicitly asks about Jamie\'s personal blog (thingelstad.com), tell them blog scope is available but not currently selected.';
  }
}
