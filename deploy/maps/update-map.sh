#!/bin/sh
# The admin panel's base map: the Kuwait extract of the OpenStreetMap base map from the Protomaps daily build,
# one PMTiles file (~25 MB) that nginx serves (docker-compose: the "maps" volume, mounted at /srv/maps).
# docker-compose runs it for you: the "maps" service (run.sh) at the first start and then every month, into the
# "maps" volume. By hand on a host (needs the go-pmtiles CLI, "pmtiles"):
#   MAPS_DIR=/srv/fleet-maps ./update-map.sh        # default: this folder
# MAP_SOURCE: a PMTiles file or URL to extract from instead of the newest Protomaps daily build (a mirror).
# Free with no usage limits; the map data is OpenStreetMap (ODbL): the map shows the attribution.
set -eu
cd "${MAPS_DIR:-$(dirname "$0")}"

BBOX="${MAP_BBOX:-46.5,28.5,48.5,30.15}"   # Kuwait with a margin (west,south,east,north)
MAXZOOM="${MAP_MAXZOOM:-15}"               # street level; the map zooms further by scaling level 15

# daily builds are kept for a few days only: take the newest one available
url="${MAP_SOURCE:-}"
if [ -z "$url" ]; then
  now=$(date -u +%s)
  for back in 1 2 3 4 5 6 7; do
    # "-d @seconds": GNU and busybox (the image); "-r seconds": BSD / macOS
    day=$(date -u -d "@$((now - back * 86400))" +%Y%m%d 2>/dev/null || date -u -r "$((now - back * 86400))" +%Y%m%d)
    url="https://build.protomaps.com/$day.pmtiles"
    if pmtiles show "$url" >/dev/null 2>&1; then break; fi
    url=""
  done
  [ -n "$url" ] || { echo "no Protomaps build found in the last 7 days" >&2; exit 1; }
fi

echo "extracting Kuwait from $url"
rm -f kuwait.pmtiles.new
pmtiles extract "$url" kuwait.pmtiles.new --bbox="$BBOX" --maxzoom="$MAXZOOM"
pmtiles verify kuwait.pmtiles.new
size=$(wc -c < kuwait.pmtiles.new)
# a near-empty extract (a wrong MAP_BBOX, a broken build) never replaces a good map
if [ "$size" -lt "${MAP_MIN_BYTES:-5000000}" ]; then
  rm -f kuwait.pmtiles.new
  echo "extract too small ($size bytes): kept the current map" >&2
  exit 1
fi
mv kuwait.pmtiles.new kuwait.pmtiles       # atomic: requests in flight keep reading the old file
pmtiles show kuwait.pmtiles | head -20
