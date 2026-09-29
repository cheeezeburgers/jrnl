.PHONY: install tag release

install:
	./install.sh

# Commit the current version first, then run make tag and make release.
tag:
	bash development/release.sh tag

release:
	bash development/release.sh release
