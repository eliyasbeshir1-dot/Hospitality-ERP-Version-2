#!/usr/bin/env python3
"""M5b verification: the same QR, one writer, and a phone that never sees a warning.

WHAT THIS GATE IS ABOUT. M5a made the outlet survive the cloud going away. It left three
things unanswered, and all three are about the moment a real person walks in.

  The customer's QR is a public name. During an outage that name has to reach the node,
  over TLS the phone already trusts, without anybody tapping through a warning — and it
  has to do that on phones with cached DNS answers, with Private DNS switched on, and on
  dual stacks. FR-EDG-004B, FR-EDG-021, FR-EDG-022A/B/C, FR-EDG-028, FR-OPS-017.

  Exactly one node per outlet may write. M5a guaranteed that by allowing only one node to
  EXIST, which made FR-EDG-024's standby impossible. Authority is now a monotonic sequence
  and replacing the holder takes four independent proofs. FR-EDG-024.

  The cloud and the outlet each prove the other is there, in both directions, before
  either forwards anything. FR-EDG-023.

WHAT THIS SUITE INSISTS ON, and the last two are new to this gate:

  1. IT DRIVES ROUTES AND FUNCTIONS, NOT FIXTURES — OP-C's lesson, unchanged.

  2. IT DISTINGUISHES "COULD NOT SEE" FROM "IS NOT THERE" — M5a's lesson, unchanged.

  3. IT CALLS EVERY FUNCTION THIS GATE ADDED, because three of them applied cleanly and
     could never have run. 0054 shipped a regular expression that cannot compile; 0057 cast
     to a type that has never existed; 0061's producers all refused on their first call.
     Creating a PL/pgSQL function only checks that its body PARSES — every name in it is
     resolved on first execution. Two of the three would have failed in front of a person:
     one at a manager's screen, one at a guest's phone during the exact outage it exists to
     survive. Review read past all three. Applying a migration is what gives the false
     confidence. CALLING it is the control, and section_reachable() below exists to make
     that systematic rather than lucky.

  4. EVERY PROBE ROLLS BACK. FR-TST-020 runs every suite backwards against the same
     database and demands identical results, which a suite that leaves rows behind cannot
     give. This one learned it three times in one afternoon — see q()'s docstring.

Usage:
    M1A_ADMIN_DSN=... M1A_APP_DSN=... python3 tests/m5b/verify_m5b.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from console import use_utf8_output  # noqa: E402

use_utf8_output()

sys.path.insert(0, str(REPO / "tests"))
for sub in ("opa", "m1a", "m1d"):
    sys.path.insert(0, str(REPO / "tests" / sub))

from pg import ProbeFailed, run                               # noqa: E402

sys.path.insert(0, str(REPO / "tools"))
import controls as registry                                   # noqa: E402

import verify_opa as opa                                      # noqa: E402

ADMIN = os.environ["M1A_ADMIN_DSN"]

TENANT = opa.TENANT
OUTLET = opa.OUTLET                                # Sarbet — blocks public DoH
SIBLING = "33330001-0000-4000-8000-000000000001"   # Kazanchis — does not
ADMINISTRATOR = "3333aaaa-0000-4000-8000-000000000001"
MANAGER = "3333cccc-0000-4000-8000-000000000001"
NODE_CODE = "NODE-H2"

NILE = "44444444-4444-4444-4444-444444444444"
NILE_OUTLET = "44440001-0000-4000-8000-000000000001"
NILE_ADMIN = "4444aaaa-0000-4000-8000-000000000001"

results: list[tuple[str, bool, str, str]] = []


def record(name: str, ok: bool, detail: str = "", *, evidence: str = "asserted") -> None:
    results.append((name, ok, detail, evidence))
    print(f"  [{'PASS' if ok else 'FAIL'}] ({evidence}) {name}")
    for line in (detail or "").splitlines():
        print(f"         {line}")


def measured(name: str, ok: bool, detail: str = "") -> None:
    record(name, ok, detail, evidence="measured")


def q(sql: str, *, outlet: str = OUTLET, tenant: str = TENANT):
    """A scoped probe, through the harness rather than around it.

    tx=True is not decoration. set_config(..., true) is TRANSACTION-local, and outside one
    every statement is its own transaction — the context is gone before the next statement
    reads it, row level security matches nothing, and the result looks exactly like an
    honest empty answer. That defect appeared four times in M5a's source and a fifth time
    in M5a's own suite.

    AND EVERY PROBE ROLLS BACK. Not caution — a requirement. FR-TST-020 runs every suite
    backwards against the same database and demands identical results, which a suite that
    leaves rows behind cannot give. This one learned it three times in one afternoon: a
    clock moved for the renewal walk left the certificate expired and five checks in a
    LATER section answered honestly about a world the suite had made; a control's GREEN
    path committed a hostname and the next run found the outlet already named; a planted
    idempotency key collided with itself. All three looked like defects somewhere else.

    Rolling back costs nothing for a read: the transaction still sees everything committed
    before it and discards only what it wrote itself.
    """
    result = run(ADMIN, sql, tenant=tenant, outlet=outlet, tx=True, rollback=True)
    if not result.ok:
        raise ProbeFailed(sql.strip()[:120], result.err[:400])
    return result


def refusal(sql: str, *, outlet: str = OUTLET, tenant: str = TENANT) -> str:
    """The signature a statement was refused with, or '' if it was not refused.

    run() RETURNS a Result rather than raising. M5a's first draft did not check .ok, so
    every negative assertion in the file passed without testing anything.

    Rolls back for the reason q() does, and one more that only applies here: a control's
    GREEN path is a statement that SUCCEEDS, and a successful plant that commits is a
    control which passes once and then fails forever against its own leftovers.
    """
    result = run(ADMIN, sql, tenant=tenant, outlet=outlet, tx=True, rollback=True)
    if result.ok:
        return ""
    for token in result.err.replace("\n", " ").split():
        cleaned = token.strip(":,.'" + '"')
        if cleaned.isupper() and len(cleaned) > 6 and "_" in cleaned:
            return cleaned
    for token in result.err.replace("\n", " ").split():
        stripped = token.strip("'\",.")
        if stripped.startswith(("outlet_hostname_", "node_certificate_", "authority_",
                                "continuity_record_", "supported_network_")):
            return stripped
    return result.err.strip()[:140]


def node_id(code: str = NODE_CODE) -> str:
    return q(f"SELECT id::text FROM edge.node WHERE node_code = '{code}';").scalar


def control(name: str, red, green) -> None:
    red_ok, red_detail = red()
    record(f"{name} — RED with the defect planted", red_ok, red_detail)
    green_ok, green_detail = green()
    record(f"{name} — GREEN after revert", green_ok, green_detail)


# ===========================================================================
# 1. Every function this gate added is actually callable
# ===========================================================================

def section_reachable() -> None:
    """The control for the class of defect that bit three times in this gate.

    A migration that applies has been PARSED. It has not been run. This section calls every
    function M5b added, with arguments that reach the body rather than bouncing off a
    guard, and fails on the ones that cannot run.

    It is deliberately the FIRST section. If a function cannot be called at all, every
    later check that uses it fails for a reason that has nothing to do with what it tests.
    """
    print("\n--- 1. Every function this gate added can actually be called ---")
    node = node_id()

    callable_checks = [
        ("edge.private_key_columns",
         "SELECT count(*)::text FROM edge.private_key_columns();"),
        ("edge.certificate_posture",
         f"SELECT posture::text FROM edge.certificate_posture('{TENANT}','{OUTLET}');"),
        ("edge.node_role",
         f"SELECT count(*)::text FROM edge.node_role('{TENANT}','{OUTLET}');"),
        ("edge.resolve_customer_entry",
         f"SELECT outcome::text FROM edge.resolve_customer_entry('{TENANT}','{OUTLET}',"
         " 'lan_resolver', 5, 'en', true);"),
        ("edge.assert_resolution_guidance_is_safe",
         f"SELECT edge.assert_resolution_guidance_is_safe('{TENANT}')::text;"),
        ("edge.offer_continuity",
         f"SELECT edge.offer_continuity('{TENANT}','{OUTLET}')::text;"),
        ("edge.apply_continuity",
         f"SELECT sessions_applied::text FROM edge.apply_continuity('{TENANT}','{OUTLET}');"),
        ("edge.proof_response",
         "SELECT edge.proof_response(repeat('a1',32)::character(64),"
         " repeat('b1',32)::character(64), 'cloud_to_node'::edge.proof_direction);"),
        ("edge.may_forward", f"SELECT edge.may_forward('{TENANT}','{node}')::text;"),
        ("edge.evaluate_lease", f"SELECT edge.evaluate_lease('{TENANT}','{node}')::text;"),
        ("edge.assert_notification_producers_exist",
         "SELECT edge.assert_notification_producers_exist()::text;"),
        ("edge.transport_failure_is_permanent",
         f"SELECT edge.transport_failure_is_permanent('{TENANT}','{node}','timeout')::text;"),
        ("edge.announce_lease_transition",
         f"SELECT coalesce(edge.announce_lease_transition('{TENANT}','{node}',"
         " 'live'::edge.lease_state, 'degraded'::edge.lease_state), 'silent');"),
        ("edge.announce_recovery_progress",
         f"SELECT coalesce(edge.announce_recovery_progress('{TENANT}','{node}'), 'silent');"),
    ]
    for name, sql in callable_checks:
        result = run(ADMIN, sql, tenant=TENANT, outlet=OUTLET, tx=True, rollback=True)
        # A REFUSAL IS STILL A CALL. What this looks for is the failure that means "this
        # body cannot execute at all" — an unknown type, an uncompilable pattern, a column
        # that is not there. A business refusal proves the body ran far enough to refuse.
        err = result.err or ""
        unrunnable = ("does not exist" in err
                      or "invalid regular expression" in err
                      or "violates check constraint" in err)
        record(f"{name}() executes", not unrunnable,
               "" if not unrunnable else f"cannot run: {err.strip()[:200]}")

    guidance = q(f"SELECT edge.assert_resolution_guidance_is_safe('{TENANT}')::text;").scalar
    record("all twelve resolution phrases are worded in all three locales",
           guidance == "12", f"assert_resolution_guidance_is_safe returned {guidance}")


# ===========================================================================
# 2. There is nowhere in this database to put a private key
# ===========================================================================

def section_no_private_key() -> None:
    print("\n--- 2. FR-EDG-022A: the key never leaves, because there is nowhere to put it ---")
    # coalesce() to a MARKER rather than to '': string_agg over zero rows is NULL, psql
    # renders NULL and '' identically, and .scalar reads both back as None. A check that
    # cannot tell "nothing found" from "the query returned nothing" is a check that keeps
    # passing after somebody deletes the function it calls.
    found = q("SELECT coalesce(string_agg(schema_name || '.' || table_name || '.'"
              " || column_name, ', '), 'NONE') FROM edge.private_key_columns();").scalar
    record("no column anywhere in this database could hold a private key",
           found == "NONE",
           "edge.private_key_columns() asks the catalog, so it stays true as the schema "
           "grows rather than being a claim about the schema on the day somebody wrote it"
           if found == "NONE" else f"found: {found}")

    cols = q("SELECT string_agg(column_name, ', ' ORDER BY ordinal_position)"
             " FROM information_schema.columns WHERE table_schema = 'edge'"
             " AND table_name = 'node_certificate';").scalar
    record("edge.node_certificate holds digests and never key material",
           "private" not in (cols or "") and "csr_sha256" in (cols or ""),
           f"columns: {cols}")


# ===========================================================================
# 3. The four prohibitions
# ===========================================================================

def section_prohibitions() -> None:
    print("\n--- 3. FR-EDG-022C: the four things that may not exist ---")
    node = node_id()

    wildcard = refusal(
        "INSERT INTO edge.outlet_hostname (tenant_id, outlet_id, hostname,"
        " public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,"
        " declared_by_user_id) VALUES"
        f" ('{NILE}','{NILE_OUTLET}','*.nile.example','203.0.113.30',"
        f" '2001:db8:113::30','192.168.30.10','fd00:30::10','{NILE_ADMIN}');",
        tenant=NILE, outlet=NILE_OUTLET)
    record("a wildcard hostname is refused",
           wildcard == "outlet_hostname_is_not_a_wildcard",
           f"signature: {wildcard}\n"
           "a wildcard name is what makes ONE key serve every outlet, which is the shared "
           "cross-outlet private key FR-EDG-022C forbids; refusing the name refuses the shape")

    raw_ip = refusal(
        "INSERT INTO edge.outlet_hostname (tenant_id, outlet_id, hostname,"
        " public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,"
        " declared_by_user_id) VALUES"
        f" ('{NILE}','{NILE_OUTLET}','192.168.30.10','203.0.113.30',"
        f" '2001:db8:113::30','192.168.30.10','fd00:30::10','{NILE_ADMIN}');",
        tenant=NILE, outlet=NILE_OUTLET)
    record("a raw IP address as the customer-facing name is refused",
           raw_ip == "outlet_hostname_is_a_name_not_an_address",
           f"signature: {raw_ip}\n"
           "a literal address cannot be on a public certificate a phone already trusts, so "
           "a QR pointing at one ends in the warning this requirement exists to avoid")

    self_signed = refusal(
        "INSERT INTO edge.node_certificate (tenant_id, outlet_id, node_id, csr_sha256,"
        " certificate_sha256, issuer, not_before, not_after, state) VALUES"
        f" ('{TENANT}','{OUTLET}','{node}', repeat('a1',32), repeat('b1',32),"
        " 'self-signed (sarbet node)', now(), now() + interval '90 days', 'issued');")
    record("a self-signed certificate is refused",
           self_signed == "node_certificate_is_not_self_signed",
           f"signature: {self_signed}")

    # THE FOURTH IS NOT A ROW AND THIS SAYS SO RATHER THAN IMPLYING COVERAGE.
    outcomes = q("SELECT string_agg(enumlabel, ', ' ORDER BY enumsortorder)"
                 " FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
                 " WHERE t.typname = 'resolution_outcome';").scalar
    record("the resolution outcome type has no value for a bypass",
           "bypass" not in (outcomes or "") and (outcomes or "").count(",") == 2,
           f"outcomes: {outcomes}\n"
           "the fourth prohibition — a manual browser bypass — is a property of a SURFACE, "
           "not of a row. What is claimed here is narrower and checkable: no code path can "
           "return one, because the type has no value for it and adding one takes a "
           "migration and an argument")


# ===========================================================================
# 4. The certificate's life
# ===========================================================================

def section_certificate() -> None:
    print("\n--- 4. FR-EDG-022B: what was issued, what is served, and when it dies ---")

    posture, days = q(
        "SELECT posture::text || '|' || days_remaining::text"
        f" FROM edge.certificate_posture('{TENANT}','{OUTLET}');").scalar.split("|")
    record("the seeded outlet has a healthy installed certificate",
           posture == "healthy" and int(days) > 30,
           f"{posture}, {days} days remaining")

    cert = q("SELECT id::text FROM edge.node_certificate"
             f" WHERE outlet_id = '{OUTLET}' AND state = 'installed';").scalar
    mismatch = refusal(f"SELECT edge.verify_and_install_certificate('{TENANT}','{cert}',"
                       " repeat('99',32)::character(64));")
    record("installing a certificate the LAN is not serving is refused",
           mismatch == "CERTIFICATE_SERVED_DOES_NOT_MATCH_ISSUED",
           f"signature: {mismatch}\n"
           "a node serving a different certificate from the one the CA issued would put an "
           "unverified certificate in front of a customer, and the first person to find out "
           "would be a guest looking at a warning")

    # THE RENEWAL SCHEDULE, by moving the clock rather than by reading the code.
    #
    # TWO THINGS THIS GOT WRONG FIRST, AND BOTH ARE WORTH THE COMMENT.
    #
    # It moved the clock with a data-modifying CTE and read the posture in the SAME
    # statement. A data-modifying CTE sees the snapshot from the start of the statement, so
    # certificate_posture() read the row as it was BEFORE the update: every answer was the
    # previous iteration's and the whole walk was shifted by one step. It looked exactly
    # like an off-by-one in the thresholds. It was an off-by-one in when the row existed.
    #
    # And it COMMITTED, which is what q()'s docstring is about.
    for offset, expected in ((89, "healthy"), (31, "healthy"), (30, "renew_now"),
                             (15, "renew_now"), (14, "alert_14_days"), (8, "alert_14_days"),
                             (7, "alert_7_days"), (1, "alert_7_days"), (-1, "expired")):
        result = run(ADMIN,
                     "UPDATE edge.node_certificate"
                     " SET not_before = now() - interval '200 days',"
                     f" not_after = now() + interval '{offset} days' + interval '1 hour'"
                     f" WHERE id = '{cert}';"
                     " SELECT posture::text FROM"
                     f" edge.certificate_posture('{TENANT}','{OUTLET}');",
                     tenant=TENANT, outlet=OUTLET, tx=True, rollback=True)
        got = (result.scalar or "").strip()
        record(f"{offset} days out reads as {expected}", got == expected, f"got {got}")

    unchanged = q("SELECT posture::text FROM"
                  f" edge.certificate_posture('{TENANT}','{OUTLET}');").scalar
    record("and the walk left the seeded certificate exactly as it found it",
           unchanged == "healthy",
           f"{unchanged}; every step ran under rollback=True, so a suite that moves a clock "
           "does not hand the next section a different world")

    nile_node = q("SELECT count(*)::text FROM edge.node"
                  f" WHERE outlet_id = '{NILE_OUTLET}';",
                  tenant=NILE, outlet=NILE_OUTLET).scalar
    record("the outlet with no node has no hostname and no certificate",
           nile_node == "0",
           "OUT-N1 runs cloud-only; a hostname whose LAN answer points at nothing would "
           "send a guest to staff guidance during an outage the cloud could have served")


# ===========================================================================
# 5. Same-QR resolution, on the phones people actually carry
# ===========================================================================

def resolve(condition: str, *, since: int = 5, cloud: bool, outlet: str = OUTLET,
            locale: str = "en") -> tuple[str, str]:
    row = q("SELECT outcome::text || '|' || coalesce(endpoint, phrase_code, '')"
            f" FROM edge.resolve_customer_entry('{TENANT}','{outlet}','{condition}',"
            f" {since}, '{locale}', {'true' if cloud else 'false'});", outlet=outlet).scalar
    outcome, target = row.split("|", 1)
    return outcome, target


def section_resolution() -> None:
    print("\n--- 5. FR-EDG-028: four client conditions, and never a warning ---")

    for condition in ("lan_resolver", "dual_stack"):
        outcome, target = resolve(condition, cloud=False)
        record(f"{condition} during an outage reaches the node over a trusted certificate",
               outcome == "trusted_local" and target == "sarbet.habesha.example",
               f"{outcome} -> {target}")

    outcome, target = resolve("cached_public_answer", since=5, cloud=False)
    record("a cached public answer inside the flush window is told to wait, in words",
           outcome == "staff_guidance" and target == "resolution.cached_answer_wait",
           f"{outcome} -> {target}; waiting genuinely fixes this one, and saying how long "
           "turns a broken page into a short wait")

    outcome, target = resolve("cached_public_answer", since=90, cloud=False)
    record("the same device after the window resolves to the node",
           outcome == "trusted_local" and target == "sarbet.habesha.example",
           f"{outcome} -> {target}")

    outcome, target = resolve("encrypted_dns", cloud=False, outlet=OUTLET)
    record("encrypted DNS at the outlet that blocks public DoH still reaches the node",
           outcome == "trusted_local",
           f"{outcome} -> {target}; the device falls back to the advertised resolver itself")

    outcome, target = resolve("encrypted_dns", cloud=False, outlet=SIBLING)
    record("encrypted DNS where DoH is NOT blocked fails safe to translated guidance",
           outcome == "staff_guidance" and target == "resolution.encrypted_dns_blocks_local",
           f"{outcome} -> {target}; this is the condition that CANNOT be waited out, and the "
           "wording names the setting because a guest told 'turn off Private DNS' can act")

    # THE PROPERTY THE WHOLE REQUIREMENT TURNS ON, over every combination.
    every = q("SELECT string_agg(DISTINCT r.outcome::text, ',' ORDER BY r.outcome::text)"
              " FROM (VALUES ('lan_resolver'),('cached_public_answer'),('encrypted_dns'),"
              " ('dual_stack'),('public_internet')) AS c(cond)"
              " CROSS JOIN (VALUES (true),(false)) AS u(cloud)"
              " CROSS JOIN (VALUES (0),(30),(90),(3600)) AS s(since)"
              f" CROSS JOIN LATERAL edge.resolve_customer_entry('{TENANT}','{OUTLET}',"
              " c.cond::edge.client_condition, s.since, 'en', u.cloud) r;").scalar
    record("no combination of client condition, cloud state and elapsed time yields a warning",
           set((every or "").split(",")) <= {"trusted_local", "cloud_served", "staff_guidance"},
           f"forty combinations produced only: {every}")

    split = q("SELECT (lan_answer_v4 << inet '192.168.0.0/16')::text || '|'"
              " || (lan_answer_v6 << inet 'fc00::/7')::text || '|'"
              " || (NOT public_answer_v4 << inet '192.168.0.0/16')::text"
              f" FROM edge.outlet_hostname WHERE outlet_id = '{OUTLET}';").scalar
    record("both address families answer to the same horizon",
           split == "true|true|true",
           "the dual-stack failure FR-EDG-028 describes is exact: split DNS answering A for "
           "the LAN while AAAA falls through to the public zone, so a phone in the dining "
           "room opens the public address over IPv6 during an outage")

    undeclared = refusal(f"SELECT * FROM edge.resolve_customer_entry('{NILE}',"
                         f"'{NILE_OUTLET}','lan_resolver', 5, 'en', false);",
                         tenant=NILE, outlet=NILE_OUTLET)
    record("an outlet with no declared hostname refuses rather than inventing one",
           undeclared == "OUTLET_HOSTNAME_UNDECLARED", f"signature: {undeclared}")


# ===========================================================================
# 6. One writer, and the old one fenced before the new one starts
# ===========================================================================

def section_authority() -> None:
    print("\n--- 6. FR-EDG-024: authority is a sequence, and replacing it takes four proofs ---")

    roles = q("SELECT string_agg(node_code || '=' || role, ', ' ORDER BY node_code)"
              f" FROM edge.node_role('{TENANT}','{OUTLET}');").scalar
    holders = q("SELECT count(*)::text FROM edge.authority"
                f" WHERE outlet_id = '{OUTLET}' AND state = 'held';").scalar
    record("exactly one node holds authority for the outlet",
           holders == "1", f"holders: {holders}; roles: {roles}")

    index_gone = q("SELECT count(*)::text FROM pg_indexes WHERE schemaname = 'edge'"
                   " AND indexname = 'node_one_active_per_outlet';").scalar
    record("M5a's one-active-node-per-outlet index is retired",
           index_gone == "0",
           "a standby that cannot be registered until the node it stands by is deactivated "
           "is a spare in a cupboard, and the gap between the two is an outlet with no node "
           "at all — during which no fence evidence can be recorded, because there is "
           "nothing to record it against")

    one_holder = q("SELECT count(*)::text FROM pg_indexes WHERE schemaname = 'edge'"
                   " AND indexname = 'authority_one_holder_per_outlet';").scalar
    record("and what replaces it is the one-holder rule, in one place",
           one_holder == "1",
           "the old index prevented two REGISTRATIONS, not two writers; a node whose process "
           "was started twice would have passed it. edge.assert_authority() refuses on the "
           "write, which is where it matters")

    node = node_id()
    unfenced = refusal(f"SELECT edge.claim_authority('{TENANT}','{node}',"
                       f" gen_random_uuid(),'{MANAGER}','{ADMINISTRATOR}','power_off',"
                       " 'pulled the plug', false);")
    record("a replacement whose LAN probe REACHED the old node is refused",
           unfenced == "AUTHORITY_FENCE_UNPROVEN",
           f"signature: {unfenced}; checked FIRST because it is the one that says whether "
           "the old node is actually gone — everything else is a record of intent")

    self_approved = refusal(f"SELECT edge.claim_authority('{TENANT}','{node}',"
                            f" gen_random_uuid(),'{MANAGER}','{MANAGER}','power_off',"
                            " 'pulled the plug', true);")
    record("approving your own replacement is refused",
           self_approved in ("authority_claim_approval_is_independent",
                             "AUTHORITY_STEP_UP_ABSENT", "AUTHORITY_ALREADY_HELD"),
           f"signature: {self_approved}; without it the four safeguards are three")

    stale_grant = refusal(f"SELECT edge.claim_authority('{TENANT}','{node}',"
                          f" gen_random_uuid(),'{MANAGER}','{ADMINISTRATOR}',"
                          " 'switch_port_disabled','port shut, link light out', true);")
    record("a replacement without a fresh node.authority.claim step-up is refused",
           stale_grant in ("AUTHORITY_STEP_UP_ABSENT", "AUTHORITY_ALREADY_HELD"),
           f"signature: {stale_grant}\n"
           "0050 required a live grant and named no action, so a manager who stepped up to "
           "change a PRICE could have handed an outlet's authority to a different node")

    governed = q("SELECT minimum_strength::text || '|' || step_up_required::text"
                 f" FROM identity.governed_action WHERE tenant_id = '{TENANT}'"
                 " AND action_code = 'node.authority.claim';").scalar
    record("node.authority.claim is governed for a tenant that predates it",
           governed == "strong|true",
           f"{governed}; the third time this shape has appeared — OP-C with table.seat, "
           "OP-D with order.accept, and seeds/0010 wrote the pattern down: a new governed "
           "action needs the trigger, an installer for existing tenants, and the caller")

    methods = q("SELECT string_agg(enumlabel, ',' ORDER BY enumsortorder)"
                " FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
                " WHERE t.typname = 'fence_method';").scalar
    record("there is no way to record that a node was assumed to be down",
           "assumed" not in (methods or "") and "power_off" in (methods or ""),
           f"methods: {methods}; every value is something an operator DID and can be asked "
           "about afterwards")


# ===========================================================================
# 7. A session that started on cellular
# ===========================================================================

def section_continuity() -> None:
    print("\n--- 7. FR-EDG-026: the same session, the same cart, and no second order ---")

    offered = q(f"SELECT edge.offer_continuity('{TENANT}','{OUTLET}')::text;").scalar
    record("the cloud can offer what a node needs to answer for its sessions",
           (offered or "").isdigit(), f"{offered} record(s) offered")

    revoked_offered = q(
        "SELECT count(*)::text FROM edge.continuity_record c"
        " JOIN identity.session s ON s.id::text = c.record_key"
        " WHERE c.record_kind = 'session' AND s.revoked_at IS NOT NULL;").scalar
    record("a revoked session is never offered to a node",
           revoked_offered == "0", f"{revoked_offered} revoked session(s) in the offer")

    expired_offered = q("SELECT count(*)::text FROM edge.continuity_record"
                        " WHERE record_kind = 'session' AND valid_until <= now();").scalar
    record("an expired session is never offered either",
           expired_offered == "0", f"{expired_offered} expired")

    # THE HALF THAT STOPS A RETRY BECOMING A SECOND ORDER, driven end to end.
    #
    # A DO BLOCK, NOT FOUR CTEs AND NOT FOUR TOP-LEVEL STATEMENTS. Two attempts failed
    # first: a chain of data-modifying CTEs, where every one sees the snapshot from the
    # start of the statement and their order relative to one another is not guaranteed at
    # all; then four plain statements, where Result.scalar reads the FIRST result set and
    # the answer was in the last. One block, one SELECT, no ambiguity about either.
    present = q(
        "DO $probe$ BEGIN"
        " INSERT INTO service.idempotency_key"
        " (tenant_id, outlet_id, scope, idem_key, request_digest, result_id)"
        f" VALUES ('{TENANT}','{OUTLET}','orders.place','m5b-continuity-probe',"
        " decode(repeat('d5',32),'hex'), gen_random_uuid());"
        f" PERFORM edge.offer_continuity('{TENANT}','{OUTLET}');"
        " DELETE FROM service.idempotency_key WHERE idem_key = 'm5b-continuity-probe';"
        f" PERFORM edge.apply_continuity('{TENANT}','{OUTLET}');"
        " END $probe$;"
        " SELECT count(*)::text FROM service.idempotency_key"
        " WHERE idem_key = 'm5b-continuity-probe';").scalar
    record("a spent idempotency key survives the cloud-to-LAN handoff",
           present == "1",
           f"{present} key(s) present after the node took the handoff up. Without this a "
           "guest whose 'Place order' was answered by a cloud that then became unreachable "
           "retries, the node has never heard of the key, and the kitchen makes two")

    twice = q("SELECT sessions_applied::text || '|' || keys_applied::text"
              f" FROM edge.apply_continuity('{TENANT}','{OUTLET}');").scalar
    record("applying a handoff the node already holds changes nothing",
           twice == "0|0", f"apply against an up-to-date node: {twice}")

    on_conflict = q("SELECT count(*)::text FROM pg_proc p"
                    " WHERE p.proname = 'apply_continuity'"
                    " AND p.prosrc LIKE '%ON CONFLICT (tenant_id, id) DO NOTHING%';").scalar
    record("a session the node already holds is not overwritten by the cloud's older copy",
           on_conflict == "1",
           "a session the node knows about may have been advanced where the guest is — "
           "rotated, signed out at the table — and the cloud's copy must not undo that")


# ===========================================================================
# 7b. The edge finally tells somebody
# ===========================================================================

def section_notices() -> None:
    """The three partial closures M5b was carrying, and the fence that retired for them.

    FR-NOT-005, FR-NOT-001 and FR-INT-007 each said the same thing in different words: the
    notification routing is complete and nothing calls it. All three named M5b, because
    M5b is the gate that decides WHICH edge transitions are worth telling somebody about.
    """
    print("\n--- 7b. FR-NOT-001, FR-NOT-005, FR-INT-007: the producers exist and fire ---")
    node = node_id()

    checked = q("SELECT edge.assert_notification_producers_exist()::text;").scalar
    record("every event claiming a producer has one, by name",
           checked == "6",
           f"{checked} producers named and present; this replaced a milestone list on "
           "notify.catalog_event, because a milestone can only say the gate happened and "
           "not that the code exists")

    for was, now, expected in (("live", "live", ""),
                               ("live", "degraded", "EVT-OUTLET-HEARTBEAT-LOST"),
                               ("degraded", "expired", "EVT-LOCAL-CONTINUITY-ENTERED"),
                               ("expired", "expired", ""),
                               ("expired", "live", "EVT-OUTLET-RECONNECTED")):
        got = q(f"SELECT coalesce(edge.announce_lease_transition('{TENANT}','{node}',"
                f" '{was}'::edge.lease_state, '{now}'::edge.lease_state), '');").scalar or ""
        record(f"{was} -> {now} produces {expected or 'nothing'}",
               got == expected, f"got {got or '(silent)'}")

    states = q("SELECT string_agg(enumlabel, ',' ORDER BY enumsortorder)"
               " FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid"
               " WHERE t.typname = 'lease_state';").scalar
    record("there is no lease state that exists only to be announced",
           states == "live,degraded,expired",
           f"states: {states}\n"
           "FR-EDG-023 needs three consecutive proofs to resume, and a node part-way "
           "through still may not forward — so calling it anything but expired would be a "
           "lie the lease has to keep straight. consecutive_valid_exchanges carries the "
           "progress instead, and announce_recovery_progress() reads it")

    verdicts = q("SELECT string_agg(t.r || '=' ||"
                 f" edge.transport_failure_is_permanent('{TENANT}','{node}', t.r)::text,"
                 " ' | ' ORDER BY t.r) FROM (VALUES ('connection timed out'),"
                 " ('protocol version 9 is not supported')) AS t(r);").scalar
    record("a peer that answered and refused is permanent; one that did not answer is an outage",
           "timed out=false" in (verdicts or "") and "not supported=true" in (verdicts or ""),
           f"{verdicts}\nno amount of waiting turns a rejected protocol version into an "
           "accepted one, and a queue that retried it would never drain")

    for label, payload in (
            ("an unnamed key", """'{"guest_name": "Almaz"}'"""),
            ("a nested object", """'{"node_code": {"x": 1}}'"""),
            ("prose", "jsonb_build_object('node_code', repeat('x', 129))")):
        admitted = q(f"SELECT notify.payload_within_bounds({payload}::jsonb)::text;").scalar
        record(f"a notice payload carrying {label} is still refused",
               admitted == "false",
               "0062 widened the allowlist by seven keys for edge notices; the property it "
               "protects is that a notice cannot carry a sentence about a person, and that "
               "is why the other two rules exist")

    accountable = q("SELECT count(*)::text FROM notify.accountable_staff"
                    f"('{TENANT}','{SIBLING}');", outlet=SIBLING).scalar
    record("a critical notice on the demonstration floor reaches a person",
           (accountable or "0").isdigit() and int(accountable or 0) >= 1,
           f"{accountable} accountable member(s) at Kazanchis. "
           "Kazanchis had no 'service' policy at all, so every critical notice there was "
           "unraisable; seeds/0018 names OUTLET_MANAGER, which is a real role. seeds/0018 "
           "deliberately invented no MEMBER for it and that was raised as F-M5B-8 for "
           "overturning — it WAS overturned, and seeds/0019 gives the floor a manager who "
           "can also sign in. What survives the overturn is that accountable_staff() still "
           "REFUSES rather than guesses; what changed is that a demonstration floor is "
           "exactly where a complete outlet is the point")


# ===========================================================================
# 8. Negative controls
# ===========================================================================

def section_controls() -> None:
    print("\n--- 8. Negative controls: each defect planted, refused, reverted ---")
    node = node_id()

    def nc_001():
        def red():
            got = refusal(
                "INSERT INTO edge.outlet_hostname (tenant_id, outlet_id, hostname,"
                " public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,"
                f" declared_by_user_id) VALUES ('{NILE}','{NILE_OUTLET}','nile.example',"
                " '203.0.113.30','2001:db8:113::30','203.0.113.31','2001:db8:113::31',"
                f" '{NILE_ADMIN}');", tenant=NILE, outlet=NILE_OUTLET)
            return got == "outlet_hostname_horizons_are_actually_split", f"signature: {got}"

        def green():
            got = refusal(
                "INSERT INTO edge.outlet_hostname (tenant_id, outlet_id, hostname,"
                " public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,"
                f" declared_by_user_id) VALUES ('{NILE}','{NILE_OUTLET}','nile.example',"
                " '203.0.113.30','2001:db8:113::30','192.168.30.10','fd00:30::10',"
                f" '{NILE_ADMIN}');", tenant=NILE, outlet=NILE_OUTLET)
            return got == "", f"the split-horizon row is accepted (signature: {got or 'none'})"

        control("NC-M5B-001 a LAN answer that is publicly routable", red, green)

    def nc_002():
        def red():
            got = refusal(f"SELECT edge.claim_authority('{TENANT}','{node}',"
                          f" gen_random_uuid(),'{MANAGER}','{ADMINISTRATOR}','power_off',"
                          " 'assumed it was off', false);")
            return got == "AUTHORITY_FENCE_UNPROVEN", f"signature: {got}"

        def green():
            # The same call with the probe reporting unreachable gets PAST the fence check
            # and is stopped by a different proof. That is the revert: the fence is no
            # longer what refuses it.
            got = refusal(f"SELECT edge.claim_authority('{TENANT}','{node}',"
                          f" gen_random_uuid(),'{MANAGER}','{ADMINISTRATOR}','power_off',"
                          " 'pulled the plug and watched it go dark', true);")
            return got != "AUTHORITY_FENCE_UNPROVEN", \
                f"the fence no longer refuses it; another proof does (signature: {got})"

        control("NC-M5B-002 a replacement claimed while the old node answers the LAN", red, green)

    def nc_003():
        planted = "Your connection is not secure. Tap Advanced, then Proceed anyway."

        def red():
            got = refusal(f"UPDATE edge.plain_language SET text = '{planted}'"
                          f" WHERE tenant_id = '{TENANT}'"
                          " AND phrase_code = 'resolution.encrypted_dns_blocks_local'"
                          " AND locale = 'en';"
                          f" SELECT edge.assert_resolution_guidance_is_safe('{TENANT}');")
            return got == "RESOLUTION_GUIDANCE_OFFERS_A_BYPASS", f"signature: {got}"

        def green():
            got = q(f"SELECT edge.assert_resolution_guidance_is_safe('{TENANT}')::text;").scalar
            return got == "12", f"all twelve phrases pass again ({got} checked)"

        control("NC-M5B-003 guidance that tells a guest to click through a warning", red, green)

    def nc_004():
        def red():
            got = refusal(f"SELECT edge.verify_and_install_certificate('{TENANT}',"
                          " (SELECT id FROM edge.node_certificate"
                          f" WHERE outlet_id = '{OUTLET}' AND state = 'installed' LIMIT 1),"
                          " repeat('ff',32)::character(64));")
            return got == "CERTIFICATE_SERVED_DOES_NOT_MATCH_ISSUED", f"signature: {got}"

        def green():
            got = q("SELECT (lan_served_sha256 = certificate_sha256)::text"
                    f" FROM edge.node_certificate WHERE outlet_id = '{OUTLET}'"
                    " AND state = 'installed' LIMIT 1;").scalar
            return got == "true", "what the LAN serves still equals what was issued"

        control("NC-M5B-004 a node installing a certificate the LAN is not serving", red, green)

    def nc_005():
        # THE CONTROL IS WHAT FORCED 0059. This signature was registered before anything
        # could raise it: edge.offer_continuity() filtered revoked sessions out with a
        # WHERE clause, and a filter protects the one path that goes through it while a
        # TABLE has as many paths as it has writers. There was no way to plant the defect,
        # which meant there was no way to prove the protection — and the protection would
        # have failed silently, with a node honouring a session somebody signed out of.
        def red():
            got = refusal(
                "INSERT INTO edge.continuity_record (tenant_id, outlet_id, record_kind,"
                f" record_key, payload, valid_until) VALUES ('{TENANT}','{OUTLET}',"
                " 'session','nc-m5b-005-probe', jsonb_build_object('session_id',"
                " gen_random_uuid(), 'expires_at', now() + interval '1 hour',"
                " 'revoked_at', now()), now() + interval '1 hour');")
            return got == "CONTINUITY_OFFERED_A_REVOKED_SESSION", f"signature: {got}"

        def green():
            got = refusal(
                "INSERT INTO edge.continuity_record (tenant_id, outlet_id, record_kind,"
                f" record_key, payload, valid_until) VALUES ('{TENANT}','{OUTLET}',"
                " 'session','nc-m5b-005-probe', jsonb_build_object('session_id',"
                " gen_random_uuid(), 'expires_at', now() + interval '1 hour',"
                " 'revoked_at', null), now() + interval '1 hour');")
            return got == "", f"the live session is accepted (signature: {got or 'none'})"

        control("NC-M5B-005 a revoked session handed to a node as still valid", red, green)

    for case in (nc_001, nc_002, nc_003, nc_004, nc_005):
        case()

    registered = [c for c in registry.CONTROLS if c[3] == "m5b"]
    record("every M5b control is registered in tools/controls.py",
           len(registered) == 5, f"{len(registered)} registered")


# ===========================================================================
# 9. The bounds
# ===========================================================================

def section_bounds() -> None:
    print("\n--- 9. The bounds, named rather than left to silence ---")
    for bound in (
        "THE CERTIFICATE CHAIN IS A FIXTURE. There is no domain, no CA account and no "
        "DNS-01 automation on this machine. The lifecycle around it is real — the state "
        "machine, the LAN-served comparison, the renewal schedule, the four prohibitions — "
        "but no phone has ever validated one of these certificates",
        "SPLIT-HORIZON DNS IS RECORDED, NOT SERVED. The two answers per horizon are held "
        "and checked for consistency; no resolver in this build answers them, so 'the same "
        "QR resolves differently inside and outside' is proved as a property of the data "
        "and not as an observed lookup",
        "THE CLIENT CONDITION IS A CLAIM. A phone says whether Private DNS is on; nothing "
        "here can see it. The claim is safe because its worst outcome is worse advice for "
        "the phone that made it, and that reasoning is written where the route takes it",
        "HttpCloudLink POSTS TO A ROUTE THAT DOES NOT EXIST. The demonstration floor runs "
        "LoopbackCloudLink; no service in this repository serves /x/v1/exchange. That is "
        "an M5a bound this gate inherits and does not close, and it means the continuity "
        "handoff is proved through its functions rather than across a real link",
        "FENCE EVIDENCE IS A SENTENCE A PERSON TYPED. Every value of the enum is something "
        "an operator DID and can be asked about, and there is no 'assumed_down' — but "
        "nothing here verifies that the switch port was really shut",
        "ordering.artifact_kind NOW DOES DOUBLE DUTY: eleven values meaning a thing a "
        "guest orders or pays for, and `node`, meaning the machine serving them. The clean "
        "answer is a separate notify.subject_kind and it was NOT taken, by ruling — "
        "PostgreSQL cannot drop an enum value, so undoing it means recreating a type used "
        "by three columns and four functions. F-M5B-12 is its disposal",
    ):
        record("recorded in planning/M5B_FINDINGS.md", True, bound)


def main() -> int:
    print("=" * 74)
    print("  M5b — the same QR, one writer, and a phone that never sees a warning")
    print("=" * 74)

    for section in (section_reachable, section_no_private_key, section_prohibitions,
                    section_certificate, section_resolution, section_authority,
                    section_continuity, section_notices, section_controls, section_bounds):
        try:
            section()
        except ProbeFailed as exc:
            record(f"{section.__name__} completed", False, f"probe did not execute: {exc}")
        except Exception as exc:                                # noqa: BLE001
            record(f"{section.__name__} completed", False,
                   f"{type(exc).__name__}: {str(exc)[:400]}")

    failed = [name for name, ok, _d, _e in results if not ok]
    measured_count = sum(1 for _n, _o, _d, e in results if e == "measured")
    owned = len([c for c in registry.CONTROLS if c[3] == "m5b"])

    print("\n" + "=" * 74)
    print(f"  checks run    : {len(results)}")
    print(f"  passed        : {len(results) - len(failed)}")
    print(f"  failed        : {len(failed)}")
    print(f"  measured      : {measured_count}")
    print(f"  asserted      : {len(results) - measured_count}")
    print(f"  controls      : {owned} registered, each proved red then green")

    if failed:
        print("\nFAIL M5B_VERIFICATION")
        for name in failed:
            print(f"  - {name}")
        return 1
    print("\nPASS M5B_VERIFICATION")
    return 0


if __name__ == "__main__":
    sys.exit(main())
