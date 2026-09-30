.PHONY: install tag push-tag release

install:
	./install.sh

# Commit the current version first, then make tag; publish with push-tag or release.
tag:
	bash development/release.sh tag

push-tag:
	bash development/release.sh push-tag

release:
	bash development/release.sh release
