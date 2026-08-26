#!/usr/bin/env bash
# Build the API into a workspace OUTSIDE the repository.
#
# tools/verify_m1.py treats node_modules/, dist/ and build/ as forbidden surface and
# checks the filesystem rather than the Git index, so a build inside the repository would
# fail the gate even though .gitignore would keep it out of commits. Building elsewhere
# keeps the repository clean at every moment, with no cleanup step to forget.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE="${M1D_WORKSPACE:-/var/lib/m1d-workspace}"

mkdir -p "$WORKSPACE"
cp "$REPO/api/package.json" "$WORKSPACE/package.json"
cp "$REPO/api/tsconfig.json" "$WORKSPACE/tsconfig.json"
rm -rf "$WORKSPACE/src"
cp -r "$REPO/api/src" "$WORKSPACE/src"

cd "$WORKSPACE"
if [ ! -d node_modules ] || [ "${M1D_FORCE_INSTALL:-0}" = "1" ]; then
    npm install --no-audit --no-fund --loglevel=error
fi

./node_modules/.bin/tsc -p tsconfig.json
echo "built into $WORKSPACE/dist"

if [ "${1:-}" = "--run" ]; then
    exec node "$WORKSPACE/dist/server.js"
fi
