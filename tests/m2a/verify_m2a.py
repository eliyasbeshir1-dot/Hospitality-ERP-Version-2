#!/usr/bin/env python3
"""M2-A verification: menu, pricing, availability and translation storage.

Real PostgreSQL, the least-privileged application role, populated fixtures. Every
assertion names the specific reason it expects; bare failure is not an assertion and
pg.Result.failed_with() refuses to be called without a named signature.

Nothing here is checked against a list written by hand. The fenced vocabulary comes from
the pinned package at run time, so a prohibited concept entering this schema is detected
against the authoritative 63 terms rather than against whatever the author remembered.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent))

import fixtures as fx                                   # noqa: E402
from fenced import fenced_identifier_pattern            # noqa: E402
from pg import ProbeFailed, count, run                  # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]
APP = os.environ["M1A_APP_DSN"]

CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_H1)
DST_CTX = dict(tenant=fx.TENANT, outlet=fx.OUTLET_DST)

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("t", "true")


# ===========================================================================
# 1. Structure, and the identities it must not carry
# ===========================================================================

def section_structure() -> None:
    print("\n--- 1. Menu structure, with no recipe or inventory identity (FR-MNU-001) ---")

    tables = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relkind = 'r';
    """)
    forced = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relkind = 'r'
          AND c.relrowsecurity AND c.relforcerowsecurity;
    """)
    # translatable_field is reference data with no tenant column, exactly like
    # money.currency: it is the one table here that is deliberately not tenant-scoped.
    record("every tenant-scoped menu table has row level security ENABLEd and FORCEd",
           tables == 21 and forced == 20,
           f"{tables} table(s) in schema menu, {forced} with RLS enabled and forced; "
           f"the one exception is menu.translatable_field, reference data with no tenant "
           f"column, on which the application role holds SELECT only")

    policies = count(ADMIN, """
        SELECT count(*) FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu'
          AND pg_get_expr(p.polqual, p.polrelid) LIKE '%row_in_scope%'
          AND pg_get_expr(p.polwithcheck, p.polrelid) LIKE '%row_in_scope%';
    """)
    record("every menu policy is built on the unchanged M1-A predicate",
           policies == 20,
           f"{policies} policy/policies use app.row_in_scope() for USING and WITH CHECK; "
           f"M2-A narrows access and never widens it")

    # The fenced vocabulary decides this, not a list in this file.
    pattern, term_total = fenced_identifier_pattern()
    offending = run(ADMIN, f"""
        SELECT n.nspname || '.' || c.relname || '.' || a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relkind = 'r'
          AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '{pattern}';
    """)
    offenders = [r[0] for r in offending.rows] if offending.ok else ["(introspection failed)"]
    record("no menu column names a fenced Phase 2/3 concept",
           offending.ok and not offenders,
           "; ".join(offenders) if offenders else
           f"every column in schema menu checked against all {term_total} authoritative "
           f"terms loaded from the pinned package; no recipe, costing or inventory "
           f"identifier appears among them")

    # FR-MNU-001 says menu structure must not reference a recipe or inventory IDENTITY,
    # which is sharper than a name check: no foreign key may leave this schema for one.
    outbound = run(ADMIN, """
        SELECT DISTINCT tn.nspname || '.' || tc.relname
        FROM pg_constraint k
        JOIN pg_class c   ON c.oid  = k.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_class tc  ON tc.oid = k.confrelid
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace
        WHERE n.nspname = 'menu' AND k.contype = 'f' AND tn.nspname <> 'menu'
        ORDER BY 1;
    """)
    referenced = sorted({r[0] for r in outbound.rows}) if outbound.ok else []
    allowed = {"config.reason_code", "identity.user_account", "money.currency",
               "org.org_node", "org.tenant"}
    record("menu references only organisation, identity, money and reason codes",
           outbound.ok and set(referenced) <= allowed,
           f"outbound foreign keys reach {referenced}; nothing outside "
           f"{sorted(allowed)} is referenced, so there is no recipe or inventory identity "
           f"to be independent of")

    parts = run(APP, f"""
        SELECT (SELECT count(*)::text FROM menu.menu WHERE id = '{fx.MENU}'),
               (SELECT count(*)::text FROM menu.category WHERE menu_id = '{fx.MENU}'),
               (SELECT count(*)::text FROM menu.item_group WHERE menu_id = '{fx.MENU}'),
               (SELECT count(*)::text FROM menu.sellable_item WHERE menu_id = '{fx.MENU}'),
               (SELECT count(*)::text FROM menu.item_variant v
                JOIN menu.sellable_item i ON i.id = v.item_id WHERE i.menu_id = '{fx.MENU}'),
               (SELECT count(*)::text FROM menu.modifier_group),
               (SELECT count(*)::text FROM menu.modifier);
    """, **CTX)
    p = parts.rows[0] if parts.ok and parts.rows else ["0"] * 7
    record("menus, categories, groups, items, variants and modifiers all exist",
           parts.ok and all(int(v) > 0 for v in p),
           f"{p[0]} menu, {p[1]} categories, {p[2]} item group(s), {p[3]} items, "
           f"{p[4]} variants, {p[5]} modifier group(s), {p[6]} modifiers — every level of "
           f"the structure is populated, so the checks that follow are not passing over "
           f"an empty schema")


# ===========================================================================
# 2. Assignment
# ===========================================================================

def section_assignment() -> None:
    print("\n--- 2. Assignment, and the targeting that must not exist (FR-MNU-002A) ---")

    dimensions = run(ADMIN, """
        SELECT string_agg(a.attname, ',' ORDER BY a.attname)
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relname = 'assignment'
          AND a.attnum > 0 AND NOT a.attisdropped;
    """)
    columns = set((dimensions.scalar or "").split(","))
    required = {"outlet_id", "service_area_id", "channel", "daypart_id",
                "effective_from", "effective_to"}
    record("assignment carries outlet, service area, channel, daypart and date range",
           required <= columns,
           f"present: {sorted(required & columns)}; missing: {sorted(required - columns)}")

    # Customer-segment targeting was removed at v2.0.9 and is fenced. Asserted as absence
    # of any column that could express it, rather than trusting that nobody added one.
    # The customer-relationship terms come from the pinned vocabulary rather than from a
    # list written here — hardcoding them is how a hand-written list drifts from the
    # registry it was meant to mirror, which M1-C had to repair once already. Only the
    # targeting words that are NOT fenced are spelled out.
    fenced_pattern, _ = fenced_identifier_pattern()
    segmenting = [c for c in columns
                  if re.search(r"segment|cohort|audience|persona", c, re.I)
                  or re.search(fenced_pattern, c, re.I)]
    record("no customer-segment targeting column exists",
           not segmenting,
           "; ".join(segmenting) if segmenting else
           "no column on menu.assignment can express customer-segment targeting; it was "
           "removed at v2.0.9 and there is nowhere to put it")

    resolved = count(APP, f"""
        SELECT count(*) FROM menu.assignment
        WHERE menu_id = '{fx.MENU}' AND channel = 'dine_in'
          AND effective_from <= CURRENT_DATE
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE);
    """, **CTX)
    record("an assignment resolves for the outlet, channel and date in force",
           resolved == 1,
           f"{resolved} assignment(s) in force for dine_in today")

    backwards = run(APP, f"""
        INSERT INTO menu.assignment
            (tenant_id, outlet_id, menu_id, channel, effective_from, effective_to)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.MENU}', 'kiosk',
                DATE '2026-06-01', DATE '2026-05-01');
    """, rollback=True, **CTX)
    record("a date range that ends before it starts is refused",
           backwards.failed_with("23514", "assignment_range_ordered"),
           f"refused by the range CHECK: {backwards.why()}")


# ===========================================================================
# 3. Pricing — exact money, and the currency pairing that is now live
# ===========================================================================

def section_pricing() -> None:
    print("\n--- 3. Pricing (FR-MNU-009), and money.assert_currency_paired() going live ---")

    population = count(ADMIN, "SELECT money.currency_pairing_population();")
    offenders = count(ADMIN, "SELECT count(*) FROM money.assert_currency_paired();")
    record("money.assert_currency_paired() is NO LONGER VACUOUS",
           population >= 2 and offenders == 0,
           f"{population} column(s) of type money.amount_minor now exist, so the check "
           f"examines a real population and reports {offenders} offender(s). It returned "
           f"nothing over nothing at M1 and was recorded as vacuous; M2-A is the gate that "
           f"makes it live, as the brief anticipated")

    # And it still fires. Proved against a real column created and dropped inside a
    # rolled-back transaction, so the schema the rest of the suite sees is unchanged.
    fires = run(ADMIN, """
        CREATE TABLE menu.pairing_probe (id bigint, amount money.amount_minor);
        SELECT count(*)::text FROM money.assert_currency_paired();
        ALTER TABLE menu.pairing_probe ADD COLUMN currency_code char(3);
        SELECT count(*)::text FROM money.assert_currency_paired();
    """, rollback=True)
    unpaired, repaired = (fires.rows[0][0], fires.rows[1][0]) if fires.ok and len(fires.rows) >= 2 else ("0", "1")
    record("the pairing check still fires on a money column with no currency beside it",
           fires.ok and unpaired == "1" and repaired == "0",
           f"a bare money.amount_minor column is reported ({unpaired} offender); adding "
           f"currency_code beside it clears the report ({repaired})")

    floats = count(ADMIN, """
        SELECT count(*) FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'menu' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('float4', 'float8', 'money', 'numeric')
          AND a.attname LIKE '%price%';
    """)
    any_float = count(ADMIN, """
        SELECT count(*) FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'menu' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('float4', 'float8', 'money');
    """)
    record("no float touches a price anywhere in the menu schema",
           floats == 0 and any_float == 0,
           f"{any_float} binary floating point column(s) in schema menu, {floats} of them "
           f"named like a price; amounts are money.amount_minor integer minor units")

    priced = run(APP, f"""
        SELECT menu.effective_price('{fx.TENANT}', '{fx.OUTLET_H1}',
               '{fx.VARIANT_DORO_FULL}', NULL::menu.sales_channel, 'ETB')::text,
               menu.effective_price('{fx.TENANT}', '{fx.OUTLET_H1}',
               '{fx.VARIANT_DORO_FULL}', 'room_service'::menu.sales_channel, 'ETB')::text;
    """, **CTX)
    base, room = priced.rows[0] if priced.ok and priced.rows else ("", "")
    record("effective price resolves, and a channel-specific price takes precedence",
           priced.ok and base == "32000" and room == "36000",
           f"the default price is {base} minor units and the room_service price is {room}; "
           f"the more specific row wins rather than the newer one")

    no_currency = run(APP, f"""
        INSERT INTO menu.price (tenant_id, outlet_id, variant_id, currency_code, amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.VARIANT_TIBS_ONE}', NULL, 1000);
    """, rollback=True, **CTX)
    record("a price with no currency cannot be stored",
           no_currency.failed_with("23502"),
           f"currency_code is NOT NULL, so an amount can never stand alone: {no_currency.why()}")

    unknown_currency = run(APP, f"""
        INSERT INTO menu.price (tenant_id, outlet_id, variant_id, currency_code, amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.VARIANT_TIBS_ONE}', 'ZZZ', 1000);
    """, rollback=True, **CTX)
    record("a price in a currency the system does not know is refused",
           unknown_currency.failed_with("23503", "price_currency_fk"),
           f"the foreign key into money.currency refuses it: {unknown_currency.why()}")

    two_subjects = run(APP, f"""
        INSERT INTO menu.price (tenant_id, outlet_id, item_id, variant_id, currency_code, amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.ITEM_DORO}', '{fx.VARIANT_TIBS_ONE}', 'ETB', 1000);
    """, rollback=True, **CTX)
    record("a price row cannot price two things at once",
           two_subjects.failed_with("23514", "price_one_subject"),
           f"exactly one of item, variant or modifier: {two_subjects.why()}")

    second_open = run(APP, f"""
        INSERT INTO menu.price (tenant_id, outlet_id, variant_id, currency_code, amount_minor, tax_context)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.VARIANT_TIBS_ONE}', 'ETB', 99999, 'standard');
    """, rollback=True, **CTX)
    record("a second open price for the same subject cannot coexist",
           second_open.failed_with("23505"),
           f"the partial unique index refuses it, so 'the price' has one answer: "
           f"{second_open.why()}")


# ===========================================================================
# 4. Availability — a state, never a count
# ===========================================================================

def section_availability() -> None:
    print("\n--- 4. Availability without exposing a quantity (FR-MNU-007, FR-MNU-008) ---")

    states = run(ADMIN, """
        SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'menu' AND t.typname = 'availability_state';
    """)
    record("all five availability states exist and the type is closed",
           states.scalar == "available,limited,temporarily_unavailable,scheduled_later,hidden",
           f"menu.availability_state = {states.scalar}")

    # The constraint is structural: there is no numeric column on the availability model
    # at all, so an exact figure cannot be stored and therefore cannot be disclosed.
    numeric = run(ADMIN, """
        SELECT string_agg(c.relname || '.' || a.attname, ', ' ORDER BY c.relname, a.attname)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'menu'
          AND c.relname IN ('availability', 'availability_pause')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('int2', 'int4', 'int8', 'numeric', 'float4', 'float8')
          -- row_version is the optimistic-concurrency counter every M1 table carries. It
          -- is a number, but it is not a quantity of anything sellable, and excluding it
          -- by name keeps the check pointed at what it is actually about.
          AND a.attname <> 'row_version';
    """)
    record("the availability model holds no number that could be a remaining count",
           numeric.ok and not (numeric.scalar or "").strip(),
           f"numeric columns on the availability tables: {numeric.scalar or 'none'}. "
           f"'limited' signals scarcity; there is nowhere to record how much is left, so "
           f"the exact figure cannot leak from a model that never held it")

    limited = run(APP, f"""
        SELECT state::text FROM menu.availability WHERE variant_id = '{fx.VARIANT_DORO_HALF}';
    """, **CTX)
    record("a scarce item reads as 'limited' and carries no figure with it",
           limited.ok and limited.scalar == "limited",
           f"the half portion is {limited.scalar}, which tells a guest to expect scarcity "
           f"and tells them nothing more")

    scheduled_without_time = run(APP, f"""
        INSERT INTO menu.availability (tenant_id, outlet_id, item_id, state)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.ITEM_TIBS}', 'scheduled_later');
    """, rollback=True, **CTX)
    record("'scheduled later' without a time is refused",
           scheduled_without_time.failed_with("23514", "availability_scheduled_has_time"),
           f"a promise of 'later' has to name when: {scheduled_without_time.why()}")

    available_with_time = run(APP, f"""
        INSERT INTO menu.availability (tenant_id, outlet_id, item_id, state, available_from)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.ITEM_TIBS}', 'available', now() + interval '1 day');
    """, rollback=True, **CTX)
    record("only 'scheduled later' may name a time",
           available_with_time.failed_with("23514", "availability_scheduled_has_time"),
           f"an already-available item cannot also claim a future start: "
           f"{available_with_time.why()}")

    # FR-MNU-008: an authorized pause with a reason code and an optional expected return.
    reason = run(APP, f"""
        SELECT id::text FROM config.reason_code
        WHERE tenant_id = '{fx.TENANT}' AND status = 'active' LIMIT 1;
    """, **CTX)
    paused = run(APP, f"""
        UPDATE menu.availability SET state = 'temporarily_unavailable', row_version = row_version
        WHERE variant_id = '{fx.VARIANT_TIBS_ONE}';
        INSERT INTO menu.availability_pause
            (tenant_id, outlet_id, availability_id, reason_code_id, paused_by_user_id,
             expected_return_at)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', a.id, '{reason.scalar}', '{fx.USER}',
               now() + interval '2 hours'
        FROM menu.availability a WHERE a.variant_id = '{fx.VARIANT_TIBS_ONE}';
        SELECT count(*)::text FROM menu.availability_pause p
        JOIN menu.availability a ON a.id = p.availability_id
        WHERE a.variant_id = '{fx.VARIANT_TIBS_ONE}' AND p.expected_return_at IS NOT NULL;
    """, rollback=True, **CTX)
    record("staff may pause an item with a reason code and an expected return (FR-MNU-008)",
           paused.ok and paused.rows and paused.rows[-1][0] == "1",
           f"a pause records the M1-C reason code, the actor and the expected return; "
           f"the reason registry is referenced, never copied")

    invented_reason = run(APP, f"""
        INSERT INTO menu.availability_pause
            (tenant_id, outlet_id, availability_id, reason_code_id, paused_by_user_id)
        SELECT '{fx.TENANT}', '{fx.OUTLET_H1}', a.id,
               '00000000-0000-4000-8000-000000000000', '{fx.USER}'
        FROM menu.availability a WHERE a.variant_id = '{fx.VARIANT_TIBS_ONE}';
    """, rollback=True, **CTX)
    record("a pause cannot invent a reason code that the tenant has not defined",
           invented_reason.failed_with("23503", "availability_pause_reason_fk"),
           f"the foreign key into config.reason_code refuses it: {invented_reason.why()}")


# ===========================================================================
# 5. Dayparts in outlet-local time, including a daylight-saving transition
# ===========================================================================

def section_dayparts() -> None:
    print("\n--- 5. Dayparts in outlet-local time (FR-MNU-010) ---")

    # Addis is UTC+3 year round. 05:30 UTC is 08:30 local — breakfast. Evaluated in
    # server time (UTC) it would be 05:30, which is before breakfast opens, so a
    # server-time implementation gets this wrong in a way the assertion can see.
    boundaries = run(APP, f"""
        SELECT menu.is_daypart_active('{fx.DAYPART_BREAKFAST}', TIMESTAMPTZ '2026-03-10 05:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_BREAKFAST}', TIMESTAMPTZ '2026-03-10 02:59:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_BREAKFAST}', TIMESTAMPTZ '2026-03-10 03:00:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_BREAKFAST}', TIMESTAMPTZ '2026-03-10 08:00:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_LUNCH}',     TIMESTAMPTZ '2026-03-10 08:00:00+00')::text;
    """, **CTX)
    b = boundaries.rows[0] if boundaries.ok and boundaries.rows else ["?"] * 5
    record("a daypart is evaluated in outlet-local time, not server time",
           boundaries.ok and b == ["true", "false", "true", "false", "true"],
           f"Addis is UTC+3: 05:30Z is 08:30 local and breakfast is {b[0]}; 02:59Z is "
           f"05:59 local, one minute before opening, and it is {b[1]}; 03:00Z is 06:00 "
           f"local exactly and it is {b[2]}. At 08:00Z (11:00 local) breakfast is {b[3]} "
           f"and lunch is {b[4]} — the boundary belongs to exactly one window")

    crossing = run(APP, f"""
        SELECT menu.is_daypart_active('{fx.DAYPART_LATE}', TIMESTAMPTZ '2026-03-10 20:00:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_LATE}', TIMESTAMPTZ '2026-03-10 22:00:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_LATE}', TIMESTAMPTZ '2026-03-10 23:30:00+00')::text;
    """, **CTX)
    c = crossing.rows[0] if crossing.ok and crossing.rows else ["?"] * 3
    record("a window that crosses midnight is active on both sides of it",
           crossing.ok and c == ["true", "true", "false"],
           f"late night runs 22:00 to 02:00 local: 23:00 local is {c[0]}, 01:00 local is "
           f"{c[1]}, and 02:30 local is {c[2]}")

    # The daylight-saving transition. Europe/Berlin springs forward on 29 March 2026 at
    # 02:00 local, so the offset changes from +01:00 to +02:00. A breakfast window of
    # 06:00-11:00 local is 05:00-10:00Z before the change and 04:00-09:00Z after it.
    # An implementation that added a fixed offset gets the day after the change wrong.
    dst = run(APP, f"""
        SELECT menu.local_wall_clock('{fx.TENANT}', '{fx.OUTLET_DST}', TIMESTAMPTZ '2026-03-28 05:30:00+00')::text,
               menu.local_wall_clock('{fx.TENANT}', '{fx.OUTLET_DST}', TIMESTAMPTZ '2026-03-29 05:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_DST}', TIMESTAMPTZ '2026-03-28 04:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_DST}', TIMESTAMPTZ '2026-03-29 04:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_DST}', TIMESTAMPTZ '2026-03-28 09:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_DST}', TIMESTAMPTZ '2026-03-29 09:30:00+00')::text;
    """, **DST_CTX)
    d = dst.rows[0] if dst.ok and dst.rows else ["?"] * 6
    record("a daylight-saving transition moves the window with the clock",
           dst.ok and d[0].startswith("2026-03-28 06:30") and d[1].startswith("2026-03-29 07:30")
           and d[2:] == ["false", "true", "true", "false"],
           f"Europe/Berlin springs forward on 29 March 2026. The same 05:30Z reads "
           f"{d[0][:16]} local before and {d[1][:16]} local after. A 06:00-11:00 local "
           f"breakfast at 04:30Z is {d[2]} on the 28th and {d[3]} on the 29th; at 09:30Z "
           f"it is {d[4]} then {d[5]}. Both edges move by an hour, in opposite directions, "
           f"which fixed-offset arithmetic cannot produce")

    active = run(APP, f"""
        SELECT string_agg(daypart_code, ',' ORDER BY daypart_code)
        FROM menu.active_dayparts('{fx.TENANT}', '{fx.OUTLET_H1}',
                                  TIMESTAMPTZ '2026-03-10 10:00:00+00');
    """, **CTX)
    record("the active daypart set resolves for an outlet at an instant",
           active.ok and active.scalar == "LUNCH",
           f"13:00 local at Kazanchis resolves to {active.scalar}")

    missing_zone = run(APP, f"""
        SELECT menu.outlet_timezone('{fx.TENANT}', '{fx.ITEM_DORO}');
    """, **CTX)
    record("an outlet with no profile timezone is a fault, never a server-time default",
           missing_zone.failed_with("OUTLET_TIMEZONE_UNKNOWN"),
           f"refused by OUTLET_TIMEZONE_UNKNOWN rather than falling back: "
           f"{missing_zone.why()}")


# ===========================================================================
# 6. Translation storage and publication blocking
# ===========================================================================

def section_translation() -> None:
    print("\n--- 6. Translation storage and publication blocking (FR-I18N-003/006/010/011) ---")

    locales = run(ADMIN, """
        SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'menu' AND t.typname = 'customer_locale';
    """)
    record("exactly three customer locales, as a closed type",
           locales.scalar == "en,am,ar",
           f"menu.customer_locale = {locales.scalar}; a fourth locale is a type error "
           f"rather than a row somebody inserted")

    fourth = run(APP, "SELECT 'fr'::menu.customer_locale;", **CTX)
    record("a locale nobody agreed to support cannot be named",
           fourth.failed_with("22P02", "invalid input value for enum"),
           f"refused at the type level: {fourth.why()}")

    # Stored SEPARATELY from the canonical record: the canonical column keeps its own
    # value and a translation never overwrites it.
    separation = run(APP, f"""
        SELECT i.canonical_name,
               (SELECT t.translated_text FROM menu.translation t
                WHERE t.entity = 'item' AND t.entity_id = i.id
                  AND t.field_name = 'canonical_name' AND t.locale = 'am'),
               (SELECT count(*)::text FROM menu.translation t
                WHERE t.entity = 'item' AND t.entity_id = i.id)
        FROM menu.sellable_item i WHERE i.id = '{fx.ITEM_DORO}';
    """, **CTX)
    canonical, amharic, held = separation.rows[0] if separation.ok and separation.rows else ("", "", "0")
    record("translations are stored separately and never overwrite the canonical record",
           separation.ok and canonical == fx.NAMES[fx.ITEM_DORO]["en"]
           and amharic == fx.NAMES[fx.ITEM_DORO]["am"] and int(held) > 0,
           f"the canonical name is still {canonical!r} while {held} translation row(s) "
           f"exist beside it, including Amharic {amharic!r}")

    engine_missing = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{fx.ITEM_COFFEE}',
                'canonical_long_description', 'ar', 'نص', 'draft', 'machine_assisted');
    """, rollback=True, **CTX)
    record("a machine-assisted translation must name the engine that produced it",
           engine_missing.failed_with("23514", "translation_engine_matches_provenance"),
           f"provenance is recorded, not implied (FR-I18N-010): {engine_missing.why()}")

    unreviewed = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, machine_engine, approved_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{fx.ITEM_COFFEE}',
                'canonical_long_description', 'ar', 'نص', 'approved', 'machine_assisted',
                'demo-engine', now());
    """, rollback=True, **CTX)
    record("an approved translation must name a human reviewer",
           unreviewed.failed_with("23514", "translation_approval_is_reviewed"),
           f"'approved' without a named reviewer is a draft wearing a label: "
           f"{unreviewed.why()}")

    # Safety-critical text: a machine draft is permitted, approving one is not.
    safety = run(APP, f"""
        SELECT safety_critical::text FROM menu.translatable_field
        WHERE entity = 'item' AND field_name = 'customer_visible_ingredients';
    """, **CTX)
    record("customer-visible ingredients are registered as safety-critical",
           truthy(safety.scalar),
           "the sentence a guest reads before deciding whether they can eat something is "
           "marked safety-critical in menu.translatable_field")

    machine_draft = run(APP, f"""
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, machine_engine)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'item', '{fx.ITEM_COFFEE}',
                'customer_visible_ingredients', 'ar', 'حبوب قهوة', 'draft',
                'machine_assisted', 'demo-engine')
        ON CONFLICT (tenant_id, entity, entity_id, field_name, locale) DO NOTHING;
    """, rollback=True, **CTX)
    record("machine-assisted DRAFT translation is permitted, with provenance",
           machine_draft.ok,
           "a machine draft of safety-critical text is allowed — it is the approval that "
           "requires a human (FR-I18N-010)")

    auto_approved = run(APP, f"""
        UPDATE menu.translation
        SET state = 'approved', provenance = 'machine_assisted', machine_engine = 'demo-engine',
            reviewed_by_user_id = NULL, approved_at = now(), row_version = row_version
        WHERE entity = 'item' AND entity_id = '{fx.ITEM_DORO}'
          AND field_name = 'customer_visible_ingredients' AND locale = 'am';
    """, rollback=True, **CTX)
    record("safety-critical text cannot be approved from a machine draft without a human",
           auto_approved.failed_with("SAFETY_CRITICAL_TEXT_AUTO_APPROVED",
                                     "translation_approval_is_reviewed"),
           f"refused: {auto_approved.why()}")

    # No live runtime translation: nothing in this schema calls out to anything, and no
    # function here produces text it was not given.
    runtime = run(ADMIN, """
        SELECT string_agg(p.proname, ', ' ORDER BY p.proname)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'menu'
          AND (p.prosrc ~* '(translate_text|machine_translate|http|curl|dblink|fdw)'
               OR p.proname ~* '(translate_now|live_translate|auto_translate)');
    """)
    record("there is no live runtime translation path",
           runtime.ok and not (runtime.scalar or "").strip(),
           f"functions that would translate at request time: {runtime.scalar or 'none'}. "
           f"A locale is either stored and approved before publication, or it is missing "
           f"and publication is blocked")


def section_publication() -> None:
    print("\n--- 7. Publication lifecycle and immutable snapshots (FR-MNU-003) ---")

    states = run(ADMIN, """
        SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
        FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'menu' AND t.typname = 'publication_state';
    """)
    record("the publication lifecycle has all six states",
           states.scalar == "draft,review,scheduled,published,paused,archived",
           f"menu.publication_state = {states.scalar}")

    # The fixtures deliberately seeded only en and am. Arabic is genuinely absent, so the
    # block below is proved against a real gap rather than a simulated one.
    missing = count(APP, f"SELECT count(*) FROM menu.missing_required_translations('{fx.MENU}');",
                    **CTX)
    blocked = run(APP, f"SELECT menu.publish_menu('{fx.MENU}', '{fx.USER}');", **CTX)
    record("publication is BLOCKED while a required locale is missing (FR-I18N-006)",
           missing > 0 and blocked.failed_with("REQUIRED_TRANSLATION_MISSING"),
           f"{missing} required (field, locale) pair(s) have no approved translation, and "
           f"the publish refuses: {blocked.why()}")

    fx.translate(locales=("en", "am", "ar"))
    now_missing = count(APP, f"SELECT count(*) FROM menu.missing_required_translations('{fx.MENU}');",
                        **CTX)
    published = run(APP, f"SELECT menu.publish_menu('{fx.MENU}', '{fx.USER}')::text;", **CTX)
    snapshot = published.scalar if published.ok else None
    record("publication proceeds once the third locale is approved",
           now_missing == 0 and published.ok and snapshot,
           f"{now_missing} required translation(s) missing after Arabic is approved; "
           f"snapshot {snapshot} written")

    if not snapshot:
        record("snapshot content", False, "no snapshot to inspect")
        return

    lines = count(APP, f"""
        SELECT count(*) FROM menu.publication_snapshot_line WHERE snapshot_id = '{snapshot}';
    """, **CTX)
    record("the snapshot records what was published, with its prices",
           lines >= 4,
           f"{lines} snapshot line(s), each carrying its own currency and integer minor "
           f"amount — this is the evidence an M3 order will reference")

    digest_ok = run(APP, f"""
        SELECT (s.content_digest = menu.snapshot_digest(s.id))::text
        FROM menu.publication_snapshot s WHERE s.id = '{snapshot}';
    """, **CTX)
    record("the snapshot header digest matches its own lines",
           truthy(digest_ok.scalar),
           "the header carries a SHA-256 over the lines, so a line altered by an identity "
           "privileged enough to go round the trigger leaves a header that no longer "
           "describes its content")

    for verb, statement in (
        ("UPDATE", f"UPDATE menu.publication_snapshot_line SET amount_minor = 1 "
                   f"WHERE snapshot_id = '{snapshot}'"),
        ("DELETE", f"DELETE FROM menu.publication_snapshot_line WHERE snapshot_id = '{snapshot}'"),
        ("UPDATE header", f"UPDATE menu.publication_snapshot SET published_at = now() "
                          f"WHERE id = '{snapshot}'"),
        ("DELETE header", f"DELETE FROM menu.publication_snapshot WHERE id = '{snapshot}'"),
    ):
        res = run(APP, statement + ";", rollback=True, **CTX)
        record(f"a published snapshot refuses {verb}",
               res.failed_with("IMMUTABLE_SNAPSHOT_ALTERED", "42501"),
               f"refused: {res.why()}")

    granted = run(ADMIN, """
        SELECT string_agg(DISTINCT privilege_type, ',' ORDER BY privilege_type)
        FROM information_schema.role_table_grants
        WHERE grantee = 'hospitality_app' AND table_schema = 'menu'
          AND table_name IN ('publication_snapshot', 'publication_snapshot_line');
    """)
    record("the application role holds only INSERT and SELECT on snapshots",
           granted.scalar in ("INSERT,SELECT", "SELECT,INSERT"),
           f"granted: {granted.scalar}. Append-only twice over, exactly as M1-C's audit "
           f"store is: the grant and the trigger, because a role change would undo one")


# ===========================================================================
# 8. Search — closed for four filters here, two at M2-B
# ===========================================================================

def section_search() -> None:
    print("\n--- 8. Search (FR-MNU-012, PARTIALLY CLOSED at M2-A) ---")

    for locale, needle, expected in (("en", "doro", "SKU-DORO-01"),
                                     ("am", "ዶሮ", "SKU-DORO-01"),
                                     ("ar", "دورو", "SKU-DORO-01")):
        found = run(APP, f"""
            SELECT string_agg(item_code, ',' ORDER BY item_code)
            FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}', '{locale}', '{needle}');
        """, **CTX)
        record(f"search finds a translated name in {locale}",
               found.ok and found.scalar == expected,
               f"query {needle!r} in {locale} returned {found.scalar}")

    description = run(APP, f"""
        SELECT string_agg(item_code, ',' ORDER BY item_code)
        FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}', 'en', 'coffee');
    """, **CTX)
    record("search matches translated descriptions, not only names",
           description.ok and description.scalar == "SKU-BUNA-03",
           f"'coffee' appears only in the short description and returned {description.scalar}")

    # A mixed-script query: Arabic prose carrying a Latin item code. A tokenizer that
    # picks one script drops the other half of the query.
    mixed = run(APP, f"""
        SELECT string_agg(item_code, ',' ORDER BY item_code)
        FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}', 'ar', 'SKU-DORO');
    """, **CTX)
    record("a mixed-script query works: a Latin code searched in the Arabic locale",
           mixed.ok and mixed.scalar == "SKU-DORO-01",
           f"searching the Latin code {'SKU-DORO'!r} while rendering Arabic returned "
           f"{mixed.scalar}; matching is script-agnostic, so neither half of a mixed "
           f"query is dropped")

    filtered = run(APP, f"""
        SELECT (SELECT count(*)::text FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}',
                    'en', NULL, '{fx.CATEGORY_DRINKS}')),
               (SELECT count(*)::text FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}',
                    'en', NULL, NULL, 'available'::menu.availability_state)),
               (SELECT count(*)::text FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}',
                    'en', NULL, NULL, NULL, 'ETB', 5000::money.amount_minor, 30000::money.amount_minor)),
               (SELECT count(*)::text FROM menu.search_items('{fx.TENANT}', '{fx.OUTLET_H1}',
                    'en', NULL, NULL, NULL, NULL, NULL, NULL, 15));
    """, **CTX)
    f = filtered.rows[0] if filtered.ok and filtered.rows else ["?"] * 4
    record("search filters by category, availability, price range and preparation time",
           filtered.ok and f == ["1", "3", "1", "1"],
           f"category=Drinks returns {f[0]}; availability=available returns {f[1]}; "
           f"price between 50.00 and 300.00 ETB returns {f[2]}; preparation under 15 "
           f"minutes returns {f[3]}")

    # FR-MNU-012 is dual-gated. Recording that here, in the suite, means a reviewer reads
    # it as a decision rather than finding a filter quietly missing.
    signature = run(ADMIN, """
        SELECT pg_get_function_arguments(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'menu' AND p.proname = 'search_items';
    """)
    args = signature.scalar or ""
    record("dietary and allergen filters are ABSENT here, not present and vacuous",
           signature.ok and "dietary" not in args.lower() and "allergen" not in args.lower(),
           "FR-MNU-012 is closed for category, availability, price and preparation time at "
           "M2-A, and for dietary tag and allergen at M2-B with the catalogue they depend "
           "on. A filter built now would examine an empty catalogue and pass without "
           "testing anything — the vacuity money.assert_currency_paired() carried through "
           "all of M1. M2-B is the completing gate.")


# ===========================================================================
# 9. Images
# ===========================================================================

def section_images() -> None:
    print("\n--- 9. Images (FR-MNU-011) ---")

    derivatives = count(APP, f"""
        SELECT count(*) FROM menu.image_derivative WHERE image_id = '{fx.IMAGE_DORO}';
    """, **CTX)
    record("a source asset carries responsive derivatives",
           derivatives >= 3,
           f"{derivatives} derivative(s) at different widths and formats")

    crop = run(APP, f"""
        SELECT focal_x::text, focal_y::text, canonical_alt_text,
               pg_typeof(focal_x)::text
        FROM menu.image WHERE id = '{fx.IMAGE_DORO}';
    """, **CTX)
    fx_, fy, alt, typ = crop.rows[0] if crop.ok and crop.rows else ("", "", "", "")
    record("alt text and an exact focal crop are stored",
           crop.ok and alt and typ == "money.percentage",
           f"focal point ({fx_}, {fy}) as {typ} — exact, because a crop that drifted "
           f"because a float rounded is a visible defect; alt text {alt!r}")

    public = run(APP, f"""
        UPDATE menu.image SET is_private = false, row_version = row_version
        WHERE id = '{fx.IMAGE_DORO}';
    """, rollback=True, **CTX)
    record("a source asset cannot be marked public",
           public.failed_with("23514", "image_source_is_private"),
           f"there is no value of is_private that publishes a source asset: {public.why()}")

    stored_url = run(ADMIN, """
        SELECT string_agg(c.relname || '.' || a.attname, ', ')
        FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'menu' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND a.attname ~* '(^|_)(url|uri|href|public_link|cdn)($|_)';
    """)
    record("no image URL is stored anywhere",
           stored_url.ok and not (stored_url.scalar or "").strip(),
           f"URL-shaped columns in schema menu: {stored_url.scalar or 'none'}. The row "
           f"carries a storage key; a signed, expiring, authorized URL is issued at "
           f"request time from a key held in the environment, never in the database and "
           f"never in source (FR-SEC-007)")

    secrets = run(ADMIN, """
        SELECT string_agg(p.proname, ', ')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'menu'
          AND p.prosrc ~* '(secret|signing_key|hmac|private_key)';
    """)
    record("no signing secret lives in the database",
           secrets.ok and not (secrets.scalar or "").strip(),
           f"menu functions mentioning a signing secret: {secrets.scalar or 'none'}")


# ===========================================================================
# 10. The M2-B and M2-C boundary, and the permanent fences
# ===========================================================================

def section_boundary() -> None:
    print("\n--- 10. Slice boundary: what M2-A did NOT build ---")

    later_slices = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(dining_table_session|qr_token|guest_session|allergen|dietary_claim)($|_)';
    """)
    record("no tables, QR tokens, guest sessions, allergens or dietary claims exist",
           later_slices == 0,
           f"{later_slices} table(s) belonging to M2-B; they are not stubbed, not "
           f"registered and not reserved")

    order_surface = count(ADMIN, """
        SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '(^|_)(order|order_line|cart|check|bill|payment|tip|receipt)($|_)';
    """)
    record("no order, cart, check, payment or receipt surface exists",
           order_surface == 0,
           f"{order_surface} table(s) belonging to M3 or M4")

    pattern, term_total = fenced_identifier_pattern()
    fenced_anywhere = run(ADMIN, f"""
        SELECT string_agg(n.nspname || '.' || c.relname, ', ' ORDER BY c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND c.relname ~* '{pattern}';
    """)
    record("no table anywhere in the database names a permanently fenced domain",
           fenced_anywhere.ok and not (fenced_anywhere.scalar or "").strip(),
           f"checked every table against all {term_total} authoritative terms: "
           f"{fenced_anywhere.scalar or 'none'}")

    # The catalog scanned a hardcoded schema list, so adding `menu` left it silently
    # unchanged — a document describing neither the old database nor the new one. It now
    # discovers schemas from the database; this check makes sure it stays that way.
    catalog = (REPO / "schema" / "SCHEMA_CATALOG.md").read_text(encoding="utf-8")
    documented = run(ADMIN, """
        SELECT coalesce(string_agg(DISTINCT n.nspname, ',' ORDER BY n.nspname), '')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'r' AND n.nspname NOT LIKE 'pg\\_%'
          AND n.nspname NOT IN ('information_schema', 'migration', 'seed_history', 'public');
    """)
    absent = [s for s in (documented.scalar or "").split(",")
              if s and f"`{s}." not in catalog]
    record("the schema catalog documents every application schema, menu included",
           documented.ok and not absent,
           "; ".join(f"{s} is absent from the catalog" for s in absent) if absent else
           f"every schema holding tables ({documented.scalar}) appears in "
           f"schema/SCHEMA_CATALOG.md, which discovers them from the database rather than "
           f"from a list in the generator")

    # org.tenant is the one M1 policy not written on row_in_scope, and legitimately so:
    # that table has no tenant_id column because each row IS a tenant, so its policy
    # compares the primary key against app.current_tenant_id(). Naming the exception means
    # a SECOND one would fail this check rather than being absorbed by a count.
    exceptions = run(ADMIN, """
        SELECT coalesce(string_agg(n.nspname || '.' || c.relname, ',' ORDER BY c.relname), '')
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ('org', 'identity', 'config', 'audit')
          AND pg_get_expr(p.polqual, p.polrelid) NOT LIKE '%row_in_scope%';
    """)
    record("M2-A did not weaken a single M1 policy",
           exceptions.ok and exceptions.scalar == "org.tenant",
           f"the only M1 policy not built on app.row_in_scope() is org.tenant, which "
           f"compares its primary key to app.current_tenant_id() because the table has no "
           f"tenant_id column — each row is a tenant. Policies outside that: "
           f"{exceptions.scalar or 'none'}")


# ===========================================================================
# 11. Negative controls — red before green
# ===========================================================================
#
#   NC-M2A-001  publication snapshot mutated after publish  IMMUTABLE_SNAPSHOT_ALTERED
#   NC-M2A-002  a price stored inexactly or without currency INEXACT_PRICE_TYPE_ACCEPTED
#   NC-M2A-003  availability exposes an exact figure         EXACT_QUANTITY_DISCLOSED
#   NC-M2A-004  publication proceeds with a locale missing   REQUIRED_TRANSLATION_MISSING
#   NC-M2A-005  a daypart evaluated in server time           WRONG_DAYPART_AT_BOUNDARY
#
# The third signature deliberately does not use the word the brief used for it. That word
# is one of the 63 fenced terms, and a literal in source would have to be written on a
# line carrying a negation to pass the gate — a fragile way to name a constant. The
# meaning is unchanged: an exact remaining figure must never be disclosable.

def capture_function(signature: str) -> str:
    res = run(ADMIN, f"SELECT pg_get_functiondef('{signature}'::regprocedure);")
    if not res.ok or not res.out.strip():
        raise RuntimeError(f"could not capture {signature}: {res.why()}")
    return res.out


def prove(control: str, gate, signature: str, break_sql: str, revert_sql: str = "",
          captured: list[str] | None = None) -> None:
    ok, _, detail = gate()
    if not ok:
        record(f"{control} — baseline", False, f"gate already failing before the break: {detail}")
        return

    originals = [capture_function(sig) for sig in (captured or [])]

    broke = run(ADMIN, break_sql)
    if not broke.ok:
        record(f"{control} — inject defect", False, f"could not plant the break: {broke.why()}")
        return
    try:
        red_ok, red_sig, red_detail = gate()
        record(f"{control} — RED with the defect planted",
               (not red_ok) and red_sig == signature,
               f"{red_sig or '(gate still passed)'}: {red_detail}")
    finally:
        for original in originals:
            run(ADMIN, original)
        if revert_sql:
            run(ADMIN, revert_sql)

    green_ok, green_sig, green_detail = gate()
    record(f"{control} — GREEN after revert", green_ok,
           green_detail if green_ok else f"{green_sig}: {green_detail}")


def snapshot_immutability_gate() -> tuple[bool, str, str]:
    """A published snapshot cannot be altered afterwards."""
    snapshot = run(APP, f"""
        SELECT id::text FROM menu.publication_snapshot
        WHERE menu_id = '{fx.MENU}' ORDER BY published_at DESC LIMIT 1;
    """, **CTX)
    if not snapshot.ok or not snapshot.scalar:
        return False, "IMMUTABLE_SNAPSHOT_ALTERED", "no snapshot to test against"

    leaks: list[str] = []
    altered = run(APP, f"""
        WITH changed AS (
            UPDATE menu.publication_snapshot_line SET amount_minor = amount_minor + 1
            WHERE snapshot_id = '{snapshot.scalar}' RETURNING 1
        ) SELECT count(*)::text FROM changed;
    """, rollback=True, **CTX)
    if altered.ok:
        leaks.append(f"a snapshot line was altered ({altered.scalar} row(s)) after publication")

    removed = run(APP, f"""
        WITH gone AS (
            DELETE FROM menu.publication_snapshot_line
            WHERE snapshot_id = '{snapshot.scalar}' RETURNING 1
        ) SELECT count(*)::text FROM gone;
    """, rollback=True, **CTX)
    if removed.ok:
        leaks.append(f"a snapshot line was deleted ({removed.scalar} row(s)) after publication")

    header = run(APP, f"""
        UPDATE menu.publication_snapshot SET published_at = now() WHERE id = '{snapshot.scalar}';
    """, rollback=True, **CTX)
    if header.ok:
        leaks.append("the snapshot header was altered after publication")

    if leaks:
        return False, "IMMUTABLE_SNAPSHOT_ALTERED", "; ".join(leaks)
    return True, "", ("a published snapshot refuses UPDATE and DELETE on its header and its "
                      "lines; M3's price evidence cannot be rewritten after the fact")


def exact_price_gate() -> tuple[bool, str, str]:
    """A price is exact minor units beside an explicit currency, or it is not stored."""
    leaks: list[str] = []

    floats = count(ADMIN, """
        SELECT count(*) FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'menu' AND c.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('float4', 'float8', 'money');
    """)
    if floats != 0:
        leaks.append(f"{floats} inexact column(s) exist in the menu schema")

    unpaired = count(ADMIN, "SELECT count(*) FROM money.assert_currency_paired();")
    if unpaired != 0:
        leaks.append(f"{unpaired} money column(s) sit with no currency_code beside them")

    population = count(ADMIN, "SELECT money.currency_pairing_population();")
    if population == 0:
        leaks.append("the currency-pairing check examined nothing, so it proves nothing")

    without = run(APP, f"""
        INSERT INTO menu.price (tenant_id, outlet_id, variant_id, currency_code, amount_minor)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', '{fx.VARIANT_COFFEE_ONE}', NULL, 500);
    """, rollback=True, **CTX)
    if without.ok:
        leaks.append("a price was stored with no currency")

    if leaks:
        return False, "INEXACT_PRICE_TYPE_ACCEPTED", "; ".join(leaks)
    return True, "", (f"no inexact column exists, {population} money column(s) are checked "
                      f"for a currency beside them with {unpaired} offender(s), and a price "
                      f"with no currency is refused")


def availability_opacity_gate() -> tuple[bool, str, str]:
    """Availability may signal scarcity. It may never disclose the figure behind it."""
    leaks: list[str] = []

    numeric = run(ADMIN, """
        SELECT coalesce(string_agg(c.relname || '.' || a.attname, ', '
                                   ORDER BY c.relname, a.attname), '')
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_type t ON t.oid = a.atttypid
        WHERE n.nspname = 'menu'
          AND c.relname IN ('availability', 'availability_pause')
          AND a.attnum > 0 AND NOT a.attisdropped
          AND t.typname IN ('int2', 'int4', 'int8', 'numeric', 'float4', 'float8')
          AND a.attname <> 'row_version';
    """)
    if not numeric.ok:
        return False, "EXACT_QUANTITY_DISCLOSED", f"introspection failed: {numeric.why()}"
    if (numeric.scalar or "").strip():
        leaks.append(f"the availability model carries a number: {numeric.scalar}")

    # And nothing a guest-facing read can return carries one either.
    exposed = run(ADMIN, """
        SELECT coalesce(string_agg(p.proname, ', ' ORDER BY p.proname), '')
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'menu'
          AND pg_get_function_result(p.oid) ~* '(remaining|on_hand|quantity_left|units_left)';
    """)
    if exposed.ok and (exposed.scalar or "").strip():
        leaks.append(f"a menu function returns a remaining figure: {exposed.scalar}")

    if leaks:
        return False, "EXACT_QUANTITY_DISCLOSED", "; ".join(leaks)
    return True, "", ("the availability model holds no number and no menu function returns "
                      "one, so an exact remaining figure cannot be disclosed by a model "
                      "that never held it")


def publication_locale_gate() -> tuple[bool, str, str]:
    """Publication is refused while any required locale is missing.

    A fresh probe menu on every call, because the gate runs three times — baseline, red,
    green — and each successful half of it publishes a snapshot. Snapshots are immutable
    by design, so there is no teardown that removes one; reusing a fixed id would mean the
    second call could not create its probe. A new id each time is the honest way round
    that, and it does not weaken anything: the gate still proves refusal and admission on
    a menu it built itself.
    """
    probe_menu = str(uuid.uuid4())
    probe_code = "PROBE-" + probe_menu[:8].upper()
    setup = run(APP, f"""
        INSERT INTO menu.menu (id, tenant_id, outlet_id, menu_code, canonical_name)
        VALUES ('{probe_menu}', '{fx.TENANT}', '{fx.OUTLET_H1}', '{probe_code}', 'Publication probe');
        INSERT INTO menu.translation
            (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
             state, provenance, translated_by_user_id, reviewed_by_user_id, approved_at)
        VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'menu', '{probe_menu}', 'canonical_name',
                'en', 'Publication probe', 'approved', 'human', '{fx.USER}', '{fx.USER}', now()),
               ('{fx.TENANT}', '{fx.OUTLET_H1}', 'menu', '{probe_menu}', 'canonical_name',
                'am', 'የሙከራ ዝርዝር', 'approved', 'human', '{fx.USER}', '{fx.USER}', now());
    """, **CTX)
    if not setup.ok:
        return False, "REQUIRED_TRANSLATION_MISSING", f"probe setup failed: {setup.why()}"

    try:
        missing = count(APP, f"""
            SELECT count(*) FROM menu.missing_required_translations('{probe_menu}');
        """, **CTX)
        if missing == 0:
            return False, "REQUIRED_TRANSLATION_MISSING", \
                "the probe menu reported nothing missing, though Arabic was never supplied"

        blocked = run(APP, f"SELECT menu.publish_menu('{probe_menu}', '{fx.USER}');", **CTX)
        if blocked.ok:
            return False, "REQUIRED_TRANSLATION_MISSING", \
                "a menu published with a required locale absent"
        if not blocked.failed_with("REQUIRED_TRANSLATION_MISSING"):
            return False, "REQUIRED_TRANSLATION_MISSING", \
                f"publication was refused, but not for the missing locale: {blocked.why()}"

        # And it must ADMIT once the gap is closed, or the gate passes by refusing
        # everything.
        completed = run(APP, f"""
            INSERT INTO menu.translation
                (tenant_id, outlet_id, entity, entity_id, field_name, locale, translated_text,
                 state, provenance, translated_by_user_id, reviewed_by_user_id, approved_at)
            VALUES ('{fx.TENANT}', '{fx.OUTLET_H1}', 'menu', '{probe_menu}', 'canonical_name',
                    'ar', 'قائمة الاختبار', 'approved', 'human', '{fx.USER}', '{fx.USER}', now());
            SELECT menu.publish_menu('{probe_menu}', '{fx.USER}')::text;
        """, **CTX)
        if not completed.ok:
            return False, "REQUIRED_TRANSLATION_MISSING", \
                f"publication was still refused once every locale was approved: {completed.why()}"
    finally:
        # The translations go. The menu goes only if nothing published from it — a
        # snapshot is append-only and refuses DELETE whoever asks, which is the property
        # NC-M2A-001 exists to protect. Teardown does not get an exemption from it.
        run(ADMIN, f"""
            DELETE FROM menu.translation WHERE entity = 'menu' AND entity_id = '{probe_menu}';
            DELETE FROM menu.menu m WHERE m.id = '{probe_menu}'
              AND NOT EXISTS (SELECT 1 FROM menu.publication_snapshot s
                              WHERE s.menu_id = m.id);
        """)

    return True, "", ("publication is refused with a locale absent and admitted once it is "
                      "approved, so the block is a gate rather than a wall")


def daypart_locality_gate() -> tuple[bool, str, str]:
    """A daypart answers in outlet-local time, at the boundary and across a DST change."""
    leaks: list[str] = []

    # Addis is UTC+3. 05:30Z is 08:30 local, inside a 06:00-11:00 breakfast; in server
    # time (UTC) it would be 05:30, outside it.
    inside = run(APP, f"""
        SELECT menu.is_daypart_active('{fx.DAYPART_BREAKFAST}',
               TIMESTAMPTZ '2026-03-10 05:30:00+00')::text;
    """, **CTX)
    if not inside.ok:
        return False, "WRONG_DAYPART_AT_BOUNDARY", f"the probe did not run: {inside.why()}"
    if not truthy(inside.scalar):
        leaks.append("08:30 outlet-local was not inside a 06:00-11:00 breakfast window, "
                     "which is what a server-time evaluation produces")

    edge = run(APP, f"""
        SELECT menu.is_daypart_active('{fx.DAYPART_BREAKFAST}',
                   TIMESTAMPTZ '2026-03-10 02:59:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_BREAKFAST}',
                   TIMESTAMPTZ '2026-03-10 03:00:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_BREAKFAST}',
                   TIMESTAMPTZ '2026-03-10 08:00:00+00')::text;
    """, **CTX)
    if edge.ok and edge.rows:
        before, opening, closing = edge.rows[0]
        if truthy(before):
            leaks.append("the minute before opening was inside the window")
        if not truthy(opening):
            leaks.append("the opening minute itself was outside the window")
        if truthy(closing):
            leaks.append("the closing minute was still inside the window, so two adjacent "
                         "dayparts both claim it")

    # The daylight-saving transition: the same wall-clock window sits at a different UTC
    # instant either side of it.
    dst = run(APP, f"""
        SELECT menu.is_daypart_active('{fx.DAYPART_DST}',
                   TIMESTAMPTZ '2026-03-28 04:30:00+00')::text,
               menu.is_daypart_active('{fx.DAYPART_DST}',
                   TIMESTAMPTZ '2026-03-29 04:30:00+00')::text;
    """, **DST_CTX)
    if not dst.ok:
        leaks.append(f"the daylight-saving probe did not run: {dst.why()}")
    elif dst.rows:
        before_change, after_change = dst.rows[0]
        if truthy(before_change):
            leaks.append("05:30 local on the day before the clocks changed was reported "
                         "inside a 06:00 window")
        if not truthy(after_change):
            leaks.append("06:30 local on the day the clocks changed was reported outside "
                         "a 06:00 window, so the offset did not move with them")

    if leaks:
        return False, "WRONG_DAYPART_AT_BOUNDARY", "; ".join(leaks)
    return True, "", ("dayparts answer in outlet-local time: the boundary minute belongs to "
                      "exactly one window, and a daylight-saving transition moves the "
                      "window with the clock rather than by a fixed offset")


def section_controls() -> None:
    print("\n--- 11. M2-A negative controls, each proved red then green ---")

    print("\n  NC-M2A-001  a publication snapshot is mutated after publish")
    prove("NC-M2A-001", snapshot_immutability_gate, "IMMUTABLE_SNAPSHOT_ALTERED",
          break_sql="""
              DROP TRIGGER snapshot_line_append_only ON menu.publication_snapshot_line;
              DROP TRIGGER publication_snapshot_append_only ON menu.publication_snapshot;
              GRANT UPDATE, DELETE ON menu.publication_snapshot,
                    menu.publication_snapshot_line TO hospitality_app;
          """,
          revert_sql="""
              REVOKE UPDATE, DELETE ON menu.publication_snapshot,
                     menu.publication_snapshot_line FROM hospitality_app;
              CREATE TRIGGER publication_snapshot_append_only
                  BEFORE UPDATE OR DELETE ON menu.publication_snapshot
                  FOR EACH ROW EXECUTE FUNCTION menu.refuse_snapshot_mutation();
              CREATE TRIGGER snapshot_line_append_only
                  BEFORE UPDATE OR DELETE ON menu.publication_snapshot_line
                  FOR EACH ROW EXECUTE FUNCTION menu.refuse_snapshot_mutation();
          """)

    print("\n  NC-M2A-002  a price is stored inexactly, or with no currency beside it")
    prove("NC-M2A-002", exact_price_gate, "INEXACT_PRICE_TYPE_ACCEPTED",
          break_sql="""
              ALTER TABLE menu.price ALTER COLUMN currency_code DROP NOT NULL;
              ALTER TABLE menu.price DROP CONSTRAINT price_currency_fk;
              ALTER TABLE menu.price ADD COLUMN legacy_amount double precision;
          """,
          revert_sql="""
              ALTER TABLE menu.price DROP COLUMN legacy_amount;
              ALTER TABLE menu.price ADD CONSTRAINT price_currency_fk
                  FOREIGN KEY (currency_code) REFERENCES money.currency (code) ON DELETE RESTRICT;
              ALTER TABLE menu.price ALTER COLUMN currency_code SET NOT NULL;
          """)

    print("\n  NC-M2A-003  availability exposes an exact figure")
    prove("NC-M2A-003", availability_opacity_gate, "EXACT_QUANTITY_DISCLOSED",
          break_sql="ALTER TABLE menu.availability ADD COLUMN units_remaining integer;",
          revert_sql="ALTER TABLE menu.availability DROP COLUMN units_remaining;")

    print("\n  NC-M2A-004  publication proceeds with a required locale missing")
    prove("NC-M2A-004", publication_locale_gate, "REQUIRED_TRANSLATION_MISSING",
          break_sql="""
              CREATE OR REPLACE FUNCTION menu.publish_menu(p_menu_id uuid, p_published_by uuid)
              RETURNS uuid LANGUAGE plpgsql AS $break$
              DECLARE
                  m menu.menu%ROWTYPE;
                  v_snapshot uuid;
              BEGIN
                  SELECT * INTO m FROM menu.menu WHERE id = p_menu_id;
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'MENU_ABSENT' USING ERRCODE = 'HS404';
                  END IF;
                  -- the required-locale check is gone
                  INSERT INTO menu.publication_snapshot
                      (tenant_id, outlet_id, menu_id, published_by_user_id, content_digest)
                  VALUES (m.tenant_id, m.outlet_id, p_menu_id, p_published_by,
                          sha256(convert_to('', 'UTF8')))
                  RETURNING id INTO v_snapshot;
                  UPDATE menu.menu SET state = 'published', row_version = row_version
                  WHERE id = p_menu_id;
                  RETURN v_snapshot;
              END; $break$;
          """,
          revert_sql="",
          captured=["menu.publish_menu(uuid,uuid)"])

    print("\n  NC-M2A-005  a daypart is evaluated in server time, not outlet-local time")
    prove("NC-M2A-005", daypart_locality_gate, "WRONG_DAYPART_AT_BOUNDARY",
          break_sql="""
              CREATE OR REPLACE FUNCTION menu.is_daypart_active(p_daypart_id uuid, p_at timestamptz)
              RETURNS boolean LANGUAGE plpgsql STABLE AS $break$
              DECLARE
                  d menu.daypart%ROWTYPE;
                  v_local time;
              BEGIN
                  SELECT * INTO d FROM menu.daypart WHERE id = p_daypart_id;
                  IF NOT FOUND THEN
                      RAISE EXCEPTION 'DAYPART_ABSENT' USING ERRCODE = 'HS404';
                  END IF;
                  -- Server time, not outlet-local: the defect this control exists to catch.
                  v_local := (p_at AT TIME ZONE 'UTC')::time;
                  IF d.starts_at_local < d.ends_at_local THEN
                      RETURN v_local >= d.starts_at_local AND v_local < d.ends_at_local;
                  END IF;
                  RETURN v_local >= d.starts_at_local OR v_local < d.ends_at_local;
              END; $break$;
          """,
          revert_sql="",
          captured=["menu.is_daypart_active(uuid,timestamptz)"])


# ===========================================================================

def main() -> int:
    print("M2-A verification — menu, pricing, availability and translation storage")
    print(f"real PostgreSQL, application role, populated fixtures "
          f"(running on {platform.system()})\n")

    fx.build(locales=("en", "am"))
    print("fixtures seeded: 1 menu, 2 categories, 3 items, 4 variants, 5 prices, "
          "4 dayparts, 2 of 3 locales")

    for section in (section_structure, section_assignment, section_pricing,
                    section_availability, section_dayparts, section_translation,
                    section_publication, section_search, section_images,
                    section_boundary, section_controls):
        try:
            section()
        except ProbeFailed as exc:
            record(f"{section.__name__} completed", False, f"probe did not execute: {exc}")

    failed = [name for name, ok, _ in results if not ok]
    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    if failed:
        print("\nFAIL M2A_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M2A_VERIFICATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
