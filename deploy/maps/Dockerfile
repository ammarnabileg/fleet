# The map service (docker-compose "maps"): keeps the Kuwait base map file present and fresh in the volume nginx serves
# from. The go-pmtiles CLI is the pinned release binary, checked against its sha256 (get-pmtiles.sh). Nothing in this
# build can fail on the network: if GitHub is not reachable now, the service fetches the tool itself when it starts,
# and until then reports "tool_missing" in status.json (the panel shows its fallback map).
FROM alpine:3.22
COPY get-pmtiles.sh update-map.sh run.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/get-pmtiles.sh /usr/local/bin/update-map.sh /usr/local/bin/run.sh \
    && mkdir -p /srv/maps \
    && (get-pmtiles.sh || echo "pmtiles not downloaded now: the service tries again when it starts")
ENV MAPS_DIR=/srv/maps
CMD ["run.sh"]
