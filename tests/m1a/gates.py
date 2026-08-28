"""M1-A verification gates.

Each gate returns (passed, signature, detail). The signature on failure is the
exact string the frozen negative-control register expects, so a control that trips
is identifiable without reading prose:

    NC-M1-001  rls_absent_context_gate       VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT
    NC-M1-002  rls_sibling_outlet_gate       SIBLING_OUTLET_ACCESS
    NC-M1-003  rls_alter_added_outlet_gate   OUTLET_POLICY_NOT_UPGRADED
    NC-M1-004  runtime_role_gate             PRIVILEGED_RUNTIME_ROLE_REJECTED

Requirements: FR-TEN-001, FR-SEC-001, FR-SEC-002A, FR-DAT-017, FR-OPS-020.
"""
from __future__ import annotations

from pg import ProbeFailed, count, run

TENANT_ACME = "11111111-1111-1111-1111-111111111111"
TENANT_GLOBEX = "22222222-2222-2222-2222-222222222222"
OUTLET_A1 = "aaaa0001-0000-4000-8000-000000000001"
OUTLET_A2 = "aaaa0002-0000-4000-8000-000000000002"
OUTLET_B1 = "bbbb0001-0000-4000-8000-000000000001"

# Node belonging to the sibling outlet A2 — a real row, present in the database.
SIBLING_NODE = "aaaa2102-0000-4000-8000-000000000002"
# Node belonging to the foreign tenant GLOBEX.
FOREIGN_NODE = "bbbb1102-0000-4000-8000-000000000001"

# DELETE probes must target rows with NO dependents at all — no children, and nothing
# referencing them from another table. org_node is self-referencing and twenty-odd tables
# point at it, so deleting a row with a dependent raises a foreign key error before row
# level security has said anything. That is how the no-context DELETE leg came to "pass"
# without the policy ever being consulted, and the first attempt at this repair hit the
# same trap a second time by picking a device node that a device_registration row
# referenced. These three are clean, and the red proofs show the DELETE genuinely
# succeeding when the policy is removed.
LEAF_NODE          = "aaaa1103-0000-4000-8000-000000000001"   # T-01,        outlet A1
SIBLING_LEAF_NODE  = "aaaa2104-0000-4000-8000-000000000002"   # T-DEL,       outlet A2
FOREIGN_LEAF_NODE  = FOREIGN_NODE                             # T-99,        tenant GLOBEX

TENANT_TABLES = [
    "org.tenant",
    "org.org_node",
    "org.org_closure",
    "org.outlet_profile",
    "org.device_registration",
]

Gate = tuple[bool, str, str]


# ---------------------------------------------------------------------------
# Probe helpers — a denial has to be observed, never inferred from an absence
# ---------------------------------------------------------------------------
# Review found the UPDATE and DELETE legs of these gates failing open: count()
# returned -1 when the statement did not execute, and `if affected > 0` read that as
# "nothing was affected". Revoking UPDATE on the table under test therefore turned the
# gate green without the row level security predicate ever being evaluated. Running the
# suite after the repair immediately produced a second, live instance: the DELETE probe
# was erroring on a foreign key constraint, so that leg had never tested RLS at all.
#
# The rule below is the fix, and it is deliberately strict: the ONLY outcome that counts
# as a denial is "the statement ran, and it affected zero rows". Everything else — a
# permission error, a constraint error, a dead connection — fails the gate, because none
# of them is evidence that the policy did its job.

def read_probe(dsn: str, sql: str, description: str, **ctx) -> tuple[int, str | None]:
    """Rows visible to a SELECT. Returns (count, leak-description-or-None)."""
    try:
        seen = count(dsn, sql, **ctx)
    except ProbeFailed as exc:
        return -1, f"{description} could not be evaluated: {exc.err.strip().splitlines()[0]}"
    if seen != 0:
        return seen, f"{description} exposed {seen} row(s)"
    return 0, None


def write_probe(dsn: str, sql: str, description: str, **ctx) -> str | None:
    """A write that must match no rows. Returns a leak description, or None.

    Anything other than "ran and affected zero rows" is a leak. A write that could not
    be attempted is not a denial by row level security, and a write that the policy
    permitted and a constraint then stopped is a policy failure wearing a constraint's
    error message.
    """
    try:
        affected = count(dsn, sql, rollback=True, **ctx)
    except ProbeFailed as exc:
        return (f"{description} could not be evaluated as a denial "
                f"({exc.err.strip().splitlines()[0]})")
    if affected != 0:
        return f"{description} affected {affected} row(s)"
    return None


# The isolation barriers an INSERT can legitimately hit, each named so a probe asserts
# the one it means. Review's point stands even when the outcome is correct: `if res.ok`
# accepted ANY refusal, and the sibling-outlet probe turned out to be refused by the
# parent-visibility trigger rather than by the policy — a true denial, but not the one
# the gate claimed to be proving.
RLS_WITH_CHECK = ("42501", "row-level security", "row level security")
PARENT_NOT_VISIBLE = ("HS404", "PARENT_NOT_VISIBLE")


def insert_probe(dsn: str, sql: str, description: str,
                 refused_by: tuple[str, ...] = RLS_WITH_CHECK, **ctx) -> str | None:
    """An INSERT that must be refused, for the stated reason and no other.

    A NOT NULL violation, a foreign key error or a missing grant would all satisfy a
    bare `not res.ok` while proving nothing about the barrier under test.
    """
    res = run(dsn, sql, rollback=True, **ctx)
    if res.ok:
        return f"{description} succeeded"
    if not res.failed_with(*refused_by):
        return (f"{description} was refused, but not by {refused_by[0]} "
                f"({res.why()})")
    return None


# ---------------------------------------------------------------------------
# NC-M1-001 — fail-closed tenant context
# ---------------------------------------------------------------------------

def rls_absent_context_gate(app_dsn: str) -> Gate:
    """With no tenant/outlet context set, nothing is visible and nothing is writable.

    The fixtures are populated, so a zero count here is a real denial rather than an
    empty table passing vacuously.
    """
    leaks: list[str] = []
    none = dict(tenant="", outlet="")

    for table in TENANT_TABLES:
        _, leak = read_probe(app_dsn, f"SELECT count(*) FROM {table};",
                             f"SELECT on {table} with no context", **none)
        if leak:
            leaks.append(leak)

    leaks += [leak for leak in (
        insert_probe(app_dsn, """
            INSERT INTO org.tenant (tenant_code, display_name)
            VALUES ('NOCTX', 'Inserted without context');
        """, "INSERT into org.tenant with no context", **none),

        write_probe(app_dsn, f"""
            WITH changed AS (
                UPDATE org.org_node SET display_name = 'no-context-write'
                WHERE id = '{SIBLING_NODE}' RETURNING 1
            ) SELECT count(*) FROM changed;
        """, "UPDATE with no context", **none),

        write_probe(app_dsn, f"""
            WITH removed AS (
                DELETE FROM org.org_node WHERE id = '{LEAF_NODE}' RETURNING 1
            ) SELECT count(*) FROM removed;
        """, "DELETE with no context", **none),
    ) if leak]

    # A malformed context must fail closed exactly like an absent one.
    _, leak = read_probe(app_dsn, "SELECT count(*) FROM org.org_node;",
                         "SELECT under a malformed context",
                         tenant="not-a-uuid", outlet="also-not-a-uuid")
    if leak:
        leaks.append(leak)

    if leaks:
        return False, "VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT", "; ".join(leaks)
    return True, "", "no rows visible or writable without context (5 tables, 4 verbs, malformed context)"


# ---------------------------------------------------------------------------
# NC-M1-002 — sibling-outlet isolation
# ---------------------------------------------------------------------------

def rls_sibling_outlet_gate(app_dsn: str) -> Gate:
    """Outlet A1's context must not reach sibling outlet A2, for any of the four verbs."""
    ctx = dict(tenant=TENANT_ACME, outlet=OUTLET_A1)
    leaks: list[str] = []

    _, leak = read_probe(app_dsn,
                         f"SELECT count(*) FROM org.org_node WHERE outlet_id = '{OUTLET_A2}';",
                         "SELECT of sibling-outlet nodes", **ctx)
    if leak:
        leaks.append(leak)

    for table, column in (("org.outlet_profile", "outlet_id"),
                          ("org.device_registration", "outlet_id"),
                          ("org.org_closure", "outlet_id")):
        _, leak = read_probe(app_dsn,
                             f"SELECT count(*) FROM {table} WHERE {column} = '{OUTLET_A2}';",
                             f"SELECT of sibling-outlet rows in {table}", **ctx)
        if leak:
            leaks.append(leak)

    leaks += [leak for leak in (
        write_probe(app_dsn, f"""
            WITH changed AS (
                UPDATE org.org_node SET display_name = 'sibling-write'
                WHERE id = '{SIBLING_NODE}' RETURNING 1
            ) SELECT count(*) FROM changed;
        """, "UPDATE of a sibling-outlet row", **ctx),

        write_probe(app_dsn, f"""
            WITH removed AS (
                DELETE FROM org.org_node WHERE id = '{SIBLING_LEAF_NODE}' RETURNING 1
            ) SELECT count(*) FROM removed;
        """, "DELETE of a sibling-outlet row", **ctx),

        # Writing a row INTO the sibling outlet must also be refused.
        # org_node derives its outlet from its parent, and the parent lookup is itself
        # scoped, so this is stopped one level before the policy's WITH CHECK. That is a
        # real denial and it is now asserted by name rather than accepted as "an error".
        insert_probe(app_dsn, f"""
            INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
            VALUES ('{TENANT_ACME}', '{OUTLET_A2}', 'dining_table', 'T-INTRUDER', 'Intruder');
        """, "INSERT under the sibling outlet", refused_by=PARENT_NOT_VISIBLE, **ctx),
    ) if leak]

    if leaks:
        return False, "SIBLING_OUTLET_ACCESS", "; ".join(leaks)
    return True, "", "sibling outlet unreachable for SELECT, INSERT, UPDATE and DELETE"


# ---------------------------------------------------------------------------
# NC-M1-003 — future schema protection
# ---------------------------------------------------------------------------

OUTLET_PREDICATE_MARKERS = ("row_in_scope", "current_outlet_id")


def rls_alter_added_outlet_gate(dsn: str) -> Gate:
    """Every table carrying an outlet_id must carry an outlet-aware policy.

    This is the gate that catches a future migration adding outlet_id to an existing
    tenant-scoped table and forgetting to upgrade its policy — the table would keep
    a tenant-only policy and silently expose sibling outlets.

    Scans every schema that holds tenant data. A schema added by a later slice and
    left out of this list would be an unscanned blind spot, not a pass.
    """
    res = run(dsn, """
        SELECT n.nspname || '.' || c.relname,
               c.relrowsecurity,
               c.relforcerowsecurity,
               coalesce(string_agg(
                   coalesce(pg_get_expr(p.polqual, p.polrelid), '') || ' ' ||
                   coalesce(pg_get_expr(p.polwithcheck, p.polrelid), ''), ' '), '')
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'outlet_id' AND a.attnum > 0
                               AND NOT a.attisdropped
        LEFT JOIN pg_policy p ON p.polrelid = c.oid
        WHERE n.nspname = ANY (ARRAY['org', 'identity']) AND c.relkind = 'r'
        GROUP BY n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
        ORDER BY n.nspname, c.relname;
    """)
    if not res.ok:
        return False, "OUTLET_POLICY_NOT_UPGRADED", f"introspection failed: {res.err}"

    rows = res.rows
    if not rows:
        return False, "OUTLET_POLICY_NOT_UPGRADED", "no outlet-scoped table found; expected at least one"

    faults: list[str] = []
    for relname, enabled, forced, expr in rows:
        if enabled != "t":
            faults.append(f"{relname}: has outlet_id but row level security is not enabled")
            continue
        if forced != "t":
            faults.append(f"{relname}: row level security is not FORCEd, so the owner bypasses it")
        if not any(marker in expr for marker in OUTLET_PREDICATE_MARKERS):
            faults.append(f"{relname}: has outlet_id but no policy references the outlet predicate")

    if faults:
        return False, "OUTLET_POLICY_NOT_UPGRADED", "; ".join(faults)
    return True, "", f"{len(rows)} outlet-scoped table(s), each with a forced outlet-aware policy"


# ---------------------------------------------------------------------------
# NC-M1-004 — runtime least privilege
# ---------------------------------------------------------------------------

def runtime_role_gate(dsn: str) -> Gate:
    """Refuse to run when the connected identity is privileged.

    Owner, superuser, BYPASSRLS, role-creating and schema-creating identities are all
    rejected. There is no fallback path (FR-OPS-020).
    """
    res = run(dsn, """
        SELECT current_user,
               r.rolsuper, r.rolbypassrls, r.rolcreatedb, r.rolcreaterole,
               pg_catalog.has_schema_privilege(current_user, 'org', 'CREATE'),
               pg_catalog.has_schema_privilege(current_user, 'app', 'CREATE'),
               EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'org' AND c.relkind = 'r'
                         AND pg_catalog.pg_get_userbyid(c.relowner) = current_user),
               EXISTS (SELECT 1 FROM pg_auth_members m
                       JOIN pg_roles g ON g.oid = m.roleid
                       WHERE m.member = r.oid AND g.rolsuper)
        FROM pg_roles r WHERE r.rolname = current_user;
    """)
    if not res.ok:
        return False, "PRIVILEGED_RUNTIME_ROLE_REJECTED", f"readiness query failed: {res.err}"

    row = res.rows[0]
    user = row[0]
    flags = {
        "is a superuser": row[1],
        "has BYPASSRLS": row[2],
        "has CREATEDB": row[3],
        "has CREATEROLE": row[4],
        "can CREATE in schema org": row[5],
        "can CREATE in schema app": row[6],
        "owns tables in schema org": row[7],
        "is a member of a superuser role": row[8],
    }
    violations = [f"{user} {label}" for label, value in flags.items() if value == "t"]

    if violations:
        return False, "PRIVILEGED_RUNTIME_ROLE_REJECTED", "; ".join(violations)
    return True, "", f"{user} is least-privileged: no superuser, BYPASSRLS, ownership or DDL right"


# ---------------------------------------------------------------------------
# Cross-tenant isolation (FR-TEN-001, FR-SEC-002A) — not a planted control
# ---------------------------------------------------------------------------

def cross_tenant_gate(app_dsn: str) -> Gate:
    """ACME's context must not reach GLOBEX's rows, for any of the four verbs."""
    ctx = dict(tenant=TENANT_ACME, outlet=OUTLET_A1)
    leaks: list[str] = []

    for sql, description in (
        (f"SELECT count(*) FROM org.org_node WHERE tenant_id = '{TENANT_GLOBEX}';",
         "SELECT of foreign-tenant nodes"),
        (f"SELECT count(*) FROM org.tenant WHERE id = '{TENANT_GLOBEX}';",
         "SELECT of the foreign tenant row"),
    ):
        _, leak = read_probe(app_dsn, sql, description, **ctx)
        if leak:
            leaks.append(leak)

    leaks += [leak for leak in (
        write_probe(app_dsn, f"""
            WITH changed AS (
                UPDATE org.org_node SET display_name = 'cross-tenant-write'
                WHERE id = '{FOREIGN_NODE}' RETURNING 1
            ) SELECT count(*) FROM changed;
        """, "UPDATE of a foreign-tenant row", **ctx),

        write_probe(app_dsn, f"""
            WITH removed AS (
                DELETE FROM org.org_node WHERE id = '{FOREIGN_LEAF_NODE}' RETURNING 1
            ) SELECT count(*) FROM removed;
        """, "DELETE of a foreign-tenant row", **ctx),

        insert_probe(app_dsn, f"""
            INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
            VALUES ('{TENANT_GLOBEX}', NULL, 'brand', 'BR-INTRUDER', 'Intruder');
        """, "INSERT into the foreign tenant", **ctx),
    ) if leak]

    # And the reverse direction, so the test is not one-sided.
    _, leak = read_probe(app_dsn,
                         f"SELECT count(*) FROM org.org_node WHERE tenant_id = '{TENANT_ACME}';",
                         "GLOBEX context reading ACME nodes",
                         tenant=TENANT_GLOBEX, outlet=OUTLET_B1)
    if leak:
        leaks.append(leak)

    if leaks:
        return False, "CROSS_TENANT_ACCESS", "; ".join(leaks)
    return True, "", "foreign tenant unreachable in both directions for all four verbs"
