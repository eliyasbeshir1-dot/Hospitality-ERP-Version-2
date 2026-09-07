#!/usr/bin/env bash
# OP-B — the staff screens. Chains from OP-A, which chains the whole history beneath it.
#
# The order matters: this gate proves a PERSON can reach behaviour the earlier slices
# built, so everything they build has to exist first. It runs against the product seed and
# a real browser, because a run against fixtures alone would prove the screens work on rows
# the tests wrote, which is the thing this gate exists to stop being sufficient.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY_BIN="${PYTHON:-python3}"
command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN=python
export PYTHON="$PY_BIN"

bash "$REPO/tests/opa/run_verification.sh"

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
echo "=== 19. OP-B verification gates ==="
"$PY_BIN" "$REPO/tests/opb/verify_opb.py"
