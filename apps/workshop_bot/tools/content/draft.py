"""Section + asset completeness for the in-flight issue.

**The DB is the draft**: ``section_status`` computes directly from
``issue_items`` rows, the DB content store, and ``currently_entries`` —
the only S3 access is the workspace listing for binaries (``cover.jpg``).
Shared by ``eddy-review`` (Eddy's review context), the ``issue-status``
job, ``build_eddy_context``, and the ``draft__section_status`` agent tool.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .. import s3

# Listed in the published section order (intro → Currently → cover →
# Notable → Journal → Briefly → outro → haiku); matches
# templates/draft_starter.md. ``outro`` is a Jamie-authored closing-prose
# block (parallel to ``intro``) projected from ``outro.md`` upstream.
#
# Promoted (featured) items splice inline at their declared
# ``promoted_position`` (driven by micro.blog's ``Featured`` category,
# applied at sync time, rendered by ``tools/renderers``).
SECTION_BLOCKS = (
    "intro", "currently", "cover", "notable", "journal", "brief",
    "outro", "haiku",
)

# Atoms that Publish Email refuses without (the
# Notable/Brief/Journal *sections* are checked from draft blocks, not
# from a file). ``final.md`` is gone — section ordering and promotions
# live in the DB now.
REQUIRED_ASSETS = ("haiku.md", "metadata.json", "intro.md", "cover.jpg")


def word_count(draft_text: str) -> int:
    """Word count of the draft, ignoring HTML comments / block markers."""
    stripped = re.sub(r"<!--.*?-->", "", draft_text or "", flags=re.DOTALL)
    return len(stripped.split())


def _atom_present(issue_number: int, name: str) -> bool:
    from .. import content_store

    body = content_store.read_issue(issue_number, name)
    return bool(body and body.strip())


def section_status(
    issue_number: int,
    *,
    list_objects: Optional[set] = None,
) -> dict[str, Any]:
    """Compute the in-flight issue's section + asset completeness straight
    from the DB (the draft). ``list_objects`` overrides the S3 workspace
    listing (binaries: ``cover.jpg``) for tests."""
    from .. import content_store, db as _db, issue_items

    n = int(issue_number)
    if list_objects is None:
        try:
            listing = s3.list_issue(n)
            list_objects = {
                o.get("filename") for o in listing.get("objects", []) if o.get("filename")
            }
        except Exception:
            list_objects = set()

    sections: dict[str, Any] = {}
    for name in ("notable", "brief", "journal"):
        rows = issue_items.list_items(n, section=name, include_promoted=False)
        sections[name] = {
            "present": len(rows) > 0,
            "item_count": len(rows),
            "placeholder": False,
        }

    content_names = set(content_store.list_issue(n))
    cta_files = sorted(
        f for f in content_names
        if (f.startswith("cta-") and f.endswith(".md"))
        or (f.startswith("thanks-") and f.endswith(".md"))
    )
    assets: dict[str, bool] = {}
    for name in REQUIRED_ASSETS:
        if name == "cover.jpg":
            assets[name] = name in list_objects
        else:
            assets[name] = _atom_present(n, name)

    currently_entries = _db.currently_get_entries(n)
    currently_content = "\n".join(
        f"**{e['type_label']}:** {e.get('value') or ''}" for e in currently_entries
    ).strip()

    intro_present = assets.get("intro.md", False)
    currently_present = bool(currently_entries)
    haiku_present = assets.get("haiku.md", False)
    cover_present = assets.get("cover.jpg", False)

    required_missing: list[str] = [a for a in REQUIRED_ASSETS if not assets.get(a)]
    if not all(sections[s]["present"] for s in ("notable", "brief", "journal")):
        required_missing.append("sections (notable/brief/journal)")

    # Word count over the body rendered from current DB state (in-memory,
    # no artifacts). Lazy import — renderers pulls the wider tools graph.
    from .. import renderers

    try:
        body = renderers.render_body_for_issue(n)
    except Exception:  # noqa: BLE001 — status must not fail on a render error
        body = ""

    return {
        "issue_number": n,
        "word_count": word_count(body),
        "sections": sections,
        "assets": assets,
        "cta_files": cta_files,
        "intro_present": intro_present,
        "currently_present": currently_present,
        "currently_content": currently_content,
        "haiku_present": haiku_present,
        "cover_present": cover_present,
        "required_missing": required_missing,
        "ship_ready": not required_missing,
    }
