<!-- dated-record -->
# The migration history's starting point — a record of M0R

**This is a RECORD, not a description.** It says what this repository held on a named
date, at a named commit, and why. It is deliberately NOT generated: deriving it from
today's tree would turn "no migration exists" into a claim about now, which is
falsification rather than locking. The document that describes what exists TODAY is
`planning/MIGRATION_AND_DOMAIN_OWNERSHIP_MAP.md`, which is generated and fails the build
the moment it stops being true.

The distinction, and the check that enforces it, are stated in
`tools/check_dated_records.py`.

Recorded against `f53c2c7` on 26 August 2026.

---

## What was true at that commit

Recorded against `f53c2c7` on 26 August 2026.

The repository contained **no migration, no `.sql` file, no schema and no `migrations/`
directory.** Not even `0001`.

That was the requirement, not an omission. Migration `0001` is created at M1, after
independent review approves M0R conformance. FR-DAT-001 and FR-GOV-001A both bind that
sequencing: a schema written before the gate that governs it is a schema nobody reviewed
the requirements for.

## What enforced it

Recorded against `f53c2c7` on 26 August 2026.

`tools/verify_m0r_skeleton.py` failed the build on any `.sql` file, any `.prisma` file,
any `migrations/`, `db/`, `database/`, `schema/` or `models/` directory, and on any file
containing SQL DDL. That check ran in CI on every push, and it is why the absence at
`f53c2c7` is evidence rather than an assertion.

The check still exists and still runs. What changed at M1 is that the repository moved
past the gate it was written for, so it now guards the M0R skeleton's own contents rather
than the whole tree.

## What was planned, and how it actually went

Recorded against `f53c2c7` on 26 August 2026.

The M0R document recorded a planned ownership order — tenancy and identity first,
then configuration and data architecture, then menu and safety, then tables and sessions,
then orders and fulfilment, then billing and payments, then the outlet edge, then
authority and routing — and deliberately pre-allocated no number ranges, because
pre-allocation produces gaps and gaps invite out-of-order application.

The plan held. The generated map shows what was actually written, in what order, and
which domain owns each file; a reader comparing the two is comparing an intention
recorded on 26 August 2026 with a state derived from the repository today, which is the
comparison this split exists to make possible.
