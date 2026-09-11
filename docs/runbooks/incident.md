# Something has gone wrong

> **Owner:** OUTLET_MANAGER
> **When this is used:** An alert fired, or somebody noticed before an alert did.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- Find who owns it: `SELECT * FROM ops.alert_ownership WHERE event_id = ...`.
  Every event that can be raised has an owner, and `ops.unowned_alerts()` returns
  nothing if that is still true

## Steps

1. Acknowledge within the window on the ownership row.
2. If it is a node failure, see the outage runbook. The outlet keeps trading.
3. If a node must be REPLACED, that is four proofs and not a decision one person
   makes: step-up for `node.authority.claim`, an independent approver, fence
   evidence naming what was physically done, and a LAN probe proving the old node
   is unreachable. The probe is checked FIRST because it is the only one that says
   whether the old node is actually gone.
4. Quarantined events need a person and a sentence to release.

## How you know it worked

The alert is acknowledged, the cause is recorded, and anything quarantined has been
looked at by somebody rather than dropped.

## If it does not work

Escalate on the escalation window in the row, to the role it names.
