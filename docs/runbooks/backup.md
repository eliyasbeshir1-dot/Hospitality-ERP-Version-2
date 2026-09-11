# Taking a backup

> **Owner:** OUTLET_MANAGER
> **When this is used:** On the schedule in `ops.backup_policy`, and before any risky change.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- `HOSPITALITY_BACKUP_KEY` is set. Without it the tool REFUSES rather than
  falling back to an unencrypted dump

## Steps

1. `python3 tools/backup.py --dsn <dsn> --tenant <uuid> --scope cloud --into <dir>
   --offsite <dir>`
2. That is all. It captures, records, decrypts, reads the archive back and copies
   it off-site, and each step refuses rather than continuing if the one before it
   did not hold.

## How you know it worked

`SELECT * FROM ops.backup_posture(<tenant>, 'cloud')` reads healthy. It reports the
last VERIFIED backup, not the last one taken: a directory full of archives nobody
has opened is exactly what that distinction exists to expose.

## If it does not work

A backup that fails verification is recorded as `failed_verification` and
KEPT. A corrupt archive is evidence about the process that produced it.
