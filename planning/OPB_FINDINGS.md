# OP-B findings — what building the staff screens found

OP-A gave the kitchen thirteen routes and nobody could press them. OP-B is the screens, and
every finding below was found the same way: by being the first thing to ask the system for
something a person would ask it for.

---

## F-OPB-1 — the cashier could not read a bill

`billing.bill_summary()`, `billing.bill_preview_lines()` and `billing.tip_options()` were
delivered at M4-A and reachable **only by a guest**. All three were called by `/c/v1/bill`
and `/c/v1/bill/tip-options` under `asGuest` and by nothing else. `POST /s/v1/bills`
returns `{ billId }`; `GET /s/v1/checks` returns allocations, not bill lines or totals.

So a till could open a bill, split it and take money for it, and had no route that told it
what the bill **said**. No cashier screen could have been built at M4-A even if somebody
had tried, which is part of why none was.

Closed by `GET /s/v1/bills/:billId` and `GET /s/v1/bills/:billId/tip-options`, calling the
same three functions the guest routes call — asserted by reading both routes' SQL, not by
comment. The bill reads back in **its own locale** (issued `am`, read by a non-Amharic
cashier, returns `am`), and scope is the database's: `billing.bill` carries RLS FORCE with
`app.row_in_scope(tenant_id, outlet_id)` and the functions are SECURITY INVOKER, so a
sibling outlet's bill and another tenant's manager are both refused `BILL_NOT_FOUND`. There
is deliberately no ownership check in the route to go stale beside the policy.

## F-OPB-2 — the demonstration floor could not be paid

OP-A's floor could seat a guest, take an order and cook it. Then it stopped. Three
separate refusals, each found by the next thing the till tried:

| refusal | what was missing | closed by |
|---|---|---|
| `BILL_TAX_UNCONFIGURED` | an **outlet**-scoped `tax` configuration | `seeds/0005` |
| every payment, including cash | `payments.payment_adapter` rows | `seeds/0006` |
| `SERVICE_POLICY_INCOMPLETE` | three of the five keys the `service` policy's readers need | `seeds/0007` |

The tax one is worth its own sentence. Seed 0001 writes a **tenant**-scoped `tax` row
shaped `{"vat_percentage": …}`. `billing.issue_bill()` reads neither: it selects on
`outlet_id` and reads `payload -> 'contexts' -> 'standard' ->> 'percentage'`. Two rows,
both called tax, in two shapes, for two readers — and the one a bill needs had only ever
been written by `tests/m3a/fixtures.py`, for Kazanchis.

The service policy is the sharpest of the three: `notify.accountable_staff` needs
`critical_alert_role_code`, and placing an order **with an allergy declaration** notifies
the accountable role — so on the demonstration floor a guest declaring an allergy could not
place an order at all. OP-A never met it because its declaration resolved to nothing on a
floor with no safety vocabulary, so the notification never fired.

All three are follow-on seeds rather than edits, because seeds are checksum-locked and an
edit refuses to apply on every database that already ran the original.

`seeds/0006` is a provisioning seed, and it grew the privileged set from three tables to
six: `billing.tip_setting`, `billing.tip_suggestion` and `payments.payment_adapter` join
the fulfillment three. Each is decided when an outlet is **installed** and then read, not
written, by the running service. The contrast that makes the boundary checkable is
`billing.bill`: also SELECT-only to the app role, and **not** provisionable, because a
function writes it in the course of business. Membership is decided by who decides the row,
never by which grant is in the way. `billing.service_charge_setting` was approved for the
set and is not in it: a floor with no service charge is correctly represented by no row,
and admitting a table nothing writes would widen the boundary for nothing.

## F-OPB-3 — the demonstration floor and the test fixtures compete for the same vocabulary

**This is the structural finding, and the three above are two of its symptoms.**

Some catalogues in this system are scoped per outlet, and some are unique per tenant. A
seed can own an outlet-scoped one: `seeds/0005` gave Sarbet its own tax configuration
beside Kazanchis's without touching it. A seed **cannot** own a tenant-unique one, because
the test fixtures already own it for that tenant, and whoever writes first owns it.

Three tenant-unique catalogues have only ever been written by fixtures:

| catalogue | owned by | what it blocks on the demonstration floor |
|---|---|---|
| `safety.allergen`, `safety.approved_wording` | `tests/m2b` | a guest cannot declare an allergy; a ticket can never show allergy emphasis |
| `billing.component_wording` | `tests/m4a` | a bill has no words for its components |
| `docs.line_wording` | `tests/m4c` | a receipt has no words for its lines |

Each was discovered when something first tried to use it, one gate at a time, and each
looks like an isolated omission until they are put beside each other. They are not three
omissions. They are one condition: **the demonstration floor and the test fixtures are the
same tenant, and the vocabulary they both need is unique per tenant.**

**What would resolve it is a product decision, and it is not this gate's to make.** Either
the demonstration floor gets its own tenant that no fixture touches — which means redoing
the floor's menu, staff, stations, QR tokens and credentials under a new tenant — or those
catalogues stop being tenant-unique and become outlet-scoped like the tax configuration,
which is a schema change to three subsystems. Whoever closes this needs the question, not
the count, so the question is written here rather than a fourth symptom being reported the
next time somebody meets one.

OP-B did not work around it. Seeding a fourth catalogue for the same tenant would have
raced the fixtures for a unique row, and moving ownership away from `tests/m4a` and
`tests/m4c` would have edited two gates that are already approved, to make a demonstration
convenient.

### What this means for FR-BIL-007, stated rather than left to inference

FR-BIL-007 asks that a bill names its components in the guest's language. **The half that
is met:** the till issues a receipt in the chain, and every figure and word on it is
correct. **The half that is not:** it works because `tests/m4a` and `tests/m4c` wrote the
wording tenant-wide, and the product data cannot produce a receipt at all. On a database
built from migrations and seeds alone, `docs.issue_receipt()` fails on
`billing.component_wording_for()` returning null, and then on `docs.wording_for()` doing
the same. A reader should not have to work that out from a passing suite.

The same sentence applies to the allergy path: OP-A's "a station acknowledges the allergy
declaration through a route" passes in the chain and fails on a product-only database,
which is exactly what a clean rebuild during this gate showed — 48 of 49, failing only
there.

## F-OPB-4 — the surface list was written twice, and the fourth surface found it

`security.ts` decided which paths get the surface content-security-policy from a list typed
out by hand: `'/'`, `'/station'`, `'/waiter'`. Beside it was a comment recording that a
surface "listed somewhere and not here" would be served the API's deny-everything policy
and "would render as a blank page with two console errors, which is how this was found the
first time."

It was found that way a fourth time. The till rendered blank with exactly two console
errors, one for its stylesheet and one for its script.

The instance is fixed by adding `/cashier`; the class is fixed by deleting the second list.
`SURFACE_DOCUMENTS` in `routes/surface.ts` is now both what registers the document routes
and what the security layer reads. Adding a surface puts it in the policy, because there is
no longer a second place to forget.

## F-OPB-4b — a fourth unmapped refusal, found by the fourth caller

`documents.ts` maps each database refusal to an HTTP status; anything missing answers 500.
OP-A found the third instance of this and wrote it up. OP-B found the fourth: a second
receipt for one bill revision is refused by `receipt_one_per_bill_revision` — FR-BIL-010's
one original per settlement, working exactly as designed — and the route answered **500**.

It surfaced only once the journeys began issuing receipts through the till, because that is
the first time anything asked twice: the screen produced one, and the journey's own
`a_receipt()` asked for another. Both halves were correct and the answer was wrong.

Now 409. The count of these is worth stating plainly: **four separate refusals in this one
file have answered 500 to a working business rule**, each found by the first caller of a
path, never by a test written for it. The map is a list somebody maintains beside a set of
rules somebody else adds to, which is the same shape as the surface list in F-OPB-4 and the
route census in F-OPB-7. It is the last hand-maintained list in this file, and the next gate
to touch printing should consider deriving it.

## F-OPB-5 — the card-data rule caught this gate's own code

The till's first idempotency key was `till-${Date.now()}-…`, and
`POST /s/v1/payments/intents` refused it: `CARD_DATA_RETAINED`, *"was given a value shaped
like a primary account number"*. A millisecond timestamp is thirteen digits and a PAN is
thirteen to nineteen. M4-B scans every textual column for that shape and it caught a value
this gate invented, in the first thing that ever sent one.

Recorded because it is the control working, not failing: the rule was right and the key was
wrong. The key is now base-36 only, which cannot produce a run of digits long enough to be
mistaken for a card.

## F-OPB-5b — a browser step that was dead code, and would have lied if it had run

`tests/journeys/journey_probe.mjs` has carried a `GJ-05` branch since M3-D. Nothing has
ever called it: `walk()` was invoked for four journeys and GJ-05 was not one of them, so
`tier_of()` reported it service tier — correctly — while a browser step for it sat in the
probe.

Two defects in one branch. It was unreachable, and it was written to call
`waiterSurface.render()` with a payload the suite handed in, so had it ever run it would
have measured the suite's own data and reported it as what the waiter saw. A test supplying
its own evidence is worse than a missing test, because it produces a green line.

Closed by the surface fetching for itself: the branch now seeds a session, lets the screen
load the floor, and measures what the service returned — including the unpaid balance.

## F-OPB-7 — deriving the surface list made the census blind to it

Repairing F-OPB-4 replaced three literal `app.get()` registrations with a loop over
`SURFACE_DOCUMENTS`. The census reads route registrations by pattern, so `surface.ts` went
from contributing three routes to contributing **zero**, and `/`, `/station`, `/waiter` and
`/cashier` vanished from the denominator.

The total stayed at 108 across the change. Two new billing routes arrived exactly as two
document routes disappeared, and a number that does not move is a number nobody questions.
That is how a miscount hides, and it is the third time this census has been wrong in this
repository's history.

The census now reads the same table. One list: the server registers from it, the
content-security-policy derives from it, and the census counts it. **111 routes, 85 called,
26 by nothing.**

## F-OPB-8 — the new suite would never have run in CI

`tests/journeys/run_verification.sh` chained from `tests/opa`, so the chain was
`journeys → opa → m4c → …`. `tests/opb` chained from `opa` too, and nothing chained from
`opb`. The suite would have existed, passed locally, been enumerated in the CI matrix, and
never executed.

Found by asking what the chain actually runs rather than by trusting that adding a suite
adds it. It is the same shape as everything else this gate exists to close: something
built, something green, and nothing reaching it.

The journeys now chain from OP-B, which chains OP-A, which chains the rest. CI additionally
requires OP-B to report at least ten **measured** checks, because a run reporting zero
measured would mean the browser never opened and the suite had silently degraded into
asserting about payloads — passing, and worth nothing.

## F-OPB-8b — the forbidden-surface gate flagged this gate's own prose, correctly

`tools/verify_m1.py` refuses the name of the row-level-security-escaping role anywhere in a
deployment path, and a file ending `.provision.sql` is a deployment path by name. Seed 0006
explained, in a comment, that the migration role is *not* that role — and was flagged for
saying the word.

Recorded because the tempting repair is the wrong one. This repository has twice fixed a
scanner that could not tell prose from code, so the reflex is to teach this one the same
distinction. Here that reflex is backwards: a provisioning seed is exactly where a bypass
role would be dangerous, the cost of a false positive is one reworded sentence, and the cost
of a false negative is a privileged role in a deployment path nobody noticed. A gate that
would rather flag a comment than miss a grant is calibrated correctly.

The comment was reworded. The gate was not touched.

## F-OPB-6 — the screens rendered and never called

The premise of the slice, recorded because it is the thing OP-B closes. Before this gate
`waiter.ts` and `station.ts` contained no `fetch`, no `XMLHttpRequest`, no `EventSource`
and no `WebSocket`. They exported render functions and waited to be handed data by a test.

M3-B and M3-D measured them by calling those functions with a payload the suite wrote,
which proves the rendering and says nothing about whether a person can reach it. That is
the same defect as a route with no caller, one layer further out, and it is why OP-A could
give the kitchen thirteen routes without a single cook being able to press one.

Both now sign in and fetch for themselves. The render functions stay exported and pure, and
nothing is fetched without a session — so M3-B's measurement, which opens the page with no
service behind it, still measures exactly what it did before.

---

## What OP-B delivered

| the brief | status after OP-B |
|---|---|
| **The station screen** | **MET.** Signs a cook in, fetches its own queue, and draws each ticket's actions from `fulfillment.transition` — one button per legal move, labelled with the database's own reason for that pair. The screen holds no state table. Smallest touch target measures 54px, above the 44px floor, measured rather than asserted. |
| **The cashier screen** | **MET.** Reads a bill in the bill's own language, splits it four ways, keeps the tip box beside the summary with nothing preselected, takes cash, card, Telebirr and CBE Birr, grades confirmation friction from `pos.confirmation_requirement`, and takes a manager's override on the manager's own session. A receipt is produced wherever the wording exists (F-OPB-3). |
| **The waiter network layer** | **MET.** Signs in, fetches home, tables, notifications and requirements in one pass, and renders the unpaid balance `pos.table_view` has returned since M3-D and nothing had ever drawn. |
| **The journeys, browser tier** | **MET and then some.** 4 browser / 7 service became **10 browser / 1 service**, derived from the run. The one that stays service is FR-TST-007A, which opens no browser and races two HTTP requests — the tier rule's own example of a journey that must not be mislabelled. |

### Which half of each journey was walked, stated rather than implied

GJ-01B and GJ-07 settle **entirely** at the till: a cashier opens the bill in a browser,
takes cash, and a receipt is produced. `a_settled_check()` grew a `make_intent=False`
switch so the screen opens its own payment intent — an intent created by the suite and
then ignored by the till would be the test doing the cashier's work and then watching
somebody else do it again.

GJ-02B, GJ-03B and GJ-06 walk the cashier's **view**, not the payment. Each proves a rule
the screen cannot express — that an unverified Telebirr proof settles nothing, that a
terminal slip is required, that a split bill's two tips stay separate — and those stay
where they are proved. The till opens the bill and the tip placement is measured on the
rendered page.

`tier_of()` was extended to follow one level of helper, because moving the cashier's half
into a helper put `walk()` one hop away and five journeys read as service tier while a
browser was demonstrably driving them. Understating evidence is the same class of error as
overstating it. When a wrapper made it two hops, the wrapper was deleted rather than the
rule loosened: "some function somewhere opens a browser" is not a claim about a journey.

## Which of Codex's five P0s are now closed

| P0 | closed by | where |
|---|---|---|
| P0-1 the printer test recorded a caller's claim | OP-A | migration 0034, NC-OPA-009 |
| **P0-2 no cashier browser journey** | **OP-B** | the till; GJ-01B and GJ-07 settle in a browser |
| P0-3 the KDS could not be operated | OP-A routes, **OP-B screen** | a cook now presses the buttons |
| P0-4 nobody could log in | OP-A | `POST /v1/auth/login`, migration 0033 |
| P0-5 no product seed | OP-A, extended by **OP-B** | seeds 0003–0004, plus 0005–0007 so the floor can be paid |

All five are closed. Three of them needed OP-B to be reachable by a person rather than only
by a suite, which was the whole argument for this gate.

## What OP-B did not do

The demonstration floor cannot compose a receipt or accept an allergy declaration, for the
one structural reason in F-OPB-3. `tools/open_the_floor.sh` prints both limits on the way
in, because a demonstration that hides its own gaps is worse than no demonstration.

Nothing here touched M5a's outlet node, sync or print queue; M5b's DNS, TLS or authority
lease; or M6. No fenced domain is named anywhere in this gate's suite, surfaces or seeds —
checked programmatically against all 63 terms.
