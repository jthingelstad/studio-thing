.PHONY: build serve clean librarian-corpus librarian-corpus-upload librarian-graph librarian-graph-upload librarian-deploy content-build refresh-copy refresh-copy-dry audio audio-issue stats test-workshop test-workshop-env

librarian-corpus:
	npm run librarian:corpus

librarian-corpus-upload:
	npm run librarian:corpus:upload

librarian-graph:
	npm run librarian:graph

librarian-graph-upload:
	npm run librarian:graph:upload

librarian-deploy:
	npm run librarian:deploy

build:
	python pipeline/content/content.py build
	npm run build:all

serve:
	python pipeline/content/content.py build
	npm run serve

clean:
	rm -rf _site cache tmp test-results playwright-report
	rm -f data/librarian/*.embedded.json
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

content-build:
	python pipeline/content/content.py build

stats:
	python pipeline/content/content.py stats

refresh-copy:
	npm run refresh-copy

refresh-copy-dry:
	npm run refresh-copy:dry

audio:
	python pipeline/audio/audio.py build --latest

audio-issue:
	python pipeline/audio/audio.py build --issue $(ISSUE)

test-workshop:
	venv/bin/python -m unittest discover -s apps/workshop_bot/tests -t .

test-workshop-env:
	set -a; source .env; set +a; venv/bin/python -m unittest discover -s apps/workshop_bot/tests -t .
