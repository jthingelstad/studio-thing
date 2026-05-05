# Linked URL Pipeline

This directory is reserved for the next data pipeline step: retrieving and aggregating metadata for URLs already extracted from curated issue links.

Expected inputs:

- `apps/site/archive/*.md` front matter link records
- `data/librarian/corpus.json` link records, when a built corpus is more convenient

Expected outputs:

- tracked aggregate artifacts under `data/links/`

Keep this step downstream of `pipeline/content/content.py`; it should not independently parse raw Buttondown bodies.
