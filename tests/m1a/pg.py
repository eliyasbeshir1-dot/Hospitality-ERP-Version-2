"""psql transport for the M1-A verification harness.

Deliberately thin. Tests speak SQL to a real PostgreSQL through the same client a
DBA would use, under the actual application role (FR-DAT-017). No ORM, no driver
that could quietly reconnect with different privileges or reset session context.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

UNIT = "\x1f"


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


def run(dsn: str, sql: str, *, tenant: str | None = None, outlet: str | None = None) -> Result:
    """Execute SQL, optionally under a tenant/outlet context.

    Context is set with set_config inside the same session as the statements, which
    is exactly how the application will supply it.
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
        script += f"\\o /dev/null\n{prelude}\\o\n"
    script += sql

    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X"],
        input=script, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return Result(proc.returncode == 0, proc.stdout.strip(), proc.stderr.strip())


def count(dsn: str, sql: str, **ctx) -> int:
    """Run a counting query and return the integer, or -1 if the statement failed."""
    res = run(dsn, sql, **ctx)
    if not res.ok:
        return -1
    try:
        return int(res.scalar or "0")
    except ValueError:
        return -1
