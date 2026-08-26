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

from pg import count, run

TENANT_ACME = "11111111-1111-1111-1111-111111111111"
TENANT_GLOBEX = "22222222-2222-2222-2222-222222222222"
OUTLET_A1 = "aaaa0001-0000-4000-8000-000000000001"
OUTLET_A2 = "aaaa0002-0000-4000-8000-000000000002"
OUTLET_B1 = "bbbb0001-0000-4000-8000-000000000001"

# Node belonging to the sibling outlet A2 — a real row, present in the database.
SIBLING_NODE = "aaaa2102-0000-4000-8000-000000000002"
# Node belonging to the foreign tenant GLOBEX.
FOREIGN_NODE = "bbbb1102-0000-4000-8000-000000000001"

TENANT_TABLES = [
    "org.tenant",
    "org.org_node",
    "org.org_closure",
    "org.outlet_profile",
    "org.device_registration",
]

Gate = tuple[bool, str, str]


# ---------------------------------------------------------------------------
# NC-M1-001 — fail-closed tenant context
# ---------------------------------------------------------------------------

def rls_absent_context_gate(app_dsn: str) -> Gate:
    """With no tenant/outlet context set, nothing is visible and nothing is writable.

    The fixtures are populated, so a zero count here is a real denial rather than an
    empty table passing vacuously.
    """
    leaks: list[str] = []

    for table in TENANT_TABLES:
        visible = count(app_dsn, f"SELECT count(*) FROM {table};", tenant="", outlet="")
        if visible != 0:
            leaks.append(f"SELECT on {table} returned {visible} row(s) with no context")

    # INSERT must be refused by the policy's WITH CHECK.
    res = run(app_dsn, """
        INSERT INTO org.tenant (tenant_code, display_name)
        VALUES ('NOCTX', 'Inserted without context');
    """, tenant="", outlet="")
    if res.ok:
        leaks.append("INSERT into org.tenant succeeded with no context")

    # UPDATE and DELETE must match zero rows.
    updated = count(app_dsn, """
        WITH changed AS (
            UPDATE org.org_node SET display_name = 'no-context-write'
            WHERE id = '%s' RETURNING 1
        ) SELECT count(*) FROM changed;
    """ % SIBLING_NODE, tenant="", outlet="")
    if updated > 0:
        leaks.append(f"UPDATE affected {updated} row(s) with no context")

    deleted = count(app_dsn, """
        WITH removed AS (
            DELETE FROM org.org_node WHERE id = '%s' RETURNING 1
        ) SELECT count(*) FROM removed;
    """ % SIBLING_NODE, tenant="", outlet="")
    if deleted > 0:
        leaks.append(f"DELETE affected {deleted} row(s) with no context")

    # A malformed context must fail closed exactly like an absent one.
    malformed = count(app_dsn, "SELECT count(*) FROM org.org_node;",
                      tenant="not-a-uuid", outlet="also-not-a-uuid")
    if malformed != 0:
        leaks.append(f"SELECT returned {malformed} row(s) under a malformed context")

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

    visible = count(app_dsn,
                    f"SELECT count(*) FROM org.org_node WHERE outlet_id = '{OUTLET_A2}';", **ctx)
    if visible != 0:
        leaks.append(f"SELECT exposed {visible} sibling-outlet node(s)")

    for table, column in (("org.outlet_profile", "outlet_id"),
                          ("org.device_registration", "outlet_id"),
                          ("org.org_closure", "outlet_id")):
        seen = count(app_dsn, f"SELECT count(*) FROM {table} WHERE {column} = '{OUTLET_A2}';", **ctx)
        if seen != 0:
            leaks.append(f"SELECT exposed {seen} sibling-outlet row(s) in {table}")

    updated = count(app_dsn, f"""
        WITH changed AS (
            UPDATE org.org_node SET display_name = 'sibling-write'
            WHERE id = '{SIBLING_NODE}' RETURNING 1
        ) SELECT count(*) FROM changed;
    """, **ctx)
    if updated > 0:
        leaks.append(f"UPDATE modified {updated} sibling-outlet row(s)")

    deleted = count(app_dsn, f"""
        WITH removed AS (
            DELETE FROM org.org_node WHERE id = '{SIBLING_NODE}' RETURNING 1
        ) SELECT count(*) FROM removed;
    """, **ctx)
    if deleted > 0:
        leaks.append(f"DELETE removed {deleted} sibling-outlet row(s)")

    # Writing a row INTO the sibling outlet must also be refused.
    res = run(app_dsn, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_ACME}', '{OUTLET_A2}', 'dining_table', 'T-INTRUDER', 'Intruder');
    """, **ctx)
    if res.ok:
        leaks.append("INSERT created a row under the sibling outlet")

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
    """
    res = run(dsn, """
        SELECT c.relname,
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
        WHERE n.nspname = 'org' AND c.relkind = 'r'
        GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
        ORDER BY c.relname;
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

    seen = count(app_dsn, f"SELECT count(*) FROM org.org_node WHERE tenant_id = '{TENANT_GLOBEX}';", **ctx)
    if seen != 0:
        leaks.append(f"SELECT exposed {seen} foreign-tenant node(s)")

    seen = count(app_dsn, f"SELECT count(*) FROM org.tenant WHERE id = '{TENANT_GLOBEX}';", **ctx)
    if seen != 0:
        leaks.append(f"SELECT exposed the foreign tenant row")

    updated = count(app_dsn, f"""
        WITH changed AS (
            UPDATE org.org_node SET display_name = 'cross-tenant-write'
            WHERE id = '{FOREIGN_NODE}' RETURNING 1
        ) SELECT count(*) FROM changed;
    """, **ctx)
    if updated > 0:
        leaks.append(f"UPDATE modified {updated} foreign-tenant row(s)")

    deleted = count(app_dsn, f"""
        WITH removed AS (
            DELETE FROM org.org_node WHERE id = '{FOREIGN_NODE}' RETURNING 1
        ) SELECT count(*) FROM removed;
    """, **ctx)
    if deleted > 0:
        leaks.append(f"DELETE removed {deleted} foreign-tenant row(s)")

    res = run(app_dsn, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_GLOBEX}', NULL, 'brand', 'BR-INTRUDER', 'Intruder');
    """, **ctx)
    if res.ok:
        leaks.append("INSERT created a row in the foreign tenant")

    # And the reverse direction, so the test is not one-sided.
    seen = count(app_dsn, f"SELECT count(*) FROM org.org_node WHERE tenant_id = '{TENANT_ACME}';",
                 tenant=TENANT_GLOBEX, outlet=OUTLET_B1)
    if seen != 0:
        leaks.append(f"GLOBEX context exposed {seen} ACME node(s)")

    if leaks:
        return False, "CROSS_TENANT_ACCESS", "; ".join(leaks)
    return True, "", "foreign tenant unreachable in both directions for all four verbs"
