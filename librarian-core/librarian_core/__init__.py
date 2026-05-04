"""Shared retrieval primitives for The Weekly Thing archive.

Modules:
- ``librarian_core.paths`` — canonical filesystem paths (REPO, archive, corpus, graph).
- ``librarian_core.corpus`` — read archive markdown, build chunk corpus, optionally
  embed via Bedrock Cohere.
- ``librarian_core.retrieval`` — BM25 lexical search over corpus chunks.
"""
