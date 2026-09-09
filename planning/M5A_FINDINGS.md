# M5a findings — the outlet keeps working when the cloud does not

M5a is the first gate that builds a second place where this system runs. Everything before
it assumed one database and one API, reachable or not. FR-EDG-001 says that assumption is
not permitted in production.

Six defects are recorded below. **Five of them are the same defect**, and that is the
finding — not the individual bugs, which are small, but the shape they share: *a mechanism
that answers plausibly when it has not looked.* Every one produced an answer a reader would
have believed. None of them said "I could not tell".

Read F-M5A-2 first. It is the one that will happen again.

---

## F-M5A-1 — a refusal that cited a classification which does not exist

`app.refuse_financial_mutation()` refuses UPDATE and DELETE on append-only tables. Its
message said:

> It is an append-only financial ledger — **app.financial_table_class() says so** — and a
> row here is the record of something that happened.

`app.financial_table_class()` says nothing at all about four of the tables that trigger
guards. `pos.counter_order_entry` has been one of them **since M4-C**: it lives in `pos`,
which is not a financial schema, so it has no class, and every refusal it has ever raised
cited a classification that does not exist. M5a was about to make it four by attaching the
same guard to `edge.node_health_sample`, `edge.node_admin_action` and
`integration.sync_evidence`.

**The part worth keeping.** The function carries a comment explaining that an *earlier*
version of it named a cause it had not verified — it said "a receipt is the record of a
document a customer is holding", true of the two tables it guarded when written and false
by the time 0028 attached it to a drawer count. The comment then states the rule the repair
followed:

> What is true of every table this guards is the sentence below, so that is the sentence.

The replacement did not follow it. **Same defect, one revision later, inside the fix for
it.**

**Why nothing caught it.** `app.assert_financial_tables_are_classified()` asks one
question — is every table in a financial schema classified? — and passes. The question it
never asks is the converse: does every table *claiming* a classification have one. One
question standing in for two, which is the census defect from OP-D in a different file.

**Repaired in 0042.** The signature stays, because NC-M4C-005 is registered against
`LEDGER_ROW_DELETED_NOT_REVERSED` and a control that stops matching is a control that stops
running. Only the unverifiable clause goes. `app.append_only_tables()` now declares every
such table and why, and `app.assert_append_only_guards_are_declared()` asks both
directions.

**And the repair repeated the class once before shipping.** Its first draft looked for the
guard *by name* and reported seven ledgers unguarded — `billing.bill_event`, `billing.tip`,
`billing.tip_correction`, `cash.movement`, `cash.shift_transition`,
`payments.payment_event`, `payments.reversal`. All seven refuse destructive change through
four differently-named functions this repository wrote for them. "Guarded" is now derived
from what the trigger *does*: row-level, BEFORE, on both UPDATE and DELETE, and raises.

---

## F-M5A-2 — one defect, four files, four different plausible wrong answers

**This is the important one.**

`set_config(key, value, true)` is TRANSACTION-local. That is deliberate: M1-D's migration
0005 changed it precisely because context that outlived `COMMIT` travelled back to the pool
with the connection and leaked into the next request. The guarantee is real and worth
keeping.

What nothing wrote down is the other half. **Outside an explicit transaction, every
statement is its own transaction**, so context set that way is gone before the next
statement reads it. It does not error. It does not warn. Row-level security then matches
nothing, and the caller gets an empty result that is indistinguishable from an honest one.

In M5a it produced four different wrong answers in four files:

| File | What it looked like |
|---|---|
| `api/src/node/identity.ts` | every node refused to start, with a message about fingerprints that read as a sensible answer |
| `api/src/routes/node.ts` | the connectivity banner answered **CONNECTED** — see F-M5A-4 |
| `api/src/node/sync-worker.ts` | every synchronization round failed |
| `api/src/node/realtime-gateway.ts` | the watermark read zeros forever, so nothing was ever pushed and the screens silently stopped updating |

Four symptoms, one cause, **none of them saying "you have no context"**, and three of them
plausible enough to be believed.

**How the first one survived being tested.** `identity.ts` was checked three ways — wrong
outlet, wrong fingerprint, wrong node code — and all three arms agreed on
`NODE_IDENTITY_MISMATCH`. They agreed because **none of them was reaching the check**.
Agreement between arms that share a defect is not corroboration. The fourth arm — a
*correct* start — is what exposed it, and it was only added because the first three
agreeing on the same answer looked wrong.

**Repaired once, not four times.** `api/src/node/context.ts` is a single helper that cannot
be called without a transaction, and all four callers use it. The file's docstring carries
this table, so the next person meets the rule rather than the symptom.

**It then happened a fifth time, in the suite written to catch it.** `tests/m5a` hand-rolled
the same context instead of using `tests/m1a/pg.run()`, which already sets it in a prelude
whose output is discarded. `SELECT set_config(...)` returns a row, and `Result.scalar` reads
the first result set — so every check in the file read back the tenant id and compared it
against what it expected. Half the suite failed with the same wrong value, which at least
pointed somewhere. **A check that happened to expect a uuid would have passed.**

---

## F-M5A-3 — a refusal that could never fire

Migration 0039 gave `edge.authenticate_node()` four separate refusals on purpose, and said
why: *"Unknown, revoked, wrong fingerprint and wrong outlet are four refusals, not one,
because an operator should not have to guess which of them happened."*

Three of them were reachable. `NODE_OUTLET_MISMATCH` was dead code from the moment it was
written — in the function whose entire job is FR-CFG-001E's *"prove it starts only with the
correct outlet identity"*.

`edge.node` carries FORCE row-level security scoped by (tenant, outlet), and the node
process set its context to the outlet it **believed** it served before asking whether that
belief was right. A node booted with the wrong outlet id looked for its own registration in
a scope the registration is not in, found nothing, and was told:

> `NODE_UNKNOWN`: no node NODE-H2 is registered for this tenant

which the function had not verified and which was false. The node was registered. It was
standing in the wrong room. **An operator reading that goes and re-registers a node that
already exists, and the mistyped outlet id survives.**

**The proof was there and the diagnosis was wrong**, which is the harder half to notice —
the node *did* refuse to start.

**Repaired in 0046 with a policy, not a widening.** The tempting fix is to let a node read
its tenant's nodes and compare, which hands every outlet its siblings' fingerprints,
endpoints and secret-store references in order to fix a message. What the node actually has
at boot is its own fingerprint, and presenting it *is* the authentication — so the policy
discloses exactly one row to a caller that already knows that row's fingerprint. The lookup
is now by what the caller **proves** rather than by what it **claims**, which is what makes
the outlet branch reachable at all.

Found by starting the process. Not by reading the function.

---

## F-M5A-4 — a banner that said the outlet was fine because it had failed to look

`edge.connectivity_banner()` returns what FR-EDG-009 puts in front of customers and staff.
Its first version treated *"I could not see a node"* as *"there is no node"*, took the
cloud-only branch — which is correct for a demonstration outlet with no node, since
FR-EDG-001 forbids cloud-only only in production — and returned **CONNECTED**.

A banner that reassures the room because it could not look is worse than no banner: staff
read a reassurance produced by the absence of information.

It now requires the caller's context to match the outlet being asked about and raises
`CONNECTIVITY_OUT_OF_SCOPE` otherwise, which a surface renders as **unknown**. Unknown is a
true thing to say.

The guard then immediately caught the route that reads it — `GET /n/v1/connectivity` was
the second entry in F-M5A-2's table. That is the guard working: the version without it
would have answered CONNECTED, in production, over an outage.

---

## F-M5A-5 — eight aspects M5a was registered to complete, and cannot

`planning/partial_closures.json` named M5a as the completing gate for thirteen open aspects.
M5a genuinely completes **five**. The other eight are moved, each with its reason recorded
in the register:

| Aspect | Moved to | Because |
|---|---|---|
| FR-FUL-008 salience on real paper | M6 | M5a gets bytes to a printer; it does not put ink on paper |
| FR-FUL-014 physical printing and dedup across restart | M6 | dedup across restart IS proved; the aspect as written names both halves |
| FR-FUL-015 rerouting with the node authoritative | M6 | routing offline is proved; an authorized reroute offline is not |
| FR-BIL-017 paper out of a physical machine | M6 | needs a chosen production device |
| FR-TST-005A settlement at the browser tier | M6 | GJ-10 walks one of the five settlement journeys, not the other four |
| FR-NOT-001 outage and sync producers | M5b | M5a produces the outage STATE and no notification from it |
| FR-NOT-005 operational alert producers | M5b | same, and deliberately the same gate |
| FR-INT-007 transport failures in the dead-letter queue | M5b | an unreachable cloud is local continuity, not a dead letter |

**This is a finding rather than bookkeeping.** Eight aspects were filed against the gate
that builds the *machinery* — printing, fulfilment, notification transport — when what each
of them actually needs is the gate that puts the machinery into production. The register's
own rule is what surfaced it: `PARTIAL_CLOSURE_NOT_REVISITED` fires the moment a completing
gate lands, so M5a could not be finished while leaving them open and unexamined.

Two of the five closures needed GJ-10 strengthening before they could be made honestly:
FR-FUL-003 required a cook to **work** a ticket offline rather than an order merely existing
offline, and FR-PAY-002 required cash actually taken during the outage rather than the
structural proof M4-B recorded. Both steps were added. Closing them on the evidence that was
already there would have been the rounding-up this register exists to stop.

---

## The bounds — what M5a does not prove

Named here and named again in the suite's own output, so a reader meets them rather than
inferring them from silence.

**The update attestation is a keyed digest, not a signature.** This database has no
pgcrypto — no `hmac()`, no asymmetric verification. What core PostgreSQL offers is
`sha256()`, and what can honestly be built with it is
`sha256(artifact_digest || the node's trust anchor)`. That proves the publisher knew a
shared secret; it does not prove who they were, it does not survive anyone who has ever read
the anchor, and it has the length-extension weakness every naive keyed digest has. The
column is called `attestation_sha256` rather than `signature` for that reason. **What closes
it:** an asymmetric signature verified over the bundle before the bytes reach the node, with
this check as the second of two.

**The outage is cut at a process seam, not a NIC.** `EDGE_UPLINK=cut` makes the cloud client
refuse to dial, the way it would with the WAN down. Every cloud call goes through
`api/src/node/link.ts` so that "nothing else reaches the cloud" is checkable rather than
asserted — but the process is still on a machine with a working network stack. What it
faithfully reproduces is the only thing a node can observe. **Not reproduced:** a partial
link, a slow link, a DNS lie. Those are M5b's.

**The node's fingerprint is not bound to hardware.** It is read from configuration and
compared against what was registered. A real deployment binds it to a TPM or to a file only
the node's user can read. Nothing here does.

**A death between the paper and the row can still print twice.** Between the write to the
device and the write to the database there is a gap, and a process can die in it. What is
arranged is which way the gap fails: the job stays claimed, its lease expires, and it is
offered again — so a job that *did* print is at risk of a second physical copy.
`docs.complete_print_job()` on an already-printed job changes nothing, which covers every
other failure. **What closes it:** a device that can be asked what it last printed, which no
ESC/POS printer in this class offers.

**The demonstration floor is not ready.** `edge.readiness_report()` reports three of eleven
elements unheld at the seeded floor — allergens, taxes and printers. `safety.allergen` and
`ordering.charge_rule` are empty for every tenant, and no printer is seeded: those
catalogues are created by test fixtures rather than by seeds. Seeding them to make the
number look right would collide with the tenant-unique catalogues `tests/m2b` owns, so the
gap is recorded and the suite asserts readiness against the state it actually runs in. **A
reader should expect the floor's readiness panel to show three gaps.**

---

## What M5a delivered

Ten migrations, three seeds, four processes, one shared surface module, a verification suite
with five negative controls, and GJ-10.

| | |
|---|---|
| `0039` `edge` | the node, its binding to one outlet, its five services, its identity, its health |
| `0040` `ops` | the outlet's physical estate across six device classes |
| `0041` `integration` | outbox, inbox, ordered cursors, the append-only evidence ledger |
| `0042` — | the append-only message repair (F-M5A-1), attributed to M4-C |
| `0043` `integration` | conflict policy over six domains, reconnection, idempotency keys |
| `0044` `docs` | the durable print queue |
| `0045` `edge` | readiness, outage authority, plain language |
| `0046` `edge` | the unreachable refusal (F-M5A-3) |
| `0047` `edge` | the connectivity banner (F-M5A-4) |
| `0048` `edge` | signed updates, compatibility checks, rollback that proves the queues survived |

The five requirements-level things a reader should check first:

- **a production outlet running cloud-only cannot be recorded** — the rule is a CHECK, not a
  start-up guard, because a start-up guard runs on the machine that is already wrong
- **an action nobody classified is refused during an outage**, rather than working by
  accident because somebody forgot to classify it
- **a conflict cannot be settled without a person and a sentence** — there is no automatic
  path, rather than a rule nobody has broken yet
- **a printed job can never return to the queue** — enforced by a trigger rather than by the
  functions that use it, because a function can be called by something new next year
- **rollback refuses if the local queues have shrunk** — an outbox row written while the new
  build ran is work the outlet did, and it is owed to the cloud whichever build produced it
