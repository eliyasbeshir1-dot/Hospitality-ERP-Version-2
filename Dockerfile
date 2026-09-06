# Deployment image for the Hospitality OS API. NOT part of the gated build.
#
# This file exists because the repository is, by design, unbuildable by a
# zero-config platform builder. api/build.sh compiles into a workspace OUTSIDE
# the repository, because tools/verify_m1.py treats node_modules/, dist/ and
# build/ as forbidden surface and checks the filesystem rather than the git
# index. So there is no root package.json for a builder to detect, and Railpack
# refuses with "No start command detected" before it reaches any of our code.
#
# A Dockerfile states the build instead of guessing it. Nothing here changes a
# guard: the service still starts under whatever identity DATABASE_URL names,
# and FR-OPS-001 still decides whether that identity may run.
FROM node:22-bookworm-slim

# psql and python3 are the migration transport — tools/migrate.py and
# tools/seed.py shell out to psql, which keeps the tool SQL-first end to end.
# They are in the runtime image, not just the build image, because migrations
# run as a pre-deploy step under the MIGRATOR identity, separately from the
# app identity the server runs as.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client python3 bash ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src

# Outside the repository tree, exactly as the local build does.
ENV M1D_WORKSPACE=/workspace
ENV PYTHONDONTWRITEBYTECODE=1
RUN bash api/build.sh

CMD ["bash", "/src/deploy/start.sh"]
