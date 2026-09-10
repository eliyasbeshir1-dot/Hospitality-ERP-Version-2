# GENERATED FROM tools/artifact.py — DO NOT EDIT BY HAND.
#
# Regenerate:  python3 tools/generate_dockerfile.py --out deploy/Dockerfile
# Check:       python3 tools/generate_dockerfile.py --check deploy/Dockerfile
#
# The COPY list below is the artifact manifest and nothing else. An image with its
# own idea of what to copy is a second manifest, and a second manifest goes stale.

# ---------------------------------------------------------------------------
# STAGE 1 — compile, in a place the repository is not
# ---------------------------------------------------------------------------
#
# api/build.sh compiles into a workspace OUTSIDE the repository because
# tools/verify_m1.py treats dist/, node_modules/ and build/ inside it as forbidden
# surface, checked on the filesystem rather than the Git index. The build stage is
# that workspace: the source goes in, the compiled output comes out, and the tree
# that ships never contains a compiler.
FROM node:22-bookworm-slim AS build
WORKDIR /build
COPY api/package.json api/tsconfig.json ./
RUN npm install --no-audit --no-fund --loglevel=error
COPY api/src ./src
COPY pwa ./pwa
RUN ./node_modules/.bin/tsc -p tsconfig.json \
 && mkdir -p dist/public \
 && cp pwa/index.html pwa/app.css pwa/manifest.webmanifest dist/public/ \
 && ./node_modules/.bin/tsc -p pwa/tsconfig.json --outDir dist/public
RUN npm prune --omit=dev

# ---------------------------------------------------------------------------
# STAGE 2 — what production runs
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim

# THE DATABASE CLIENT FR-OPS-019 NAMES. tools/migrate.py shells to psql, so an
# image without one is an image that cannot apply its own schema — and reaching
# for a client on the host is the development mount the requirement forbids.
# python3 is here for the same reason: the print agent and the migrator are Python.
RUN apt-get update \
 && apt-get install --yes --no-install-recommends postgresql-client python3 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/hospitality

COPY --from=build /build/dist ./dist
COPY --from=build /build/node_modules ./node_modules
COPY print ./print
COPY migrations ./migrations
COPY tools/migrate.py ./tools/migrate.py
COPY tools/console.py ./tools/console.py
COPY api/package.json ./package.json

# WHAT IS DELIBERATELY ABSENT, and why each one would be a defect rather than a
# convenience. FR-CFG-007B asks for a scan proving no demo-reset route, job or
# script is present; these are the things that scan is looking for.
#   seeds        every seed in this repository builds the DEMONSTRATION floor. A loader that creates demonstration tenants in production is what FR-CFG-007B forbids, and is worse than a way to reset them
#   tests        a test harness in production is a set of routes and fixtures nobody reviewed as product, and several of them plant defects on purpose
#   docs         not runtime
#   planning     not runtime
#   evidence     not runtime

# NOT ROOT. Nothing this image runs needs to write outside its own working
# directory, and a print agent that can rewrite the migrator is a print agent
# whose compromise is the whole node's.
RUN useradd --system --uid 10001 --home /srv/hospitality hospitality \
 && chown -R hospitality:hospitality /srv/hospitality
USER hospitality

# THE ADVERTISED ENTRY POINTS, which tools/verify_artifact.py runs from inside the
# built tree with PYTHONPATH and NODE_PATH cleared. A file that is present and
# cannot execute is the failure FR-OPS-019 is about.
#   api                  local_api          dist/server.js
#   print-agent          print_agent        print/agent.py
#   print-queue-runner   print_agent        print/queue_runner.py
#   migrate              operations         tools/migrate.py

# The API is the default because it is the one every deployment runs; the print
# agent and the migrator are the same image invoked differently.
CMD ["node", "dist/server.js"]
