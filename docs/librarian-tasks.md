# Librarian Backend Tasks

Concrete follow-ups for the Librarian API backend — Lambda, auth, entitlements, corpus
pipeline, and the eval loop. The Thingy *product* roadmap and web-surface tasks live in
`thingy.thingelstad.com/docs/ROADMAP.md` and `docs/TASKS.md`; this file is the Studio-side
(backend) half of that partition.

## Entitlements And Auth

- [ ] Audit Jamie's owner entitlement path periodically. Owner mode currently comes from `jamie@thingelstad.com` / owner hash or `thingy-owner`.
- [ ] Add a short operator note listing the active mode tags in Buttondown so future Jamie knows which tags grant which Thingy capabilities.
- [ ] Confirm Fastmail/JMAP token rotation procedure for `thingy@thingelstad.com`.
- [ ] Add monitoring for magic-link send failures and expired/invalid redemption spikes.
- [ ] Consider a dedicated owner/admin auth path before exposing any non-local operator dashboard.
- [ ] Finish the dedicated CloudFormation service-role cleanup described in `reference/librarian.md`.

## Operator Review

- [ ] Add more client-side filters to the operator report if review volume grows: mode, source scope, eval flag, feedback reaction, runtime timeout, and Jamie-vs-reader.
- [ ] Add an explicit report section for mode usage and mode-specific eval flags.
- [ ] Convert repeated evaluator takeaways into a lightweight improvement queue.

## Corpus And Pipeline

- [ ] Add a corpus freshness/status view that shows last successful source sync and corpus upload for Weekly Thing, blog, and podcast.
- [ ] Confirm that the external-content sync workflow runs after new blog posts and podcast episodes and that failures are visible.
- [ ] Add a deploy summary that says whether corpus upload was skipped or refreshed and why.
- [ ] Revisit whether old pre-server-side conversation records can be deleted from DynamoDB now that canonical conversation rows are the only supported structure.

## Quality And Tests

- [ ] Add end-to-end Lambda handler tests or a repeatable live QA harness for modes, auth, conversations, and evaluator flow.
- [ ] Add regression tests for citation-footer consistency and retrospective-vs-contemporaneous timeline evidence.
- [ ] Add timeout-path tests so evaluator reports runtime exhaustion as runtime exhaustion, not answer-quality failure.
