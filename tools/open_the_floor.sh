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
# AN INTERPRETER THAT EXISTS IS NOT AN INTERPRETER THAT RUNS.
#
# This asked `command -v python3` and took yes for an answer. On Windows that resolves to
# the Microsoft Store alias in WindowsApps — a zero-byte stub that prints "Python was not
# found" and exits non-zero — so the check passed, the fallback to `python` never fired,
# and the rebuild died on the migration step with the Store's advertisement as its error
# message.
#
# tests/*/run_verification.sh met this at the cross-platform gate and was repaired then;
# docs-local/CROSS_PLATFORM_COMMANDS.md records it by name as one of the seven defects
# Linux could not expose. This script kept the weaker check, so the one entry point a
# person actually types was the one place the repair never reached.
#
# The probe below is the drivers' own: every candidate is RUN, not merely located.
PY_BIN="${PYTHON:-}"
if [ -z "$PY_BIN" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
            PY_BIN="$candidate"
            break
        fi
    done
fi
if [ -z "$PY_BIN" ]; then
    echo "FAIL PREREQUISITE_ABSENT: no runnable Python on PATH. On Windows the python3 in" >&2
    echo "  WindowsApps is the Microsoft Store alias and runs nothing; install Python or" >&2
    echo "  set PYTHON to an interpreter that does." >&2
    exit 1
fi
export PYTHON="$PY_BIN"

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
      sign in on the page itself; the screen fetches the floor, and
      seats a free table from the list below the occupied ones

  A GUEST AT TABLE 11        http://127.0.0.1:${PORT}/?t=${TENANT}&o=${OUTLET}&c=${QR}
      scan-equivalent link: opening it SEATS you, because the table is
      empty and the scan is the seating act. Order from the
      three-language menu, take something back out of the basket, and
      the ticket appears on the station board above

  WHAT WORKS AND WHAT DOES NOT, so nothing here surprises you:
    - a guest can seat themselves by opening the link, or a waiter can
      seat the table first; either way the same occupancy is opened.
      A waiter who seats it becomes accountable for it; a guest who
      seats themselves leaves the table reading "no waiter is
      accountable", which is the floor screen telling the truth.
    - a guest can order and the kitchen has it IMMEDIATELY: this floor
      accepts QR orders automatically (seeds/0009), so the ticket
      appears on the station board without anybody confirming it. An
      outlet that chooses staff confirmation instead gets a "Waiting to
      be confirmed" list at the top of the waiter floor, and the guest
      is told their order is waiting rather than that the kitchen has
      it. Both paths are real; this floor is on the first.
    - the kitchen can cook it; the till can bill it, split it, take
      cash, a card, Telebirr or CBE Birr, and settle it.
    - the menu says what a dish IS — description, ingredients and how
      long it takes — and not only what it costs. There are no IMAGES:
      menu.image is private by constraint and reachable only through a
      signed URL path that this build does not have, so seeding one
      would give the surface a key it cannot render. F-OPD-3.
    - anyone holding this link can seat themselves at table 11 from
      anywhere, including before you sit down at it. That is F-OPC-3 in
      planning/OPC_FINDINGS.md: a placard is a long-lived secret and
      nothing tests how fresh a scan is. On a demonstration floor it
      costs nothing; in a restaurant it is a stranger reading, adding
      to and being paid for on your table's session.
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
