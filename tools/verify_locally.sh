#!/usr/bin/env bash
# THE LOCAL RUN MUST BE THE RUN CI DOES, OR IT IS NOT VERIFICATION.
#
# OP-D's clear_the_kitchen() passed locally and failed in CI. Not because the check was
# wrong — because the DATABASE was. It set context to one outlet and selected tickets
# across the whole tenant, and the local database had only ever seen that one outlet.
# CI's chain runs M4-A first, whose counter orders leave tickets at Kazanchis, so CI met
# a row local could not produce. The defect was in the suite the whole time; local simply
# could not see it, and a green that cannot see a class of defect is not evidence.
#
# What made local diverge was not a missing feature. It was running ONE driver by hand
# against whatever state the last thing left behind. The chain is the seed: every suite
# beneath the one under test writes rows the one under test will meet.
#
# So this runs what CI's Windows job runs, the way it runs it. That job was already the
# answer — one entry point, one streamed log, the register audit pointed at it — and this
# is that job with the machine-specific parts named. It is not a second opinion about how
# to verify; drift from it is checked below rather than trusted.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKFLOW="$REPO/.github/workflows/m1-conformance.yml"

# AN INTERPRETER THAT EXISTS IS NOT AN INTERPRETER THAT RUNS. The same probe the drivers
# carry, for the same reason: python3 on Windows is a Store stub that runs nothing.
PY_BIN="${PYTHON:-}"
if [ -z "$PY_BIN" ]; then
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
            PY_BIN="$candidate"
            break
        fi
    done
fi
if [ -z "$PY_BIN" ]; then
    echo "FAIL PREREQUISITE_ABSENT: no runnable interpreter on PATH" >&2
    exit 1
fi
export PYTHON="$PY_BIN"

# THE BASH THAT RUNS THIS MUST BE THE ONE THAT CAN SEE WINDOWS.
#
# `bash` on a Windows PATH is ambiguous: C:\Windows\System32ash.exe is the WSL
# launcher, and prepending System32 to PATH — which anyone reaching for taskkill or
# netstat does — makes `bash tools/verify_locally.sh` start a LINUX shell against the
# Windows checkout. It got a long way before failing: it rebuilt nothing, ignored every
# exported PGPORT and LOG_DIR because they belong to the other shell, and died on
# `psql: command not found` after reporting "running on Linux".
#
# That is a whole run's wall-clock spent proving nothing, and the verdict line it would
# have printed says nothing about which shell produced it. This job exists to reproduce
# CI's WINDOWS execution, so a Linux shell running it is not a lesser version of the same
# thing — it is a different claim wearing the same name.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) : ;;                       # Git Bash: the intended shell
    Linux)
        if [ -d /mnt/c ] && [ -e /proc/sys/fs/binfmt_misc/WSLInterop ]; then
            echo "FAIL LOCAL_RUNNER_WRONG_SHELL: this is WSL, running against a Windows" >&2
            echo "  checkout at $REPO. This runner reproduces CI's Windows job, and a" >&2
            echo "  Linux shell cannot: it has no psql, and the environment you exported" >&2
            echo "  in the other shell never reached it." >&2
            echo "  Run it from Git Bash, and check whether C:/Windows/System32 is ahead" >&2
            echo "  of Git's bin directory on PATH — System32\bash.exe is the WSL launcher." >&2
            exit 1
        fi
        ;;
esac

# THIS RUNNER IS A COPY OF A CI STEP, AND A COPY THAT CANNOT NOTICE THE ORIGINAL MOVED IS
# THE DEFECT IT EXISTS TO PREVENT. If CI stops entering the chain here, or stops handing
# the register audit its logs, a local green would be a green over a sequence nobody runs.
ENTRY="tests/journeys/run_verification.sh"
for required in "bash $ENTRY 2>&1 | tee" 'export M4C_LOG_DIR="$LOG_DIR"'; do
    grep -qF -- "$required" "$WORKFLOW" || {
        echo "FAIL LOCAL_RUNNER_STALE: the workflow no longer contains" >&2
        echo "  $required" >&2
        echo "so this runner reproduces a sequence CI has stopped running. Re-derive it" >&2
        echo "from the Windows job before trusting a local green." >&2
        exit 1; }
done

# The connection variables carry the names the workflow's Windows job uses, so the only
# difference between the two runs is where the server is. Defaults are this machine's
# throwaway container (docker start m1-win); override any of them for another.
export PGTCP_HOST="${PGTCP_HOST:-localhost}"
export PGPORT="${PGPORT:-5434}"
export SUPERUSER="${SUPERUSER:-postgres}"
export DB="${DB:-hospitality_os}"
export PGPASSWORD="${PGPASSWORD:-}"

# LOGS LIVE OUTSIDE THE CHECKOUT. The workflow records why: the README and evidence
# generators read the working tree, and a tee'd log inside it made the report say NOT
# CLEAN over a file the run had just written. A verification that dirties the thing it
# measures reports on itself.
LOG_DIR="${LOG_DIR:-${TMPDIR:-/tmp}/hosp-local-logs}"
mkdir -p "$LOG_DIR"
rm -f "$LOG_DIR"/*.log
export LOG_DIR
export M1D_WORKSPACE="${M1D_WORKSPACE:-${TMPDIR:-/tmp}/m1d-workspace}"

# THE REGISTER AUDIT NEEDS TO SEE THIS RUN'S OUTPUT. tests/m4c runs FR-GOV-004 over the
# logs the run produced and REFUSES when it cannot read them, which is right and is why
# M4C_VERIFICATION_UNUSABLE was this runner's verdict until this line existed. One
# streamed file is enough: the audit reads citations out of file CONTENT, not file names.
export M4C_LOG_DIR="$LOG_DIR"

# A DECLARED DIVERGENCE, NOT A SILENT ONE. The surface build runs tsc over four surfaces
# and dies with a V8 zone-allocation failure on a machine with under a gigabyte free.
# This caps the old-space heap so the compiler spills instead of aborting; it changes what
# the compiler may allocate, not what it emits. CI's runners have the headroom and set
# nothing, so this is the one line of this script CI has no counterpart for.
if [ -z "${NODE_OPTIONS:-}" ]; then
    export NODE_OPTIONS=--max-old-space-size=1024
    echo "note: NODE_OPTIONS=$NODE_OPTIONS — heap cap for a small machine, not a CI setting"
fi

echo "=== the whole chain, through the driver CI enters it by ==="
echo "    server : $PGTCP_HOST:$PGPORT/$DB as $SUPERUSER"
echo "    logs   : $LOG_DIR"
echo
# The journeys driver runs the OP-D driver — and therefore every suite beneath it — then
# walks the journeys. One entry point, so this runner cannot fall behind CI by a slice.
bash "$REPO/$ENTRY" 2>&1 | tee "$LOG_DIR/local-suites.log"

# THE LIST IS DERIVED FROM THE REPOSITORY, not typed. The workflow's copy of this loop was
# stale twice — it said M1A..M3A while the driver ran through M3-C, and M1A..M4A while it
# ran through M4-B — and each time suites were passing without anybody requiring them to.
# tests/ is where the suites are, so tests/ is what the loop reads.
cd "$REPO"
for suite in $(ls -d tests/m[0-9]* tests/opa tests/opb tests/opc tests/opd | sed 's#tests/##' | sort); do
    verdict="$(echo "$suite" | tr '[:lower:]' '[:upper:]')"
    grep -q "^PASS ${verdict}_VERIFICATION" "$LOG_DIR/local-suites.log" || {
        echo "FAIL ${verdict} did not report PASS" >&2; exit 1; }
done
grep -q '^PASS GOLDEN_JOURNEY_VERIFICATION' "$LOG_DIR/local-suites.log" || {
    echo "FAIL the golden journeys did not report PASS" >&2; exit 1; }
for journey in $(grep -oP '^\s+\("(\K[A-Z]+-[A-Z0-9-]+)(?="\,)' tests/journeys/verify_journeys.py); do
    grep -qE "^\s+PASS\s+$journey\s" "$LOG_DIR/local-suites.log" || {
        echo "FAIL $journey did not pass, or did not run" >&2; exit 1; }
done
total="$(grep -oP '(?:checks run|steps checked)\s+:\s+\K[0-9]+' \
         "$LOG_DIR/local-suites.log" | awk '{s+=$1} END {print s}')"
suites="$(grep -cE '^(PASS|FAIL) [A-Z0-9_]+_VERIFICATION' "$LOG_DIR/local-suites.log")"
failed="$(grep -oP 'failed\s+:\s+\K[0-9]+' "$LOG_DIR/local-suites.log" \
          | awk '{s+=$1} END {print s}')"
test "${failed:-1}" -eq 0 || { echo "FAIL ${failed} check(s) failed" >&2; exit 1; }
echo
echo "PASS LOCAL_CHAIN: $total checks and journey steps across $suites suites, 0 failures"
