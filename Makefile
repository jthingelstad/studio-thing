.PHONY: build serve clean data sync refresh-copy refresh-copy-dry

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

refresh-copy:
	python scripts/refresh_marketing_copy.py

refresh-copy-dry:
	python scripts/refresh_marketing_copy.py --dry-run
