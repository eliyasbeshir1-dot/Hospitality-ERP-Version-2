#!/usr/bin/env bash
# M1-D verification driver: rebuild from empty, apply seeds through the runner, then run
# all four slices in order.
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


bash "$REPO/tests/m1c/run_verification.sh"

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
export M1A_PRIVILEGED_DSN="$(dsn hospitality_bypassrls "$DB")"

echo
echo "=== 6. Seed provenance recorded by the seed runner ==="
"$PY_BIN" "$REPO/tools/seed.py" --dsn "$M1A_MIGRATOR_DSN" --content-dsn "$M1A_APP_DSN" \
        --seeds "$REPO/seeds" apply

echo
echo "=== 7. M1-D verification gates ==="
"$PY_BIN" "$REPO/tests/m1d/verify_m1d.py"
