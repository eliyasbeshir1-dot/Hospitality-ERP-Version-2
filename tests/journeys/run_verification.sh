#!/usr/bin/env bash
# Golden journey driver: rebuild from empty through every slice, then walk the journeys.
#
# Runs AFTER the slice suites — the M4-B driver, which chains the whole history beneath
# it — and reports its own outcome whether or not one of them failed. If a slice check and a journey fail together that is one signal; if only the
# journey fails that is a different and more interesting one, and a driver that stopped
# at the first slice failure would hide the second case entirely.
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
    exit 1
fi
export PYTHON="$PY_BIN"

slice_status=0
bash "$REPO/tests/m4c/run_verification.sh" || slice_status=$?

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
echo "=== 16. The five golden journeys ==="
journey_status=0
"$PY_BIN" "$REPO/tests/journeys/verify_journeys.py" || journey_status=$?

if [ "$slice_status" -ne 0 ]; then
    echo "NOTE: a slice suite failed before the journeys ran; both outcomes are above." >&2
fi
exit $(( slice_status != 0 || journey_status != 0 ))
