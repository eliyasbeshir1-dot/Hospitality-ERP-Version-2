#!/usr/bin/env bash
# M1-B verification driver: rebuild from empty, then run both slices in order.
#
# M1-A must stay green — M1-B binds directly to the isolation it proved, so a
# regression there invalidates this slice's results too.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

bash "$REPO/tests/m1a/run_verification.sh"

PGHOST_DIR="${PGHOST_DIR:-/var/lib/m1apg/run}"
PGPORT="${PGPORT:-5433}"
SUPERUSER="${SUPERUSER:-pgadmin}"
DB="${DB:-hospitality_os}"
dsn() {
    if [ -n "${PGTCP_HOST:-}" ]; then
        echo "postgresql://$1@$PGTCP_HOST:$PGPORT/$2"
    else
        echo "postgresql://$1@/$2?host=$PGHOST_DIR&port=$PGPORT"
    fi
}
export M1A_ADMIN_DSN="$(dsn "$SUPERUSER" "$DB")"
export M1A_APP_DSN="$(dsn hospitality_app "$DB")"

echo
echo "=== 4. M1-B verification gates ==="
python3 "$REPO/tests/m1b/verify_m1b.py"
