"""The encoding this process writes its own evidence in.

Every suite here reads psql with an explicit encoding, because leaving that to
locale.getpreferredencoding() produced mojibake on Windows. The other half of that
problem was never addressed: what this process writes to its own stdout.

Python picks the console encoding from the platform. On the Windows runner that is
cp1252, which cannot represent Amharic or Arabic at all — so the M2-A suite proved it
had stored 'ቁርስ' correctly and then died with UnicodeEncodeError trying to say so. The
same stream also silently re-encoded characters cp1252 *can* hold, so an em dash left
Python as one byte and arrived in the log as another.

Both are the same defect: evidence altered or destroyed by the channel reporting it.
Neither is fixed by removing the non-ASCII text, which is the actual subject under
test — a system storing three locales must be able to say what it stored.

errors stays strict on purpose. A replacement character is a quiet lie about what the
database returned, and this harness does not report unreadable output as output
(FR-OPS-021).
"""
from __future__ import annotations

import sys


def use_utf8_output() -> None:
    """Write this process's stdout and stderr as UTF-8 regardless of the platform.

    Called at the top of every entry point, before anything prints. Idempotent, and a
    no-op where the stream is already UTF-8 — which is every Linux run, so this changes
    nothing there.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # A stream replaced by a test harness or a pipe wrapper may not expose it.
            # Nothing to do: it is not a TextIOWrapper choosing a platform default.
            continue
        if (getattr(stream, "encoding", "") or "").lower().replace("-", "") == "utf8":
            continue
        reconfigure(encoding="utf-8", errors="strict")
