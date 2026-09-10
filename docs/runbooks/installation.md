# Installing an outlet

> **Owner:** OUTLET_MANAGER
> **When this is used:** A new outlet is being brought onto the system for the first time.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The outlet exists in `org.org_node` with `kind = 'outlet'` and an outlet profile
- You know whether it will run a continuity node or cloud-only. FR-EDG-001 says a
  PRODUCTION outlet may not run cloud-only, and `edge.deployment_profile` refuses
  to record one that does

## Steps

1. Apply the schema: `python3 tools/migrate.py apply --dsn <dsn>`
2. Record the deployment profile. A production outlet must declare a node.
3. Register the node with `edge.register_node()`. It needs all five services
   FR-EDG-002A names; four is refused.
4. Grant it first authority with `edge.grant_first_authority()`. Until it holds a
   sequence in `edge.authority` it may not write.
5. Declare the hostname and the split-horizon answers in `edge.outlet_hostname`.
6. Document the backup schedule in `ops.backup_policy`.

## How you know it worked

`SELECT * FROM ops.pilot_readiness(<tenant>, <outlet>)` and every clause is ready.

## If it does not work

An outlet that is half-installed is more dangerous than one that is not
installed, because staff will try to use it. Deactivate the node rather than
leaving it registered and unable to write.
