#!/usr/bin/env bash
# Run a long command so that a watcher ALWAYS gets a terminal event.
#
# WHY THIS EXISTS, TWICE OVER.
#
# A monitor that tails a log and greps for success strings has no branch that fires when
# the process dies. `tail -f` never exits, the grep never matches again, and the watcher
# sits armed until the session ends. That has now cost hours on two separate occasions —
# run 46, and the OP-A suite chain, which died sixty seconds in on a constraint violation
# and was believed to be running for the next two and a half hours. Both times it looked
# exactly like work in progress, and both times it was silence.
#
# The defect is not the grep pattern. It is that the stream's END is not an event. A
# process exiting is the one thing a watcher most needs to know and the one thing a log
# file does not say. So this wrapper guarantees a final line, on every path out:
#
#     ### RUN-COMPLETE <name> exit=<code> at <timestamp>
#
# On success, on failure, on a signal, on a crash — the trap fires either way. A monitor
# grepping for `RUN-COMPLETE` therefore cannot wait forever, and one that also greps for
# progress strings gets the outcome as well as the running commentary.
#
# Usage:
#     bash tools/watched_run.sh <name> <logfile> <command...>
#
# Example, with the monitor that pairs with it:
#     bash tools/watched_run.sh suites /tmp/suites.log bash tests/journeys/run_verification.sh
#     tail -f /tmp/suites.log | grep -E --line-buffered '^(PASS|FAIL) [A-Z0-9_]+_VERIFICATION|^### RUN-'
#
# The marker is deliberately greppable with the verdict lines the suites already print, so
# one pattern covers progress and termination without the watcher needing two rules.

set -uo pipefail

if [ "$#" -lt 3 ]; then
    echo "usage: watched_run.sh <name> <logfile> <command...>" >&2
    exit 2
fi

NAME="$1"; LOG="$2"; shift 2

mkdir -p "$(dirname "$LOG")"
: > "$LOG"

# The marker is written by a trap rather than after the command, so it survives the paths
# a trailing line would miss: a non-zero exit under `set -e` in a caller, a SIGTERM from a
# harness timeout, a SIGINT from somebody's Ctrl-C.
STATUS=1
finish() {
    printf '### RUN-COMPLETE %s exit=%s at %s\n' \
        "$NAME" "$STATUS" "$(date -Is)" >> "$LOG"
}
trap finish EXIT
trap 'STATUS=143; exit 143' TERM
trap 'STATUS=130; exit 130' INT

printf '### RUN-START %s at %s\n' "$NAME" "$(date -Is)" >> "$LOG"

# STDIN COMES FROM /dev/null, EXPLICITLY, and that is not tidiness.
#
# A detached run started with `nohup … >/dev/null 2>&1 &` redirects stdout and stderr and
# leaves stdin pointing at the shell that launched it. When that shell exits, the handle
# becomes invalid, and on Windows the next attempt to spawn a child fails with
# `OSError: [WinError 6] The handle is invalid` — not because anything is wrong with the
# child, but because a process cannot be created with a broken standard handle.
#
# That cost a run: tests/m1d probes for a usable bash by spawning one, the spawn raised
# WinError 6, the probe reported the bash unusable, and the suite told its reader to
# install Git for Windows on a machine where Git for Windows was working perfectly. A
# valid, empty stdin costs nothing and removes the whole class.
#
# NOT stdbuf ON WINDOWS, AND THE REASON IS WORTH THE PARAGRAPH.
#
# stdbuf line-buffers a child by setting LD_PRELOAD to libstdbuf, and LD_PRELOAD is
# inherited by EVERY descendant, not just the child. On MSYS the value Git's stdbuf sets
# is a Windows path — C:/Program Files/Git/usr/lib/coreutils/libstdbuf.dll — and the
# loader splits LD_PRELOAD on ':' as a POSIX list. The first element is therefore "C",
# and every subsequent bash launched anywhere beneath this wrapper dies at startup with
#
#     fatal error - error while loading shared libraries: C: cannot open shared object
#
# The suites spawn bash to build the API, so this took out the whole chain — and because
# the probe that spawns it reported the failure as "no bash can see this filesystem", it
# read as a missing Git installation rather than as a poisoned environment. A line added
# to make failures more visible was the cause of a failure nobody could see.
#
# Line buffering is a nicety; not corrupting the environment of everything downstream is
# not. So it is used only where its mechanism is sound.
case "$(uname -s 2>/dev/null || echo unknown)" in
    MINGW*|MSYS*|CYGWIN*)  USE_STDBUF=0 ;;
    *)                     USE_STDBUF=1 ;;
esac

if [ "$USE_STDBUF" = "1" ] && command -v stdbuf >/dev/null 2>&1; then
    stdbuf -oL -eL "$@" >> "$LOG" 2>&1 < /dev/null
else
    "$@" >> "$LOG" 2>&1 < /dev/null
fi
STATUS=$?

exit "$STATUS"
