"""Canonical paths used by librarian-core consumers.

Resolved from this file's location on disk so editable installs work without
extra env vars: librarian-core/ lives at the repo root, so parents[2] is REPO.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO / "site" / "archive"
CORPUS_PATH = REPO / "data" / "librarian" / "corpus.json"
GRAPH_PATH = REPO / "data" / "librarian" / "graph.json"
