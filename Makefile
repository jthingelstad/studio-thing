.PHONY: build clean content-build librarian-corpus librarian-corpus-upload librarian-blog-corpus-upload librarian-podcast-import librarian-podcast-corpus librarian-podcast-corpus-upload librarian-corpora-upload librarian-graph librarian-graph-upload librarian-deploy audio audio-issue refresh-copy refresh-copy-dry test test-lambda test-workshop test-workshop-env

PYTHON ?= python3

librarian-corpus:
	$(PYTHON) pipeline/corpus/build.py

librarian-corpus-upload:
	$(PYTHON) pipeline/deploy/upload_corpus.py

librarian-blog-corpus-upload:
	$(PYTHON) pipeline/deploy/upload_blog_corpus.py

librarian-podcast-import:
	$(PYTHON) pipeline/podcast/import_another_thing.py

librarian-podcast-corpus:
	$(PYTHON) pipeline/corpus/build_podcast.py

librarian-podcast-corpus-upload:
	$(PYTHON) pipeline/deploy/upload_podcast_corpus.py

librarian-corpora-upload:
	$(PYTHON) pipeline/deploy/upload_corpus.py
	$(PYTHON) pipeline/deploy/upload_blog_corpus.py
	$(PYTHON) pipeline/deploy/upload_podcast_corpus.py

librarian-graph:
	$(PYTHON) pipeline/graph/build.py

librarian-graph-upload:
	$(PYTHON) pipeline/graph/build.py --upload

librarian-deploy:
	$(PYTHON) pipeline/deploy/aws.py $(ARGS)

# Build the generated artifacts Studio hands to downstream surfaces.
build:
	$(PYTHON) pipeline/content/content.py build
	$(PYTHON) pipeline/corpus/build.py
	$(PYTHON) pipeline/graph/build.py

clean:
	rm -rf cache tmp test-results playwright-report
	rm -f data/librarian/*.embedded.json
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

content-build:
	$(PYTHON) pipeline/content/content.py build

refresh-copy:
	$(PYTHON) pipeline/content/refresh_marketing_copy.py

refresh-copy-dry:
	$(PYTHON) pipeline/content/refresh_marketing_copy.py --dry-run

audio:
	$(PYTHON) pipeline/audio/audio.py build --latest

audio-issue:
	$(PYTHON) pipeline/audio/audio.py build --issue $(ISSUE)

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -t .

test-lambda:
	npm --prefix apps/librarian/lambda test

test-workshop:
	$(PYTHON) -m unittest discover -s apps/workshop_bot/tests -t .

test-workshop-env:
	set -a; source .env; set +a; $(PYTHON) -m unittest discover -s apps/workshop_bot/tests -t .
