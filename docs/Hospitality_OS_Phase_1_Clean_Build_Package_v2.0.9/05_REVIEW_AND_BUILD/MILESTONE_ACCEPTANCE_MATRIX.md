# Milestone Acceptance Matrix

| Gate | Requirement count | Mandatory journeys | Exit criterion |
|---|---:|---|---|
| M0 | 2 |  | Codex independent review of this exact ZIP. |
| M0R | 30 |  | No database, migration, route, worker or UI exists. |
| M1 | 77 |  | Real PostgreSQL and production-role isolation tests pass. |
| M2 | 49 |  | English/Amharic/Arabic customer surfaces and true Arabic RTL pass. |
| M3 | 75 | GJ-01A, GJ-02, GJ-03A, GJ-04, GJ-05 | The three M3 language journeys pass without billing or local authority. |
| M4 | 55 | GJ-01B, GJ-02B, GJ-03B, GJ-06, GJ-07 | Live pilot payment paths and physical/digital receipts pass. |
| M5a | 24 | GJ-10 | Restart, retry, deduplication, reconnect and print recovery pass. |
| M5b | 12 | GJ-08, GJ-09 | Same QR works under supported resolver conditions without split-brain or browser bypass. |
| M6 | 12 | GJ-11, GJ-12, GJ-13 | Destructive restore, production roles, full scans and second-tenant evidence pass. |
