# Infiny Box
#
#   make wsl        build infiny.wsl (Windows)
#   make docker     build the image for macOS/Linux
#   make installer  build infiny.wsl and place it in installer/, ready to zip
#   make clean      remove build artifacts
#
# There are no ISO, mkosi, QEMU or snapshot targets. Those belong to Infiny OS —
# the installable system — which is a separate project in its own repository.

.PHONY: wsl docker installer clean help

help:
	@echo "Infiny Box:"
	@echo "  make wsl        portable infiny.wsl (Windows)"
	@echo "  make docker     image for macOS/Linux"
	@echo "  make installer  infiny.wsl + installer/ (ready to zip)"
	@echo "  make clean      remove build artifacts"

wsl:
	bash build-wsl.sh

docker:
	bash build-docker.sh

# Depends on wsl on purpose. The copy used to be a separate step, and
# installer/infiny.wsl silently fell nine days behind the root one — so zipping
# installer/ would have shipped a stale image.
installer: wsl
	cp infiny.wsl installer/
	@echo "→ installer/ is ready to distribute (zip the installer/ folder)"

# Does not touch installer/infiny.wsl: that copy is what gets released, and
# removing it as part of a cleanup is a good way to publish nothing.
clean:
	rm -f infiny.wsl infiny-rootfs.tar
