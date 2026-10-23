#!/bin/sh
# The "maps" service of docker-compose: keeps kuwait.pmtiles present and fresh in the volume nginx serves (/srv/maps).
# At start: downloads it if it is missing or older than MAP_REFRESH_DAYS; then checks once a day. A failed download
# (no network, the build site down) never stops anything: the panel shows its fallback map with a note, the current
# file (if any) stays, and the next try comes after MAP_RETRY_HOURS. status.json, served at /maps/status.json, tells
# the panel what is going on (no secrets in it: times, a state and the last error line).
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
  # the error is one line of the tool's output: only plain characters, so the JSON stays valid
  err=$(printf '%s' "${3:-}" | tr -cd 'A-Za-z0-9 .,:;_/()=+-' | cut -c1-200)
  printf '{"state":"%s","file_updated_at":%s,"checked_at":"%s","next_try_at":"%s","error":"%s"}\n' \
    "$1" "$file_at" "$(iso "$(date -u +%s)")" "$(iso "$2")" "$err" > "$DIR/status.json.new"
  mv "$DIR/status.json.new" "$DIR/status.json"
}

due() {
  [ -s "$FILE" ] || return 0
  [ $(( $(date -u +%s) - $(mtime "$FILE") )) -ge $(( REFRESH_DAYS * 86400 )) ]
}

while :; do
  now=$(date -u +%s)
  if due; then
    status updating "$now"
    echo "map: downloading the Kuwait extract"
    if update-map.sh > /tmp/update.log 2>&1; then
      cat /tmp/update.log
      wait_s=$CHECK_SECONDS
      status ok "$(( $(date -u +%s) + wait_s ))"
    else
      cat /tmp/update.log >&2
      wait_s=$(( RETRY_HOURS * 3600 ))
      status failed "$(( $(date -u +%s) + wait_s ))" "$(grep -v '^ *$' /tmp/update.log | tail -n 1)"
      echo "map: download failed, next try in ${RETRY_HOURS}h (the panel shows its fallback map meanwhile)" >&2
    fi
  else
    wait_s=$CHECK_SECONDS
    status ok "$(( now + wait_s ))"
  fi
  sleep "$wait_s"
done
