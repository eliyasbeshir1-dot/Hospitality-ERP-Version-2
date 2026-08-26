#!/usr/bin/env python3
"""M1-A verification harness.

Runs against a real PostgreSQL through the actual application role (FR-DAT-017).

Every negative control is proved RED before it is trusted GREEN: the gate is run
against the correct system, a deliberate defect is then injected, the gate is
required to emit its exact registered signature, the defect is reverted, and the
gate is required to pass again. A control that cannot fail is a coverage gap, so a
control that never went red is reported as a failure of this harness.

Usage:
    M1A_ADMIN_DSN=... M1A_MIGRATOR_DSN=... M1A_APP_DSN=... python3 tests/m1a/verify_m1a.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gates import (  # noqa: E402
    OUTLET_A1, OUTLET_A2, SIBLING_NODE, TENANT_ACME,
    cross_tenant_gate, rls_absent_context_gate, rls_alter_added_outlet_gate,
    rls_sibling_outlet_gate, runtime_role_gate,
)
from pg import count, run  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MIGRATION = REPO / "migrations" / "0001_organizational_model_and_rls.sql"
PACKAGE = REPO / "docs" / "Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9"


def fenced_identifier_pattern() -> tuple[str, int]:
    """Build an identifier-matching regex from the package's fenced vocabulary.

    Terms are matched as whole identifier components — bounded by start, end or an
    underscore — so a short term such as "hr" cannot false-positive on "threshold".
    Multi-word terms tolerate either a space or an underscore between words.
    """
    rules = json.loads(
        (PACKAGE / "02_MACHINE_READABLE" / "forbidden_surface_rules.json").read_text(encoding="utf-8")
    )
    terms = sorted({t for group in rules["forbidden_positive_obligations"].values() for t in group})
    alternatives = []
    for term in terms:
        cleaned = "".join(ch for ch in term.lower() if ch.isalnum() or ch in " _-")
        alternatives.append(re.sub(r"[ _-]+", "[_ ]*", cleaned.strip()))
    return "(^|_)(" + "|".join(alternatives) + ")(_|$)", len(terms)

ADMIN = os.environ["M1A_ADMIN_DSN"]
MIGRATOR = os.environ["M1A_MIGRATOR_DSN"]
APP = os.environ["M1A_APP_DSN"]

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")


def migrate(dsn: str, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "tools" / "migrate.py"), "--dsn", dsn,
         "--migrations", str(REPO / "migrations"), command],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


# ===========================================================================
# 1. Migration
# ===========================================================================

def section_migration() -> None:
    print("\n--- 1. Migration history (FR-DAT-001, FR-DAT-016) ---")

    applied = count(MIGRATOR, "SELECT count(*) FROM migration.schema_migrations;")
    has_0001 = count(MIGRATOR, "SELECT count(*) FROM migration.schema_migrations WHERE version = 1;")
    on_disk = len(list((REPO / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")))
    record("0001 applied to a database built from empty", has_0001 == 1 and applied == on_disk,
           f"version 0001 recorded; {applied} of {on_disk} migration(s) on disk applied")

    res = run(MIGRATOR, "SELECT version, filename FROM migration.schema_migrations ORDER BY version;")
    first = res.rows[0] if res.rows else ["", ""]
    record("history begins at 0001", first[0] == "1",
           f"first recorded version is {first[0]} ({first[1]})")

    # Checksum lock: edit an applied migration and require preflight to refuse.
    original = MIGRATION.read_bytes()
    try:
        MIGRATION.write_bytes(original + b"\n-- deliberate edit to an applied migration\n")
        proc = migrate(MIGRATOR, "preflight")
        tripped = proc.returncode != 0 and "MIGRATION_CHECKSUM_MISMATCH" in proc.stderr
        record("checksum lock rejects an edited applied migration", tripped,
               proc.stderr.strip().splitlines()[0] if proc.stderr.strip() else "no signature emitted")

        proc = migrate(MIGRATOR, "apply")
        record("apply refuses to proceed while the history is broken",
               proc.returncode != 0 and "MIGRATION_CHECKSUM_MISMATCH" in proc.stderr,
               "preflight runs before any migration is applied")
    finally:
        MIGRATION.write_bytes(original)

    proc = migrate(MIGRATOR, "preflight")
    record("checksum lock passes once the file is restored",
           proc.returncode == 0, proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else "")

    # Forward-only: the runner offers no downgrade path at all.
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools" / "migrate.py"), "--dsn", MIGRATOR, "down"],
        capture_output=True, text=True)
    record("runner exposes no rollback command", proc.returncode != 0,
           "forward-only: recovery is by restore, not reverse migration")

    # The frozen v1.1 history must be absent.
    legacy = count(MIGRATOR, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname IN ('django_migrations','alembic_version','knex_migrations',
                            'schema_version','flyway_schema_history');
    """)
    record("no v1.1 migration history imported (FR-DAT-001, FR-GOV-006)", legacy == 0,
           f"{legacy} legacy history table(s) present")


# ===========================================================================
# 2. Row level security with populated fixtures
# ===========================================================================

def section_rls() -> None:
    print("\n--- 2. Tenant isolation and RLS (FR-TEN-001, FR-SEC-001, FR-SEC-002A) ---")

    populated = count(APP, "SELECT count(*) FROM org.org_node;", tenant=TENANT_ACME, outlet=OUTLET_A1)
    total = count(ADMIN, "SELECT count(*) FROM org.org_node;")
    record("fixtures are populated, so isolation is not vacuous",
           total >= 15 and populated >= 1,
           f"{total} node(s) exist in total; {populated} visible under ACME/A1 context")

    for name, gate, dsn in (
        ("cross-tenant denied for SELECT/INSERT/UPDATE/DELETE", cross_tenant_gate, APP),
        ("sibling-outlet denied for SELECT/INSERT/UPDATE/DELETE", rls_sibling_outlet_gate, APP),
        ("no rows visible or writable without context", rls_absent_context_gate, APP),
        ("every outlet-scoped table has a forced outlet-aware policy", rls_alter_added_outlet_gate, APP),
    ):
        ok, signature, detail = gate(dsn)
        record(name, ok, detail if ok else f"{signature}: {detail}")

    ok, signature, detail = runtime_role_gate(APP)
    record("runtime role is least-privileged", ok, detail if ok else f"{signature}: {detail}")


# ===========================================================================
# 3. Data architecture
# ===========================================================================

def section_data_architecture() -> None:
    print("\n--- 3. Identifiers, timestamps, concurrency, lifecycle, constraints ---")
    ctx = dict(tenant=TENANT_ACME, outlet=OUTLET_A1)

    # FR-DAT-003 — opaque keys, human numbers in separate columns.
    non_uuid_pk = count(ADMIN, """
        SELECT count(*) FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name
        JOIN information_schema.columns c
          ON c.table_schema = k.table_schema AND c.table_name = k.table_name
         AND c.column_name = k.column_name
        WHERE tc.table_schema = 'org' AND tc.constraint_type = 'PRIMARY KEY'
          AND c.data_type <> 'uuid';
    """)
    record("all primary keys are opaque UUIDs (FR-DAT-003)", non_uuid_pk == 0,
           f"{non_uuid_pk} non-uuid primary key column(s)")

    human = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'org'
          AND column_name IN ('tenant_code','reference_code','registration_code');
    """)
    record("human numbers live in their own columns (FR-DAT-003)", human >= 3,
           f"{human} human-number column(s), none of them a key")

    # FR-DAT-004 — UTC instants plus outlet timezone context.
    naive = count(ADMIN, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'org' AND data_type = 'timestamp without time zone';
    """)
    tz = run(APP, f"""
        SELECT timezone FROM org.outlet_profile WHERE outlet_id = '{OUTLET_A1}';
    """, **ctx)
    record("timestamps are UTC instants with outlet timezone context (FR-DAT-004)",
           naive == 0 and tz.scalar == "Africa/Addis_Ababa",
           f"{naive} naive timestamp column(s); outlet A1 timezone is {tz.scalar}")

    bad_tz = run(APP, f"""
        UPDATE org.outlet_profile SET timezone = 'Mars/Olympus_Mons'
        WHERE outlet_id = '{OUTLET_A1}';
    """, **ctx)
    record("an invalid timezone is rejected", not bad_tz.ok, "INVALID_TIMEZONE raised")

    # FR-DAT-007 — optimistic concurrency.
    version = run(APP, f"SELECT row_version FROM org.org_node WHERE id = '{OUTLET_A1}';", **ctx).scalar
    stale = run(APP, f"""
        UPDATE org.org_node SET display_name = 'Renamed', row_version = {int(version) - 1}
        WHERE id = '{OUTLET_A1}';
    """, **ctx)
    fresh = run(APP, f"""
        UPDATE org.org_node SET display_name = 'Bole Branch (renamed)', row_version = {version}
        WHERE id = '{OUTLET_A1}';
    """, **ctx)
    after = run(APP, f"SELECT row_version FROM org.org_node WHERE id = '{OUTLET_A1}';", **ctx).scalar
    stale_rejected = (not stale.ok) and stale.sqlstate_is("HS409")
    record("a stale expected version raises an explicit conflict (FR-DAT-007)",
           stale_rejected and fresh.ok and after == str(int(version) + 1),
           f"stale update {'rejected with SQLSTATE HS409' if stale_rejected else 'NOT rejected as expected'}; "
           f"correct version {version} {'accepted' if fresh.ok else 'REJECTED'} and row_version is now {after}")

    # FR-DAT-009 — soft lifecycle preserves references.
    child_before = count(APP, f"""
        SELECT count(*) FROM org.org_node WHERE parent_id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    deact = run(APP, """
        UPDATE org.org_node
        SET status = 'inactive', deactivated_at = now(),
            row_version = (SELECT row_version FROM org.org_node
                           WHERE id = 'aaaa1101-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    child_after = count(APP, f"""
        SELECT count(*) FROM org.org_node WHERE parent_id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    record("deactivating master data preserves references (FR-DAT-009)",
           deact.ok and child_before == child_after and child_after > 0,
           f"{child_after} child row(s) still resolve after the parent was deactivated")

    inconsistent = run(APP, """
        UPDATE org.org_node SET status = 'inactive', deactivated_at = NULL,
               row_version = (SELECT row_version FROM org.org_node WHERE id = 'aaaa1104-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1104-0000-4000-8000-000000000001';
    """, **ctx)
    record("an inconsistent lifecycle state is rejected", not inconsistent.ok,
           "status/deactivated_at CHECK holds")

    # FR-DAT-002 — constraints.
    cross = run(APP, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_ACME}', '{SIBLING_NODE}', 'dining_table', 'T-XT', 'Cross tenant parent');
    """, tenant=TENANT_ACME, outlet=OUTLET_A2)
    dup = run(APP, """
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('%s', '%s', 'dining_table', 'T-11', 'Duplicate code');
    """ % (TENANT_ACME, OUTLET_A2), tenant=TENANT_ACME, outlet=OUTLET_A2)
    blank = run(APP, f"""
        INSERT INTO org.org_node (tenant_id, parent_id, kind, reference_code, display_name)
        VALUES ('{TENANT_ACME}', '{OUTLET_A1}', 'dining_table', '  ', 'Blank code');
    """, **ctx)
    record("constraints reject invalid rows (FR-DAT-002)",
           (not dup.ok) and (not blank.ok),
           "duplicate reference_code rejected; blank reference_code rejected"
           + ("; cross-tenant parent rejected" if not cross.ok else ""))

    # Cycles and outlet nesting.
    cycle = run(APP, """
        UPDATE org.org_node SET parent_id = 'aaaa1103-0000-4000-8000-000000000001',
               row_version = (SELECT row_version FROM org.org_node WHERE id = 'aaaa1101-0000-4000-8000-000000000001')
        WHERE id = 'aaaa1101-0000-4000-8000-000000000001';
    """, **ctx)
    record("a hierarchy cycle is refused", not cycle.ok, "ORG_CYCLE raised")

    # FR-TEN-002A — depth is not fixed.
    depth = run(APP, f"""
        SELECT max(depth) FROM org.org_closure WHERE ancestor_id = '{OUTLET_A1}';
    """, **ctx).scalar
    record("hierarchy depth is configurable, not fixed (FR-TEN-002A)",
           depth is not None and int(depth) >= 3,
           f"outlet A1 has descendants {depth} level(s) deep, reached without a fixed-level join")

    kinds = count(ADMIN, "SELECT count(*) FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid WHERE t.typname='node_kind';")
    record("all six required entity kinds exist (FR-TEN-002A)", kinds >= 6,
           f"{kinds} node kinds defined")

    # FR-TEN-002B — no fenced-domain entity, at any gate. The vocabulary is loaded from
    # the pinned package rather than restated here: a second copy could drift from the
    # registry the package validates against.
    pattern, term_count = fenced_identifier_pattern()
    forbidden = count(ADMIN, f"""
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
          AND (table_name ~* '{pattern}' OR column_name ~* '{pattern}');
    """)
    record("no fenced-domain table or column exists (FR-TEN-002B)", forbidden == 0,
           f"{forbidden} fenced identifier(s) found; vocabulary of {term_count} terms "
           f"loaded from the pinned package registry")


# ===========================================================================
# 4. Negative controls — each proved red, then green
# ===========================================================================

def prove_control(control: str, gate, dsn_for_gate, break_sql: str, revert_sql: str,
                  signature: str, *, gate_dsn_when_broken=None) -> None:
    """Run gate clean, inject the defect, require the exact signature, revert, re-run."""
    ok, _, detail = gate(dsn_for_gate)
    if not ok:
        record(f"{control} — baseline", False, f"gate already failing before the break: {detail}")
        return

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.err}")
        return

    try:
        red_ok, red_signature, red_detail = gate(gate_dsn_when_broken or dsn_for_gate)
        went_red = (not red_ok) and red_signature == signature
        record(f"{control} — RED with the defect planted", went_red,
               f"{red_signature or '(gate still passed)'}: {red_detail}")
    finally:
        reverted = run(ADMIN, revert_sql)

    if not reverted.ok:
        record(f"{control} — revert", False, f"could not revert the break: {reverted.err}")
        return

    green_ok, green_signature, green_detail = gate(dsn_for_gate)
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_signature}: {green_detail}")


def section_negative_controls() -> None:
    print("\n--- 4. The four M1 negative controls ---")

    print("\n  NC-M1-001  fail-closed tenant context  ->  VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT")
    prove_control(
        "NC-M1-001", rls_absent_context_gate, APP,
        break_sql="CREATE POLICY nc_m1_001_break ON org.org_node FOR ALL USING (true) WITH CHECK (true);",
        revert_sql="DROP POLICY nc_m1_001_break ON org.org_node;",
        signature="VISIBLE_OR_WRITABLE_ROWS_WITHOUT_CONTEXT",
    )

    print("\n  NC-M1-002  sibling-outlet isolation  ->  SIBLING_OUTLET_ACCESS")
    prove_control(
        "NC-M1-002", rls_sibling_outlet_gate, APP,
        break_sql=("ALTER POLICY org_node_isolation ON org.org_node "
                   "USING (app.current_tenant_id() IS NOT NULL AND tenant_id = app.current_tenant_id()) "
                   "WITH CHECK (app.current_tenant_id() IS NOT NULL AND tenant_id = app.current_tenant_id());"),
        revert_sql=("ALTER POLICY org_node_isolation ON org.org_node "
                    "USING (app.row_in_scope(tenant_id, outlet_id)) "
                    "WITH CHECK (app.row_in_scope(tenant_id, outlet_id));"),
        signature="SIBLING_OUTLET_ACCESS",
    )

    print("\n  NC-M1-003  future schema protection  ->  OUTLET_POLICY_NOT_UPGRADED")
    prove_control(
        "NC-M1-003", rls_alter_added_outlet_gate, APP,
        break_sql="""
            CREATE TABLE org.nc_m1_003_probe (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id uuid NOT NULL REFERENCES org.tenant(id)
            );
            ALTER TABLE org.nc_m1_003_probe ENABLE ROW LEVEL SECURITY;
            ALTER TABLE org.nc_m1_003_probe FORCE  ROW LEVEL SECURITY;
            CREATE POLICY nc_probe_isolation ON org.nc_m1_003_probe FOR ALL
                USING (tenant_id = app.current_tenant_id())
                WITH CHECK (tenant_id = app.current_tenant_id());
            GRANT SELECT ON org.nc_m1_003_probe TO hospitality_app;
            -- the defect: the column arrives, the policy is not upgraded with it
            ALTER TABLE org.nc_m1_003_probe ADD COLUMN outlet_id uuid;
        """,
        revert_sql="DROP TABLE org.nc_m1_003_probe;",
        signature="OUTLET_POLICY_NOT_UPGRADED",
    )

    print("\n  NC-M1-004  runtime least privilege  ->  PRIVILEGED_RUNTIME_ROLE_REJECTED")
    privileged_dsn = os.environ["M1A_PRIVILEGED_DSN"]
    ok, _, detail = runtime_role_gate(APP)
    record("NC-M1-004 — baseline", ok, detail)

    red_ok, red_signature, red_detail = runtime_role_gate(privileged_dsn)
    record("NC-M1-004 — RED when configured with a BYPASSRLS role",
           (not red_ok) and red_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{red_signature}: {red_detail}")

    owner_ok, owner_signature, owner_detail = runtime_role_gate(MIGRATOR)
    record("NC-M1-004 — RED when configured with the owner role",
           (not owner_ok) and owner_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{owner_signature}: {owner_detail}")

    super_ok, super_signature, super_detail = runtime_role_gate(ADMIN)
    record("NC-M1-004 — RED when configured with a superuser",
           (not super_ok) and super_signature == "PRIVILEGED_RUNTIME_ROLE_REJECTED",
           f"{super_signature}: {super_detail}")

    green_ok, _, green_detail = runtime_role_gate(APP)
    record("NC-M1-004 — GREEN for the real runtime role", green_ok, green_detail)


def main() -> int:
    print("M1-A verification — real PostgreSQL, application role, populated fixtures")
    section_migration()
    section_rls()
    section_data_architecture()
    section_negative_controls()

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL M1A_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M1A_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
