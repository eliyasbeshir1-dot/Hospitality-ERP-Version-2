#!/usr/bin/env bash
# M2-A verification driver: rebuild from empty through every earlier slice, then M2-A.
#
# Chaining rather than standing alone is deliberate. M2-A builds on M1's isolation
# predicate, exact money types and reason-code registry; a suite that assumed those were
# present would be testing a database nobody had proved.
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

# The interpreter is named differently per platform, and the harness must not assume the
# POSIX one. A standard Windows Python installs python.exe and no python3.exe, and the
# python3.exe usually on a Windows PATH is the zero-byte Microsoft Store alias, which runs
# nothing — tools/check_prerequisites.py already refuses that one by name. Resolving here
# means the documented Windows path runs these drivers rather than a hand-copied subset.
PY_BIN="${PYTHON:-}"
if [ -z "$PY_BIN" ]; then
    if command -v "$PY_BIN" >/dev/null 2>&1 && "$PY_BIN" -c "" >/dev/null 2>&1; then
        PY_BIN=python3
    elif command -v python >/dev/null 2>&1 && python -c "" >/dev/null 2>&1; then
        PY_BIN=python
    else
        echo "FAIL PREREQUISITE_ABSENT: no runnable "$PY_BIN" or python on PATH" >&2
        exit 1
    fi
fi
export PYTHON="$PY_BIN"


bash "$REPO/tests/m1d/run_verification.sh"

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
echo "=== 7. M2-A verification gates ==="
"$PY_BIN" "$REPO/tests/m2a/verify_m2a.py"
