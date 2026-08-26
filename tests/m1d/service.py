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
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("M1D_WORKSPACE", "/var/lib/m1d-workspace"))

ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def sync_and_build() -> None:
    """Copy source from the repository into the workspace and compile it."""
    proc = subprocess.run(["bash", str(REPO / "api" / "build.sh")],
                          capture_output=True, text=True, env=ENV)
    if proc.returncode != 0:
        raise RuntimeError(f"build failed: {proc.stderr.strip() or proc.stdout.strip()}")


def compile_only() -> None:
    """Recompile whatever is in the workspace, without re-copying from the repository."""
    proc = subprocess.run([str(WORKSPACE / "node_modules" / ".bin" / "tsc"),
                           "-p", str(WORKSPACE / "tsconfig.json")],
                          capture_output=True, text=True, cwd=WORKSPACE, env=ENV)
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
        self.log_path = Path(f"/tmp/m1d-service-{self.port}.log")
        self._database_url = database_url
        self._environment = environment
        self._extra = extra_env or {}
        self._process: subprocess.Popen | None = None

    def start(self, wait_seconds: float = 15.0) -> bool:
        """Start the service. Returns True once it answers, False if it refused to start."""
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
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self._process.poll() is not None:
                return False                      # exited before listening
            try:
                self.get("/health", timeout=1)
                return True
            except Exception:
                time.sleep(0.25)
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

    def __enter__(self) -> "Service":
        if not self.start():
            raise RuntimeError(f"service did not start; log:\n{self.logs()[:2000]}")
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()
