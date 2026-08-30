"""psql transport for the M1 verification harnesses.

Deliberately thin. Tests speak SQL to a real PostgreSQL through the same client a
DBA would use, under the actual application role (FR-DAT-017). No ORM, no driver
that could quietly reconnect with different privileges or reset session context.

Three rules this module exists to enforce, each of them a defect that was found by
review rather than by the suites themselves:

  1. A statement that FAILED is not evidence of anything until you know WHY it failed.
     `not res.ok` is satisfied by a bad DSN, a dead server, a typo or a missing grant.
     Result.failed_with() makes the reason part of the assertion.
  2. A probe that could not RUN is not a passing probe. count() raises rather than
     returning a sentinel that compares false against "> 0" and so reads as "no leak".
  3. Nothing here may be POSIX-only. The harness has to run on Windows, where a
     hardcoded POSIX null-device path is not valid and makes psql exit before the first
     assertion. os.devnull is used instead, and M1-A scans for regressions.
  4. Nothing here may inherit the machine's locale. text=True alone decodes with
     locale.getpreferredencoding(), which is UTF-8 on the Linux runner but cp1252 on a
     Windows console. psql speaks UTF-8 on both, so an undecodable byte raised
     UnicodeDecodeError inside a subprocess reader thread and a decodable-but-wrong one
     silently produced mojibake. encoding="utf-8" is stated at every call site.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

UNIT = "\x1f"


class ProbeFailed(Exception):
    """A probe statement did not execute.

    Raised rather than returned. A caller comparing an integer cannot accidentally
    read "the query never ran" as "the query found nothing", which is how the UPDATE
    and DELETE legs of the isolation gates came to pass with their grants revoked.
    """

    def __init__(self, sql: str, err: str) -> None:
        self.sql = " ".join(sql.split())[:120]
        self.err = err
        super().__init__(f"probe did not execute: {self.sql} -- {err.strip()[:400]}")


@dataclass
class Result:
    ok: bool
    out: str
    err: str

    @property
    def rows(self) -> list[list[str]]:
        return [line.split(UNIT) for line in self.out.splitlines() if line.strip()]

    @property
    def scalar(self) -> str | None:
        rows = self.rows
        return rows[0][0] if rows and rows[0] else None

    def sqlstate_is(self, code: str) -> bool:
        return f"SQLSTATE {code}" in self.err or code in self.err

    def failed_with(self, *reasons: str) -> bool:
        """True only if the statement failed AND failed for one of the stated reasons.

        A reason is either a five-character SQLSTATE ('42501', 'HS401') or a named
        signature the code raises ('SESSION_NOT_LIVE'). Bare failure never satisfies
        this, which is the whole point: an assertion that any error will satisfy is
        satisfied by a typo, and proves nothing about the barrier it claims to test.
        """
        if self.ok:
            return False
        if not reasons:
            raise ValueError("failed_with() requires at least one reason; "
                             "bare failure is not an assertion")
        return any(self.sqlstate_is(r) if _looks_like_sqlstate(r) else r in self.err
                   for r in reasons)

    def why(self) -> str:
        """The failure reason, for a detail line. Empty when the statement succeeded."""
        if self.ok:
            return ""
        for line in self.err.splitlines():
            if line.startswith("ERROR:"):
                return line.strip()
        return self.err.strip().splitlines()[0] if self.err.strip() else "(no error text)"


def _looks_like_sqlstate(reason: str) -> bool:
    return len(reason) == 5 and reason[:2].isalnum() and reason.upper() == reason


def run(dsn: str, sql: str, *, tenant: str | None = None, outlet: str | None = None,
        tx: bool = False, rollback: bool = False) -> Result:
    """Execute SQL, optionally under a tenant/outlet context.

    tx=True wraps the script in BEGIN/COMMIT. Required whenever one statement
    establishes request context and a later statement depends on it: since 0005 that
    context is transaction-local, so in psql's autocommit mode it would be gone by the
    next statement. Running those sequences in a transaction is also how the API uses
    the function, so the test exercises the real path rather than a looser one.
    """
    prelude = ""
    if tenant is not None:
        prelude += f"SELECT set_config('app.tenant_id', '{tenant}', false);\n"
    if outlet is not None:
        prelude += f"SELECT set_config('app.outlet_id', '{outlet}', false);\n"

    # VERBOSITY verbose makes psql print the SQLSTATE. Without it an assertion on a
    # specific error code silently degrades into "some error happened", which is how a
    # wrong-reason failure gets mistaken for a right-reason one.
    script = (f"\\set QUIET on\n\\set VERBOSITY verbose\n\\pset tuples_only on\n"
              f"\\pset format unaligned\n\\pset fieldsep '{UNIT}'\n")
    if prelude:
        # os.devnull, never a hardcoded POSIX device path: on Windows the POSIX literal
        # is not a valid path, psql exits on it under ON_ERROR_STOP, and every
        # context-scoped assertion downstream then runs against a client that is already
        # gone — the suite crashes instead of failing cleanly.
        script += f"\\o {os.devnull}\n{prelude}\\o\n"
    if rollback:
        # A write probe has to be ABLE to succeed, or it proves nothing when the barrier
        # it tests is removed. Rolling back means the observation is real while the
        # fixtures survive a red proof intact.
        script += f"BEGIN;\n{sql}\nROLLBACK;\n"
    elif tx:
        script += f"BEGIN;\n{sql}\nCOMMIT;\n"
    else:
        script += sql

    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X"],
        input=script, capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return Result(proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip())


def count(dsn: str, sql: str, **ctx) -> int:
    """Run a counting probe and return the integer.

    Raises ProbeFailed if the statement did not execute. It used to return -1, which
    every caller written as `if affected > 0` read as "nothing was affected" — so
    revoking UPDATE on the table under test silently turned an isolation gate green
    without the row level security predicate ever being evaluated.
    """
    res = run(dsn, sql, **ctx)
    if not res.ok:
        raise ProbeFailed(sql, res.err)
    try:
        return int(res.scalar or "0")
    except ValueError as exc:
        raise ProbeFailed(sql, f"non-integer result {res.scalar!r}") from exc


def count_or(dsn: str, sql: str, fallback: int, **ctx) -> int:
    """count() for the rare probe whose failure is an expected, asserted outcome.

    The caller must name the fallback explicitly at the call site, so a reader can see
    that failure was anticipated rather than swallowed.
    """
    try:
        return count(dsn, sql, **ctx)
    except ProbeFailed:
        return fallback


class CommandUnreadable(RuntimeError):
    """A child process ran, but its output could not be read.

    subprocess.run(capture_output=True) is documented to return strings for both
    streams, and on Linux it always has. On a Windows runner one came back as None and
    the caller — reasonably assuming a string — died with a TypeError several frames
    from the cause, naming nothing useful.

    Raised rather than returned, and never swallowed: a command whose output cannot be
    read has produced no evidence, and no evidence is not the same as evidence of
    absence. Same rule count() follows.
    """


def run_command(command: list[str], *, extra_env: dict[str, str] | None = None,
                cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run a child process and guarantee its output is readable, or say why it is not.

    Every suite that shells out goes through here, so a platform that breaks stream
    capture is reported once, by name, at whichever call site hit it — instead of
    surfacing as a different exception in a different file each time.
    """
    proc = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=cwd, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(extra_env or {})},
    )
    if proc.stdout is None or proc.stderr is None:
        raise CommandUnreadable(
            f"{command[0]} ran (exit {proc.returncode}) but its output could not be "
            f"captured: stdout is {type(proc.stdout).__name__}, stderr is "
            f"{type(proc.stderr).__name__}. Command: {' '.join(map(str, command))[:200]}")
    return proc
