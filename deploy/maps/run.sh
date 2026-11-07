#!/bin/sh
# The "maps" service of docker-compose: keeps kuwait.pmtiles present and fresh in the volume nginx serves (/srv/maps).
# At start: downloads it if it is missing or older than MAP_REFRESH_DAYS; then checks once a day. A failed download
# (no network, the build site down) never stops anything: the panel shows its fallback map with a note, the current
# file (if any) stays, and the next try comes after MAP_RETRY_HOURS. status.json, served at /maps/status.json, tells
# the panel what is going on: times, a state and a fixed error code with its plain message, never the tool's output
# (a mirror URL in MAP_SOURCE may carry a token).
# Upgrading from the old host folder: a kuwait.pmtiles in MAPS_LEGACY_DIR (default /srv/fleet-maps, mounted at
# /legacy) is copied into the volume once, so the map shows at once and is refreshed from there.
set -u
DIR="${MAPS_DIR:-/srv/maps}"
FILE="$DIR/kuwait.pmtiles"
REFRESH_DAYS="${MAP_REFRESH_DAYS:-30}"
RETRY_HOURS="${MAP_RETRY_HOURS:-6}"
CHECK_SECONDS="${MAP_CHECK_SECONDS:-86400}"
mkdir -p "$DIR"

iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ; }
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }

# status <state> <next try (epoch)> [error]   state: updating | ok | failed
status() {
  file_at=null
  [ -s "$FILE" ] && file_at="\"$(iso "$(mtime "$FILE")")\""
  code=${3:-}
  case "$code" in
    tool_missing) msg="the pmtiles tool could not be downloaded from GitHub" ;;
    no_build) msg="no Protomaps build found in the last 7 days" ;;
    download_failed) msg="the download of the map extract failed" ;;
    verify_failed) msg="the downloaded map file is damaged" ;;
    too_small) msg="the downloaded map file is too small, the current one was kept" ;;
    "") msg="" ;;
    *) code=failed; msg="the map update failed" ;;
  esac
  mkdir -p "$DIR/.work"
  printf '{"state":"%s","file_updated_at":%s,"checked_at":"%s","next_try_at":"%s","error_code":"%s","error":"%s"}\n' \
    "$1" "$file_at" "$(iso "$(date -u +%s)")" "$(iso "$2")" "$code" "$msg" > "$DIR/.work/status.json"
  mv "$DIR/.work/status.json" "$DIR/status.json"
}

# the tool's output in the service log, with any credentials or query string of a URL removed
clean() { sed -e 's|\([a-z]*://\)[^/@ ]*@|\1|g' -e 's|[?#][^ ,"]*||g'; }

due() {
  [ -s "$FILE" ] || return 0
  [ $(( $(date -u +%s) - $(mtime "$FILE") )) -ge $(( REFRESH_DAYS * 86400 )) ]
}

if [ ! -s "$FILE" ] && [ -s /legacy/kuwait.pmtiles ]; then
  echo "map: copying the map from the old host folder"
  mkdir -p "$DIR/.work" && cp /legacy/kuwait.pmtiles "$DIR/.work/kuwait.pmtiles.new" \
    && touch -r /legacy/kuwait.pmtiles "$DIR/.work/kuwait.pmtiles.new" && mv "$DIR/.work/kuwait.pmtiles.new" "$FILE"
fi

while :; do
  now=$(date -u +%s)
  if due; then
    status updating "$now"
    echo "map: downloading the Kuwait extract"
    if ! get-pmtiles.sh > /tmp/update.log 2>&1; then
      rc=tool
    elif update-map.sh >> /tmp/update.log 2>&1; then
      rc=0
    else
      rc=$?
    fi
    if [ "$rc" = 0 ]; then
      clean < /tmp/update.log
      wait_s=$CHECK_SECONDS
      status ok "$(( $(date -u +%s) + wait_s ))"
    else
      clean < /tmp/update.log >&2
      wait_s=$(( RETRY_HOURS * 3600 ))
      case "$rc" in tool) c=tool_missing ;; 2) c=no_build ;; 3) c=download_failed ;; 4) c=verify_failed ;; 5) c=too_small ;; *) c=failed ;; esac
      status failed "$(( $(date -u +%s) + wait_s ))" "$c"
      echo "map: download failed, next try in ${RETRY_HOURS}h (the panel shows its fallback map meanwhile)" >&2
    fi
  else
    wait_s=$CHECK_SECONDS
    status ok "$(( now + wait_s ))"
  fi
  sleep "$wait_s"
done
