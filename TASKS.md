# Thingy Tasks

Concrete follow-ups that need operator action, a decision, or a focused implementation pass.

## Access And Entitlements

- [ ] Add Buttondown tags for people who should get Trusted Circle mode:
  - `thingy-trusted-circle`
  - `thingy-family`
  - `thingy-close-friends`
- [ ] Decide whether supporting members should get only Research Guide or also any warmer/experimental modes.
- [ ] Audit Jamie's owner entitlement path periodically. Owner mode currently comes from `jamie@thingelstad.com` / owner hash or `thingy-owner`.
- [ ] Add a short operator note listing the active mode tags in Buttondown so future Jamie knows which tags grant which Thingy capabilities.

## Operator Review

- [ ] Decide whether the local static operator report is enough for now or whether to build a real authenticated web dashboard after magic-link owner auth is extended to admin surfaces.
- [ ] Add more client-side filters to the operator report if review volume grows: mode, source scope, eval flag, feedback reaction, runtime timeout, and Jamie-vs-reader.
- [ ] Convert repeated evaluator takeaways into a lightweight improvement queue.
- [ ] Add an explicit report section for mode usage and mode-specific eval flags.

## Auth And Security

- [ ] Confirm Fastmail/JMAP token rotation procedure for `thingy@thingelstad.com`.
- [ ] Add monitoring for magic-link send failures and expired/invalid redemption spikes.
- [ ] Consider a dedicated owner/admin auth path before exposing any non-local operator dashboard.
- [ ] Finish the dedicated CloudFormation service-role cleanup described in `reference/librarian.md`.

## Corpus And Pipeline

- [ ] Add a corpus freshness/status view that shows last successful source sync and corpus upload for Weekly Thing, blog, and podcast.
- [ ] Confirm that the external-content sync workflow runs after new blog posts and podcast episodes and that failures are visible.
- [ ] Add a deploy summary that says whether corpus upload was skipped or refreshed and why.
- [ ] Revisit whether old pre-server-side conversation records can be deleted from DynamoDB now that canonical conversation rows are the only supported structure.

## Product And UX

- [ ] Keep a small browser QA checklist for rail, mobile drawer, New Chat, mode selection, source picker, curiosity map, copy/share, voice input, response playback, and expired-session handling.
- [ ] Add a gentle explanation somewhere in the product docs that modes change posture, not corpus access.
- [ ] Recheck Archive Sparks frequency after real usage; they should delight, not interrupt.
- [ ] Tune curiosity map seeding and conversation behavior as usage patterns emerge.

## Quality And Tests

- [ ] Add end-to-end Lambda handler tests or a repeatable live QA harness for modes, auth, conversations, and evaluator flow.
- [ ] Add regression tests for citation-footer consistency and retrospective-vs-contemporaneous timeline evidence.
- [ ] Add timeout-path tests so evaluator reports runtime exhaustion as runtime exhaustion, not answer-quality failure.
