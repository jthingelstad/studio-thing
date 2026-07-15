# Studio issue workspace design

Design direction for rebuilding Studio around one job: help Jamie create and
ship each issue of The Weekly Thing. This uses the 2023 OmniFocus/Shortcuts
workflow as a guide, but deliberately changes it for the new Studio/Eddy model.

Sources:

- `https://www.thingelstad.com/2023/10/01/task-management-for.html`
- `https://files.thingelstad.com/posts/2023/send-weekly-thing.taskpaper`
- `https://www.thingelstad.com/2023/09/24/how-i-build.html`
- `notes/design/issue-atoms.md`
- `notes/design/publishing-workflow-wizard-plan.md`
- `docs/publishing-process.md`

## Design thesis

Studio should not be a generic production tracker, a Discord command wrapper,
or a pile of per-field forms. Studio should be the active issue project.

The old system worked because it combined:

- a time-aware project plan
- next-action thinking
- durable section state
- rerunnable automation
- clear separation between creative work and mechanical build steps

Studio should keep those strengths and move them into a private web app where
the newsletter issue is the first-class object. The web app should replace the
coordination burden of OmniFocus plus the build cockpit role of Shortcuts.
Drafts, Pinboard, micro.blog, Buttondown, and the archive can remain important
systems, but Studio should show what is needed, what is ready, and what happens
next.

## Product principles

1. **The current issue is the home screen.** Opening Studio should answer:
   what issue is active, where are we in the week, what is the next action, and
   what is blocking publish?
2. **Jamie writes every word.** Eddy can review, suggest, retrieve archive
   context, compose mechanical packaging options, and surface missing work, but
   the UI should not imply that Eddy authors the newsletter.
3. **The DB is the draft.** The workspace edits current issue state and the
   visible issue is rendered from that state continuously.
4. **Source systems stay legible.** Pinboard and micro.blog are not hidden.
   Studio should show what came from where, when it was synced, and what was
   excluded or promoted.
5. **The rendered issue is the editor.** The issue should appear in reading
   order and support atomic inline editing. There should not be a separate
   "generate preview" step for normal work.
6. **The workflow is time-aware.** The content cutoff and publish target should
   drive available/soon/blocked states.
7. **Build and ship are runbooks.** The app should not require Jamie to
   remember a command sequence.

## Old workflow to Studio mapping

The old project had four major sequential phases. The first phase had flexible
ordering; the rest behaved more like a runbook.

| Old phase | Studio phase | Studio responsibility |
|---|---|---|
| Create Content | Write | Intro, Currently, cover/photo, optional outro, early drafted atoms |
| Curate Links | Curate | Pinboard sync, Notable/Briefly selection, Journal sync, promote/deselect/reorder |
| Build and Send | Build / Publish | live issue validation, Eddy review, subject/description/haiku/Echoes, Buttondown, website, audio |
| Finalize | Close | put to bed, file issue, create/plan the next issue |

The new flow can be simpler than the old one because Studio has live access to
the issue state. We do not need to recreate every OmniFocus task. We need to
surface the next meaningful decision at the right time and preserve the ability
to inspect the full runbook.

## Primary app structure

### 1. Current Issue

`/` should redirect to the current issue workspace when an issue is active.
When no issue is active, it should show a compact issue planner with the next
issue number/date and a button to create or resume an issue.

The issue header should show:

- `WT###`
- title or working label
- publish date and target send time
- content cutoff
- phase
- next action
- readiness summary
- last source sync

The header should be operational, not decorative. It should behave like the top
of an OmniFocus project: current status, due pressure, and what can be done now.

### 2. Workflow rail

A persistent rail should show the issue runbook:

1. Plan issue
2. Create content
3. Curate sources
4. Assemble issue
5. Review
6. Package
7. Publish
8. Close issue

Each row should have one of these states:

- ready now
- waiting until later
- blocked
- done
- optional
- warning

Rows should expand to show tasks and links. The rail should not become a second
editor; it is for orientation and next action.

### 3. Live issue canvas

The main work surface should be a live, rendered issue canvas. It should look
like the current issue, not like a form builder. Each section and item is an
editable atom in place:

- Intro
- Currently
- Photo / cover
- Notable
- Featured
- Journal
- Briefly
- Outro
- Echoes
- Haiku / closer

For each atom, the UI should show:

- kind
- title
- rendered body
- source
- selected/excluded state
- publish-impact status
- Eddy note count, if any

Expected controls:

- edit the atom in place
- save without leaving the page
- move up/down or drag within section
- promote/demote where valid
- select/deselect without deleting
- open source in Pinboard or micro.blog
- ask Eddy about this atom
- show source-sync timestamp or provenance

Editing should feel WYSIWYG enough that Jamie can trust the page as the issue.
For markdown-heavy fields, the editing control can expose Markdown while active,
but the default/resting state should be rendered issue output. Editing a link
blurb should happen right where that link appears in Notable or Briefly.

Build one good canvas before adding secondary surfaces. The separate current
`/editor` page should disappear into the issue page rather than remain a side
route.

### 4. Source tray

Studio should have a source tray for inbound material. This replaces the mental
load of checking Pinboard unread, Safari Reading List, blog posts, and sync
outputs across separate tools.

The tray should show:

- sync status for Pinboard and micro.blog
- new items since last sync
- selected vs excluded source items
- source items missing descriptions or titles
- Journal posts with images and alt status
- Pinboard items not yet assigned or recently changed

The tray should be filterable by source and status. The first version can be
read-only plus links to source systems; later versions can support Pinboard
write-back and direct derived atom editing.

### 5. Live rendering and validation

Studio should not need a preview capability in the old sense. The issue canvas
is the preview and the editor. The normal workflow should never require Jamie to
click "generate preview" to understand what will ship.

Rendering still matters for channel-specific validation:

- issue body should always be current
- email-specific differences should be surfaced as validation or packaging
  notes, not as a separate working mode
- website/archive-specific metadata should be visible in package/publish
  readiness
- audio transcript can remain a generated publish artifact, not an authoring
  preview

If the system cannot render the issue canvas from current DB state, that is a
workspace error, not a stale preview problem.

### 6. Eddy review

Eddy should appear as a review layer, not as a chat-first coworker.

Capabilities:

- run issue review
- show anchored notes beside atoms
- resolve/dismiss notes
- rerun review and close stale notes when clean
- run continuity check for Intro or selected atom
- retrieve archive context for a theme or phrase
- ask Eddy about one atom or the whole issue

Chat can remain secondary. The issue workspace should surface Eddy's output in
place, where Jamie is editing.

### 7. Package panel

Packaging should have its own clear section, because it is a different mode
than writing and curation.

Package fields:

- subject
- description
- haiku
- Echoes
- cover metadata
- email-specific blocks if still active
- publish-stamped fields such as Buttondown ID and archive URL

The UI should distinguish:

- authored by Jamie
- generated as options for Jamie to choose
- derived deterministically
- stamped by a publish action

The earlier `metadata.json` confusion should disappear from the product
surface.

### 8. Publish runbook

Publish should be a gated checklist, not a cluster of buttons.

Rows:

- draft reads clean
- required sections present
- intro present
- cover image and metadata present
- subject and description present
- haiku present
- Echoes present
- Buttondown draft created or updated
- website published
- audio rendered and published
- issue put to bed

Per-channel gates:

- Email needs subject, description, haiku, intro, cover, and required sections.
- Website needs the archive render and Buttondown/URL state required by the
  current publish pipeline.
- Audio needs transcript/audio inputs and progress visibility.
- Put to bed needs the intended publish legs complete or explicitly skipped.

The panel should allow per-channel publish and "ship all" only when gates pass.
Every live action should show a confirmation with the exact issue and
destination.

### 9. Finalize and next issue

Finalize should not be an afterthought. The old workflow treated the next issue
project as part of closing this one; Studio should too.

After publish:

- verify shipped URL
- file issue into local issue data
- close active window
- show final status
- offer to create the next issue with computed number/date
- allow defer for break periods
- allow a one-off housekeeping item for post-break cleanup

## Screen proposal

### Desktop

Use a dense, work-focused layout.

```
┌─────────────────────────────────────────────────────────────────────┐
│ WT351 · publishes Sat 7:00 AM · cutoff Thu 11:59 PM · next action   │
├───────────────┬─────────────────────────────────────┬───────────────┤
│ Workflow      │ Live issue canvas                    │ Notes/Package  │
│ rail          │ rendered atoms in reading order      │ tabs           │
│               │ inline edit/reorder/promote          │               │
│ Source tray   │                                     │ Publish panel  │
└───────────────┴─────────────────────────────────────┴───────────────┘
```

The live issue canvas is the largest region. Workflow and publish state frame
the work but do not dominate it.

### Mobile / narrow

Use tabs:

- Work
- Sources
- Review
- Publish

The mobile view should be functional for checking status, editing short atoms,
and publishing in an emergency. It does not have to be the ideal long-form
writing environment.

## Time model

Studio should compute relative states from publish date:

- early week: content creation and link curation available
- after link curation deadline approaches: source tray warnings become visible
- after content cutoff: build/review/package becomes primary
- publish day: publish runbook becomes primary
- after send: finalize/next issue becomes primary

This is guidance, not lockout. Jamie can always override, because individual
issues vary.

## Data and implementation notes

Near-term implementation should continue to avoid a big-bang atoms migration.

Use current stores:

- `issue_windows` and `productions` mirror for issue lifecycle
- `issue_items` for Pinboard/micro.blog rows
- `currently_entries` for Currently
- `production_content` for authored atoms
- `editorial_comments` for Eddy notes
- S3 only for publishing assets and binaries

Add read models before storage migrations:

- `issue_workspace_state(issue_number)` for the whole page
- `issue_runbook_state(issue_number)` for the workflow rail
- `source_tray_state(issue_number)` for source sync/triage
- `publish_runbook_state(issue_number)` for package/publish gates

The current `production_state.build_state` and `publish_state` are a start, but
they are too publish-phase oriented. The workspace needs a product-level view
that answers "what should Jamie do next?"

## Implementation slices

### Slice 1: Current issue workspace shell

- Make `/` land on the active issue workspace.
- Rename visible UI from productions to issues.
- Replace the current dashboard layout with header, workflow rail, live issue
  canvas, notes/package rail, and publish panel.
- Keep existing forms/actions under the hood.

Acceptance:

- A current issue can be opened, edited in place, synced, reviewed, marked
  built, and published using the new workspace.
- No route or label requires the operator to understand "production."

### Slice 2: Workflow rail and next action

- Encode the Studio-native runbook.
- Compute ready/blocked/done/soon states.
- Show the next action in the issue header.
- Preserve manual override.

Acceptance:

- At any point in the week, the page tells Jamie what matters next.
- Build/publish gates are visible before a failed publish click.

### Slice 3: Live issue canvas becomes the primary surface

- Merge the separate editor route into the main workspace.
- Render the issue continuously from DB state.
- Improve inline atomic editing, reorder, select/deselect, promote/demote.
- Add per-atom provenance and Eddy note affordances.

Acceptance:

- Jamie can assemble and edit the issue in reading order without Discord
  commands or a separate preview.
- Derived atoms are clearly source-owned until Pinboard write-back lands.

### Slice 4: Source tray

- Show Pinboard and micro.blog sync status.
- Highlight new/changed/missing/excluded items.
- Link directly to source records.

Acceptance:

- Jamie can tell whether source material is ready without leaving Studio.

### Slice 5: Package and publish runbook

- Split package fields by ownership.
- Add channel gates and live action status.
- Make publish actions confirm exact destination and issue.
- Make put-to-bed part of the visible runbook.

Acceptance:

- The ship-night command sequence is replaced by a visible checklist.
- A missing subject, cover, haiku, Echoes, or publish-stamped field is visible
  before shipping.

### Slice 6: Finalize and next issue

- Close current issue.
- Offer next issue creation with computed date/number.
- Support break/defer periods.

Acceptance:

- Studio replaces the "create next project" closeout step.

## Open product decisions

1. Should Studio still create or update OmniFocus tasks, or is the web
   workspace the project now?
2. Should Intro/Currently authoring remain in Drafts for now, or should Studio
   become the normal writing surface for those atoms?
3. Should Studio keep a "defer until" concept for individual workflow rows, or
   derive availability only from publish date?
4. Should package generation offer selectable options in-page, or should Eddy
   write draft values that Jamie edits directly?
5. Is audio a default publish leg for every issue or an optional leg that can be
   explicitly skipped?
6. How much source editing should happen in Studio before Pinboard write-back is
   implemented?

## Recommendation

Do not start with a visual redesign of the current pages. Start by changing the
product model of the page.

The first build should be a Studio-native issue workspace that combines:

- old OmniFocus next-action clarity
- old Shortcuts rerunnable build confidence
- the new live atom editor
- the new Eddy review layer
- a visible publish runbook

Once that structure exists, visual polish and interaction details will matter a
lot more. Without it, prettier templates will still feel like the old workflow
is missing.
