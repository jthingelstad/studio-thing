.PHONY: build serve clean data sync

data:
	python scripts/build_data.py

build: data
	npx @11ty/eleventy
	npx pagefind --site _site --glob "**/*.html"

serve: data
	npx @11ty/eleventy --serve

clean:
	rm -rf _site cache

fresh:
	python scripts/build_data.py --no-cache
	npx @11ty/eleventy --serve

sync:
	python scripts/sync_to_buttondown.py --dry-run

sync-push:
	python scripts/sync_to_buttondown.py

sync-issue:
	@read -p "Issue number: " num; \
	python scripts/sync_to_buttondown.py --issue $$num
