FROM postgres:16-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends pgbackrest \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/spool/pgbackrest /var/log/pgbackrest \
 && chown -R postgres:postgres /var/spool/pgbackrest /var/log/pgbackrest
# baked in, not mounted: a deploy platform that keeps only the compose file (Coolify) has no repository files to mount
COPY pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
COPY initdb/ /docker-entrypoint-initdb.d/
