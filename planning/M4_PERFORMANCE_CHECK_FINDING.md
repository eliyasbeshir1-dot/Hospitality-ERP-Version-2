<!-- dated-record -->
# A check that reports a cause it cannot distinguish — recorded at the M4 repair

**This is a RECORD, not a description.** It says what two named CI runs measured, against
the commit they measured it at. The numbers below are observations of particular runs on
particular machines and they do not describe the system now; that is the distinction
`tools/check_dated_records.py` exists to hold.

Recorded against `2f9ba4b` on 6 September 2026.

Found while getting the M4 repair green, not by a check that was looking for it.

---

## 1. What the check does, and what it actually distinguishes

Recorded against `2f9ba4b` on 6 September 2026.

The M4-A calibration gives every performance budget in `tests/m2c` two failure names.
`PERFORMANCE_BUDGET_EXCEEDED` when a reference measurement says the machine is inside its
normal band — the surface is what is slow. `PERFORMANCE_NOT_MEASURABLE` when the reference
says the machine is starved — everything is slow together, so the run is not evidence
about the surface. Both are failures; the budget does not move for either. The calibration
was built for a good reason: a breach reported as a regression on a machine that was
simply starved would be a diagnostic naming a cause it did not verify.

**It decides between the two by which starvation the reference happened to catch.** The
reference is a fixed arithmetic loop. Starvation in any dimension that loop cannot see —
disk, process launch, a filesystem filter driver scanning a freshly written workspace —
does not move the reference, so the check reports the breach as a slow artifact. It does
not distinguish the two causes. It distinguishes one of them from everything else and
gives the remainder the other's name.

That is the same class of defect the calibration was built to prevent, sitting inside the
calibration. The founder counts it the fourth instance of that class in this project. Two
others are on the record and can be checked: NC-M2C-009's diagnosis, which reported a
surface defect when it could not tell that apart from a probe timing outcome, repaired at
this gate; and the read/write classifier that decided by function name, which reported a
reader as a writer until it was replaced by `provolatile` from the catalog.

## 2. What was measured

Recorded against `2f9ba4b` on 6 September 2026.

CI run 71 on `2f9ba4b`. The Windows job failed `M2C_VERIFICATION` at 63 of 65 checks; the
two that failed were both paint budgets. The Linux job of the same run, on the same
commit, passed them.

| | Linux | Windows |
|---|---|---|
| reference, fixed arithmetic loop | 131ms against a 195ms baseline → 0.67x | 229ms against a 195ms baseline → 1.17x |
| first contentful paint | 780ms against a 2500ms budget | 5964ms against a 2500ms budget |
| menu on screen | 2215ms against a 5000ms budget | 7336ms against a 5000ms budget |

The reference puts the two machines 1.75x apart. First paint is 7.6x apart and the menu
3.3x. The check read that gap as *"within its normal band, so the surface is what is
slow"*, of a commit whose diff touches no surface, no route and no browser path — it
changes the evidence report's journey table, the review findings, the coverage register,
one negative control and the control registry.

`tests/m1d/service.py` already documents the Windows pathology this points at, for a
different symptom: the first launch after a build competes with the filesystem filter
driver scanning freshly written `dist/` and `node_modules/`, and that made one start in
four fail until the readiness window was widened.

## 3. What was done about it, and what was not

Recorded against `2f9ba4b` on 6 September 2026.

The single further Windows attempt authorised for this failure was not spent as a re-run
of run 71. It could not have produced a verdict: run 71 was independently red on Linux for
an unrelated reason of the builder's own making — the evidence report was regenerated from
a working tree that still held eight other modified files, so it anchored to the previous
commit and marked itself NOT CLEAN, and CI regenerates from a clean checkout and diffs.
The attempt was taken instead on the next commit, whose diff against `2f9ba4b` is this
record, the pointer to it, and that corrected report: nothing that touches a surface, a
route or a browser path, so it tests the same question.

**One further attempt, and a second failure changes the reading.** Two consecutive Windows
failures on this commit, while Linux paints the same surface in 780ms, would be evidence
of a real regression and it is to be hunted before the gate goes to review — not re-run a
third time, and not re-labelled.

**THE ATTEMPT PASSED.** CI run 72 on `12439aa`, 6 September 2026, on the same Windows
runner image: both paint budgets came in inside their thresholds and the run was green
on both platforms. The rule above was therefore never reached, and the reading stands:
the breach on run 71 was starvation in a dimension the reference cannot see, not a slow
surface. That is one observation and not a measurement of how often it happens — what it
establishes is that the check reported a cause it could not distinguish, which the
repair at M5a is for. It does not establish that this runner meets these budgets
reliably.

The dirty-tree defect named at the top of this section is closed rather than only
recorded: `assert_tree_is_clean()` refuses to write the report from a tree carrying
uncommitted work, proved red then green as `NC-M4C-010`.

**The budget numbers are untouched.** No threshold in `tests/m2c` was changed, raised or
made conditional at this gate.

**The repair belongs to M5a.** Two shapes are open to it: give the reference a component
in the dimension the budget is actually sensitive to, so that a starved machine is
detected as starved; or make the two signatures derivable from what was measured rather
than residual, so that neither is the name given to whatever the other did not catch. The
second is the stronger fix and the harder one. Changing a check's calibration while that
check is red, in the commit handing the gate to an independent reviewer, is how a check
gets quietly weakened, which is why neither was done here.
