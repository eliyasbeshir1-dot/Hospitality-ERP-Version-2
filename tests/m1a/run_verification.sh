#!/usr/bin/env bash
# M1-A verification driver.
#
# Rebuilds the database from empty on every run, so the result is reproducible and
# "applies to an empty database" is proved rather than assumed (FR-DAT-001).
#
# Requires a running PostgreSQL and a superuser DSN in PGADMIN_DSN. Everything the
# gates assert is then done through the least-privileged application role.

set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1   # never write __pycache__ into the tree

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PGHOST_DIR="${PGHOST_DIR:-/var/lib/m1apg/run}"
PGPORT="${PGPORT:-5433}"
SUPERUSER="${SUPERUSER:-pgadmin}"
DB="${DB:-hospitality_os}"

dsn() { echo "postgresql://$1@/$2?host=$PGHOST_DIR&port=$PGPORT"; }

ADMIN_POSTGRES="$(dsn "$SUPERUSER" postgres)"
export M1A_ADMIN_DSN="$(dsn "$SUPERUSER" "$DB")"
export M1A_MIGRATOR_DSN="$(dsn hospitality_migrator "$DB")"
export M1A_APP_DSN="$(dsn hospitality_app "$DB")"
export M1A_PRIVILEGED_DSN="$(dsn hospitality_bypassrls "$DB")"

echo "=== 0. Rebuild the database from empty ==="
psql "$ADMIN_POSTGRES" -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS $DB WITH (FORCE);" \
  -c "CREATE DATABASE $DB;"

psql "$ADMIN_POSTGRES" -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
    -- The runtime identity used by the NC-M1-004 negative control: privileged on
    -- purpose, so the readiness gate has something real to reject.
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hospitality_bypassrls') THEN
        CREATE ROLE hospitality_bypassrls LOGIN BYPASSRLS NOSUPERUSER
            PASSWORD 'bypass_local_only';
    END IF;
END;
$$;
SQL

psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q -f "$REPO/tools/bootstrap_database.sql"
psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q \
  -c "GRANT CONNECT ON DATABASE $DB TO hospitality_bypassrls;"
echo "database recreated; roles provisioned"

echo
echo "=== 1. Apply the migration history to the empty database ==="
python3 "$REPO/tools/migrate.py" --dsn "$M1A_MIGRATOR_DSN" --migrations "$REPO/migrations" apply

psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q \
  -c "GRANT USAGE ON SCHEMA org, app TO hospitality_bypassrls;" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA org TO hospitality_bypassrls;"

echo
echo "=== 2. Seed populated fixtures through the application role ==="
psql "$M1A_APP_DSN" -v ON_ERROR_STOP=1 -q -o /dev/null -f "$REPO/tests/m1a/fixtures.sql"
echo "fixtures seeded (two tenants, two sibling outlets, depth 3)"

echo
echo "=== 3. Verification gates ==="
python3 "$REPO/tests/m1a/verify_m1a.py"
