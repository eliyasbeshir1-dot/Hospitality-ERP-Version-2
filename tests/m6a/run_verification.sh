#!/usr/bin/env bash
# M6-A — the built artifact, and nothing in it that can reset production. Chains from M5b,
# which chains the rest.
#
# It runs LAST for a reason beyond order: it builds the artifact out of the same compiled
# workspace M1-D produced, so a chain that reached here has already proved the thing being
# packaged. Packaging output nobody has verified is how a green build ships a broken one.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# AN INTERPRETER THAT EXISTS IS NOT AN INTERPRETER THAT RUNS.
#
# This asked `command -v python3` and took yes for an answer, then EXPORTED the result —
# so on Windows, where python3 resolves to the Microsoft Store alias in WindowsApps (a
# zero-byte stub that runs nothing), this driver poisoned every driver it chains. The
# chain died at the first migration with the Store's advertisement as its error message,
# and m1a's own correct probe never got to run because PYTHON was already set.
#
# Sixteen drivers carry the probe below. OP-B copied the weak form, OP-C copied OP-B and
# OP-D copied OP-C — the same inherited-misreading shape as F-OPD-8, in the scripts that
# run the checks rather than in the checks. Every candidate is RUN, not merely located.
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

bash "$REPO/tests/m5b/run_verification.sh"

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
export M1D_WORKSPACE="${M1D_WORKSPACE:-${TMPDIR:-/tmp}/m1d-workspace}"

echo
echo "=== 24. M6-A verification gates ==="
"$PY_BIN" "$REPO/tests/m6a/verify_m6a.py"
