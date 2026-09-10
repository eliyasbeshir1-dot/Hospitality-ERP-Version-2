# M5b findings — the same QR, one writer, and a phone that never sees a warning

M5a made the outlet survive the cloud going away. M5b is about the three things that left
unanswered, and all three are about the moment a real person walks in: the customer's QR
has to reach the node over TLS their phone already trusts; exactly one node may write and
replacing it must be safe; and the cloud and the outlet each have to prove the other is
there before either forwards anything.

Fifteen migrations (0049–0063), four seeds (0015–0018), one API route, one worker step,
86 suite checks with five negative controls, and two golden journeys.

---

## F-M5B-1 · Three migrations applied cleanly and could never have run

This is the finding of the gate, and it happened three times.

| migration | what it defined | why it could not run |
|---|---|---|
| 0054 | `edge.assert_resolution_guidance_is_safe()` | `v_text ~* 'A' \|\| 'B'` — `~*` and `\|\|` share a precedence class and associate left to right, so the pattern was `(v_text ~* 'A')` — half a regex with an unclosed parenthesis |
| 0057 | `edge.apply_continuity()` | cast to `identity.authentication_strength`, a type that has never existed; it is called `identity.auth_strength` |
| 0061 | all six notification producers | every payload was refused by `notify.payload_within_bounds()`, a key allowlist chosen when every notice was about an order |

**All three reported success.** Creating a PL/pgSQL function only checks that its body
PARSES — every name, type and pattern inside it is resolved when a statement first
executes. Applying a migration is precisely the operation that gives false confidence here.

Two of the three would have failed in front of a person. 0054's at a manager's screen.
0057's at a guest's phone, during the exact outage the function exists to survive.

**What caught them was calling them, within a minute of writing them.** Not review — review
read past all three. So `tests/m5b/verify_m5b.py` opens with `section_reachable()`, which
calls every function this gate added with arguments that reach the body rather than
bouncing off a guard, and fails on any that cannot execute. It is deliberately the first
section: a function that cannot be called at all makes every later check fail for a reason
unrelated to what it tests.

**The safer option, recorded for overturning:** each repair is a forward migration
(0056, 0058, 0062) rather than an edit to the original. That is the rule, and it also
leaves the mistake legible. A reader can see that 0054 was wrong and why.

---

## F-M5B-2 · M5a's one-node-per-outlet index had to be retired, and said so itself

`0039` put a unique index on `edge.node` allowing one active node per outlet, with its
reason attached:

> Two would make "which node is authoritative here" a question with two answers, which is
> the M5b split-brain this gate must not create.

That was correct while nothing could answer the question. `0050` answers it: authority is a
monotonic sequence with one holder per outlet by partial unique index. And FR-EDG-024 is
explicitly about a **standby** — a standby that cannot be registered until the node it
stands by is deactivated is a spare in a cupboard, and the gap between deactivating one and
registering the other is an outlet with no node at all, during which no fence evidence can
be recorded because there is nothing to record it against.

**The old index never prevented two writers.** It prevented two REGISTRATIONS. A node whose
process was started twice would have passed it. `edge.assert_authority()` refuses on the
write, which is where it matters.

This is the fourth gate fence to retire and be replaced by what outlives it — M4-A retired
six, M5a retired three, and `0061` retires a seventh below.

---

## F-M5B-3 · The three-part pattern appeared twice more, in two different shapes

`seeds/0010` wrote it down: a new governed action needs the trigger for new tenants, an
installer for the ones that already exist, and the caller. OP-C found it with `table.seat`,
OP-D with `order.accept`.

**Shape one — `0052` and `seeds/0015`.** `0050` required a live step-up grant and named no
action code, so *any* live grant would have done: a manager who stepped up to change a
price could have handed an outlet's authority to a different node on the strength of it.
FR-AUTH-006 scopes the window per action for exactly this reason.

**Shape two — `seeds/0017`, and this one is the plain version.** FR-EDG-023 and FR-EDG-024
both landed as a schema, a set of functions, and **nothing in the tables**. `edge.lease_policy`
held zero rows on a floor with two registered nodes, so FR-EDG-023's 5/10/20/3 schedule
existed only as four DEFAULT clauses nobody had inserted against. `edge.authority` held
zero rows, so `edge.assert_authority()` refused every write at both outlets with
`AUTHORITY_ABSENT`.

Nothing broke, and that is the uncomfortable part: no write path calls `assert_authority()`
yet, so a mechanism refusing everything looked exactly like a mechanism that was working.
**GJ-09 is what found it** — the journey asked for the schedule and got an empty result.

---

## F-M5B-4 · The outcome type has no value for a bypass

FR-EDG-028 ends with the sentence the whole requirement is for:

> Every unsupported client configuration fails safe to a clear instruction, never to a
> certificate warning or a bypass prompt.

`edge.resolution_outcome` has three values — the node, the cloud, or a sentence in the
guest's own language. There is no fourth, and adding one would take a migration and an
argument. The same reasoning gives `0053` no private-key column anywhere:
`edge.private_key_columns()` asks the catalog rather than trusting anybody's memory, and a
schema with nowhere to put a key cannot leak one.

Three of FR-EDG-022C's four prohibitions are CHECKs that refuse at write time. **The fourth
— a manual browser bypass — is a property of a surface, and the suite says so rather than
implying coverage.** What is claimed instead is narrower and checkable: no code path can
return one.

The certificate is checked **before** the client condition, because sending a phone to a
node without a valid certificate is the warning FR-EDG-022C prohibits, and that does not
stop being true because the cloud is down.

---

## F-M5B-5 · `0053` gave each horizon one answer, and FR-EDG-028 needs two

The failure FR-EDG-028 describes is exact: split-horizon DNS answers A for the LAN while
AAAA falls through to the public zone, so a dual-stack phone opens the public address over
IPv6 while sitting in the dining room with the internet down.

One answer per horizon cannot express that, so it could not refuse it either. `0054`
corrects it forward: both families on both horizons, LAN answers constrained to private
ranges and public answers constrained out of them.

---

## F-M5B-6 · A retry across the cloud-to-LAN transition was cooking two dinners

FR-EDG-026's crux, found by looking rather than assuming. `integration.sync_direction` has
carried a `cloud_to_outlet` value since `0041` and **nothing has ever produced one** — the
sync worker pushes the outbox up and acknowledges, and that is all it does.

So a guest session created at the cloud existed only at the cloud. When their phone started
talking to the node instead, the session token was unknown and — worse — **the idempotency
key was unknown**. A guest whose "Place order" was answered by a cloud that then became
unreachable retries; the node has never heard of the key; the kitchen makes two. Nobody
finds out until the bill.

`0057` is narrow on purpose. The general answer is bidirectional replication, which is far
larger than this requirement asks for. FR-EDG-026 names three properties — tokens still
valid, no duplicate order, cart ownership intact — and all three are answered by the node
holding two kinds of row for its own outlet's live sessions. Digests move; tokens do not.

`DO NOTHING` on conflict in both halves, for **opposite** reasons: a session the node
already holds may have been advanced where the guest is and the cloud's older copy must not
undo that; an idempotency key already spent is the entire point, because the second write
is the retry this exists to absorb.

**Continuity rides the acknowledgement rather than a second call**, and is applied at step
2b — before the batch claim, because the batch has an early return when there is nothing to
send and an idle node is exactly the node that needs this. A node with an empty outbox is a
node between services, and the guest walking in with a session started on cellular arrives
in that gap.

---

## F-M5B-7 · A filter is not a refusal, and NC-M5B-005 is what forced the difference

`0057` protected against handing a node a revoked session with a WHERE clause in
`edge.offer_continuity()`. Writing the negative control is what showed that was not enough:
the registry named a signature, `CONTINUITY_OFFERED_A_REVOKED_SESSION`, and **nothing in
the database could ever raise it**.

A filter protects the one path that goes through it. `edge.continuity_record` is a table,
and a table has as many paths as it has writers — including a future cloud-to-node
transport, which is precisely what these records exist to travel on. Worse, a filter fails
silently and in the wrong direction: if the clause were ever wrong, the symptom is a node
quietly honouring a session somebody signed out of, with no error anywhere.

`0059` moves the rule to where the row lands, and keeps the filter. Refusing at the
boundary *and* not offering it is two independent things going wrong before a guest is
affected.

**This is the general lesson of the negative-control discipline**: a control you cannot
plant is a protection you have not proved.

---

## F-M5B-8 · The demonstration floor could not raise a critical notice at all

Found by calling `0061`'s producers. Kazanchis — the outlet **every golden journey runs
at**, and the one with the node GJ-09 partitions — had no `service` policy, so
`notify.accountable_staff()` refused with `ORDER_POLICY_ABSENT` and every critical notice
there was unraisable.

`seeds/0007` had left it out deliberately and wrote down why: the only role this floor had
was `M3C_SUPERVISOR`, invented by M3-C's fixtures, and *"a seed pointing at a fixture's role
would be product data depending on test data."* That reasoning was right and still is. What
changed is that Kazanchis now has something critical to say — a lease that degrades, an
outlet entering local continuity, a sync conflict, a printer that stopped. Before M5b the
only critical events here were raised by fixtures against their own role. Now the **product**
raises them.

`seeds/0018` names `OUTLET_MANAGER`, which is real.

**The safer option was recorded for overturning, and it WAS OVERTURNED.** `seeds/0018`
deliberately invented no member for the role, on the reasoning that who is accountable is
an operator's decision and a seed granting somebody a role to make a check pass would be
guessing on their behalf.

**Ruling: the demonstration floor should have a manager.** `seeds/0019` gives Kazanchis
one — the account, the verified channel FR-AUTH-001 requires, a credential and the
membership — so a critical notice there reaches a person rather than being created and
addressed to nobody.

The part of the original reasoning that survives is worth keeping straight, because it was
never the wrong half: `notify.accountable_staff()` still REFUSES rather than guesses, and
nothing in the overturn changes that. What was wrong was applying that caution to a
DEMONSTRATION FLOOR, which is precisely where a complete outlet is the point. Sarbet has
had a manager since `0003`; Kazanchis is where every golden journey runs and had no product
staff at all — only fixture users.

A separate seed rather than an edit, for the reason `0007`, `0014` and `0016` all give:
seeds are checksum-locked. `0018` is not wrong and is not rewritten — it named the role,
and `0019` fills it. The scrypt parameters were verified rather than copied: the Sarbet
manager's stored digest was re-derived from its stored salt and checked to match before a
new one was minted, so the credential uses what `identity.authenticate_credential()`
actually does rather than what a comment says it does.

---

## F-M5B-9 · Three notices, four states, and no state invented to be announced

`EVT-OUTLET-RECONNECTING` has no corresponding lease state. `edge.lease_state` is `live`,
`degraded`, `expired`, and a node part-way through FR-EDG-023's three consecutive proofs
**still may not forward** — so calling it anything but expired would be a lie the lease has
to keep straight everywhere else.

Reconnecting is PROGRESS, not a state, and
`forwarding_lease.consecutive_valid_exchanges` already carries it.
`edge.announce_recovery_progress()` fires once, on the first proof: a notice per proof would
be three notices in fifteen seconds saying the same thing.

Adding a fourth state whose only purpose was to be announced was the alternative and was
rejected.

Related: `EVT-SYNC-EVENT-QUEUED` stays producerless on purpose. An event entering the
outbox happens on every order, bill and payment, and a notice per queued event is a channel
nobody reads by the end of one service.

---

## F-M5B-10 · A milestone list cannot say that code exists

`notify.catalog_event` carried `CHECK (NOT has_producer OR milestone IN ('M1'..'M4'))` — a
gate fence in the M4-A sense, stopping a later gate's event being marked produced before
that gate existed. It became the thing preventing the gate it was waiting for from doing
its job.

It retires and is replaced by something stronger:
`edge.assert_notification_producers_exist()` NAMES the function that produces every event
claiming a producer, and fails if either the claim or the function is missing. A milestone
can only ever say *the gate happened*; this says *the code exists*.

Declared in two places on purpose — the same shape as `PROVISIONABLE_TABLES` — so a seventh
producer cannot arrive as a one-word diff.

---

## F-M5B-12 · Widening a shared enum made another schema's rule quietly unowned

`0060` added `node` to `ordering.artifact_kind` so an edge notice would have a subject to
point at. **tests/m4b caught it**, and the check was written for precisely this case:

> The kinds are read from the ENUM, so a kind added at M4-C appears here without anybody
> extending a list, and the assertion is that each one names a rebuild. NULL is the safe
> answer — an unowned kind is deleted by nobody — but it is not a silent one.

`ordering.correlation_link_rebuilt_by('node')` returned NULL, and `0025`'s own comment says
what NULL means there: *"nobody thought about this kind, and that is precisely the defect
they exist to catch."* It was right. A whole gate later, an enum shared between two schemas
grew a value for one of them and the other's rule went unowned.

`0063` gives the honest answer — a node is never in `ordering.correlation_link`, so no
rebuild restores its links because there are none — in the shape `receipt` already
established: a definite sentence rather than a NULL. And it is **enforced rather than
asserted**: `ordering.link_correlation_artifact()` refuses the kind, so the claim is a
property of the schema. Same move `0059` made when NC-M5B-005 showed a filter is not a
refusal.

**RULED: the widening stays, and this finding is its disposal.** The alternative was put
up for overturning and the ruling was to keep `0060`. What follows is therefore the
recorded disposal of a decision rather than an open question.

`ordering.artifact_kind`
now does double duty: eleven values meaning "a thing a guest orders or pays for" and one
meaning "the machine serving them". The type lives in `ordering` and `notify` is the only
user of the twelfth value. The clean answer is a separate `notify.subject_kind`. It was not
taken here because **PostgreSQL cannot drop an enum value** — undoing `0060` means
recreating a type used by three columns and four functions, and a type-recreation migration
written at the end of a gate to fix a naming problem is a larger risk than the problem.
Named as work for a later gate rather than left as a shape somebody has to rediscover.

---

## F-M5B-11 · The suite had to learn to leave nothing behind

FR-TST-020 runs every suite backwards against the same database and demands identical
results. A suite that commits cannot give that, and this one learned it three times in one
afternoon:

- a clock moved for the renewal walk left the certificate expired, and five checks in a
  **later** section then answered honestly about a world the suite had made
- a control's GREEN path committed a hostname, and the next run found the outlet named
- a planted idempotency key collided with itself

All three looked like defects somewhere else. Every probe now runs `rollback=True`, which
costs nothing for a read.

Two more traps, both about **data-modifying CTEs**, and both worth naming because they
produce plausible wrong answers rather than errors:

- the renewal walk moved the clock in a CTE and read the posture in the same statement. A
  data-modifying CTE sees the snapshot from the start of the statement, so every answer was
  the previous iteration's and the whole walk was shifted by one step. It looked exactly
  like an off-by-one in the thresholds.
- the continuity probe chained plant/offer/delete/apply as four CTEs, whose execution order
  relative to one another is not guaranteed at all. It is a `DO` block now.

---

## The bounds

Named here and named again in the suite's own output, so they are not left to silence.

1. **The certificate chain is a fixture.** No domain, no CA account, no DNS-01 automation
   on this machine. The lifecycle around it is real — the state machine, the LAN-served
   comparison, the renewal schedule verified across nine boundaries, the four prohibitions
   — but **no phone has ever validated one of these certificates**. Closed by a real domain
   and an ACME account at pilot.

2. **Split-horizon DNS is recorded, not served.** Both answers per horizon are held and
   checked for consistency; no resolver in this build answers them. "The same QR resolves
   differently inside and outside" is proved as a property of the data, not as an observed
   lookup. Closed by an outlet gateway running a real split zone.

3. **The client condition is a claim.** A phone says whether Private DNS is on; nothing
   here can see it. It is safe to take at face value because the worst a false claim
   achieves is worse advice for the phone that made it — it cannot cross a tenant, skip the
   certificate check, or produce a bypass. That reasoning is written where the route takes
   the claim, not only here.

4. **`HttpCloudLink` posts to a route that does not exist.** The demonstration floor runs
   `LoopbackCloudLink`; no service in this repository serves `/x/v1/exchange`. This is an
   **M5a bound M5b inherits and does not close**, and it means the continuity handoff is
   proved through its functions rather than across a real link.

5. **Fence evidence is a sentence a person typed.** Every value of `edge.fence_method` is
   something an operator DID and can be asked about, and there is deliberately no
   `assumed_down` — but nothing here verifies that the switch port was really shut. The LAN
   probe is what makes that safe, and it is checked first for that reason.

6. **No staff member holds `OUTLET_MANAGER` at Kazanchis**, so the notices this gate
   produces there are created and addressed to nobody. See F-M5B-8.

---

## What M5b delivered

**FR-EDG-023** — bidirectional reachability proofs, a 5/10/20/3 lease, and forwarding that
is refused by a clock rather than by a cached boolean.

**FR-EDG-024** — authority as a monotonic sequence, one holder per outlet by unique index,
and a replacement that requires step-up for *this* action, an independent approver enforced
by CHECK, fence evidence naming something a person did, and a LAN-unreachability probe
checked first. Stale events quarantine rather than drop; releasing one takes a person and a
sentence.

**FR-OPS-017, FR-EDG-022A/B/C** — one hostname per outlet with no wildcard and no raw
address; a certificate lifecycle whose install step requires the LAN-served fingerprint to
equal the issued one; a renewal schedule verified at nine boundaries; and no private-key
column anywhere in the database, proved from the catalog.

**FR-EDG-004B, FR-EDG-015B, FR-EDG-021, FR-EDG-028** — five client conditions across cloud
up and down, both address families constrained to one horizon, twelve phrases of translated
guidance in three locales with a check on what they may not say, and forty combinations of
condition, cloud state and elapsed time producing no warning and no bypass.

**FR-EDG-026** — session and idempotency continuity across the cloud-to-LAN transition, so
a retry is absorbed rather than cooked twice.

**FR-NOT-001, FR-NOT-005, FR-INT-007** — the three partial closures this gate was carrying,
closed with six producers, a permanence test that distinguishes a peer that refused from a
peer that did not answer, and a check that every claimed producer exists by name.

**GJ-08** and **GJ-09**, both mandatory, both driven end to end.

Six partial closures remain open. All six name M6.
