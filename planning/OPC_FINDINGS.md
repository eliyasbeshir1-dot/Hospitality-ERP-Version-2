# OP-C findings — the step that came before everything

OP-B ended with four findings a person made in five minutes on a floor nineteen green
suites had signed off. OP-C closes them. The first of the four is the one that mattered,
and closing it turned out to expose a second gap of exactly the same shape one level out —
which is recorded here as its own finding rather than folded into the repair, because the
shape repeating twice is the more useful fact.

---

## F-OPC-1 — nobody could be seated, and now two people can seat

**F-OPB-9, closed.** `INSERT INTO service.table_session` occurred in four files and all
four were tests. No route, no migration and no seed opened a table occupancy;
`/c/v1/join` joined an existing one and there was never one to join. A guest scanned a
real placard, chose dishes, and could not place the order.

The product question OP-A recorded and declined to guess at — *does a guest scanning a QR
seat themselves, or does a waiter seat them?* — was answered: **both**, one function, two
opening sources. A guest scanning an unoccupied table opens the occupancy, and that scan
is the seating act. A waiter can open one too.

`service.open_table_session()` is that function. It is the only writer of a table
occupancy in the delivered code path, and the two things it does differently by source are
the whole of the difference:

| opened by | attributed as | what else it writes |
|---|---|---|
| `qr_scan` | the guest session that scanned | the guest is enrolled as a participant of the occupancy they opened |
| `staff` / `host_stand` | the member of staff, from **their session**, never the request body | the first `service.table_ownership` row — see F-OPC-2 |

`service.opening_source` has had three values and no writer since M2-B. A column with
three values implies more than one writer; until this gate it had none, which is what made
FR-TAB-003 met in shape and unreachable in fact.

**The guest surface calls one route and does not choose between the two.**
`POST /c/v1/seat` opens when the table is empty and joins when it is not, and
`service.seat_guest_from_scan()` makes that decision inside the database. A screen that
decided would be a second opinion about whether a table is busy, and the two would
disagree the moment a party sits down between the scan and the tap.

### What was not weakened, stated because it was the risk

`service.join_table_session()` is **untouched**. The stale-QR guarantee is called
unchanged, verification arguments passed straight through, and this gate added no branch
in which a join simply proceeds. No `service.qr_scan` row is rewritten to make a join
succeed — the column's own comment says an occupancy number is carried "with it forever",
and a function that edited it afterwards would have made that sentence false for every
reader of the column. The guest who opens is a participant by construction, in the same
statement that created the occupancy, which is a different act from joining rather than a
way around it.

NC-OPC-001 is the control that holds this: a scan bound to no occupancy, presented against
one opened since, must still be refused.

### The race, and why the repair is not a loophole

Two people at an empty table can scan in the same instant. One opens; the other's scan was
taken while the table was still empty, so it is bound to no occupancy and M2-B refuses it
as stale — correctly, and by exactly the rule that refuses a photograph from last week.
The device's repair is what that rule asks of anybody: **present the code again.** The
second scan is a real scan, taken now, under the occupancy that is now open, and it joins
on its own merits. Bounded to one attempt, because a loop would be a way of waiting out a
refusal rather than answering it.

## F-OPC-2 — the handover chain has never had an origin

**This is the structural finding, and nobody was looking for it.**

`service.table_ownership` decides who is answerable for a table. Its only non-test writer
is `pos.acknowledge_handover()`, and `pos.propose_handover()` hands over **from** an
existing owner. So the FIRST owner of any table could never be established by the
delivered code path. The other three writers are `tests/m2b` (twice) and `tests/m3b`.

Three consequences, none of which any suite could see:

- `pos.table_view()` reported *"no waiter is accountable for this table"* for every table,
  forever. The waiter floor's attention flag was permanently on, which is the same as
  permanently off.
- `pos.propose_handover()` refuses `HANDOVER_CARRIES_NOTHING` when the proposer holds no
  open table and no open request. With no owner ever established, a handover could carry
  **service requests only** — never a table. FR-POS-007's headline case had never once
  been executed against a real table.
- FR-TAB-006's acknowledgement rule, which M3-D proved carefully against hand-built
  ownership rows, governed a transition nothing could reach.

**This is F-OPB-9's shape, one level out**: a table with a column for a fact, a function
that moves the fact, and nothing that establishes it in the first place — proved thoroughly
by tests that wrote the starting row themselves.

Closed by seating. A waiter who seats a table is accountable for it from that moment, which
is how service works and is the origin the chain never had. `assigned_by_user_id` is the
same person, because nobody else has decided anything yet and naming a supervisor who was
not consulted would be a fiction in an audit column. A guest-opened occupancy gets **no**
owner, and the floor screen correctly reads "needs attention" — that is the flag doing its
job rather than a gap.

The suite walks the whole chain from its new origin: seat, propose, acknowledge, ownership
moved. It is the first time that sequence has run against a table anybody seated.

### The open question, recorded rather than guessed

Whether the waiter who seats is always the waiter accountable, or whether a separate
assignment belongs on the floor screen, is a product decision about how sections work in a
large room. It is **not blocked** by what this gate did: reassignment is
`pos.propose_handover()`, which now has an origin to work from, so the answer can be given
later without unpicking any of this.

## F-OPC-3 — a photographed placard can seat a stranger, and the stale-QR rule does not fire

**This is a hole in a guard that was ruled an invariant. It is not an edge case, and it is
recorded at full strength.**

A QR placard is a long-lived secret and `service.open_guest_session()` applies no freshness
test to it. A photographed code therefore opens a guest session from anywhere, at any time.
Before OP-C that bought an attacker nothing, because nothing could open an occupancy.

Now it does. Someone holding a photograph can open an occupancy on an **empty** table
remotely. The real party that later sits at that table scans fresh, matches the occupancy
the stranger opened, and joins it. What the stranger can then do at that table:

- **read what the party orders**, through the session they now share;
- **place orders against the same session**, which reach the kitchen as that table's;
- **be paid for by them** — on a shared bill, the stranger's items are among the components
  the party settles.

**Why the stale-QR rule does not fire, precisely.** That rule refuses a scan bound to an
occupancy *other* than the open one. The stranger's scan was bound to this occupancy **at
the moment it began**, not after it. The rule's test is `occupancy_at_scan IS DISTINCT FROM
occupancy_number`, and for the opener those two values are equal by construction. Nothing
about that is an oversight in the rule's implementation; the rule is about joining, and
this is opening.

**The bound, stated honestly.** The stranger's table shows on the waiter floor as occupied,
with a guest count and *"no waiter is accountable for this table"*, before anybody sits at
it. **That is visibility, not mitigation.** A restaurant that does not look at its floor
screen has no protection at all, and a busy room has every reason not to look.

**What would close it.** Three options, given as options because choosing between them is a
product decision and this gate has consistently refused to make those:

1. **A proximity proof.** Something the device can only produce at the table — a rotating
   code shown on a table card, a short-lived value the placard cannot carry, a staff
   confirmation for the opening act specifically. Closes it completely; costs the guest a
   step at exactly the moment the ruling wanted no step.
2. **An idle-close on an unattended `qr_scan` occupancy.** An occupancy opened by a scan
   with no cart line and no order after some interval closes itself. Bounds the window to
   that interval and nothing more; requires somebody to choose the interval, which is a
   policy value nobody has asked for.
3. **A placard token that rotates.** Ends long-lived photographs as a class, and ends
   printed placards with them, since the physical card would have to change.

Whoever closes it needs the choices, so the choices are written here rather than a
recommendation being smuggled in as one.

## F-OPC-4 — a fifth unmapped refusal, and the one a person actually met

`POST /c/v1/join` mapped exactly one database refusal to a status and answered **500** to
everything else. `NO_OPEN_OCCUPANCY` was everything else, so the first guest to scan the
demonstration floor was told the server had broken while the service was correctly
reporting that the table had no session to join. It is in the founder's own log:

    POST /c/v1/join   ->  500  {"error":"internal error"}

**That is the fifth instance of this class in this repository.** F-OPB-4b counted four in
`documents.ts` and observed that a hand-maintained map of refusals sitting beside a set of
rules somebody else adds to is the recurring shape. This is the same shape in a different
file, and it was found the same way every one of them has been found: by the first caller
of a path, never by a test written for it.

Both guest seating routes now derive the reason from the refusal rather than listing the
ones somebody remembered, so a refusal added tomorrow does not become a 500 by being new.

## F-OPC-5 — the three smaller absences, closed

| finding | what was missing | closed by |
|---|---|---|
| **F-OPB-10** | no remove, decrement or delete anywhere in the guest surface, and no function or route behind one | `service.remove_cart_line()`, `DELETE /c/v1/cart/lines/:lineId`, and one control per basket line |
| **F-OPB-11** | `#bill` and `#tip-box` were bordered rectangles with no heading before a bill was loaded | both boxes name themselves in all three of their states |
| **F-OPB-12** | `waiter.ts` exported `signIn()` and rendered nothing; the only way in was the browser console | a sign-in form, in its own section |

Two of these are worth a sentence beyond the table.

**The basket could not name its own lines.** `commit()` discarded the id the server
returned, because nothing had ever needed it. A basket that cannot refer to a line cannot
remove one, so the absence of the control and the absence of the id were the same absence.
The rule about *when* removal is allowed is not restated anywhere new:
`service.refuse_change_to_submitted_cart()` has fired on `DELETE` since 0010 and had simply
never had a delete to fire on.

**The waiter's sign-in form is in its own section, not in `#next`.** M3-B and M3-D measure
that page with no service behind it by calling `render()` directly, and `render()` replaces
the contents of `#next`. A form living there would have been wiped by the first measurement
and present in none of them — which is "exists but is never reached" again, one layer in.

## F-OPC-6 — the line that hid the gap is the line that now proves it closed

`tests/opa/verify_opa.py`'s `an_order_ready_for_the_kitchen()` began with a direct
`INSERT INTO service.table_session`, and every suite that chains through it inherited that.
The INSERT is gone. The helper now scans and calls `POST /c/v1/seat`, so the occupancy is
opened by the product rather than by the test.

This is a deliberate change to an approved gate, and the argument for it is that a helper
which arranges the one step the product cannot perform is the defect, not a convenience.
Every suite downstream of it now walks that step instead of stepping over it, which is
worth more than any check written beside it.

What is still a fixture, and is labelled as one: **standing the previous party up.** The
helper closes the open occupancy directly before the next scan, because it is called
several times in a run and each call is a new party at the same table. Closing is
`service.close_table_session()`, which since 0021 refuses while anything financial is
outstanding — a real rule belonging to a different requirement. Emptying the room is
fixture work; seating is the product, and only that half was ever the finding.

The OP-C suite goes further and writes no occupancy at all: it is checked from its own
source, and again in CI, that `INSERT INTO service.table_session` appears nowhere in
`tests/opc/`. A gate that closed this finding and then arranged its own occupancies would
have proved nothing.

---

## What OP-C delivered

| the brief | status |
|---|---|
| **`open_table_session`, both opening sources, and a route the guest surface calls on scan** | **MET.** One function, two sources, `POST /c/v1/seat` and `POST /s/v1/tables/:tableNodeId/seat`. The guest surface calls it and does not choose between opening and joining. |
| **The remove-from-basket control** | **MET.** One control per line, on every line, with an accessible name that says which line, at the 44px target, measured in a browser and driven by tapping it. |
| **Labels on the till's two boxes** | **MET.** Named in all three states — no bill, a bill with no tip offered, and a bill with options — so the name does not appear at the moment it stops being needed. |
| **The waiter sign-in form** | **MET.** Four fields and a submit, in its own section, and the floor is fetched only after it returns. |
| *(not asked for)* | **FR-TAB-006 given an origin.** F-OPC-2. Seating by staff establishes the first ownership row, and the handover chain is walked end to end for the first time. |
| *(not asked for)* | **A fifth 500 on a working rule, removed.** F-OPC-4. |

Seven controls, each planted, required to produce its registered signature, reverted and
required to pass again. Four break a rule and three break a screen, which is the split the
gate itself has.

## What OP-C did not do

**F-OPB-3 is unchanged and is still the open structural question.** The demonstration floor
and the test fixtures are the same tenant, and `safety.allergen`, `safety.approved_wording`,
`billing.component_wording` and `docs.line_wording` are unique per tenant. A guest on a
product-only database still cannot declare an allergy and a bill still has no words for its
components. Nothing here worked around it, for the same reason OP-B did not.

**F-OPC-3 is open by decision.** Guest seating ships with the exposure recorded, at full
strength, with three ways to close it and no recommendation between them.

Nothing here touched M5a's outlet node, sync or print queue; M5b's DNS, TLS or authority
lease; or M6. No fenced domain is named anywhere in this gate's migration, routes, surfaces
or suite — checked programmatically against all 63 terms.

## The gate does not close on a green chain

It closes when somebody opens the floor and walks it: scan, order, kitchen, till, cash.
Five minutes of that found what nineteen suites did not, and nothing in this document is
evidence that it would not do so again.
