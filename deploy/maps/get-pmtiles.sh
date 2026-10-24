#!/bin/sh
# Installs the go-pmtiles CLI as /usr/local/bin/pmtiles: the pinned release binary from GitHub, kept only if its
# sha256 is the one written here. Run when the image is built and, if that download failed (no network to GitHub
# then), again by run.sh before each map download: a failed download never fails the image build or the stack.
# The checksums were taken from the release files themselves (the release publishes no checksum file).
set -eu
VERSION=1.31.2
case "$(uname -m)" in
  x86_64) ARCH=x86_64; SUM=3ed7dbf4ec2e6dfe5e25b6f70d1ffc932729f93c86db353bf514dd71010a312f ;;
  aarch64) ARCH=arm64; SUM=f8bd47e7ea866863489cad588fbaf2f31f42e5821f7a03f009b3769f05801cb1 ;;
  *) echo "pmtiles: no release for $(uname -m)" >&2; exit 1 ;;
esac
[ -x /usr/local/bin/pmtiles ] && exit 0
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
wget -q -O "$work/p.tgz" "https://github.com/protomaps/go-pmtiles/releases/download/v$VERSION/go-pmtiles_${VERSION}_Linux_$ARCH.tar.gz"
echo "$SUM  $work/p.tgz" | sha256sum -c -s || { echo "pmtiles: checksum mismatch, not installed" >&2; exit 1; }
tar -xzf "$work/p.tgz" -C "$work" pmtiles
install -m 0755 "$work/pmtiles" /usr/local/bin/pmtiles
