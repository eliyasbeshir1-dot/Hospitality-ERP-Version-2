# Restoring from a backup

> **Owner:** OUTLET_MANAGER
> **When this is used:** Data has been lost, or a restore drill is due.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- **Read this line before running anything.** `tools/restore.py` DROPS the
  database it is pointed at. Point it at the target, never at production, and
  never at the database you are restoring FROM
- The archive is `verified` or `offsite`. An unverified one may not be restored

## Steps

1. `python3 tools/restore.py --archive <path> --admin <maintenance-dsn>
   --target-db <name> --into <target-dsn> --app-dsn <app-role-dsn>`
2. It decrypts, drops, recreates, restores and then reads the estate back THROUGH
   THE APPLICATION ROLE. A restore verified as a superuser proves the bytes came
   back and not that anybody can use them.

## How you know it worked

`PASS RESTORE_DRILL` and a recovery time. The estate is readable in scope by
`hospitality_app` and invisible to it unscoped. Both, because either alone can be
right for the wrong reason.

## If it does not work

If the restore reports RESTORED_BUT_UNUSABLE the data is present and the
grants are not. Do not hand it over. That state looks fine to a superuser.
