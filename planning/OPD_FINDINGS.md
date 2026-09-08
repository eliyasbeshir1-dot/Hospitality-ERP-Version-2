# OP-D findings — the order reaching the kitchen, and what a menu says

OP-C made it possible to be seated. The founder then walked the floor, placed an order,
and it stopped: the station board said *"No tickets at this station"* while the order sat
in the database. Everything below came out of that one observation, or out of building the
repair.

---

## F-OPD-1 — the order stopped at acceptance, and no screen could admit it

**The diagnosis, before the repair.** Six orders existed, all `submitted`, all
`accepted_at NULL`. Zero tickets, zero `fulfillment.ticket_event` — not even a ledger
entry, so release had never run. `fulfillment.kds_queue()` returned 0 rows for the seeded
station, with routing and station profiles provisioned: the board was reporting an empty
queue **accurately**.

The seeded ordering policy made `guest_qr` orders `staff_confirmed`, so a placed order
waits for a person. `POST /s/v1/orders/:orderId/accept` has existed since OP-A and works.
Its callers were `tests/journeys` (three sites) and `tests/opa` (one). **No surface called
it.**

And it was worse than a missing button. **No screen anywhere listed an order awaiting
acceptance.** The station board shows TICKETS, and an unaccepted order has none — so the
order was invisible on every screen in the system until somebody accepted it, and nobody
could accept it because no screen showed it. A cook who knew the rule still had nothing to
press.

**The route's own comment described this failure one layer in**, from OP-A:

> *"THE STEP WITHOUT WHICH NO GUEST ORDER EVER REACHES A STATION… `ordering.accept_order()`
> existed with no caller anywhere in `api/src`… Found by placing an order and watching it
> stop."*

OP-A found the *function* had no route and added the route. OP-B built the screens and did
not add the control. The identical finding happened twice at adjacent layers, and the
second time the first one's own comment was sitting there describing it.

### What was built

**Automatic acceptance, seeded.** `seeds/0009` puts `guest_qr: automatic` in force. QR
ordering exists to remove the waiter as the bottleneck; requiring a tap to start puts them
back in front of it. `waiter_entered` stays automatic — the waiter *is* the staff
confirmation — and `counter` stays `staff_confirmed`, because a counter order may be paid
before it is cooked and FR-ORD-007B's payment-dependent acceptance runs through that
branch.

**As a new policy VERSION, not an edit.** `config.policy` carries `version`,
`effective_from` and `effective_to`, and `ordering.effective_policy()` reads whichever row
is in force. Updating the 0003 row would have made every past order look as though it had
always been automatic — the same class of defect as an editable audit trail.

**And `staff_confirmed` still works, because FR-ORD-007A makes it a policy.** The waiter
floor now lists the orders waiting and admits them:

| | |
|---|---|
| `pos.pending_orders()` | oldest first, with the table, the line count and how long it has waited |
| `GET /s/v1/orders/pending` | a staff route |
| the waiter floor | a section **above** the tables, drawn only when non-empty |

**Above the tables**, because FR-POS-002 makes the order of that screen the priority and a
guest whose food has not started outranks a table that merely exists. **On the waiter floor
and not the station board**, because a cook cooks and gating an order is a host act.
**Drawn only when non-empty**, because on a floor that accepts automatically the list is
permanently empty and a permanent "Nothing waiting" heading is one a waiter learns to stop
reading.

### What automatic acceptance moves, and what a demonstration floor will meet

Worth stating because it surfaced within an hour of making the change and it is not a
defect.

Under `staff_confirmed`, an unaccepted order is a row in `submitted`. It costs the kitchen
nothing, and a floor could accumulate them indefinitely. Under `automatic`, acceptance
releases immediately, so **every order becomes live tickets at once** — and FR-ORD-006's
capacity rule then does its job:

    station 33334101-… has 12 live ticket(s) against a threshold of 12;
    the service policy says throttle

Ordering stops until the kitchen works the queue down. **The backpressure has moved from
"orders waiting for a waiter" to "tickets waiting for a kitchen"**, which is where it
belongs — but on a demonstration floor, where nobody marks anything ready, a person
ordering repeatedly will hit the throttle at the thirteenth order and see a refusal that
looks like a bug and is not. `bash tools/open_the_floor.sh` rebuilds from empty and clears
it; working the tickets through the station board clears it properly.

## F-OPD-2 — the guest surface was telling the guest something that was not so

*"Your order is with the kitchen."* Under `staff_confirmed` that is false: the order is in
`submitted`, no kitchen has seen it, and it waits for a person.

The surface could not have known. `POST /c/v1/orders` answered with an id and nothing
else, so there was no outcome for it to be truthful about. The route now reports the state
the order landed in, **read back from the row** rather than inferred from the policy — one
answer, and one that stays right the day FR-ORD-007B holds an order pending a verified
payment.

Two sentences, in all three languages: with the kitchen when it was accepted, waiting to
be confirmed when it was not.

## F-OPD-3 — the menu said what a dish costs and not what it is

FR-MNU-004 asks for a description, the customer-visible ingredients, a preparation time
and images. Per field, as asked:

| field | seed | route / function | surface |
|---|---|---|---|
| short description | **writes it** since 0003 | did not return it | did not render it |
| long description | **writes it** | did not return it | *deliberately still not rendered — see below* |
| customer-visible ingredients | **writes it** | did not return it | did not render it |
| preparation time | **writes it** | did not return it | did not render it |
| images | **writes nothing** | — | — |
| image derivatives + alt text | **writes nothing** | — | — |

So for four of the six the data was there, the requirement was met in the schema, and one
function returned a name and a price. `menu.published_menu_for_guest()` now returns all
four; the route passes them through as nulls-are-nulls; the card renders description,
ingredients and preparation time.

**Where the prose comes from, and why not the snapshot.** Commercial terms — price,
currency, availability, tax context — stay read from `menu.publication_snapshot_line`,
because a guest must be charged what was published. The prose is read live from
`menu.sellable_item`. A snapshot pins what somebody agreed to pay; a corrected ingredient
list is not a change to that agreement, and freezing the words would mean a typo could only
be fixed by republishing the menu.

**The long description is carried and not drawn.** The short one is what a guest reads
while choosing; putting both on every card turns a five-dish menu into a page of prose and
buries the price and the allergens under it. It is in the payload for a detail view
somebody may build. Recorded here rather than rendered because it happened to arrive.

### Images are not closed, and are not pretended to be

This is not one gap but three, and the third is a subsystem.

`menu.image` and `menu.image_derivative` exist and carry alt text. Both hold **zero rows**
on every database this repository builds — that is the seed. But `menu.image` is private by
CHECK CONSTRAINT — `image_source_is_private CHECK (is_private)`, with no value that
publishes it — and `menu.image_derivative`'s own comment says *"none is public. Access to
any of them goes through the same signed, expiring, authorized URL path as the source."*

**No such path exists.** Nothing under `api/src` serves an image or signs a URL for one.
So seeding image rows would hand the guest surface a storage key it cannot turn into a
`src`, and rendering an `<img>` pointing at nothing is worse than rendering none. Images
need storage, signing, expiry and authorization — a gate, not a column. Naming that is the
honest close; building half of it would have made the requirement look met.

## F-OPD-4 — the census pooled two different questions, and that is why this was missed twice

**You said this fix is worth more than the other three. It is, and the reason is
measurable.**

`tools/uncalled_routes.py` pooled its callers: `tests/**` and the four surfaces went into
one "called" count. It answered *"does anything call this route"* and never *"can a person
reach it."* A route driven only by a suite was indistinguishable from one a cook presses.

`POST /s/v1/orders/:orderId/accept` — the step without which no guest order reaches a
kitchen — was called by two suites and no surface, and the census reported it **green**
while an order sat in `submitted` with no screen able to show it. F-OPB-9 had already named
the shape: *"no amount of adding tests of this shape would have caught it."* The instrument
meant to find such things was averaging them away.

Now: **reachable** when a surface calls it, **proved** when a suite does, reported apart.

    117 addressable route(s); 50 REACHABLE BY A PERSON (a surface calls them);
    47 proved by a suite and reachable by nobody; 20 called by nothing at all

The middle column prints first, because a route with no caller at all was always obvious
and this set never was. It is **not a defect on its own** — an operator route or an
integration endpoint has no screen by design — but it is where every "the tests pass and a
person cannot" finding in this repository has come from.

### The reader could not see a single surface call, and that had been true all along

Building the split exposed why it had never been possible. **Not one of the four surfaces
calls `fetch()` with a literal path for its API traffic.** Every one wraps it —
`waiterApi('GET', '/s/v1/home')`, `api('POST', '/s/v1/bills', …)` — and inside the wrapper
the argument to `fetch()` is a variable, which the reader correctly refuses to guess at.
Every surface call landed in `unresolved`.

That did not matter while one count answered both questions: the Python readers saw the
suites and the number came out right for the question being asked. It mattered the instant
the question became "can a *person* reach this" — a reachability number built on a reader
blind to every surface would have said **15 of 117** and been worse than no number.

The TypeScript reader now reads the `(verb, path)` helper shape the Python reader has
always read. Four new self-test cases, each written to fail under the reader that preceded
it. Fixing it also moved "called by nothing" from 26 to 20: the census had been
**understating** coverage as well.

## F-OPD-5 — a new staff action needs three things, and this is the second time

`order.accept` is a new action on a staff screen. The waiter surface grades an **ungraded**
action as `deliberate` — confirmation plus a written reason — which is the fail-closed
default and is right. Ungraded, the Confirm button would have demanded a reason and then
done nothing, which is exactly how `table.seat` behaved at OP-C.

It was graded in the same migration that created the list it appears on, rather than after
somebody pressed it. But the grade still did not reach the demonstration tenants, because
the trigger fires on tenant INSERT and `pos.install_registries_for()` has to be *called* —
and `seeds/0008`, which exists to call it, is checksum-locked and already applied.

So it needed `seeds/0010`. **That is now the pattern, and it will recur:**

1. the action in **both** lists in a migration (the tenant trigger and the installer),
2. a seed that calls the installer for tenants that already exist,
3. the button.

Miss the second and the action is graded for nobody. Miss the first or second and the
button demands a reason and does nothing. A migration cannot do step 2 — it runs with no
tenant context, `org.tenant` carries FORCE row-level security, and a backfill `SELECT` over
it matches nothing, which is why `pos.install_registries_for()` exists at all.

`order.accept` is graded **elevated**, not routine: admitting an order commits a kitchen to
cooking it and a guest to paying for it. It is deliberately **not** a governed action —
grading and governing are different questions, and admitting an order needs a signed-in
member of staff and nothing further.

## F-OPD-6 — `open_the_floor.sh` could not start on Windows, by a defect already fixed elsewhere

The first attempt to run the full rebuild died on the migration step with
*"Python was not found; run without arguments to install from the Microsoft Store."*

The script asked `command -v python3` and took yes for an answer. On Windows that resolves
to the Microsoft Store alias in `WindowsApps` — a zero-byte stub that runs nothing — so the
check passed, the fallback to `python` never fired, and the rebuild died with the Store's
advertisement as its error message.

**This defect was found and fixed once already.** `tests/*/run_verification.sh` met it at
the cross-platform gate and was repaired to *run* every candidate rather than merely locate
it; `docs-local/CROSS_PLATFORM_COMMANDS.md` records it by name as one of the seven defects
Linux could not expose. The repair never reached `open_the_floor.sh` — so the one entry
point a person actually types was the one place still carrying it.

It now uses the drivers' own probe and fails with a message naming what is missing.

## F-OPD-7 — layout, recorded and not restyled

You asked for these to be named rather than fixed now, so they are named.

- **The menu card is a flat stack.** Name and price on one line, then description, then
  ingredients and preparation time, then allergens, then Add. Nothing groups them and
  nothing establishes which matters most; on a five-dish menu it reads as one long column.
- **The waiter floor has four stacked sections** — Next, Waiting to be confirmed, Tables,
  Notifications — with the same heading weight and no visual separation. The priority is
  in the DOM order and nowhere else.
- **The till's two boxes are labelled but not laid out.** Bill and Tip are full-width
  siblings; on a wide screen the tip box sits far below the bill it belongs beside, which
  is the arrangement FR-BIL-014 permits but not the one it is best served by.
- **Nothing on any surface has been designed at a breakpoint.** Every screen is a
  single-column flow that happens to work at the widths the probes use.

None of this is a correctness defect and none of it is measured by any control. It is the
next thing a person will notice after the things this gate fixed.

---

## What OP-D delivered

| the ask | status |
|---|---|
| **Seed `guest_qr` as automatic; keep `staff_confirmed` working; put the accept control on the waiter floor** | **MET.** Both paths run and both are driven by the suite; NC-OPD-002 proves the policy is honoured in both directions. |
| **Stop the guest surface lying** | **MET.** The route reports the state; the surface says which of the two happened, in three languages. |
| **The menu: say per field whether it is seed, route or surface — then close it** | **MET for four fields, named for images.** Description, ingredients and preparation time were a route gap over data the seed had always written. Images are a missing serving subsystem, not a column, and are not half-built. |
| **Split the census** | **MET.** Reachable / proved / uncalled, reported apart — and the reader taught to see surface calls at all, without which the split would have been fiction. |
| **Layout: record, do not restyle** | **RECORDED.** F-OPD-7. |

45 checks, 9 measured in a browser, 5 controls each proved red then green.

## What OP-D did not do

The bill you saw rendering *"Total"* with no lines **could not be reproduced**, and I am
not going to invent a cause. On the rebuilt floor: the guest bill section is correctly
hidden with no bill (`hidden` attribute set, `display: none`, zero height); the till's empty
state reads *"Bill / No bill is open"*; and no check or bill existed on the floor at all, so
none could have been opened. `billing.bill_preview_lines()` has a last-resort label
fallback, so missing wording cannot drop lines either. If you see it again, the screen it
was on would settle it.

F-OPB-3 is unchanged: the demonstration floor still cannot compose a receipt or accept an
allergy declaration, and a stale scan still cannot be resolved by anybody, because those
catalogues are tenant-unique and fixture-owned. F-OPC-3 is unchanged and still open by your
decision.

Nothing here touched M5a, M5b or M6. No fenced domain is named anywhere in this gate's
migration, seeds, routes, surfaces or suite — checked programmatically against all 63 terms.
