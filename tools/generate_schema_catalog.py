#!/usr/bin/env python3
"""Generate the schema and domain catalog from the live database (FR-DAT-015).

Nothing here is hand-written. Every table, column, constraint, policy and relationship
in the output is read from the running database's catalogs, so the document cannot drift
from the schema: if it did, the verification suite regenerates it and the diff fails.

Usage:
    python3 tools/generate_schema_catalog.py --dsn <dsn> --out schema/SCHEMA_CATALOG.md
    python3 tools/generate_schema_catalog.py --dsn <dsn> --check schema/SCHEMA_CATALOG.md

--check regenerates and compares without writing, exiting 1 on any difference.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

UNIT = "\x1f"
SCHEMAS = ("app", "org", "identity", "money", "config", "audit")


def md(text: str) -> str:
    """Escape a value for a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ")


def query(dsn: str, sql: str) -> list[list[str]]:
    proc = subprocess.run(
        ["psql", dsn, "-v", "ON_ERROR_STOP=1", "--no-psqlrc", "-X",
         "-t", "-A", "-F", UNIT],
        input=sql, capture_output=True, text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if proc.returncode != 0:
        raise SystemExit(f"catalog query failed: {proc.stderr.strip()}")
    return [line.split(UNIT) for line in proc.stdout.splitlines() if line.strip()]


def build(dsn: str) -> str:
    schema_list = ", ".join(f"'{s}'" for s in SCHEMAS)

    schemas = query(dsn, f"""
        SELECT n.nspname, coalesce(obj_description(n.oid, 'pg_namespace'), '')
        FROM pg_namespace n WHERE n.nspname IN ({schema_list}) ORDER BY n.nspname;
    """)

    tables = query(dsn, f"""
        SELECT n.nspname, c.relname,
               coalesce(obj_description(c.oid, 'pg_class'), ''),
               c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ({schema_list}) AND c.relkind = 'r'
        ORDER BY n.nspname, c.relname;
    """)

    columns = query(dsn, f"""
        SELECT n.nspname, c.relname, a.attname,
               format_type(a.atttypid, a.atttypmod),
               CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE '' END,
               coalesce(pg_get_expr(d.adbin, d.adrelid), ''),
               coalesce(col_description(c.oid, a.attnum), '')
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid = c.oid AND d.adnum = a.attnum
        WHERE n.nspname IN ({schema_list}) AND c.relkind = 'r'
        ORDER BY n.nspname, c.relname, a.attnum;
    """)

    constraints = query(dsn, f"""
        SELECT n.nspname, c.relname, con.conname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ({schema_list})
        ORDER BY n.nspname, c.relname, con.conname;
    """)

    policies = query(dsn, f"""
        SELECT n.nspname, c.relname, p.polname,
               coalesce(pg_get_expr(p.polqual, p.polrelid), '')
        FROM pg_policy p
        JOIN pg_class c ON c.oid = p.polrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ({schema_list})
        ORDER BY n.nspname, c.relname, p.polname;
    """)

    enums = query(dsn, f"""
        SELECT n.nspname, t.typname, string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder)
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        JOIN pg_enum e ON e.enumtypid = t.oid
        WHERE n.nspname IN ({schema_list})
        GROUP BY n.nspname, t.typname ORDER BY n.nspname, t.typname;
    """)

    domains = query(dsn, f"""
        SELECT n.nspname, t.typname, format_type(t.typbasetype, t.typtypmod),
               coalesce(obj_description(t.oid, 'pg_type'), '')
        FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname IN ({schema_list}) AND t.typtype = 'd'
        ORDER BY n.nspname, t.typname;
    """)

    # Foreign keys, for the relationship diagram.
    edges = query(dsn, f"""
        SELECT sn.nspname || '.' || sc.relname, tn.nspname || '.' || tc.relname
        FROM pg_constraint con
        JOIN pg_class sc ON sc.oid = con.conrelid
        JOIN pg_namespace sn ON sn.oid = sc.relnamespace
        JOIN pg_class tc ON tc.oid = con.confrelid
        JOIN pg_namespace tn ON tn.oid = tc.relnamespace
        WHERE con.contype = 'f' AND sn.nspname IN ({schema_list})
        GROUP BY 1, 2 ORDER BY 1, 2;
    """)

    out: list[str] = []
    w = out.append

    w("# Schema and Domain Catalog")
    w("")
    w("**Generated from the live database by `tools/generate_schema_catalog.py`.**")
    w("Do not edit by hand: the verification suite regenerates this file and fails on any")
    w("difference, so a hand edit is reported as drift (FR-DAT-015).")
    w("")
    w(f"Schemas covered: {', '.join('`' + s + '`' for s in SCHEMAS)}.")
    w("")
    w("---")
    w("")
    w("## Domains")
    w("")
    w("| Domain | Base type | Purpose |")
    w("|---|---|---|")
    for s, name, base, comment in domains:
        w(f"| `{s}.{name}` | `{base}` | {md(comment)} |")
    w("")

    w("## Enumerated types")
    w("")
    w("| Type | Values |")
    w("|---|---|")
    for s, name, labels in enums:
        w(f"| `{s}.{name}` | {labels} |")
    w("")

    w("## Relationships")
    w("")
    w("Foreign-key edges between tables, read from `pg_constraint`.")
    w("")
    w("```mermaid")
    w("graph LR")
    seen_nodes = set()
    for src, dst in edges:
        for node in (src, dst):
            if node not in seen_nodes:
                seen_nodes.add(node)
                w(f'  {node.replace(".", "_")}["{node}"]')
    for src, dst in edges:
        w(f'  {src.replace(".", "_")} --> {dst.replace(".", "_")}')
    w("```")
    w("")

    w("## Schemas")
    w("")
    for s, comment in schemas:
        w(f"### `{s}`")
        w("")
        if comment:
            w(comment)
            w("")

        for ts, tn, tcomment, rls, forced in tables:
            if ts != s:
                continue
            w(f"#### `{ts}.{tn}`")
            w("")
            if tcomment:
                w(tcomment)
                w("")
            w(f"Row level security: **{'enabled' if rls == 't' else 'DISABLED'}**, "
              f"**{'forced' if forced == 't' else 'not forced'}**.")
            w("")
            w("| Column | Type | Null | Default | Notes |")
            w("|---|---|---|---|---|")
            for cs, cn, col, ctype, notnull, default, ccomment in (
                    (r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in columns):
                if cs != ts or cn != tn:
                    continue
                w(f"| `{col}` | `{ctype}` | {notnull or ''} | "
                  f"{('`' + default + '`') if default else ''} | {md(ccomment)} |")
            w("")

            rows = [r for r in constraints if r[0] == ts and r[1] == tn]
            if rows:
                w("Constraints:")
                w("")
                for _, _, name, definition in rows:
                    w(f"- `{name}` — `{definition}`")
                w("")

            prows = [r for r in policies if r[0] == ts and r[1] == tn]
            if prows:
                w("Policies:")
                w("")
                for _, _, name, expr in prows:
                    w(f"- `{name}` — `{expr}`")
                w("")

    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the schema catalog from a live database.")
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--out")
    ap.add_argument("--check")
    args = ap.parse_args()

    generated = build(args.dsn)

    if args.check:
        path = Path(args.check)
        if not path.exists():
            print(f"FAIL SCHEMA_CATALOG_ABSENT — {path} does not exist", file=sys.stderr)
            return 1
        current = path.read_text(encoding="utf-8")
        if current != generated:
            print("FAIL SCHEMA_CATALOG_DRIFT — the catalog does not match the live schema",
                  file=sys.stderr)
            import difflib
            diff = list(difflib.unified_diff(
                current.splitlines(), generated.splitlines(),
                fromfile="committed", tofile="live", lineterm="", n=1))
            for line in diff[:40]:
                print(f"  {line}", file=sys.stderr)
            if len(diff) > 40:
                print(f"  … {len(diff) - 40} more line(s) of difference", file=sys.stderr)
            return 1
        print("PASS SCHEMA_CATALOG_MATCHES_LIVE_SCHEMA")
        print(f"  {len(generated.splitlines())} lines verified against the running database")
        return 0

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated, encoding="utf-8")
        print(f"wrote {path} ({len(generated.splitlines())} lines)")
        return 0

    sys.stdout.write(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
