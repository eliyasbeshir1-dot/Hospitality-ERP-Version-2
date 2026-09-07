#!/usr/bin/env bash
#
# Open the demonstration floor: the station board, the till and the waiter screen, in a
# browser on this machine.
#
# WHY THIS EXISTS. Every gate so far has been provable and unusable at the same time. A
# suite reporting PASS is a claim about the system; a person opening the till and taking
# money is the system. This script is the shortest path from a clean checkout to the
# second thing.
#
# It builds nothing you cannot see: the database is rebuilt from the migration history,
# the demonstration floor is applied by the seed runner with its own provenance, the
# service is built from source, and then it tells you where to go and who to sign in as.
#
#     bash tools/open_the_floor.sh              # rebuild everything and serve
#     bash tools/open_the_floor.sh --keep       # serve what is already there
#
# The credentials it prints are demonstration credentials and are published in
# seeds/0003's header for the same reason: they are not secrets and must never be mistaken
# for any.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

: "${PGTCP_HOST:=localhost}"
: "${PGPORT:=5434}"
: "${SUPERUSER:=postgres}"
: "${DB:=hospitality_os}"
: "${PORT:=8080}"
PY_BIN="${PYTHON:-python3}"
command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN=python

dsn() { echo "postgresql://$1@$PGTCP_HOST:$PGPORT/$2"; }
export M1A_ADMIN_DSN="$(dsn "$SUPERUSER" "$DB")"
export M1A_APP_DSN="$(dsn hospitality_app "$DB")"
export M1A_MIGRATOR_DSN="$(dsn hospitality_migrator "$DB")"

if [ "$KEEP" -eq 0 ]; then
    echo "==> rebuilding the database from empty"
    psql "$(dsn "$SUPERUSER" postgres)" -v ON_ERROR_STOP=1 -q \
      -c "DROP DATABASE IF EXISTS $DB WITH (FORCE);" -c "CREATE DATABASE $DB;"
    psql "$(dsn "$SUPERUSER" postgres)" -v ON_ERROR_STOP=1 -q <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hospitality_bypassrls') THEN
        CREATE ROLE hospitality_bypassrls LOGIN BYPASSRLS NOSUPERUSER;
    END IF;
END;
$$;
SQL
    psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q -f "$REPO/tools/bootstrap_database.sql"
    psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q \
      -c "GRANT CONNECT ON DATABASE $DB TO hospitality_bypassrls;"

    echo "==> applying the migration history"
    "$PY_BIN" "$REPO/tools/migrate.py" --dsn "$M1A_MIGRATOR_DSN" \
      --migrations "$REPO/migrations" apply | tail -3

    psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q \
      -c "GRANT USAGE ON SCHEMA org, app TO hospitality_bypassrls;" \
      -c "GRANT SELECT ON ALL TABLES IN SCHEMA org TO hospitality_bypassrls;"

    echo "==> seeding the demonstration floor"
    "$PY_BIN" "$REPO/tools/seed.py" apply --dsn "$M1A_MIGRATOR_DSN" \
      --content-dsn "$M1A_APP_DSN" | tail -4
fi

echo "==> building the service and the four surfaces"
bash "$REPO/api/build.sh" | tail -1

TENANT="33333333-3333-3333-3333-333333333333"
OUTLET="33330002-0000-4000-8000-000000000002"
STATION="33334101-0000-4000-8000-000000000001"

# The QR token a guest would scan off the table, minted now so there is a link to click
# rather than a placard to photograph.
QR="$(psql "$M1A_ADMIN_DSN" -tAc \
  "SELECT service.issue_table_qr('$TENANT'::uuid,
                                 '33335101-0000-4000-8000-000000000001'::uuid,
                                 '3333aaaa-0000-4000-8000-000000000001'::uuid);")"

cat <<INFO

======================================================================
  The demonstration floor is Habesha Kitchens, Sarbet.
  Serving on http://127.0.0.1:${PORT}
======================================================================

  THE STATION BOARD          http://127.0.0.1:${PORT}/station
      sign in with           kitchen@habesha.example / Habesha!Cook1
      tenant                 ${TENANT}
      outlet                 ${OUTLET}
      station                ${STATION}

  THE TILL                   http://127.0.0.1:${PORT}/cashier
      sign in with           manager@habesha.example / Habesha!Manager1
      tenant                 ${TENANT}
      outlet                 ${OUTLET}

  THE WAITER FLOOR           http://127.0.0.1:${PORT}/waiter
      same manager sign-in; the screen fetches the floor itself

  A GUEST AT TABLE 11        http://127.0.0.1:${PORT}/?t=${TENANT}&o=${OUTLET}&c=${QR}
      scan-equivalent link: order from the three-language menu, and the
      ticket appears on the station board above

  WHAT WORKS AND WHAT DOES NOT, so nothing here surprises you:
    - a guest can order; the kitchen can cook it; the till can bill it,
      split it, take cash, a card, Telebirr or CBE Birr, and settle it.
    - a RECEIPT cannot be produced on this floor. Receipt wording lives
      in two tenant-unique catalogues that only the test fixtures have
      ever written, so product data cannot compose one. That is
      F-OPB-3 in planning/OPB_FINDINGS.md, and it is a product
      decision rather than a seeding one.
    - an ALLERGY cannot be declared on this floor, for the same reason:
      the allergen catalogue is tenant-unique and fixture-owned.

  Ctrl-C to stop.

INFO

# The same workspace api/build.sh writes to, resolved the same way it resolves it — the
# build lives outside the repository because tools/verify_m1.py treats dist/ as forbidden
# surface and checks the filesystem rather than the Git index.
WORKSPACE="${M1D_WORKSPACE:-/var/lib/m1d-workspace}"

# The service refuses to start without these, by design — REQUIRED_ENVIRONMENT_ABSENT is
# M1-D's readiness gate, and it is the reason this script sets them explicitly rather than
# hoping the shell already has them. It runs as the APPLICATION role, not the migrator or
# the superuser, so the floor a founder clicks around is behind the same row level
# security every suite runs against.
DATABASE_URL="$M1A_APP_DSN" \
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-demonstration}" \
PORT="$PORT" exec node "$WORKSPACE/dist/server.js"
