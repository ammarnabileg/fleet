#!/bin/bash
# First start only (an empty data volume): the application's least-privilege login. Its grants come from the
# migrations (public.fleet_apply_grants). Changing the password later: ALTER ROLE fleet_app PASSWORD '...' and the
# same value in FLEET_APP_DB_PASSWORD.
set -euo pipefail
if [ -z "${FLEET_APP_DB_PASSWORD:-}" ]; then
  echo "FLEET_APP_DB_PASSWORD is empty: fleet_app is not created" >&2
  exit 1
fi
# the password goes through a psql variable (quoted by psql), never pasted into the SQL text
psql -v ON_ERROR_STOP=1 -v pw="$FLEET_APP_DB_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE fleet_app LOGIN PASSWORD :'pw';
GRANT CONNECT ON DATABASE fleet TO fleet_app;
SQL
