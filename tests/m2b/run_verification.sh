#!/usr/bin/env bash
# M2-B verification driver: rebuild from empty through every earlier slice, then M2-B.
#
# Chaining rather than standing alone is deliberate. M2-B builds on M1's isolation
# predicate, exact money types, reason-code registry and retention engine, and on M2-A's
# menu, translation approval workflow and publication snapshot. An allergen declaration is
# a statement about an item, so a suite that assumed the item was there would be testing a
# database nobody had proved.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The interpreter is named differently per platform, and the harness must not assume the
# POSIX one. A standard Windows Python installs python.exe and no python3.exe, and the
# python3.exe usually on a Windows PATH is the zero-byte Microsoft Store alias, which runs
# nothing — tools/check_prerequisites.py already refuses that one by name. Resolving it
# here means the documented Windows path runs these drivers rather than a hand-copied
# subset of what they do.
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

bash "$REPO/tests/m2a/run_verification.sh"

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
echo "=== 8. M2-B verification gates ==="
"$PY_BIN" "$REPO/tests/m2b/verify_m2b.py"
