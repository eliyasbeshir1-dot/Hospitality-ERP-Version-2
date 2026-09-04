#!/usr/bin/env bash
# M4-C verification driver: rebuild from empty through every earlier slice, then M4-C.
#
# Chains for the reason every slice before it does. A receipt is a claim about a
# settlement, which is a claim about a payment, which is a claim about a bill, a check, an
# accepted order and a seated guest reading a priced menu in a language they chose. A
# suite that started here would be printing paper for a restaurant nobody had proved
# exists — and paper is the one artefact a customer takes away.
#
# The golden journeys are NOT run from here, for the reason M3-D's driver records:
# "a journey failed" and "an M4-C check failed" must be distinguishable without reading a
# log.
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

bash "$REPO/tests/m4b/run_verification.sh"

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
echo "=== 16. M4-C verification gates ==="
"$PY_BIN" "$REPO/tests/m4c/verify_m4c.py"
