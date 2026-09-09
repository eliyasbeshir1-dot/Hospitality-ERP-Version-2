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
    # The database NAME is passed, not assumed. bootstrap_database.sql grants CONNECT
    # and CREATE on a named database and used to name hospitality_os literally, so a
    # DB override created one database and granted on another — silently, whenever
    # hospitality_os happened to exist. It now refuses rather than guesses.
    psql "$M1A_ADMIN_DSN" -v ON_ERROR_STOP=1 -q -v db_name="$DB" \n      -f "$REPO/tools/bootstrap_database.sql"
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
# THE NODE THIS FLOOR RUNS AS, read from the database rather than typed here.
#
# M5a binds a continuity node to exactly one outlet and refuses to start anywhere else, so
# the fingerprint below is not a constant this script may choose — it is whatever
# seeds/0012 registered. Reading it means a floor that cannot start is a floor whose node
# is genuinely wrong, rather than one whose script fell out of step with its seed.
NODE_CODE="$(psql "$M1A_ADMIN_DSN" -tAc \
  "SELECT node_code FROM edge.node
    WHERE tenant_id = '$TENANT' AND outlet_id = '$OUTLET' AND status = 'active';")"
NODE_FINGERPRINT="$(psql "$M1A_ADMIN_DSN" -tAc \
  "SELECT identity_fingerprint FROM edge.node
    WHERE tenant_id = '$TENANT' AND outlet_id = '$OUTLET' AND status = 'active';")"
if [ -z "$NODE_CODE" ]; then
    echo "FAIL FLOOR_HAS_NO_NODE: no active continuity node is registered at $OUTLET." >&2
    echo "  seeds/0012 registers one. Without it the floor would serve the CLOUD profile," >&2
    echo "  and every M5a screen would be missing rather than empty." >&2
    exit 1
fi

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

  THE OUTLET RUNS ITS OWN NODE NOW (M5a)
    This floor is served BY the continuity node ${NODE_CODE}, not by a
    cloud pretending to be one. Three of its five services are running:
    the local API you are talking to, the synchronization worker and the
    realtime gateway. The print agent runs on demand and PostgreSQL is
    the fifth.

    CUT THE INTERNET by creating one file, and restore it by deleting
    it. The worker reads it every round, so the banner follows within a
    couple of seconds and there is no process to find:

      cut      : touch ${EDGE_UPLINK_CUT_FILE}
      restore  : rm -f ${EDGE_UPLINK_CUT_FILE}

    What you should see:
      - a strip at the top of EVERY screen saying the outlet is working
        offline and that service continues. It is not a modal and blocks
        nothing; that is FR-EDG-009's own wording.
      - ordering, the kitchen, bills, tips, cash and printing all still
        work. Card AUTHORISATION does not, and says why in the language
        the screen is in.
    Restore it and the strip disappears, because a banner that is always
    visible is a banner nobody reads.

    THE OPERATOR'S OWN SCREENS, if you want to look underneath:
      /n/v1/connectivity   what the room is told (no sign-in needed)
      /n/v1/readiness      the eleven things a node must hold. THREE ARE
                           MISSING on this floor and that is honest:
                           allergens, taxes and printers live in
                           fixture-owned catalogues, never in seeds.
      /n/v1/sync-states    the five states, in plain language
      /n/v1/print-queue    the durable queue and every printer's health
      /n/v1/estate         the six device classes FR-OPS-018 names

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
# THE NODE'S OTHER SERVICES, beside the API.
#
# FR-EDG-002A names five. PostgreSQL is already running, the print agent runs on demand
# through print/queue_runner.py, and these two run for as long as the floor does. Without
# the worker the connectivity strip would never move — cutting the link would change
# nothing anybody can see, which is the same "provable and unusable" gap this script
# exists to close.
#
# NOT `exec` ANY MORE. exec replaces this shell and a trap set before it does not survive,
# so the worker and the gateway would outlive Ctrl-C as orphans holding connections. The
# API runs in the foreground instead and the trap cleans up after it.
NODE_LOGS="${TMPDIR:-/tmp}/floor-node-logs"
# The switch an operator flips to cut the internet. The worker reads it every round.
export EDGE_UPLINK_CUT_FILE="${EDGE_UPLINK_CUT_FILE:-${TMPDIR:-/tmp}/edge-uplink-cut}"
rm -f "$EDGE_UPLINK_CUT_FILE"
mkdir -p "$NODE_LOGS"

SYNC_PID=""
GATEWAY_PID=""
stop_the_node_services() {
    [ -n "$SYNC_PID" ] && kill "$SYNC_PID" 2>/dev/null
    [ -n "$GATEWAY_PID" ] && kill "$GATEWAY_PID" 2>/dev/null
    return 0
}
trap stop_the_node_services EXIT INT TERM

DATABASE_URL="$M1A_APP_DSN" \
NODE_CODE="$NODE_CODE" NODE_TENANT_ID="$TENANT" NODE_OUTLET_ID="$OUTLET" \
NODE_FINGERPRINT="$NODE_FINGERPRINT" \
node "$WORKSPACE/dist/node/sync-worker.js" >"$NODE_LOGS/sync-worker.log" 2>&1 &
SYNC_PID=$!

DATABASE_URL="$M1A_APP_DSN" \
NODE_CODE="$NODE_CODE" NODE_TENANT_ID="$TENANT" NODE_OUTLET_ID="$OUTLET" \
NODE_FINGERPRINT="$NODE_FINGERPRINT" REALTIME_PORT="${REALTIME_PORT:-7102}" \
node "$WORKSPACE/dist/node/realtime-gateway.js" >"$NODE_LOGS/realtime-gateway.log" 2>&1 &
GATEWAY_PID=$!

# The service refuses to start without these, by design — REQUIRED_ENVIRONMENT_ABSENT is
# M1-D's readiness gate. NODE_CODE is what turns this from the cloud into the outlet's own
# node: api/src/node/identity.ts proves the binding against edge.node BEFORE the listener
# opens, so a wrong outlet id here is a refusal rather than a floor serving the wrong room.
DATABASE_URL="$M1A_APP_DSN" \
ENVIRONMENT_NAME="${ENVIRONMENT_NAME:-demonstration}" \
NODE_CODE="$NODE_CODE" NODE_TENANT_ID="$TENANT" NODE_OUTLET_ID="$OUTLET" \
NODE_FINGERPRINT="$NODE_FINGERPRINT" \
PORT="$PORT" node "$WORKSPACE/dist/server.js"
