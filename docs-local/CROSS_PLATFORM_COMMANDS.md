# Cross-platform commands (FR-OPS-021)

Ordinary commands on an ordinary machine. Nothing here depends on a PATH that only exists
inside CI, and nothing is injected by the pipeline: every command below works from a plain
shell on a developer's own machine, or fails with a message naming what is missing.

## What was verified, and what was not

**Verified on Linux.** Every command in the Linux column was executed on
`Linux 6.18.44 x86_64` with Python 3.11, PostgreSQL 16.13, Node 22.22 and Git 2.43, and
`tools/check_prerequisites.py` was run in both its passing and its failing form.

**Verified on Windows.** Every command in the Windows column was executed on
`Windows 11 (AMD64)` with Python 3.12.10, a PostgreSQL 16.15 server in Docker reached over
TCP by a psql 18.4 client, Node 24.16.0, npm 11.13.0 and Git 2.54.0. All five suites were
run against a database built from empty — fenced-gate 33, M1-A 43, M1-B 35, M1-C 60 and
M1-D 49 checks, 220 in total — and `tools/check_prerequisites.py` was run in its passing
form, its absent-tool form and its present-but-unrunnable form.

That run is what closed F3, and it found what a documented-but-unexecuted path always
hides: seven defects that Linux could not expose. Locale decoding (`text=True` inherits
cp1252 on Windows and corrupted psql output), a Windows path handed to bash, `bash`
resolving to the WSL launcher rather than Git Bash, npm's extensionless `tsc`, a
`python3` requirement no standard Windows install can satisfy, a POSIX-only temporary
path, and a start window too tight for a cold start. Each is repaired and each is proved
red before green.

**What is still not claimed.** These are the versions above, on one machine. The suites are
not run on Windows in CI, so Windows is verified by execution but not guarded against
regression by it; a Windows defect introduced tomorrow would not be caught until someone
runs the suites there again.

### Prerequisites on Windows

`psql` must be on `PATH`. Every tool here reaches the database by running the `psql`
binary — there is no driver and no ORM — so a missing client blocks all five suites rather
than one check. Installing PostgreSQL does not always add its `bin` directory to `PATH`.

The interpreter is `python` on Windows and `python3` on Linux, and the checker requires the
one that belongs to the platform it is running on. A standard Windows Python installs
`python.exe` and no `python3.exe`; the `python3.exe` on a typical Windows `PATH` is the
zero-byte Microsoft Store alias, which runs nothing.

The API build is a bash script, and on Windows it needs **Git Bash**. The `bash` on `PATH`
is normally `C:\WINDOWS\system32\bash.exe`, the WSL launcher — a different operating system
with a different filesystem view. The harness locates Git Bash from the `git` on `PATH` and
refuses rather than falling back to WSL.

## Discovering prerequisites

| | Command |
|---|---|
| Linux / macOS | `python3 tools/check_prerequisites.py` |
| Windows (PowerShell) | `python tools\check_prerequisites.py` |
| Windows (cmd) | `python tools\check_prerequisites.py` |

It prints every required tool, where it was found and its version. When a tool is absent it
exits non-zero with `FAIL PREREQUISITE_ABSENT`, the PATH it searched, and the install
command for the platform it is running on.

Add a tool to the requirement list with `--require`, for example
`python3 tools/check_prerequisites.py --require docker`.

## Applying migrations

| | Command |
|---|---|
| Linux / macOS | `python3 tools/migrate.py --dsn "$DATABASE_URL" apply` |
| Windows (PowerShell) | `python tools\migrate.py --dsn $env:DATABASE_URL apply` |
| Windows (cmd) | `python tools\migrate.py --dsn %DATABASE_URL% apply` |

`preflight` checks the history without applying anything; `status` lists every migration
and whether it is applied, pending or edited.

## Applying seeds

Seeds have their own ordered record and their own checksum lock, separate from migrations.
Bookkeeping runs as the migration identity; seed content is applied through the
least-privileged application role.

| | Command |
|---|---|
| Linux / macOS | `python3 tools/seed.py --dsn "$MIGRATOR_URL" --content-dsn "$DATABASE_URL" apply` |
| Windows (PowerShell) | `python tools\seed.py --dsn $env:MIGRATOR_URL --content-dsn $env:DATABASE_URL apply` |

## Building and running the API

| | Command |
|---|---|
| Linux / macOS | `bash api/build.sh` then `bash api/build.sh --run` |
| Windows (PowerShell) | `npm install; npx tsc -p api\tsconfig.json --outDir $env:M1D_WORKSPACE\dist` |

The build deliberately writes `node_modules/` and `dist/` **outside** the repository, into
`$M1D_WORKSPACE` (default `/var/lib/m1d-workspace`; set it to any writable directory on
Windows). `tools/verify_m1.py` treats those directories as forbidden surface and inspects
the filesystem rather than the Git index, so building inside the repository would fail the
gate even with a `.gitignore` entry. Building elsewhere keeps the repository clean at every
moment, with no cleanup step to forget.

Required environment for the service:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | connection string for the **least-privileged application role** |
| `PORT` | TCP port to listen on |
| `ENVIRONMENT_NAME` | environment label, reported by `/health` |
| `HOST` | optional, defaults to `127.0.0.1` |
| `LOG_LEVEL` | optional, defaults to `info` |

The service validates all of these, plus the privilege level of `DATABASE_URL`, **before**
it opens a listener. Given an owner, superuser or BYPASSRLS credential it refuses to start
and exits `78`, printing `STARTUP REFUSED — PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED` without
echoing the credential.

## Running the verification suites

| | Command |
|---|---|
| Linux / macOS | `python3 tests/m1a/verify_m1a.py` (likewise `m1b`, `m1c`, `m1d`) |
| Windows (PowerShell) | `python tests\m1a\verify_m1a.py` |

Each suite needs `M1A_ADMIN_DSN`, `M1A_APP_DSN` and `M1A_MIGRATOR_DSN` in the environment.
The drivers under `tests/*/run_verification.sh` are bash and have no PowerShell equivalent;
on Windows, run the Python harnesses directly against an already-prepared database.
