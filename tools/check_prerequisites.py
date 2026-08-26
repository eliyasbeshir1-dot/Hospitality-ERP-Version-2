#!/usr/bin/env python3
"""Discover the tools a build or deployment needs, and fail clearly when one is absent.

Requirement: FR-OPS-021.

The point is that an ordinary command on an ordinary machine either finds what it needs or
says exactly what is missing and where it looked. Acceptance must not depend on a PATH that
only exists inside CI, so this uses nothing but the interpreter's standard library and the
caller's own PATH.

Usage:
    python3 tools/check_prerequisites.py
    python3 tools/check_prerequisites.py --require docker --require openssl
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys

# Tool, the flag that makes it print a version, and how to install it on each platform.
DEFAULT_TOOLS: list[tuple[str, list[str], str, str]] = [
    ("python3", ["--version"],
     "apt install python3   (or: winget install Python.Python.3)",
     "winget install Python.Python.3"),
    ("psql", ["--version"],
     "apt install postgresql-client",
     "winget install PostgreSQL.PostgreSQL"),
    ("node", ["--version"],
     "apt install nodejs   (or use nvm)",
     "winget install OpenJS.NodeJS.LTS"),
    ("npm", ["--version"],
     "apt install npm   (ships with nodejs)",
     "ships with OpenJS.NodeJS.LTS"),
    ("git", ["--version"], "apt install git", "winget install Git.Git"),
]

WINDOWS = platform.system() == "Windows"


def describe(tool: str, version_flag: list[str]) -> tuple[bool, str]:
    path = shutil.which(tool)
    if path is None:
        return False, ""
    try:
        proc = subprocess.run([path, *version_flag], capture_output=True, text=True, timeout=20)
        version = (proc.stdout or proc.stderr).strip().splitlines()
        return True, f"{path}  ({version[0] if version else 'version unknown'})"
    except Exception:
        return True, f"{path}  (present, version could not be read)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check build and deployment prerequisites.")
    parser.add_argument("--require", action="append", default=[],
                        help="an extra tool that must be present")
    args = parser.parse_args()

    tools = list(DEFAULT_TOOLS) + [(name, ["--version"], f"install {name}", f"install {name}")
                                   for name in args.require]

    print(f"platform: {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"PATH entries: {len(os.environ.get('PATH', '').split(os.pathsep))}")
    print()

    missing: list[tuple[str, str]] = []
    for tool, flag, posix_hint, windows_hint in tools:
        found, detail = describe(tool, flag)
        print(f"  {'found  ' if found else 'MISSING'}  {tool:<10} {detail}")
        if not found:
            missing.append((tool, windows_hint if WINDOWS else posix_hint))

    if missing:
        print(f"\nFAIL PREREQUISITE_ABSENT — {len(missing)} tool(s) not found", file=sys.stderr)
        for tool, hint in missing:
            print(f"  {tool}: not on PATH", file=sys.stderr)
            print(f"      searched: {os.environ.get('PATH', '(PATH is unset)')[:200]}", file=sys.stderr)
            print(f"      install:  {hint}", file=sys.stderr)
        return 1

    print(f"\nPASS PREREQUISITES — {len(tools)} tool(s) discovered on PATH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
