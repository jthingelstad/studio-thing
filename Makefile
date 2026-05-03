.PHONY: build serve clean data librarian-corpus librarian-corpus-upload librarian-graph librarian-graph-upload librarian-deploy librarian-ask fresh content-pull content-pull-latest content-build content-diff content-push content-push-live fetch-latest sync sync-push sync-issue refresh-copy refresh-copy-dry audio audio-issue

data:
	npm run data

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

librarian-ask:
	python pipeline/librarian/archive_chat.py $(ARGS)

build: data
	npm run build:all

serve: data
	npm run serve

clean:
	rm -rf _site cache tmp test-results playwright-report
	rm -f data/librarian/*.embedded.json
	find . -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

fresh:
	npm run data:fresh
	npm run serve

content-pull:
	npm run content:pull

content-pull-latest:
	npm run content:pull:latest

content-build:
	npm run content:build

content-diff:
	npm run content:diff

content-push:
	npm run content:push

content-push-live:
	npm run content:push:live

fetch-latest:
	npm run fetch:latest

sync:
	npm run sync

sync-push:
	npm run sync:push

sync-issue:
	@read -p "Issue number: " num; \
	python pipeline/content/content.py push --issue $$num --dry-run

refresh-copy:
	npm run refresh-copy

refresh-copy-dry:
	npm run refresh-copy:dry

audio:
	python pipeline/audio/audio.py build --latest

audio-issue:
	python pipeline/audio/audio.py build --issue $(ISSUE)
