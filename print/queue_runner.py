#!/usr/bin/env python3
"""The print agent as a SERVICE: drain the durable queue FR-EDG-029 asks for.

WHY THIS IS A SECOND FILE AND NOT A FLAG ON THE FIRST.

print/agent.py takes one document and puts it on one sink. That contract is what M4-C's
suites invoke and what FR-BIL-017's minimum production path is measured through, and it
should keep being a thing you can run by hand against one receipt when a printer is
misbehaving. What M5a adds is not a different way to print — it is a decision about WHICH
job to print and what to do when it fails, which is a different question with a different
failure mode. So the agent still puts bytes on a sink, and this decides what to hand it.

THE LOOP, AND WHY IT IS IN THIS ORDER.

  1. recover expired claims   a lease belonging to an agent that stopped
  2. claim what is runnable   under a fresh lease, oldest first
  3. render and write         through agent.produce(), unchanged
  4. record the outcome       complete_print_job() or fail_print_job()

Recovery is first for the reason the sync worker recovers first: a runner that starts by
claiming leaves the previous run's leases to expire on their own, and a queue that looks
busy is a queue nobody looks at.

WHAT HAPPENS WHEN THE PAPER COMES OUT AND THE DATABASE DOES NOT HEAR ABOUT IT.

This is the failure that makes printing different from everything else, and it cannot be
designed away — between the write to the device and the write to the database there is a
gap, and a process can die in it. What CAN be arranged is which way the gap fails:

  * the job stays claimed, its lease expires, and it is offered again;
  * docs.complete_print_job() on an already-printed job changes nothing and returns null;
  * so a re-offered job that DID print is at risk of a second physical copy, and that is
    stated here rather than hidden — FR-EDG-029 asks for no duplicate physical output, and
    what this achieves is no duplicate output for every failure except a death inside that
    gap. planning/M5A_FINDINGS.md records it as an accepted bound with the shape of what
    would close it (a device that can be asked what it last printed, which no ESC/POS
    printer in this class offers).

Standard library only, and psql for the database, because that is what this repository
uses everywhere else and a print agent is the wrong place to introduce a driver.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))

from console import use_utf8_output          # noqa: E402
from migrate import psql, sql_literal        # noqa: E402
from agent import PrintRefused, produce      # noqa: E402

UNIT = "\x1f"


def rows(dsn: str, sql: str) -> list[list[str]]:
    out = psql(dsn, sql)
    return [line.split(UNIT) for line in out.splitlines() if line != ""]


def scoped(tenant: str, outlet: str, sql: str) -> str:
    """Every statement runs inside one transaction with the context set.

    set_config(..., true) is TRANSACTION-local. Without the BEGIN the context is gone
    before the next statement reads it, and row level security then matches nothing — a
    queue that silently appears empty. That defect cost a debugging session in
    api/src/node/identity.ts on the same day; it is written out here so the next reader
    meets it as a rule rather than as a surprise.
    """
    return (f"BEGIN;\n"
            f"SELECT set_config('app.tenant_id', {sql_literal(tenant)}, true),\n"
            f"       set_config('app.outlet_id', {sql_literal(outlet)}, true);\n"
            f"{sql}\n"
            f"COMMIT;")


def claim(dsn: str, tenant: str, outlet: str, agent: str, lease: int,
          limit: int) -> list[dict]:
    recovered = rows(dsn, scoped(tenant, outlet,
        f"SELECT docs.recover_expired_print_claims("
        f"{sql_literal(tenant)}::uuid, {sql_literal(outlet)}::uuid);"))
    if recovered and recovered[0][0] not in ("0", ""):
        print(json.dumps({"event": "print.recovered", "jobs": recovered[0][0]}))

    claimed = rows(dsn, scoped(tenant, outlet,
        f"SELECT job_id, receipt_id, printer_id, is_reprint, attempts\n"
        f"  FROM docs.claim_print_jobs({sql_literal(tenant)}::uuid, "
        f"{sql_literal(outlet)}::uuid, {sql_literal(agent)}, {lease}, {limit});"))
    return [{"job_id": r[0], "receipt_id": r[1], "printer_id": r[2],
             "is_reprint": r[3] == "t", "attempts": int(r[4])} for r in claimed if len(r) >= 5]


def printer_of(dsn: str, tenant: str, outlet: str, printer_id: str) -> dict:
    found = rows(dsn, scoped(tenant, outlet,
        f"SELECT sink::text, COALESCE(device_path,''), COALESCE(host_and_port,'')\n"
        f"  FROM docs.printer\n"
        f" WHERE tenant_id = {sql_literal(tenant)}::uuid "
        f"   AND id = {sql_literal(printer_id)}::uuid;"))
    if not found:
        raise PrintRefused(f"PRINTER_UNKNOWN: {printer_id}")
    sink, device_path, host = found[0]
    return {"sink": sink, "device_path": device_path or None, "host_and_port": host or None}


def document_of(dsn: str, tenant: str, outlet: str, receipt_id: str) -> dict:
    found = rows(dsn, scoped(tenant, outlet,
        f"SELECT docs.receipt_document({sql_literal(tenant)}::uuid, "
        f"{sql_literal(receipt_id)}::uuid)::text;"))
    if not found or not found[0][0]:
        raise PrintRefused(f"RECEIPT_DOCUMENT_ABSENT: {receipt_id}")
    return json.loads(found[0][0])


def run_once(dsn: str, tenant: str, outlet: str, actor: str, agent: str,
             lease: int, limit: int, workspace: Path | None) -> dict:
    done, failed = 0, 0
    for job in claim(dsn, tenant, outlet, agent, lease, limit):
        try:
            printer = printer_of(dsn, tenant, outlet, job["printer_id"])
            document = document_of(dsn, tenant, outlet, job["receipt_id"])
            result = produce(document, sink=printer["sink"],
                             device_path=printer["device_path"],
                             host_and_port=printer["host_and_port"],
                             workspace=workspace)
        except PrintRefused as refused:
            psql(dsn, scoped(tenant, outlet,
                f"SELECT docs.fail_print_job({sql_literal(tenant)}::uuid, "
                f"{sql_literal(job['job_id'])}::uuid, {sql_literal(str(refused))});"))
            failed += 1
            print(json.dumps({"event": "print.failed", "job": job["job_id"],
                              "reason": str(refused)[:200]}))
            continue

        psql(dsn, scoped(tenant, outlet,
            f"SELECT docs.complete_print_job(\n"
            f"  {sql_literal(tenant)}::uuid, {sql_literal(job['job_id'])}::uuid,\n"
            f"  {sql_literal(printer['sink'])}::docs.sink_kind,\n"
            f"  {sql_literal(str(result.get('resolved_destination', '')))},\n"
            f"  {sql_literal(result['bytes_sha256'])}::character(64),\n"
            f"  {result['byte_count']}, {sql_literal(actor)}::uuid);"))
        done += 1
        print(json.dumps({"event": "print.completed", "job": job["job_id"],
                          "bytes": result["byte_count"]}))
    return {"printed": done, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    use_utf8_output()
    parser = argparse.ArgumentParser(
        description="Drain the durable local print queue (FR-EDG-029).")
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--outlet", required=True)
    parser.add_argument("--actor", required=True,
                        help="the user the print attempt is attributed to")
    parser.add_argument("--agent", default=f"print-agent@{socket.gethostname()}")
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--once", action="store_true",
                        help="drain what is runnable now and stop; this is what the "
                             "suite drives, and what an operator runs to clear a queue")
    args = parser.parse_args(argv)

    if not args.dsn:
        print(json.dumps({"refused": "DATABASE_URL_ABSENT"}))
        return 1

    if args.once:
        print(json.dumps(run_once(args.dsn, args.tenant, args.outlet, args.actor,
                                  args.agent, args.lease_seconds, args.limit,
                                  args.workspace)))
        return 0

    while True:
        try:
            run_once(args.dsn, args.tenant, args.outlet, args.actor, args.agent,
                     args.lease_seconds, args.limit, args.workspace)
        except Exception as error:            # noqa: BLE001 — the runner must not stop
            # A round that fails is a round. The queue this drains is what an outage
            # fills, so the process that drains it is the one that must survive.
            print(json.dumps({"event": "print.round_failed",
                              "errorClass": type(error).__name__}), file=sys.stderr)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
