#!/usr/bin/env bash
# Deployment entrypoint. NOT gate work — this file exists only on deploy/railway.
#
# Ordered so that each step runs under the identity that step is entitled to:
#
#   SUPER_URL      creates the two roles, once, and sets their passwords. Present
#                  only on the first deployment; removed afterwards so the running
#                  service cannot reach a superuser credential at all.
#   MIGRATOR_URL   applies migrations and seeds. Never used at runtime.
#   DATABASE_URL   the app identity, and the only one the server is given.
#
# Nothing here relaxes FR-OPS-001. The server decides for itself whether the
# identity in DATABASE_URL may run, and this script has no say in it.
set -euo pipefail
cd /src

if [ -n "${SUPER_URL:-}" ]; then
  echo "=== 1. roles, from the repository's own tools/bootstrap_database.sql ==="
  psql "$SUPER_URL" -v ON_ERROR_STOP=1 -f tools/bootstrap_database.sql
  echo "=== 2. authentication, from the deployment secret store, never from the file ==="
  psql "$SUPER_URL" -v ON_ERROR_STOP=1 \
    -v mp="$MIGRATOR_PW" -v ap="$APP_PW" \
    -c "ALTER ROLE hospitality_migrator PASSWORD :'mp'" \
    -c "ALTER ROLE hospitality_app PASSWORD :'ap'"
  echo "=== 3. role attributes as the managed cluster holds them ==="
  psql "$SUPER_URL" -v ON_ERROR_STOP=1 -c \
    "SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolcanlogin
       FROM pg_roles WHERE rolname LIKE 'hospitality%' ORDER BY rolname"
else
  echo "=== 1-3. skipped: no superuser credential in this deployment, by design ==="
fi

echo "=== 4. migrations, as the migrator ==="
python3 tools/migrate.py --dsn "$MIGRATOR_URL" --migrations migrations apply

echo "=== 5. seeds ==="
python3 tools/seed.py --dsn "$MIGRATOR_URL" --content-dsn "$DATABASE_URL" --seeds seeds apply

echo "=== 6. the identity the server is about to be handed ==="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "SELECT current_user, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb
     FROM pg_roles r WHERE r.rolname = current_user"

echo "=== 7. starting the service; FR-OPS-001 now decides ==="
exec node /workspace/dist/server.js
