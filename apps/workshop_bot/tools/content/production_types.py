"""Newsletter issue phase vocabulary.

The ``productions`` table remains as the internal mirror for newsletter issue
rows, but Studio is no longer a multi-surface production manager. The only
first-class production type is ``newsletter``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionType:
    """One production kind Studio understands.

    ``key``            the stable type id stored in ``productions.production_type``.
    ``label``          human display name.
    ``id_prefix``      the ``productions.id`` prefix — ``WT350``.
    ``phases``         the ordered phase vocabulary (``phases[0]`` is the default).
    ``terminal_phase`` the phase meaning "shipped/done" (must be in ``phases``).
    ``surface``        the public publishing surface label.
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
    """The ``productions.id`` prefix for a type (``WT``)."""
    return get_type(production_type).id_prefix


# Sentinel so is_valid_phase can answer False for unknown types without raising.
_EMPTY = ProductionType("", "", "", (), "", "")
