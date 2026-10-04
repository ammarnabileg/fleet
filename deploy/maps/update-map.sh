#!/bin/sh
# The admin panel's base map: the Kuwait extract of the OpenStreetMap base map from the Protomaps daily build,
# one PMTiles file (~tens of MB) that nginx serves (docker-compose mounts MAPS_DIR at /srv/maps).
#   MAPS_DIR=/srv/fleet-maps ./update-map.sh        # same MAPS_DIR as in .env; default: this folder
# Run at install, then monthly (cron). Needs the go-pmtiles CLI on the host:
#   https://github.com/protomaps/go-pmtiles/releases   (one static binary, "pmtiles")
# Free with no usage limits; the map data is OpenStreetMap (ODbL): the map shows the attribution.
set -eu
cd "${MAPS_DIR:-$(dirname "$0")}"

BBOX="${MAP_BBOX:-46.5,28.5,48.5,30.15}"   # Kuwait with a margin (west,south,east,north)
MAXZOOM="${MAP_MAXZOOM:-15}"               # street level; the map zooms further by scaling level 15

# daily builds are kept for a few days only: take the newest one available
for back in 1 2 3 4 5 6 7; do
  day=$(date -u -d "-$back day" +%Y%m%d 2>/dev/null || date -u -v-"$back"d +%Y%m%d)
  url="https://build.protomaps.com/$day.pmtiles"
  if pmtiles show "$url" >/dev/null 2>&1; then break; fi
  url=""
done
[ -n "$url" ] || { echo "no Protomaps build found in the last 7 days" >&2; exit 1; }

echo "extracting Kuwait from $url"
pmtiles extract "$url" kuwait.pmtiles.new --bbox="$BBOX" --maxzoom="$MAXZOOM"
pmtiles verify kuwait.pmtiles.new
mv kuwait.pmtiles.new kuwait.pmtiles       # atomic: requests in flight keep reading the old file
pmtiles show kuwait.pmtiles | head -20
