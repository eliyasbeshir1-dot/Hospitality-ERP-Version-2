#!/usr/bin/env bash
# OP-C — being seated. Chains from OP-B, which chains the whole history beneath it.
#
# The order matters for the same reason it did at OP-B, and for one more. This gate proves
# the step that comes BEFORE everything the earlier slices built, so everything they built
# has to exist first — and OP-A's own order helper now seats through the route this gate
# adds, which means the chain below is not merely running in front of this suite, it is
# exercising the thing this suite is about.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="${PYTHON:-python3}"
command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN=python
export PYTHON="$PY_BIN"

bash "$REPO/tests/opb/run_verification.sh"

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
echo "=== 20. OP-C verification gates ==="
"$PY_BIN" "$REPO/tests/opc/verify_opc.py"
