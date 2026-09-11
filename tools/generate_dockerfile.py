#!/usr/bin/env python3
"""deploy/Dockerfile, derived from tools/artifact.py rather than written beside it.

FR-OPS-019. A Dockerfile with its own COPY list is a second manifest, and a second
manifest is one that goes stale — the CI matrix, the README and the schema catalog each
taught this repository that lesson once. So the image is generated from the same
declaration the builder copies from and the checker probes, and --check refuses if the
committed file has drifted.

WHAT THIS FILE CLAIMS AND WHAT IT DOES NOT. It claims the image DEFINITION is derived and
consistent. It does not claim the image has been built: Docker's daemon is not running on
the machine this gate was written on, and a Dockerfile nobody has built is a plan rather
than an artifact. planning/M6_FINDINGS.md carries that as a named bound with what closes
it, and tools/verify_artifact.py proves the same tree the image would contain — built,
probed and scanned — so the gap is the packaging rather than the contents.

Usage:
    python3 tools/generate_dockerfile.py --out deploy/Dockerfile
    python3 tools/generate_dockerfile.py --check deploy/Dockerfile
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from artifact import (                                     # noqa: E402
    ENTRY_POINTS, EXCLUDED_ALWAYS, INCLUDED_FILES, INCLUDED_TREES,
)
from console import use_utf8_output                        # noqa: E402

use_utf8_output()

NODE_IMAGE = "node:22-bookworm-slim"


def render() -> str:
    lines: list[str] = []
    add = lines.append

    add("# GENERATED FROM tools/artifact.py — DO NOT EDIT BY HAND.")
    add("#")
    add("# Regenerate:  python3 tools/generate_dockerfile.py --out deploy/Dockerfile")
    add("# Check:       python3 tools/generate_dockerfile.py --check deploy/Dockerfile")
    add("#")
    add("# The COPY list below is the artifact manifest and nothing else. An image with its")
    add("# own idea of what to copy is a second manifest, and a second manifest goes stale.")
    add("")
    add("# ---------------------------------------------------------------------------")
    add("# STAGE 1 — compile, in a place the repository is not")
    add("# ---------------------------------------------------------------------------")
    add("#")
    add("# api/build.sh compiles into a workspace OUTSIDE the repository because")
    add("# tools/verify_m1.py treats dist/, node_modules/ and build/ inside it as forbidden")
    add("# surface, checked on the filesystem rather than the Git index. The build stage is")
    add("# that workspace: the source goes in, the compiled output comes out, and the tree")
    add("# that ships never contains a compiler.")
    add(f"FROM {NODE_IMAGE} AS build")
    add("WORKDIR /build")
    add("COPY api/package.json api/tsconfig.json ./")
    add("RUN npm install --no-audit --no-fund --loglevel=error")
    add("COPY api/src ./src")
    add("COPY pwa ./pwa")
    add("RUN ./node_modules/.bin/tsc -p tsconfig.json \\")
    add(" && mkdir -p dist/public \\")
    add(" && cp pwa/index.html pwa/app.css pwa/manifest.webmanifest dist/public/ \\")
    add(" && ./node_modules/.bin/tsc -p pwa/tsconfig.json --outDir dist/public")
    add("RUN npm prune --omit=dev")
    add("")
    add("# ---------------------------------------------------------------------------")
    add("# STAGE 2 — what production runs")
    add("# ---------------------------------------------------------------------------")
    add(f"FROM {NODE_IMAGE}")
    add("")
    add("# THE DATABASE CLIENT FR-OPS-019 NAMES. tools/migrate.py shells to psql, so an")
    add("# image without one is an image that cannot apply its own schema — and reaching")
    add("# for a client on the host is the development mount the requirement forbids.")
    add("# python3 is here for the same reason: the print agent and the migrator are Python.")
    add("RUN apt-get update \\")
    add(" && apt-get install --yes --no-install-recommends postgresql-client python3 \\")
    add(" && rm -rf /var/lib/apt/lists/*")
    add("")
    add("WORKDIR /srv/hospitality")
    add("")

    for origin, source, target in INCLUDED_TREES:
        if origin == "build":
            add(f"COPY --from=build /build/{source} ./{target}")
        else:
            add(f"COPY {source} ./{target}")
    for origin, source, target in INCLUDED_FILES:
        if origin == "build":
            add(f"COPY --from=build /build/{source} ./{target}")
        else:
            add(f"COPY {source} ./{target}")

    add("")
    add("# WHAT IS DELIBERATELY ABSENT, and why each one would be a defect rather than a")
    add("# convenience. FR-CFG-007B asks for a scan proving no demo-reset route, job or")
    add("# script is present; these are the things that scan is looking for.")
    for excluded, why in EXCLUDED_ALWAYS:
        add(f"#   {excluded:<12} {why}")
    add("")
    add("# NOT ROOT. Nothing this image runs needs to write outside its own working")
    add("# directory, and a print agent that can rewrite the migrator is a print agent")
    add("# whose compromise is the whole node's.")
    add("RUN useradd --system --uid 10001 --home /srv/hospitality hospitality \\")
    add(" && chown -R hospitality:hospitality /srv/hospitality")
    add("USER hospitality")
    add("")
    add("# THE ADVERTISED ENTRY POINTS, which tools/verify_artifact.py runs from inside the")
    add("# built tree with PYTHONPATH and NODE_PATH cleared. A file that is present and")
    add("# cannot execute is the failure FR-OPS-019 is about.")
    for entry in ENTRY_POINTS:
        add(f"#   {entry.name:<20} {entry.service:<18} {entry.path}")
    add("")
    add("# The API is the default because it is the one every deployment runs; the print")
    add("# agent and the migrator are the same image invoked differently.")
    add('CMD ["node", "dist/server.js"]')
    add("")
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out")
    parser.add_argument("--check")
    args = parser.parse_args()

    rendered = render()

    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(rendered.encode("utf-8"))
        print(f"wrote {target} ({len(rendered.splitlines())} lines)")
        return 0

    if args.check:
        target = Path(args.check)
        if not target.exists():
            print(f"FAIL DOCKERFILE_ABSENT: {target} does not exist")
            return 1
        committed = target.read_text(encoding="utf-8")
        if committed != rendered:
            print("FAIL DOCKERFILE_DRIFT — the committed Dockerfile does not match a fresh")
            print("  generation from tools/artifact.py. The manifest changed and the image")
            print("  did not, which is the second-manifest defect this generator prevents.")
            return 1
        print("PASS DOCKERFILE_MATCHES_MANIFEST")
        print(f"  {len(rendered.splitlines())} lines derived from tools/artifact.py")
        return 0

    parser.error("pass --out or --check")
    return 2


if __name__ == "__main__":
    sys.exit(main())
