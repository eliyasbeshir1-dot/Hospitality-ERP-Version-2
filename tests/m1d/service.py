"""Service lifecycle and HTTP helpers for the M1-D harness.

The service under test is the real compiled build, started as a real process against the
real database. Nothing here stubs the API: a route that answers 401 does so because the
database refused a context, not because a test said it should.

Defects for the negative controls are planted in the BUILD WORKSPACE, never in the
repository. api/build.sh re-copies source from the repository on every run, so reverting a
defect is a rebuild rather than an edit, and the repository is never in a broken state
even for an instant.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "m1a"))

from pg import CommandUnreadable, run_command  # noqa: E402

REPO = HERE.parents[1]
WORKSPACE = Path(os.environ.get("M1D_WORKSPACE", "/var/lib/m1d-workspace"))

WINDOWS = os.name == "nt"

# Paths handed to bash are written POSIX-style, and so is the workspace bash is told to
# build into. str() on a Windows Path yields backslashes, which bash consumes as escape
# characters: the repository path arrived at bash with every separator eaten and the build
# died on a filename that was never on disk. as_posix() is identical to str() on Linux, so
# this changes nothing on the CI runner.
ENV_OVERRIDES = {"M1D_WORKSPACE": WORKSPACE.as_posix()}
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **ENV_OVERRIDES}

# npm publishes two entry points in .bin: an extensionless shell script for POSIX and a
# .cmd shim for Windows. Only the shim is a valid Win32 executable — handing CreateProcess
# the extensionless one fails with WinError 193, which is not a compile error and would be
# reported as one.
TSC = "tsc.cmd" if WINDOWS else "tsc"

# Upper bound on a cold start, not a sleep — see Service.start(). Overridable for machines
# slower than the default allows.
READY_TIMEOUT = float(os.environ.get("M1D_READY_TIMEOUT", "60"))

# Resolved once. The discovery below launches child processes to probe, and repeating
# that on every build and rebuild would charge the suite for an answer that cannot change
# mid-run.
_BASH: str | None = None


def _bash_candidates() -> "list[Path]":
    """Every bash this machine offers, in the order worth trying.

    Discovery, not assumption. Three independent routes, because each fails on a
    different machine: git may be a shim whose own directory holds no bash, PATH may
    carry a bash that git knows nothing about, and on the GitHub Windows image the
    directory holding bash is deliberately kept off PATH so it cannot shadow the
    system tools. Asking git where its own executables live (`git --exec-path`)
    survives all three, because it is git answering about itself rather than us
    guessing where it was installed.
    """
    roots: list[Path] = []

    exec_path = None
    try:
        proc = run_command(["git", "--exec-path"])
        if proc.returncode == 0 and proc.stdout.strip():
            exec_path = Path(proc.stdout.strip())
    except (CommandUnreadable, OSError):
        exec_path = None

    for anchor in (exec_path, Path(shutil.which("git")) if shutil.which("git") else None):
        if anchor is None:
            continue
        # .../Git/cmd/git.exe, .../Git/bin/git.exe and
        # .../Git/mingw64/libexec/git-core all reach the install root by walking up.
        for parent in [anchor, *anchor.parents][:6]:
            roots.append(parent)

    candidates: list[Path] = []
    for root in roots:
        for relative in ("bin/bash.exe", "usr/bin/bash.exe"):
            candidate = root / relative
            if candidate.is_file() and candidate not in candidates:
                candidates.append(candidate)

    on_path = shutil.which("bash")
    if on_path and Path(on_path) not in candidates:
        # Kept last, and still probed rather than trusted: on Windows this is usually
        # C:\WINDOWS\system32\bash.exe, the WSL launcher, which the probe rejects.
        candidates.append(Path(on_path))
    return candidates


def _sees_this_filesystem(bash: "Path | str") -> bool:
    """Can this bash open the very file it is about to be asked to run?

    The WSL launcher is a real bash on a real filesystem — just not this one. It is
    excluded by what it can reach, not by where it is installed, because a name is not
    a capability and the path spelling of a shell says nothing about the volume it
    mounts. This is the exact question the build depends on, asked directly.
    """
    build = (REPO / "api" / "build.sh").as_posix()
    try:
        proc = run_command([str(bash), "-c", 'test -f "$1"', "probe", build])
    except (CommandUnreadable, OSError):
        return False
    return proc.returncode == 0


def bash_executable() -> str:
    """The bash that shares this process's filesystem, discovered rather than assumed.

    On Windows, plain "bash" resolves to C:\\WINDOWS\\system32\\bash.exe — the WSL
    launcher. That is a different operating system with a different filesystem view
    (/mnt/c/...), its own node and its own npm. It cannot open a C:/ or D:/ path at
    all, and if it could, the build under test would no longer be the Windows build.

    Absence is reported with the full list of what was examined, so the next reader
    learns which candidates this machine actually offered rather than being told a
    cause the code never checked (FR-OPS-021).
    """
    global _BASH
    if _BASH is not None:
        return _BASH
    if not WINDOWS:
        _BASH = "bash"
        return _BASH

    examined: list[str] = []
    for candidate in _bash_candidates():
        if _sees_this_filesystem(candidate):
            _BASH = str(candidate)
            return _BASH
        examined.append(f"{candidate} (cannot open {(REPO / 'api' / 'build.sh').as_posix()})")

    raise RuntimeError(
        "PREREQUISITE_ABSENT: no bash on this machine can see this filesystem. The API "
        "build is a bash script and must run against the Windows volume the repository "
        "is checked out on. Install Git for Windows (winget install Git.Git). "
        + (f"Examined: {'; '.join(examined)}." if examined
           else "No bash executable was found at all: neither git --exec-path nor PATH "
                "led to one."))


def sync_and_build() -> None:
    """Copy source from the repository into the workspace and compile it."""
    proc = run_command([bash_executable(), (REPO / "api" / "build.sh").as_posix()],
                       extra_env=ENV_OVERRIDES)
    if proc.returncode != 0:
        raise RuntimeError(f"build failed: {proc.stderr.strip() or proc.stdout.strip()}")


def compile_only() -> None:
    """Recompile whatever is in the workspace, without re-copying from the repository."""
    proc = run_command([str(WORKSPACE / "node_modules" / ".bin" / TSC),
                        "-p", str(WORKSPACE / "tsconfig.json")],
                       cwd=str(WORKSPACE), extra_env=ENV_OVERRIDES)
    if proc.returncode != 0:
        raise RuntimeError(f"compile failed: {proc.stdout.strip() or proc.stderr.strip()}")


def patch_workspace(relative: str, old: str, new: str) -> None:
    """Plant a defect in the workspace copy and recompile it."""
    path = WORKSPACE / "src" / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"cannot plant defect: anchor not found in {relative}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    compile_only()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class Response:
    status: int
    body: str
    headers: dict[str, str]

    @property
    def json(self) -> dict:
        try:
            return json.loads(self.body)
        except json.JSONDecodeError:
            return {}


class Service:
    """A running instance of the API."""

    def __init__(self, database_url: str, environment: str = "verification",
                 extra_env: dict[str, str] | None = None) -> None:
        self.port = free_port()
        # tempfile.gettempdir(), not a hardcoded POSIX temp path: the literal resolved to a
        # drive-relative \tmp\ on Windows, which is a different directory on every drive and
        # need not exist at all. Same defect class as F3, in a directory the F3 scanner does
        # not look for.
        self.log_path = Path(tempfile.gettempdir()) / f"m1d-service-{self.port}.log"
        self._database_url = database_url
        self._environment = environment
        self._extra = extra_env or {}
        self._process: subprocess.Popen | None = None
        self._not_ready = ""

    def start(self, wait_seconds: float = READY_TIMEOUT) -> bool:
        """Start the service and wait for it to signal readiness.

        Readiness is a signal, not a sleep. The loop returns the instant /health answers, and
        returns False the instant the process exits — a healthy start still returns in well
        under a second, so the window costs nothing when nothing is wrong. It is only an
        upper bound on how long a cold start is allowed to take.

        That bound used to be 15 seconds and it was too tight on Windows, where the first
        launch after a build competes with the filesystem filter driver scanning freshly
        written dist/ and node_modules/ files: one run in four failed here with the service
        alive and simply not listening yet. A gate that goes red without a defect devalues
        every red it reports, so the bound is now generous and stated rather than guessed,
        and M1D_READY_TIMEOUT overrides it on a slow machine.

        There is no retry: a start is attempted once. Distinguishing "exited" from "still
        starting" is what makes that safe — a service that refuses to start is reported
        immediately and is never confused with one that is merely slow.
        """
        self.log_path.write_text("", encoding="utf-8")
        env = {
            **ENV,
            "DATABASE_URL": self._database_url,
            "PORT": str(self.port),
            "ENVIRONMENT_NAME": self._environment,
            **self._extra,
        }
        handle = self.log_path.open("w")
        self._process = subprocess.Popen(
            ["node", str(WORKSPACE / "dist" / "server.js")],
            stdout=handle, stderr=subprocess.STDOUT, env=env,
        )
        started = time.time()
        deadline = started + wait_seconds
        while time.time() < deadline:
            if self._process.poll() is not None:
                # Exited before listening. Definitive, so stop now rather than waiting out
                # the window: this is a refusal to start, not a slow start.
                self._not_ready = (f"process exited with code {self._process.returncode} "
                                   f"after {time.time() - started:.1f}s without listening")
                return False
            try:
                self.get("/health", timeout=1)
                return True
            except Exception:
                time.sleep(0.25)
        self._not_ready = (f"still running but did not answer /health on port {self.port} "
                           f"within {wait_seconds:.0f}s (raise M1D_READY_TIMEOUT if this "
                           f"machine is slower than the window allows)")
        return False

    def stop(self) -> None:
        if self._process and self._process.poll() is None:
            self._process.send_signal(signal.SIGTERM)
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None

    @property
    def exit_code(self) -> int | None:
        return self._process.poll() if self._process else None

    def logs(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="ignore")

    def request(self, method: str, path: str, token: str | None = None,
                headers: dict[str, str] | None = None, timeout: float = 10) -> Response:
        url = f"http://127.0.0.1:{self.port}{path}"
        request = urllib.request.Request(url, method=method)
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return Response(response.status, response.read().decode(),
                                {k.lower(): v for k, v in response.headers.items()})
        except urllib.error.HTTPError as error:
            return Response(error.code, error.read().decode(),
                            {k.lower(): v for k, v in error.headers.items()})

    def get(self, path: str, token: str | None = None, **kw) -> Response:
        return self.request("GET", path, token, **kw)

    def delete(self, path: str, token: str | None = None, **kw) -> Response:
        return self.request("DELETE", path, token, **kw)

    def restart(self) -> None:
        """Stop and start again, picking up a rebuilt bundle.

        Added for M2-C. The service reads the customer surface's files once at startup —
        which is what a server should do — so a rebuilt bundle only reaches a browser
        after a restart. Additive: nothing in M1-D's own path calls this.
        """
        self.stop()
        if not self.start():
            raise RuntimeError(f"service did not restart — {self._not_ready}; "
                               f"log:\n{self.logs()[:2000]}")

    def __enter__(self) -> "Service":
        if not self.start():
            raise RuntimeError(f"service did not start — {self._not_ready}; "
                               f"log:\n{self.logs()[:2000]}")
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()
