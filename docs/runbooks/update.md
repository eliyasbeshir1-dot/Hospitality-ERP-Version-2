# Updating a node

> **Owner:** OUTLET_MANAGER
> **When this is used:** A new version is being rolled out to an outlet.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The outlet is not mid-service. An update during a dinner rush is a decision
  about the dinner rush
- There is a verified backup

## Steps

1. Stage the update. It is verified against the node trust anchor before it is
   applied: a keyed digest rather than a signature, because this database has no
   pgcrypto and saying so is better than pretending otherwise.
2. Apply it.
3. Watch the five services come back.

## How you know it worked

The node reports all five services and the connectivity banner is truthful.

## If it does not work

Roll back. The rollback REFUSES if the local queues have shrunk: an update that
lost queued work does not get to pretend it did not.
