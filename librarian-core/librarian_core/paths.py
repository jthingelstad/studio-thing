"""Canonical paths used by librarian-core consumers.

Resolved from this file's location on disk so editable installs work without
extra env vars: librarian-core/ lives at the repo root, so parents[2] is REPO.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO / "apps" / "site" / "archive"
SITE_DIR = REPO / "apps" / "site"
FAQ_PATH = REPO / "apps" / "librarian" / "lambda" / "shared" / "faq.json"
CORPUS_PATH = REPO / "data" / "librarian" / "corpus.json"
GRAPH_PATH = REPO / "data" / "librarian" / "graph.json"

# thingelstad.com blog — Jamie's 20-year personal blog, ingested by
# pipeline/blog/ingest_blog.py. Its own corpus (separate from the Weekly
# Thing corpus above) so blog scope loads lazily and never crowds out
# Weekly-Thing retrieval. See build_blog_corpus in corpus.py.
BLOG_DIR = REPO / "data" / "blog" / "posts"
BLOG_CORPUS_PATH = REPO / "data" / "librarian" / "blog_corpus.json"
