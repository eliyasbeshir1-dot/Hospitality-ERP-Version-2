#!/usr/bin/env bash
# M6-B — a backup that was encrypted, read back, and put somewhere else. Chains from M6-A.
#
# After M6-A rather than beside it: the backup tool is one of the things the artifact must
# carry, so proving it works and proving it SHIPS are two claims and this is the second
# one's turn. It takes a real pg_dump of the live database, so it also wants a database
# that every earlier suite has finished with.
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

bash "$REPO/tests/m6a/run_verification.sh"

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
# The key is the suite's own if the environment has none. A backup key that defaults
# silently in PRODUCTION would be a defect; defaulting in a verification run whose archives
# are deleted at the end is the difference between a test that runs and one that needs a
# secret to be provisioned before anybody can run it.
export HOSPITALITY_BACKUP_KEY="${HOSPITALITY_BACKUP_KEY:-m6b-suite-key-not-a-production-secret}"

echo
echo "=== 25. M6-B verification gates ==="
"$PY_BIN" "$REPO/tests/m6b/verify_m6b.py"
