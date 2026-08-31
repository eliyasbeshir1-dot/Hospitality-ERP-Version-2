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

# The customer surface compiles beside the server, into dist/public, so one build
# produces both and there is no second artefact to deploy or to forget. Its tsconfig
# targets the browser — ES modules and the DOM library — which is why it cannot share the
# server's, and removeComments is on because the comments in that file are for whoever
# maintains it, not for the phone downloading it over mobile data.
# The surface source is copied into the workspace and compiled FROM there, exactly as the
# server's is. The M2-C negative controls plant their defects in that copy: build.sh
# re-copies from the repository on every run, so reverting a defect is a rebuild rather
# than an edit and the repository is never in a broken state even for an instant.
rm -rf "$WORKSPACE/pwa"
cp -r "$REPO/pwa" "$WORKSPACE/pwa"
mkdir -p "$WORKSPACE/dist/public"
cp "$WORKSPACE/pwa/index.html" "$WORKSPACE/pwa/app.css" "$WORKSPACE/pwa/manifest.webmanifest" \
   "$WORKSPACE/dist/public/"
./node_modules/.bin/tsc -p "$WORKSPACE/pwa/tsconfig.json" --outDir "$WORKSPACE/dist/public"
echo "built into $WORKSPACE/dist"

if [ "${1:-}" = "--run" ]; then
    exec node "$WORKSPACE/dist/server.js"
fi
