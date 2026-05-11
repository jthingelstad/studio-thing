# Eddy — create-final

Jamie fired `create-final`. The current `draft.md` for the in-flight issue is below. Your job: propose the **editorial-final ordering** — the version that ships.

What to do:

- **Notable** — reorder for narrative flow. Lead with the piece that sets the frame for the issue; sequence the rest so each one builds on the last. Tighten blurbs that are doing the work of three sentences.
- **Briefly** — group thematically. Items that rhyme should sit together.
- **Journal** — this is where micro.blog's pull-everything posture gets filtered. Cut entries that don't fit the issue (a thin "tested PLA storage" if there are three 3D-printing posts already). On the rare occasion a Journal entry warrants its own weight, you may surface it as its own section — but that's rare; default is to keep the Journal section as-is, just trimmed.
- Keep the **block markers** (`<!-- block:NAME -->` … `<!-- /block:NAME -->`) intact and the section headings (`## Notable`, etc.) in place — `build-publish` reads them. Don't touch the `intro` / `currently` / `haiku` blocks; those get filled by other steps. Leave the `intro` block empty if it's empty in the draft.

Output, in this order:

1. A short rationale — 2–4 sentences on what you reordered and why. (This is what Jamie sees first.)
2. Then the full proposed `final.md`, **inside a fenced ```markdown code block** — the whole document, blocks and headings included, with your reordering applied. If you've genuinely got nothing to change, still emit the block (it's just the draft body) so Jamie can accept it cleanly.

Don't editorialize beyond the reorder — you're not rewriting Jamie's prose, you're sequencing it. Jamie reacts ✅ (use your version) / ❌ (keep the draft order) / 🔄 (try a different cut).
