#!/usr/bin/env bash
# OP-D — the order reaches the kitchen. Chains from OP-C, which chains the rest.
#
# OP-C made it possible to be seated; this gate is what happens next. The order matters for
# the usual reason and for one more: OP-C's own suite places orders through the guest
# routes, and it does so under the acceptance policy seeds/0009 sets here.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="${PYTHON:-python3}"
command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN=python
export PYTHON="$PY_BIN"

bash "$REPO/tests/opc/run_verification.sh"

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
echo "=== 21. OP-D verification gates ==="
"$PY_BIN" "$REPO/tests/opd/verify_opd.py"
