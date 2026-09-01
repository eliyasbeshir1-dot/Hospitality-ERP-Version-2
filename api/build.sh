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

# The STATION surface, the same way and for the same reasons. It is a separate surface
# rather than a mode of the customer one: they share no audience, no authentication and
# no fate, and a kitchen screen that could be reached by scanning a QR code would be a
# defect rather than a feature. M3-B's negative controls plant their defects in this
# workspace copy, so reverting one is a rebuild.
rm -rf "$WORKSPACE/station"
cp -r "$REPO/station" "$WORKSPACE/station"
cp "$WORKSPACE/station/index.html" "$WORKSPACE/dist/public/station.html"
cp "$WORKSPACE/station/station.css" "$WORKSPACE/dist/public/station.css"
# The entry point is station/src/station.ts, so tsc emits station.js directly. Naming it
# app.ts and renaming the output afterwards worked and was fragile: it depended on the
# two surfaces being compiled in a particular order, because both would have emitted
# app.js into the same directory.
./node_modules/.bin/tsc -p "$WORKSPACE/station/tsconfig.json" --outDir "$WORKSPACE/dist/public"

echo "built into $WORKSPACE/dist"

if [ "${1:-}" = "--run" ]; then
    exec node "$WORKSPACE/dist/server.js"
fi
