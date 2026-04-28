.PHONY: build serve clean data librarian-corpus librarian-corpus-upload librarian-graph librarian-graph-upload librarian-deploy fresh content-pull content-pull-latest content-build content-diff content-push content-push-live fetch-latest sync sync-push sync-issue refresh-copy refresh-copy-dry

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

build: data
	npm run build:all

serve: data
	npm run serve

clean:
	rm -rf _site cache

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
	python scripts/content.py push --issue $$num --dry-run

refresh-copy:
	npm run refresh-copy

refresh-copy-dry:
	npm run refresh-copy:dry
