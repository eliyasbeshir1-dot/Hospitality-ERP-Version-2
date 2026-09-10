# Setting up a printer

> **Owner:** OUTLET_MANAGER
> **When this is used:** A new printer, a replacement, or one that has stopped printing.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The printer model is one of the supported paths. 576-dot rasterisation is what
  the receipt renderer targets

## Steps

1. Register the printer against the outlet.
2. Run the print agent: `python3 print/agent.py`.
3. Run the queue runner separately: `python3 print/queue_runner.py`. It is a
   SEPARATE process on purpose. A lease that expires must not depend on the
   process that took it still being alive.
4. Print a test receipt and read it. Allergy lines come first and in words.

## How you know it worked

A receipt asked for is printed exactly once. Ask for the same one twice and the
second is refused rather than printed again.

## If it does not work

A failed job stays in the queue and raises EVT-PRINT-JOB-FAILED to whoever
owns it in `ops.alert_ownership`. A guest waiting for a receipt is the one
operational failure they notice before you do.
