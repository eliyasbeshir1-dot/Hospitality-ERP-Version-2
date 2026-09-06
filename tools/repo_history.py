"""Facts derived from git history, with a loud failure when the history is not there.

Both generators need history: the README resolves each slice to the commit that landed
it, and the evidence report names the last commit touching anything other than itself.
Under a shallow checkout neither question has an answer, and the previous code answered
anyway — every slice became "unreleased" and the gate silently fell back to the earliest
one. A plausible wrong answer from a quiet degradation is the same defect class as a
verifier falling back to a built-in vocabulary, so this module refuses instead.

One copy, shared by both generators, for the same reason the fenced vocabulary is: a
second copy of a rule diverges from the first without anyone noticing.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class HistoryUnavailable(Exception):
    """Git history cannot answer the question. Callers must stop, not guess."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", cwd=REPO)


def assert_history_available() -> int:
    """Confirm a full history is present. Returns the commit count.

    A shallow checkout is the common case — `actions/checkout` defaults to depth 1 — and
    it is indistinguishable from "this work never happened" unless it is detected here.
    """
    inside = _git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise HistoryUnavailable("not inside a git work tree")

    shallow = _git("rev-parse", "--is-shallow-repository")
    if shallow.stdout.strip() == "true":
        raise HistoryUnavailable(
            "the checkout is SHALLOW, so commit history cannot be read. "
            "Set fetch-depth: 0 on actions/checkout for any job that runs a generator")

    count = _git("rev-list", "--count", "HEAD")
    if count.returncode != 0 or not count.stdout.strip().isdigit():
        raise HistoryUnavailable("HEAD has no readable history")
    return int(count.stdout.strip())


def commit_for_subject_prefix(prefix: str) -> str | None:
    """The first commit whose subject begins with the prefix, or None if there is none."""
    out = _git("log", "--format=%h\t%s", "--reverse").stdout
    for line in out.splitlines():
        short, _, subject = line.partition("\t")
        if subject.startswith(prefix):
            return short
    return None


def last_commit_excluding(path: str) -> tuple[str, str]:
    """(full, short) of the last commit touching anything other than `path`.

    A generated file cannot name the commit that carries it, so a report names the last
    commit that changed something else and is committed on its own afterwards.
    """
    exclude = f":(exclude){path}"
    full = _git("log", "-1", "--format=%H", "--", ".", exclude).stdout.strip()
    short = _git("log", "-1", "--format=%h", "--", ".", exclude).stdout.strip()
    if not full or not short:
        raise HistoryUnavailable(
            f"no commit was found touching anything other than {path}. "
            "In a shallow checkout this is what an unreadable history looks like")
    return full, short


def dirt_excluding(path: str) -> list[str]:
    """The uncommitted paths, ignoring one file. Named, because a refusal that cannot say
    WHICH files are uncommitted leaves the reader to run git themselves to find out."""
    lines = _git("status", "--porcelain", "--", ".", f":(exclude){path}").stdout.splitlines()
    return sorted(line[3:].strip() for line in lines if line.strip())


def current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
