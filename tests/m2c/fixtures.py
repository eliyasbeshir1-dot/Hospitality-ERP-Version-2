"""M2-C fixtures: a seated guest, a live code, and a running surface to render.

M2-C is the first slice whose subject is a rendered page, so the fixture's job is to put
a real browser in front of a real service reading a real database. Nothing here stubs a
response: the allergen warnings the page draws come from safety.selection_safety() by way
of the customer routes, which is the whole point — a surface fed by a fixture could not
discharge the handoff M2-B left it.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "m1a"))
sys.path.insert(0, str(HERE.parent / "m1d"))

from pg import run  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "m2b_fixtures", HERE.parent / "m2b" / "fixtures.py")
m2b = importlib.util.module_from_spec(_spec)
sys.modules["m2b_fixtures"] = m2b
_spec.loader.exec_module(m2b)

m2a = m2b.m2a

TENANT = m2b.TENANT
OUTLET_H1 = m2b.OUTLET_H1
USER = m2b.USER
CTX = dict(tenant=TENANT, outlet=OUTLET_H1)
APP = os.environ["M1A_APP_DSN"]
ADMIN = os.environ["M1A_ADMIN_DSN"]


def seed() -> None:
    """M2-B's floor and catalog, then a published menu for the surface to render."""
    m2b.seed()
    m2b.translate_safety()

    # The surface reads a PUBLISHED snapshot, so there has to be one. Republishing from
    # draft each run keeps the suite order-independent: an earlier run leaves the menu
    # published, and publish_menu() refuses a menu already in that state.
    run(APP, f"""
        UPDATE menu.menu SET state = 'draft', row_version = row_version
        WHERE id = '{m2a.MENU}';
    """, **CTX)
    published = run(APP, f"SELECT menu.publish_menu('{m2a.MENU}', '{USER}');", **CTX)
    if not published.ok:
        raise RuntimeError(f"could not publish a menu to render: {published.why()}")


def fresh_occupancy_and_code(table: str = m2b.TABLE_ONE) -> str:
    """Open a new occupancy and issue a live code for it, returning the printed value.

    Issued rather than looked up, because the database keeps only a hash: the plaintext a
    placard carries exists for exactly as long as the caller holds it, which is the
    property NC-M2-001 and FR-SEC-007 both depend on.
    """
    m2b.open_occupancy(table, source="staff")
    issued = run(APP, f"""
        SELECT service.issue_table_qr('{TENANT}', '{table}', '{USER}');
    """, **CTX)
    code = (issued.scalar or "").strip()
    if not issued.ok or not code:
        raise RuntimeError(f"could not issue a code: {issued.why()}")
    return code
