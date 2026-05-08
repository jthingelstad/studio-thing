"""In-flight issue resolver — exposed as ``issue.current_number``.

Extracted from ``agent_tools.py`` so the registry can register it under
the dotted ``issue.*`` namespace without keeping the implementation in
the larger module. Behavior is unchanged from the original
``t_current_issue_number`` helper.
"""

from __future__ import annotations

from typing import Any

from . import s3


def t_current_issue_number(deps) -> dict[str, Any]:
    """Resolve which issue is being assembled this week.

    Combines two signals:
      - the highest issue folder in S3 (where Jamie's iOS Shortcuts stage drafts)
      - the highest published issue in the archive corpus (the reference baseline)

    The working issue is **not** in the archive corpus — it's a draft. Use
    this when Jamie says "the current issue", "this weekend's issue", or
    "the one I'm working on" so you don't accidentally treat the most
    recently *published* issue as the in-flight one.
    """
    try:
        ws = s3.list_workspaces()
        s3_max = ws.get("current_issue_number")
    except Exception as exc:  # noqa: BLE001
        s3_max = None
        ws = {"error": f"{type(exc).__name__}: {exc}"}

    published_latest = None
    if deps is not None and getattr(deps, "corpus", None) is not None:
        published_latest = deps.corpus.latest_issue_number

    if s3_max is not None and (published_latest is None or s3_max > published_latest):
        working = s3_max
        has_workspace = True
    elif published_latest is not None:
        working = published_latest + 1
        has_workspace = False
    else:
        working = None
        has_workspace = False

    return {
        "working_issue_number": working,
        "has_s3_workspace": has_workspace,
        "s3_max_workspace": s3_max,
        "published_latest_issue": published_latest,
        "note": (
            "The working issue is the in-flight draft — it is NOT in your "
            "archive corpus yet. search_archive / get_issue won't find it."
        ),
    }
