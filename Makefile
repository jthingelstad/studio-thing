.PHONY: build serve clean data fresh fetch-latest sync sync-push sync-issue refresh-copy refresh-copy-dry

data:
	npm run data

build: data
	npm run build:all

serve: data
	npm run serve

clean:
	rm -rf _site cache

fresh:
	npm run data:fresh
	npm run serve

fetch-latest:
	npm run fetch:latest

sync:
	npm run sync

sync-push:
	npm run sync:push

sync-issue:
	@read -p "Issue number: " num; \
	python scripts/sync_to_buttondown.py --issue $$num

refresh-copy:
	npm run refresh-copy

refresh-copy-dry:
	npm run refresh-copy:dry
