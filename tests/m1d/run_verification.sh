#!/usr/bin/env bash
# M1-D verification driver: rebuild from empty, apply seeds through the runner, then run
# all four slices in order.
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

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
python3 "$REPO/tools/seed.py" --dsn "$M1A_MIGRATOR_DSN" --content-dsn "$M1A_APP_DSN" \
        --seeds "$REPO/seeds" apply

echo
echo "=== 7. M1-D verification gates ==="
python3 "$REPO/tests/m1d/verify_m1d.py"
