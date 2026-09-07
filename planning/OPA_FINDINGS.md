# OP-A findings — what the operator gate found by trying to use the system

**Gate:** M-OP, slice A · **Predecessor:** M4 at `c65c633` · **Branch:** `claude/operator-gate-opa`

The brief named four requirements that were built and unreachable, each found by use rather
than by test. Executing OP-A closed three of them and found **three more of the same shape**.
They are recorded here rather than absorbed into the repair, because the pattern is the
finding: *everything built except the step that makes it usable.*

---

## F-OPA-1 — FR-AUTH-007's secure-storage limb was never met at M1-B

**Not a gap in this gate's scope. A defect in an approved one.**

`identity.credential` has stored a bare 32-byte digest since migration 0004. Every row the
build ever wrote said `sha-256`, and there was **no salt column and no cost parameter**, so
the table's SHAPE forecloses key stretching: a user-chosen secret could only ever be stored
as an unsalted fast hash. A four-to-six digit quick PIN under that scheme is recoverable
from a single database read in the time it takes to enumerate a million digests.

FR-AUTH-007 asks for "secure credential/OTP handling" and is classified **MODIFY**. The
lockout half was built and proved at M1-B; the storage half was not — and nothing failed,
because **no function ever verified a credential**. The gap was invisible for exactly as
long as login did not exist. It became visible the moment something had to read one.

**Repaired here, under an explicit instruction to exceed the brief's "no new schema" rule.**
Migration 0033 adds `salt` and `kdf_params`, and a CHECK constraint that refuses a chosen
secret which is not salted and key-stretched. scrypt with a 32-byte derived key satisfies
`credential_digest_is_a_digest` unchanged — the existing guard is not weakened, which is
why bcrypt was rejected: its 60-character output would have required exactly that.

**Still open:** the OTP and service-secret kinds keep `sha-256` deliberately — they are
single-use high-entropy values, where stretching costs the server and protects nothing.
That asymmetry is stated in the constraint's own comment so a later reader does not
"fix" it.

### The evidence: M1-B's own fixtures were writing unsalted sha-256

This is worth stating as evidence rather than as collateral from the migration, because it
is the clearest available demonstration that the limb was never met.

The first full run after migration 0033 landed died sixty seconds in:

```
=== 4. M1-B verification gates ===
RuntimeError: outlet A1 fixtures failed: ERROR: 23514:
  new row for relation "credential" violates check constraint
  "credential_chosen_secret_is_key_stretched"
```

`tests/m1b/fixtures.py` had been storing a **password** and a **four-digit-class quick
PIN** as unsalted `sha-256` since M1-B was written, and `verify_m1b.py` asserted only that
stored credentials were 32-byte digests — which an unsalted fast hash satisfies perfectly.
So the suite that owns FR-AUTH-007 was itself writing the storage the requirement forbids,
and its own checks could not see it, because nothing in the schema or the suite ever asked
the question the requirement actually asks.

The constraint caught the build on its first real encounter, in the gate that owns the
requirement. That is the repair working, and it is also the proof that the gap was real
rather than theoretical.

**Both writers are now converted** to scrypt at the parameters `api/src/routes/auth.ts`
derives with — N=16384, r=8, p=1, 32-byte key — so what M1-B stores is what the login
route verifies, rather than a weaker variant that would exercise a path the product does
not have.

And `verify_m1b.py` gained the check that was missing. Its existing plaintext test plants
`'a-plaintext-password'::bytea`, which is 20 bytes — so the 32-byte CHECK refuses it and
the key-stretching rule is never reached. A control passing for a reason other than the one
it names. The new row is a genuine 32-byte sha-256 digest, refused because a chosen secret
may not be stored that way, with a companion row proving the same secret IS accepted once
salted and stretched — so the constraint is shown to refuse fast hashes rather than to
refuse everything.

---

## F-OPA-2 — no route accepts an order, so no guest order could ever reach a kitchen

`ordering.accept_order(tenant, order, user)` existed, was granted to the application role,
and **had no caller anywhere in `api/src`**. The seeded ordering policy makes a `guest_qr`
order `staff_confirmed`, so a placed order waits in `submitted` until a staff member
accepts it — and `ordering.release_accepted_order` is a *trigger on acceptance*, so
acceptance is the act that creates the kitchen's tickets.

The consequence is exact: **a guest could place an order and it would sit in `submitted`
for ever.** The KDS finding in the brief said no route reaches the thirteen fulfillment
writers; this is the step before that, and without it the thirteen would still never
receive anything.

**Repaired here** — `POST /s/v1/orders/:orderId/accept`, a route over a function that
already existed. Connection, not construction.

---

## F-OPA-3 — nothing opens a table occupancy (RECORDED, NOT REPAIRED)

**This is the one the walk could not do through the product.**

`service.join_table_session()` refuses with `NO_OPEN_OCCUPANCY` unless the table already
has an open occupancy. Nothing in this build opens one:

- no route inserts `service.table_session`
- no database function inserts `service.table_session`
- only test fixtures create one, by direct INSERT
- the application role **already holds INSERT/UPDATE/DELETE** on the table
- the `opening_source` enum **already carries** `qr_scan`, `staff`, `host_stand`

The grant is present, the vocabulary is present, the join function is present. Only the
caller is absent — the same shape as the four the brief lists, and as F-OPA-2 above.

**Deliberately not repaired.** Building it means deciding *when* an occupancy opens and
*who* opens it, and that is not a missing wire — it is a product decision that touches
M2-B's approved session model. The slice that does not own that model should not fix its
shape by writing whichever answer makes a walk go green.

### The open product question, which is what whoever closes this actually needs

> **Does a guest scanning a QR code at an empty table seat themselves, or does a member of
> staff seat them first?**

Both are real restaurants. They are not the same product:

| | guest seats themselves | staff seats the guest |
|---|---|---|
| `opening_source` | `qr_scan` | `staff` / `host_stand` |
| who is `host_staff_user_id` | nobody — the column goes null | the server who seated them |
| a guest scanning an occupied table | joins the party already there | joins the party already there |
| a guest scanning an empty table | starts a party | **is refused** until seated |
| walk-ins with no host stand | works | cannot order at all |
| covers/turn-time reporting | inferred | recorded at the moment of seating |

The enum carrying all three values suggests the intent was that an outlet **chooses** —
which would make this a policy (`config.policy`, category `service`), not a constant. That
is a third possible answer and probably the right one, but it is a design decision and this
gate does not own it.

**Until it is answered, the demonstration floor cannot seat a guest and the guest half of
the walk cannot run through the product.** The walk opens the occupancy by direct INSERT
and says so in its own output, including in its verdict line.

---

## F-OPA-4 — a printer test recorded the caller's claim, not the agent's evidence

`POST /s/v1/printers/:printerId/test` took `outcome` from the request body and stored it.
The M4 reviewer registered a printer whose `device_path` was `./NUL`, POSTed
`outcome='printed'` to it **as the least-privileged role with no step-up**, and the build
then reported a tested, working printer with no agent having run and no bytes having gone
anywhere. FR-CFG-001D's precondition — a receipt may only be printed on a printer that has
passed a test — was satisfiable by assertion.

Two independent defects had to line up, and both are repaired in migration 0034.

**The classification was three exact lowercase spellings.** 0032 refused `/dev/null`,
`nul` and `nul:` by string equality. Windows resolves far more than that to the null
device, and `docs.is_null_device_path()` now normalises separators, takes the final path
component, strips a trailing colon and compares the part before the first dot:

| path | 0032 | 0034 |
|---|---|---|
| `/dev/null`, `nul`, `NUL`, `nul:` | null device | null device |
| `./NUL` | **a real device** | null device |
| `C:\logs\NUL` | **a real device** | null device |
| `\\.\nul` | **a real device** | null device |
| `NUL.txt` | **a real device** | null device |
| `/dev/lp0`, `C:\printers\thermal` | a real device | a real device |

Four spellings that reached paper-claiming code now do not, and the two real devices are
still real. The classification lives **where the value is stored**, in a CHECK on
`docs.printer`, not in the agent — so no caller and no future agent can disagree with it.

**The outcome was an input.** `docs.record_printer_test()` now takes the agent's
report — which sink it put the bytes on, and what the platform resolved the destination
to — and refuses with `PRINTER_TEST_EVIDENCE_DISAGREES` when that contradicts the
printer's own classification. The outcome is then *derived* from the classification. A
printer that discards cannot be recorded as having printed, whatever the request says.

**The sibling defect, found while repairing this one.** `POST /s/v1/receipts/:receiptId/prints`
and `docs.record_receipt_print()` had the identical hole, and that one claims a
**customer's receipt** was produced — the artefact the customer takes away and the record
FR-BIL-010's duplicate rules reason about. Section 4 of 0034 closes it the same way.

**And the boundary is the table, not only the function.** Both repairs above live inside
`docs.record_printer_test()` and `docs.record_receipt_print()`, which closes the route the
review used — but `hospitality_app` holds `INSERT` directly on both tables, so a handler
writing its own `INSERT` would never reach either comparison. The repository already puts
this class of rule at the table (`print_attempt_outcome_matches_the_sink` is a trigger, not
a function body), so the agent's evidence now sits beside it: `agent_sink` is `NOT NULL` on
both tables, and a trigger refuses a row whose reported sink disagrees with the printer's
classification, whatever wrote it. Proved against a direct `INSERT` that never calls either
function:

| direct INSERT against a printer classified `discard` | result |
|---|---|
| `outcome='printed'` | refused — `NULL_DEVICE_CANNOT_CLAIM_PAPER` |
| `outcome='discarded'`, no agent report at all | refused — `PRINT_EVIDENCE_DISAGREES` |
| `outcome='discarded'`, `agent_sink='device'` | refused — `PRINT_EVIDENCE_DISAGREES` |
| `outcome='discarded'`, `agent_sink='discard'` | accepted |

The third row is the one that matters: the outcome agrees with the sink, so the rule that
existed before this migration passes it, and only the evidence check catches it. The new
triggers are named to sort *after* the existing ones, because PostgreSQL fires triggers in
name order and every refusal that had a name before this migration still answers to it.

**What this does not do.** Nothing authenticates the print agent; there is no shared
secret. A caller can still misreport what it observed. What it can no longer do is have
that misreport recorded as a print by a printer that cannot print — through the route,
through the function, or by writing to the table directly. That limit is stated in the
migration header rather than left for a reader to discover.

**Why it survived.** `POST /s/v1/printers/:printerId/test` is a route **nothing had ever
called**. M4-C's printer tests all invoke `docs.record_printer_test()` directly from their
fixtures. The route census said so and nobody read it that way — which is the second
finding below.

## F-OPA-4b — and the first caller found a second defect, exactly as the file predicted

`documents.ts` maps each database refusal to an HTTP status; anything absent from that map
answers **500** and logs `unmapped database refusal`. A comment in that file records the
last time this happened, at the second M4 repair:

> Nothing had ever called it, so nothing had noticed that the refusal a second original
> print raises was absent from this map: the route answered 500 and logged "unmapped
> database refusal" for a business rule working exactly as designed. Same shape as the
> M4-A billing routes and GJ-01A — the first caller finds the defect.

Both refusals migration 0034 added were missing from the same map. NC-OPA-009 is the first
thing ever to POST to the printer-test route, and on its first run the forgery was refused
correctly by the database and then reported to the caller as **HTTP 500** — which reads as
"this service is broken" rather than "your claim was rejected". The data was never at
risk; the answer was wrong, and a reviewer forging a print would have been told the wrong
thing about why it failed.

Both now map to 422, as does the CHECK that refuses registering a null-device path with a
device sink. The control asserts the **class** — that both answers are 4xx — rather than
"not 200", so the next unmapped refusal fails in the suite instead of in front of somebody.

This is the third recorded instance of one pattern: a route nothing has called has an
untested error path, and the first caller finds it. It is also the argument for F-OPA-5
below — the instrument that says which routes have no caller was itself miscounting.

## F-OPA-5 — the route census counted a quotation as a call

The census exists because of GJ-01A: writers proved against the database with no route
reaching them, every unit check green and the feature unreachable. It is the instrument
that is supposed to catch exactly the condition F-OPA-4 was hiding in, and it was
miscounting in three ways, all of which flattered the service.

* **It could not see the verb.** It matched on the path alone, so a caller of
  `POST /s/v1/checks` credited `GET /s/v1/checks` as well. Four paths carry two verbs.
* **It matched a path as a substring.** Fifteen route paths are a strict prefix of
  another, so every caller of `POST /s/v1/receipts/:id/prints` credited
  `GET /s/v1/receipts/:id`, which nothing had ever called.
* **It could not tell a request from a quotation of the service's own source.** M4-A
  asserts on the text of the handovers route; those two quoted lines were the *only* thing
  crediting `GET` and `POST /s/v1/handovers`.

The reader now takes call expressions rather than string literals: a helper invoked as
`(method, path)`, a helper carrying the verb in its name, an attribute call named for the
verb, or a surface's `fetch()` and navigation. The route pattern must match the caller's
path **in full**. Twelve properties are checked against inputs whose answer is known
(`python3 tools/uncalled_routes.py --self-test`, also run by `tests/opa`); **the reader at
the previous commit gets four of the twelve wrong.**

The corrected count is **84 of 108 routes called, 24 by nothing**, from 327 call sites,
with 3 whose path is built at runtime and which therefore credit nothing. Before the
repair the same service read as 85 of 108 — four routes were being credited to callers
that did not exist, while the strictness also recovered callers the old reader had missed.
Three of the newly-credited routes are the printer routes this gate gave an HTTP caller
for the first time, in NC-OPA-009.

## F-OPA-6 — nine generators wrote a different file on Windows than in CI

`Path.write_text()` opens in text mode, so Python translates `\n` to `\r\n` on Windows and
leaves it alone on Linux. Nine tools that write **committed** artefacts did that — the
schema catalog, the evidence report, the review findings, the CI matrix, the README, the
ownership map, the architecture plan and two JSON reports — and every one of them also has
a `--check` mode CI runs to prove the committed copy is current. So regenerating on
Windows produced a diff CI could not reproduce, and the working practice had become
"generate these in a Linux container to match CI" rather than fixing the generators. All
nine now pin `newline="\n"`, with the reason recorded at each call site. This is the same
class as the M4 review's CRLF finding and as the null-device spellings above: behaviour
that varies by platform in a place the repository treats as canonical.

**One of the nine still needs the container, for a different reason.** The evidence report
records the live `sys.version` and `node --version` of whatever generated it, and CI
regenerates it and `diff`s it against the committed copy — so a report generated under
Python 3.12 and Node 24 fails CI on two lines that describe the machine rather than the
build. That is not a line-ending defect and pinning newlines does not touch it. It is
arguably not a defect at all: the report is evidence about a run, and the versions are part
of what ran. But it does mean this one artefact can only be regenerated in an environment
matching CI's, and the commit that lands it must touch nothing else, because the report
anchors to the last commit that changed anything other than itself. This pass generated it
in `node:22-bookworm`, which carries Node 22 and Python 3.11 — CI's exact pair.

## F-OPA-7 — M4-C's requirement audit has never run on a developer's machine

M4-C asks `tools/requirement_coverage.py` whether the run accounts for every requirement,
reading citations out of `$M4C_LOG_DIR`. CI runs each suite as its own workflow step and
tees each to `$LOG_DIR/<suite>.log`, so that directory exists there. The local chain is one
nested script writing one combined log, and `M4C_LOG_DIR` is unset, so it defaults to a
temp path that does not exist — and the suite refuses, correctly, because reading citations
out of no output would report every requirement unaccounted.

So the section is exercised only in CI. That is not wrong, but it means a developer running
the chain locally gets a **different set of checks** from the one CI runs, and the
difference is invisible unless the chain reaches M4-C — which, before this pass, it had not
done locally in this repository's history. It is recorded rather than repaired because the
fix is a change to how sixteen `run_verification.sh` scripts record their output, which is
harness work rather than repair work, and because CI does run it.

For this pass the local runs reconstruct the per-suite layout from the combined log by
splitting on the suites' own verdict lines. The audit then sees the same partial set CI's
M4-C step sees — 13 logs, with `m4c`, `opa`, `fenced_gate` and `journeys` still to come —
and refuses it with `SUITE_LOGS_INCOMPLETE`, which is the branch M4-C asserts. The complete
account is asserted by the workflow step that runs after every suite and every journey, and
that step is the only place a complete set has ever existed.

## What OP-A delivered against the brief's four

| the brief's finding | status after OP-A |
|---|---|
| **The KDS cannot be operated** — 13 writers, 0 routes | **MET.** Every writer is routed. One generic transitions route drives all eleven states by calling `fulfillment.transition_ticket`; the other writers have their own routes. No transition rule is restated in TypeScript. |
| **Nobody can log in** | **MET, and more than asked.** `POST /v1/auth/login` turns a credential into a session; the storage it verifies against was also repaired (F-OPA-1). Quick PIN is bound to a registered terminal, lockout fires, rate limits apply. |
| **Staff surfaces make no network call** | **NOT IN OP-A.** Explicitly OP-B. |
| **There is no product seed** | **MET.** Seeds 0003 (content) and 0004 (provisioning): two tenants, a published three-language menu, priced variants, modifiers, dining tables with QR tokens, stations, routing rules, and staff who can log in. |
| **A printer test records the caller's claim** (added after the brief) | **MET.** Migration 0034: the null device is classified where it is stored, across every spelling the reviewer used and four more; the outcome is derived from that classification rather than taken from the request; the same hole in receipt printing is closed with it. Proved over the route by NC-OPA-009 (F-OPA-4). |

## And a fourth thing the seed work exposed

`fulfillment.station_profile`, `routing_rule` and `routing_rule_set` are SELECT-only to the
application role by a deliberate M1 decision — "installing a station is a configuration
act". A content seed therefore **cannot** create a station, and a floor with no station
takes no orders. Rather than widen the grant, `tools/seed.py` grew a provisioning class
(`*.provision.sql`) applied under the migration identity, with three guards: the
provisioning pass may write only those three tables, it may not issue a GRANT, and after
every seed the runner re-reads the catalog and refuses if `hospitality_app` holds anything
beyond SELECT on them.
