# Going live with a pilot outlet

> **Owner:** OUTLET_MANAGER
> **When this is used:** A real guest is about to use this for the first time.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- `SELECT * FROM ops.pilot_readiness(<tenant>, <outlet>)` and every clause is
  ready. It is six clauses and each is something an earlier gate built
- **The founder has walked the floor.** That is a standing rule of this project
  and not a formality: eight requirements have been met in SQL and unreachable by
  the person they were written for, and every one was found by somebody using the
  product rather than testing it

## Steps

1. Record the cutover in `ops.cutover`: the commit, the named operator, the data
   owner and the rollback plan. All four are NOT NULL.
2. Have somebody who is not the operator review it and record the verdict. The row
   cannot reach `live` without that. No direct production cutover from an
   unaudited branch is a CHECK here rather than a sentence.
3. Go live.

## How you know it worked

`ops.cutover` holds a live row naming the commit and both people.

## If it does not work

Roll back per the plan in the row, and record why. A cutover that cannot say
what it deployed is one nobody can roll back from with confidence.
