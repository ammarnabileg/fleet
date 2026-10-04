# ---- once, after the first start
docker compose exec -u postgres postgres pgbackrest --stanza=fleet stanza-create
docker compose exec -u postgres postgres pgbackrest --stanza=fleet check

# ---- schedule (cron on the host, or Coolify scheduled tasks)
# Fri 03:00 full, other days 03:00 differential
docker compose exec -u postgres postgres pgbackrest --stanza=fleet --type=full backup
docker compose exec -u postgres postgres pgbackrest --stanza=fleet --type=diff backup
# every 15 minutes: files (immutable, named by sha256); restic encrypts by default
# needs RESTIC_REPOSITORY, RESTIC_PASSWORD, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
restic backup /var/lib/docker/volumes/fleet_files/_data
# daily 05:00: retention
restic forget --keep-within 48h --keep-daily 30 --prune

# ---- monitoring every 5 minutes: alert if the lag exceeds 5 minutes or failed_count grows
docker compose exec postgres psql -U fleet_owner -d fleet -Atc \
  "SELECT extract(epoch FROM now() - last_archived_time)::int, failed_count FROM pg_stat_archiver"

# ---- restore onto a new server (runbook, section 15.4)
# 1) Docker + this repository + .env from the secrets store, empty volumes
# 2) database to a point in time, straight into the empty data volume
docker compose run --rm --no-deps --entrypoint sh postgres -c '
  chown postgres:postgres /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data &&
  gosu postgres pgbackrest --stanza=fleet --type=time --target="2026-11-15 10:00:00+03" --target-action=promote restore'
# 3) files: the first snapshot taken AT OR AFTER the target time (files are append-only)
restic snapshots
restic restore <snapshot-id> --target /restore
rsync -a /restore/var/lib/docker/volumes/fleet_files/_data/ /var/lib/docker/volumes/fleet_files/_data/
# 4) start, verify, then switch DNS
docker compose up -d
docker compose exec api python -m app.ops.verify_restore   # files exist + hashes match, ledger invariants, partitions
