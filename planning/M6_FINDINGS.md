# M6 findings — deployment, backup, restore, reporting, pilot readiness

M6 is the gate where everything stops being about a repository and starts being about a
machine somebody deploys. Five slices: the artifact that ships, a backup worth having, a
restore proved by destruction, an export that is an act rather than a read, and the
question a founder asks before letting a guest in.

Three migrations (0064–0066), four seeds (0018, 0020, 0021), eleven runbooks, three tools,
five suites, 132 checks and eighteen negative controls.

**Three partial closures remain open, all at `PILOT`**, which cannot land from this
repository. They are the aspects whose evidence is ink on paper. See F-M6-9.

---

## F-M6-1 · One manifest, or three places to say the same thing

`tools/artifact.py` declares what a production artifact contains. Four things derive from
it: the builder copies what it lists, `deploy/Dockerfile` is generated from it, the
completeness probe runs what it names, and the prohibition scan reads what it forbids.

The alternative is a COPY list in a Dockerfile, a manifest in a build script and a
checklist in a test — three statements of one fact, two of which go stale. The CI matrix,
the README and the schema catalog each taught this repository that lesson once, and each
is now generated and check-locked for the same reason.

The manifest names **two origins**, and that is load-bearing rather than tidy. Compiled
output may never live in the repository: `tools/verify_m1.py` treats `dist/` and
`node_modules/` inside it as forbidden surface and checks the filesystem rather than the
Git index, so `api/build.sh` compiles into a workspace outside it. An artifact assembled
from one origin would be either missing the server or built in a place the repository
forbids.

---

## F-M6-2 · Every seed here builds the demonstration floor, so none of them ship

FR-CFG-007B asks that a scan of the built image prove no demo-reset route, job or script is
present. The obvious reading is a route called `/reset`. The sharper one is that **a loader
which creates demonstration tenants in production is worse than a way to reset them**, and
every seed in this repository is exactly that: two tenants, an Ethiopian menu, a Sarbet
manager, a Kazanchis node.

So the artifact ships migrations, which are the schema, and no seeds at all.

That leaves a real gap and it is named rather than filled: **nothing in the artifact can
create a first tenant.** Production provisioning is unbuilt. Filling it with a demo loader
would have been the easy answer and the wrong one.

---

## F-M6-3 · An entry point that is present and cannot run

FR-OPS-019's hard word is "executes". A missing file is easy to notice; a file that is
present and fails because the build left a dependency behind is not.

So the completeness check RUNS every advertised entry point from inside the built tree with
`PYTHONPATH` and `NODE_PATH` cleared. The API's probe loads the module rather than starting
it — `api/src/server.ts` guards its start with `if (require.main === module)`, so requiring
it walks fastify, pg, every route and every surface and returns. Stronger than a flag, and
it needed no change to the source.

NC-M6A-002 plants exactly that defect by moving `node_modules/fastify` aside. The API is
present; it cannot run; the check fails.

---

## F-M6-4 · The restore drill found a real defect in the backup, which is the point of one

`tools/backup.py` passed `--no-owner --no-privileges`. That is the usual advice and it is
wrong here. The drill reported it in the only way that could have caught it:

> `pg_restore` completed. Every byte came back. `hospitality_app` — the role the service
> actually runs as — got `permission denied for schema org`.

**An estate without its grants is not restored; it is merely present.** Keeping owners and
privileges adds 469 entries to this floor's archive.

That is exactly why FR-OPS-007 says "start with least-privileged production roles". A
restore verified as a superuser bypasses row level security and every grant, so it would
have reported an estate that works and handed over one that nobody but a superuser can
read.

---

## F-M6-5 · And then my own check had the defect class this project keeps meeting

The first version of the drill's verification read `org.tenant` through the application
role with **no tenant context**, got 0, and reported success.

With no context, `app.row_in_scope` matches nothing — so an **empty restore looks exactly
like a correctly isolated one**. M5a's connectivity banner answered CONNECTED for precisely
this reason: row level security had hidden the node it was asked about.

There are three readings now and all three must agree:

| reading | must be |
|---|---|
| what the archive carried, bypassing RLS | non-zero |
| what the app role sees **unscoped** | zero, or isolation did not survive |
| what the app role sees **in scope** | non-zero, or the estate is present and unusable |

Any one alone can be right for the wrong reason.

---

## F-M6-6 · A backup with no state meaning "taken and assumed good"

`ops.backup_state` has `captured` and `verified`, and nothing in between. `captured` means
written, encrypted and digested; it becomes `verified` only when something has decrypted
the archive and counted its table of contents with `pg_restore --list`. Only a verified
archive may be copied off-site.

Both transitions are functions that refuse without evidence. The digest read back must
equal the digest written — a verification that opened a different file is the mistake a
directory of timestamped archives invites — and an archive that decrypts to nothing
decrypts *successfully*, which is the failure "the file exists and is not zero bytes"
cannot see.

The `cipher` column cannot hold `none`. A deployment that skipped encryption could not
record one.

**The plaintext never becomes a file.** `pg_dump` is piped straight into `openssl`; a
process that writes an unencrypted dump and deletes it has written one, and deletion is not
erasure on any filesystem in use here.

---

## F-M6-7 · The fourth appearance of the three-part pattern, and the last registered one

`report.export` has been in `identity.install_governed_actions()` **since migration 0002** —
strong, step-up, a fifteen-minute window, the only action in the registry whose window is
not five minutes — carrying `governed_from_gate = 'M6'`.

**Nothing had ever called it.** The export route asked for a staff session and nothing more,
so an action the registry described as governed was ungoverned through M4, M5a and M5b.

OP-C found this shape with `table.seat`. OP-D with `order.accept`. M5b with
`node.authority.claim`. This is the fourth, and `seeds/0010` wrote the pattern down after
the first: a governed action needs the trigger, an installer for tenants that already
exist, and **the caller**. Here the first two had been in place for sixty-three migrations.

Why an export is governed when it only reads: every other governed action changes
something. An export changes nothing and removes a whole outlet's trade into a file with
none of the access controls it had here. **The consequence is not to the data; it is that
the data leaves.**

---

## F-M6-8 · Three things that pass and prove nothing

Each was found by running it, and each is the same species: a check that is right for the
wrong reason.

- **`tests/m6b`'s refusal helper matched `backup_`** — which is the RELATION name, so every
  constraint violation reported `signature: backup_run`. `tests/m5b`'s helper carries a
  trailing underscore for exactly this reason and it is not decoration.
- **`tests/m6e`'s helper matched `OUTLET_MANAGER`** — an uppercase identifier from the SQL
  *I* sent, which PostgreSQL quotes back in its error. A control reported
  `signature: OUTLET_MANAGER` and proved nothing. Tokens echoed from the submitted
  statement are excluded now.
- **`tests/m6a` counted `FROM ` anywhere in the Dockerfile** and found three, because the
  generated header says *"GENERATED FROM tools/artifact.py"*. A check that counts a
  substring in comments is a check reporting on prose.

---

## F-M6-9 · Four partial closures, and what was done with each

Four entries named M6-E, it landed, and `PARTIAL_CLOSURE_NOT_REVISITED` fired for all four.
I declined to close any of them on the mechanism being complete, and put three options to
the founder. **Both were ruled on: build FR-TST-005A, and move the printer entries to a
pilot milestone.** What follows is what that took.

### FR-TST-005A — built, and closed at M6-E

The entry's stated blocker was *"there is no cashier settlement surface... no button reaches
these routes and no browser test can be written against one."* That was true when written
and **OP-B removed it without the entry being updated.** By M6-E the till already had Take
cash, Card on the terminal, and Telebirr and CBE Birr proof buttons, and the journey probe
already drove `.pay-cash`, `.pay-terminal` and `.pay-proof`.

Three of the five were still passing `method="none"` — walking the cashier's VIEW and
stopping — so the half a person touches was measured while the money was still taken by the
suite issuing the calls a screen would issue.

**The part that was not a parameter flip was GJ-02B.** That journey proves an unverified
proof settles nothing, and the till cannot demonstrate it: its Telebirr button raises,
attests and captures in one act, so its flow offers an unverified proof **no moment at
which to be presented**. That is a virtue of the screen rather than a gap in it. So the
rule keeps its service-tier proof, on its own proof object, and runs BEFORE the till; the
money is then taken by pressing a button. Ordered the other way the till would have closed
the bill and the refusal would have been for the wrong reason.

**GJ-06's second payer is deliberately left at the service tier.** What that journey
uniquely proves is that two payments settle two shares INDEPENDENTLY. Driving both through
the same screen in the same run would make the second payment's independence a property of
the till's state handling rather than of the allocation rules under test. One of each proves
both claims: a cashier can do it, and the rules hold whoever does it.

All five report browser tier — derived from the journey body calling `walk()`, never
declared — and `PASS GOLDEN_JOURNEY_VERIFICATION` across 13 journeys.

### FR-FUL-008, FR-FUL-014, FR-BIL-017 — moved to PILOT

One hardware dependency wearing three faces: **ink leaving a real printer.** Everything up
to the last inch is built and proved — the durable queue, the lease, the retry,
exactly-once delivery across a restart, 576-dot rasterisation, allergy lines first and in
words.

`PILOT` is declared in `planning/post_phase_1_milestones.json` rather than edited into the
pinned package, for a reason found while doing it: **the package's sha256 is quoted in
README.md and this directory's architecture plan as the pin, and nothing verifies it.**
Editing the package would have made both statements false while no check noticed. And a
pilot that happens after Phase 1 is not part of the Phase 1 specification — it is a fact
about how this repository intends to finish, which is what `planning/` holds.

It is a file rather than a list inside `tools/partial_closures.py` for that tool's own
stated reason: a hardcoded gate in the checker is a second source of truth the checker
cannot see changing.

**`PILOT` cannot land from this repository.** `landed_gates()` reads `tests/` and matches
`m<digit><letter>`, so no directory name makes it landed. That is deliberate: a milestone
whose evidence is a physical act should not become closable by adding a test file. It
closes when somebody runs it on hardware and records what came out of the machine.

Extending `known_gates()` was not enough — `gate_order()` derives independently from the
manifest's milestone list, so it needed the same treatment, appending after the package's
gates because "after Phase 1" is after every gate Phase 1 names.

---

## F-M6-10 · The pinned package's sha256 is asserted and never checked

Found while deciding whether to edit the package. `PACKAGE_SHA` is a hardcoded constant in
`tools/generate_readme.py` and `tools/generate_architecture_plan.py`, and it is printed in
both documents as **the pin**. Nothing computes it from the package files and compares.

So the pin is a claim rather than a lock: anybody could edit the package and both documents
would keep asserting the old digest. It is not exploited here — the package is untouched,
which is why `PILOT` lives in `planning/` — but a pin that cannot detect a change is not
doing the job its name claims.

**Not fixed in this gate, deliberately.** Computing it would either confirm the existing
value or reveal it is already wrong, and the second outcome needs a decision about which
package is authoritative rather than a quiet edit to make a check pass. Recorded as work.

---

## The bounds

Named here and named again in each suite's own output.

1. **The image has not been built.** Docker's daemon is not running on this machine and the
   disk would not hold an image. `deploy/Dockerfile` is derived from the manifest and
   check-locked against it, and the tree it would contain has been built, probed and
   scanned — so the gap is the packaging, not the contents.
2. **The database client is the one dependency the artifact cannot carry.** `psql` belongs
   to the PostgreSQL distribution; the Dockerfile installs `postgresql-client` and the
   check proves one is reachable, but on this machine that is the host's.
3. **Off-site is a second directory on the same disk.** The schema refuses a copy whose
   path equals the original and the digest is checked on arrival, so the mechanism is real;
   what is not proved is that the copy survives losing the machine.
4. **The backup key is an environment variable.** It never reaches the database and never
   appears on a command line, which keeps it out of the process table — but it is readable
   by the same user on either platform, and there is no rotation, escrow or split knowledge.
5. **Retention is declared and not enforced.** `retain_days` is checked for sanity against
   the interval and nothing deletes an expired archive. A retention nobody applies is a disk
   that fills, which this machine demonstrated twice during this gate.
6. **Only the cloud scope is backed up and destroyed.** FR-OPS-007 names cloud *and* outlet;
   the demonstration floor's node shares this database rather than running its own.
7. **The golden journeys are not run against the restored database.** The drill proves the
   estate is present, isolated and readable by the production role, which is the
   precondition for them rather than a substitute.
8. **Recovery time is measured on a 2MB archive.** The number is real and the shape of the
   measurement is right — drop to usable, not `pg_restore` alone — but it says nothing about
   a production-sized estate.
9. **FR-OPS-016's replacement-node procedure is built and not drilled from a backup.** M5b's
   `edge.claim_authority()` with its four proofs is what a replacement runs through and
   GJ-09 exercises it; a replacement node restoring from a backup and *then* claiming
   authority is not exercised.
10. **FR-TST-010's load test is not built.** Peak ordering, KDS, realtime, menu search and
    integration bursts with recorded thresholds needs a machine with headroom, and this one
    has been at 100% disk twice.
11. **Escalation goes to the same role on the demonstration floor.** `ops.alert_ownership`
    supports a different escalation role and this estate has one operational role. The
    schema is right and the seeded floor is thin; inventing a second role so the row looked
    correct would be worse.
12. **The runbooks are checked for existence, a fallback section and length.** Whether the
    prose is any good is not something a database can know, and the only honest test of a
    runbook is somebody following it under pressure.
13. **`node_modules` is not scanned for reset-shaped code.** It is third-party and enormous;
    scanning it would report on other people's code.

---

## What M6 delivered

**FR-OPS-019, FR-CFG-007B, FR-TST-018** — one manifest four things derive from, every
advertised entry point executed from inside the built tree with the repository unreachable,
and a scan of the artifact *and* the database proving no way to reset or reseed production.

**FR-OPS-006, FR-SEC-019** — a backup captured with the plaintext never touching disk, read
back before it counts as verified, copied off-site only after that, on a schedule an
operator can query rather than a cron line nobody can audit.

**FR-OPS-007, FR-TST-009** — a database destroyed and rebuilt from a real encrypted
archive, under the least-privileged production role, read three ways, timed from destruction
to usable.

**FR-RPT-013, FR-AUTH-006** — an export that is a governed act with a caller at last,
recorded before the bytes leave and immutable afterwards.

**FR-FUL-012, FR-FUL-015** — closed at M6-D.

**FR-OPS-011, FR-OPS-012, FR-OPS-015** — eleven runbooks, an owner for every raisable
alert, and a cutover that cannot go live unaudited or be reviewed by the person who
performed it.

FR-TST-005A closed at M6-E. Three remain open at PILOT, where a real printer
is what closes them.
