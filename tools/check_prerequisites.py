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

WINDOWS = platform.system() == "Windows"

# The interpreter is named per platform, because that is what FR-OPS-021 asks for: the
# ORDINARY command on each platform, not one platform's name imposed on the other.
#
# A standard Windows Python (python.org, or winget install Python.Python.3) installs
# python.exe and pythonw.exe and no python3.exe at all. The only python3.exe on a typical
# Windows PATH is the zero-byte Microsoft Store App Execution Alias, which runs nothing —
# so requiring "python3" on Windows demanded a file the documented install cannot produce,
# and printed an install hint that could not fix it. Every documented Windows command in
# docs-local/CROSS_PLATFORM_COMMANDS.md invokes `python`; `python3` is invoked only by the
# tests/*/run_verification.sh drivers, which are POSIX-only entry points.
#
# This is a rename, not a relaxation: the named interpreter must still be on PATH and must
# still exit zero when asked its version, or discovery fails clearly.
INTERPRETER = "python" if WINDOWS else "python3"

# Tool, the flag that makes it print a version, and how to install it on each platform.
DEFAULT_TOOLS: list[tuple[str, list[str], str, str]] = [
    (INTERPRETER, ["--version"],
     "apt install python3",
     "winget install Python.Python.3   (provides python.exe, not python3.exe)"),
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


def describe(tool: str, version_flag: list[str]) -> tuple[bool, str, str]:
    """Report whether a tool is present AND runnable, with the reason when it is not.

    A name on PATH is not a tool. Windows ships App Execution Aliases — zero-byte stubs at
    %LOCALAPPDATA%\\Microsoft\\WindowsApps that shutil.which() resolves happily; running
    python3.EXE there prints "Python was not found" and exits non-zero (49 through a shell,
    9009 through CreateProcess) without executing anything. Reporting that as `found` was a
    discovery false positive under FR-OPS-021, and it mattered: every
    tests/*/run_verification.sh driver invokes python3.

    So the tool must exit zero when asked its version. Anything else — a non-zero status, a
    timeout, an image that will not load — is absent for our purposes, because the build
    step that depends on it is going to fail regardless.
    """
    path = shutil.which(tool)
    if path is None:
        return False, "", "not on PATH"
    try:
        proc = subprocess.run([path, *version_flag], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=20)
    except Exception as exc:
        return False, path, f"on PATH at {path} but could not be executed: {exc}"
    if proc.returncode != 0:
        first = ((proc.stdout or proc.stderr).strip().splitlines() or ["no output"])[0]
        return False, path, (f"on PATH at {path} but exited {proc.returncode} when asked "
                             f"its version, so it runs nothing: {first}")
    version = (proc.stdout or proc.stderr).strip().splitlines()
    return True, f"{path}  ({version[0] if version else 'version unknown'})", ""


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

    missing: list[tuple[str, str, str]] = []
    for tool, flag, posix_hint, windows_hint in tools:
        found, detail, why = describe(tool, flag)
        print(f"  {'found  ' if found else 'MISSING'}  {tool:<10} {detail or why}")
        if not found:
            missing.append((tool, windows_hint if WINDOWS else posix_hint, why))

    if missing:
        print(f"\nFAIL PREREQUISITE_ABSENT — {len(missing)} tool(s) not usable", file=sys.stderr)
        for tool, hint, why in missing:
            # The reason is reported, not assumed: "not on PATH" and "on PATH but exits
            # non-zero" need different fixes, and printing the first for the second sends
            # the reader looking for a PATH problem that is not there.
            print(f"  {tool}: {why}", file=sys.stderr)
            print(f"      searched: {os.environ.get('PATH', '(PATH is unset)')[:200]}", file=sys.stderr)
            print(f"      install:  {hint}", file=sys.stderr)
        return 1

    print(f"\nPASS PREREQUISITES — {len(tools)} tool(s) discovered on PATH and each "
          f"exited zero when asked its version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
