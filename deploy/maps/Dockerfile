# The map service (docker-compose "maps"): keeps the Kuwait base map file present and fresh in the volume nginx serves
# from. go-pmtiles is built from its source at a pinned version: the Go toolchain checks every module against the public
# checksum database, and the build stops unless the tool's own source has the checksum written here.
FROM golang:1.25-alpine AS build
ARG PMTILES_VERSION=v1.31.2
ARG PMTILES_SUM=h1:xYXagv2oKJarheCdOIGg8MvYRp8Y03MBs9jegxf4NDQ=
ENV CGO_ENABLED=0 GOFLAGS=-trimpath
RUN set -e; \
    got=$(go mod download -json "github.com/protomaps/go-pmtiles@${PMTILES_VERSION}" | sed -n 's/.*"Sum": "\(.*\)".*/\1/p'); \
    if [ "$got" != "$PMTILES_SUM" ]; then echo "go-pmtiles ${PMTILES_VERSION}: checksum $got, expected $PMTILES_SUM" >&2; exit 1; fi; \
    go install -ldflags="-s -w" "github.com/protomaps/go-pmtiles@${PMTILES_VERSION}"; \
    /go/bin/go-pmtiles version

FROM alpine:3.22
COPY --from=build /go/bin/go-pmtiles /usr/local/bin/pmtiles
COPY update-map.sh run.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/update-map.sh /usr/local/bin/run.sh && mkdir -p /srv/maps
ENV MAPS_DIR=/srv/maps
CMD ["run.sh"]
