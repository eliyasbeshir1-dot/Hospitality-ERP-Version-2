# When the internet goes

> **Owner:** OUTLET_MANAGER
> **When this is used:** The cloud is unreachable and the outlet is still serving.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- Nothing. This runbook is for the moment it happens.

## Steps

1. Do nothing to the node. It is designed for this and is already handling it.
2. Check the connectivity banner. It should read local continuity, in the language
   the reader uses.
3. Keep trading. Orders, the kitchen, bills, cash settlement and printing all work
   locally. What needs the cloud is queued or refused with a translated
   explanation rather than silently dropped.
4. Guests scanning a QR reach the node. If a phone has Private DNS on it may not;
   the guidance it gets names the setting, and a server can take the order.

## How you know it worked

Service continues. `integration.outbox` grows and nothing is lost.

## If it does not work

If the NODE also fails, the outlet is on paper. That is not a system state, it
is a restaurant state, and the orders taken on paper are entered afterwards.
