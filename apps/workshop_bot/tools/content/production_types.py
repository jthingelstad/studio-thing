"""The production-type registry — the per-type phase vocabularies, owned in code.

This is the single source of truth for *what kinds of things Scout produces* and
*what phases each kind moves through*. It replaces the newsletter-only
``_ISSUE_PHASES`` constant (``tools/db/_issues.py``) with a generic, multi-type
model so the ``productions`` table (and the web app + agent tools that read it)
can carry newsletters, blog articles, podcast episodes, and simple single-stage
projects side by side.

Why a code registry and not a DB CHECK: a phase vocabulary is editorial, not
structural — adding "review" to the article flow should be a one-line edit here,
never a table rebuild. ``db.set_production_phase`` validates against this module.

Phase vocabularies (ordered, earliest → terminal):
- newsletter : write → build → publish → share
- article    : idea → outline → draft → publish
- podcast    : idea → outline → script → record → publish
- project    : open → done            (generic single-arc work, e.g. membership)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionType:
    """One kind of production Scout runs.

    ``key``            the stable type id stored in ``productions.production_type``.
    ``label``          human display name.
    ``id_prefix``      the ``productions.id`` prefix — ``WT350``/``ART7``/``POD3``/``PRJ2``.
    ``phases``         the ordered phase vocabulary (``phases[0]`` is the default).
    ``terminal_phase`` the phase meaning "shipped/done" (must be in ``phases``).
    ``surface``        the publishing surface label (empty for generic projects).
    """

    key: str
    label: str
    id_prefix: str
    phases: tuple[str, ...]
    terminal_phase: str
    surface: str


PRODUCTION_TYPES: dict[str, ProductionType] = {
    "newsletter": ProductionType(
        key="newsletter",
        label="Newsletter",
        id_prefix="WT",
        # 'planned' = defined with a date, not yet being worked (just a DB row,
        # no workspace). 'Start working' moves it to build (the live pipeline).
        phases=("planned", "write", "build", "publish", "share"),
        terminal_phase="share",
        surface="weekly.thingelstad.com",
    ),
    "article": ProductionType(
        key="article",
        label="Article",
        id_prefix="ART",
        phases=("idea", "outline", "draft", "publish"),
        terminal_phase="publish",
        surface="thingelstad.com",
    ),
    "podcast": ProductionType(
        key="podcast",
        label="Podcast",
        id_prefix="POD",
        phases=("idea", "outline", "script", "record", "publish"),
        terminal_phase="publish",
        surface="another.thingelstad.com",
    ),
    "project": ProductionType(
        key="project",
        label="Project",
        id_prefix="PRJ",
        phases=("open", "done"),
        terminal_phase="done",
        surface="",
    ),
}


# Production lifecycle statuses (orthogonal to the per-type phase vocabulary).
# 'active'    in-flight work — on the slate, enumerated by check-ins.
# 'paused'    deliberately shelved "not now" — off the slate, still in the
#             default registry view so it stays findable.
# 'done'      shipped (phase reached terminal).
# 'archived'  filed away — visible only behind the registry's ?all=1 view.
# 'abandoned' explicitly killed.
STATUSES: tuple[str, ...] = ("active", "paused", "done", "archived", "abandoned")


def is_valid_status(status: str) -> bool:
    """Whether ``status`` is in the production lifecycle vocabulary."""
    return status in STATUSES


def get_type(production_type: str) -> ProductionType:
    """Return the :class:`ProductionType` for ``production_type`` or raise."""
    try:
        return PRODUCTION_TYPES[production_type]
    except KeyError as exc:
        known = ", ".join(sorted(PRODUCTION_TYPES))
        raise ValueError(
            f"unknown production_type {production_type!r}; known: {known}"
        ) from exc


def phases_for(production_type: str) -> tuple[str, ...]:
    """The ordered phase vocabulary for a type."""
    return get_type(production_type).phases


def default_phase(production_type: str) -> str:
    """The phase a freshly-created production of this type starts in (phases[0])."""
    return get_type(production_type).phases[0]


def is_valid_phase(production_type: str, phase: str) -> bool:
    """Whether ``phase`` is in this type's vocabulary."""
    return phase in PRODUCTION_TYPES.get(production_type, _EMPTY).phases


def is_terminal(production_type: str, phase: str) -> bool:
    """Whether ``phase`` is this type's terminal (shipped/done) phase."""
    pt = PRODUCTION_TYPES.get(production_type)
    return bool(pt and phase == pt.terminal_phase)


def prefix_for(production_type: str) -> str:
    """The ``productions.id`` prefix for a type (``WT``/``ART``/``POD``/``PRJ``)."""
    return get_type(production_type).id_prefix


# Sentinel so is_valid_phase can answer False for unknown types without raising.
_EMPTY = ProductionType("", "", "", (), "", "")
