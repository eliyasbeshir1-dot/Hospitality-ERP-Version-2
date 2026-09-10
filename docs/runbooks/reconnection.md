# When the internet comes back

> **Owner:** OUTLET_MANAGER
> **When this is used:** The cloud is reachable again after an outage.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The outage is genuinely over. FR-EDG-023 requires THREE consecutive valid
  bidirectional proofs before forwarding resumes, so a flapping link does not
  produce a flapping estate

## Steps

1. Do nothing. The sync worker offers the outbox in dependency order, parent
   before child, and acknowledges only what the cloud names.
2. Watch for conflicts. A disagreement between the outlet and the cloud is shown
   to a person rather than settled by whichever wrote last.
3. Resolve each conflict with a decision and a sentence. Both are required.

## How you know it worked

Connectivity reads cloud-connected, the outbox drains, and no conflict is left
unresolved.

## If it does not work

Events held by a node that was fenced are QUARANTINED rather than applied or
dropped. Releasing one takes a person and a sentence. See the incident
runbook.
