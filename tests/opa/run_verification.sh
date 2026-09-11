#!/usr/bin/env bash
# OP-A verification driver: rebuild from empty through every slice, then OP-A.
#
# Chains from M4-C for the reason every driver chains: this gate proves that a PERSON can
# reach behaviour earlier slices built, and a suite that started here would be asserting
# that a route works against a database nobody had proved.
#
# THE SEEDS ARE APPLIED BEFORE THE SUITE RUNS, and that is not incidental. OP-A's subject
# is product data — a menu, a floor, staff who can log in — so a run against fixtures
# alone would prove the routes work on rows the tests wrote, which is the one thing this
# gate exists to stop being sufficient. The M1-D driver beneath this one applies them
# through tools/seed.py; this driver checks they arrived rather than assuming it.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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
    echo "FAIL PREREQUISITE_ABSENT: no runnable interpreter on PATH" >&2
    echo "  tried python3 then python; a name on PATH that cannot run is not a tool" >&2
    exit 1
fi
export PYTHON="$PY_BIN"

bash "$REPO/tests/m4c/run_verification.sh"

PGHOST_DIR="${PGHOST_DIR:-/var/lib/m1apg/run}"
PGPORT="${PGPORT:-5433}"
SUPERUSER="${SUPERUSER:-pgadmin}"
DB="${DB:-hospitality_os}"
dsn() {
    if [ -n "${PGTCP_HOST:-}" ]; then echo "postgresql://$1@$PGTCP_HOST:$PGPORT/$2"
    else echo "postgresql://$1@/$2?host=$PGHOST_DIR&port=$PGPORT"; fi
}
export M1A_ADMIN_DSN="$(dsn "$SUPERUSER" "$DB")"
export M1A_APP_DSN="$(dsn hospitality_app "$DB")"
export M1A_MIGRATOR_DSN="$(dsn hospitality_migrator "$DB")"

echo
echo "=== 18. OP-A verification gates ==="
"$PY_BIN" "$REPO/tests/opa/verify_opa.py"
