#!/usr/bin/env bash
# M3-D verification driver: rebuild from empty through every earlier slice, then M3-D.
#
# Chains for the same reason every slice before it does, and for one more of its own. A
# waiter surface is the last thing in this system to be built and the first that needs
# everything: a menu from M2-A, a seated guest from M2-B, a language from M2-C, an order
# from M3-A, a kitchen from M3-B and a service request from M3-C. A suite that started
# here would be handing tables to waiters in a restaurant nobody had proved.
#
# The five golden journeys are NOT run from here. They are a separate suite with a
# separate driver, because they walk M1 through M3-C rather than this slice, and because
# "a journey failed" and "an M3-D check failed" must be distinguishable without reading
# a log.
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

bash "$REPO/tests/m3c/run_verification.sh"

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
echo "=== 13. M3-D verification gates ==="
"$PY_BIN" "$REPO/tests/m3d/verify_m3d.py"
