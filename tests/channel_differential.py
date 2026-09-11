"""The channel differential: ONE instrument, used by every gate that adds a channel.

M3-D built it for two channels and this is that same instrument, moved here so a third
channel extends it rather than getting one of its own. Two implementations of the check
that proves there are not two implementations would be a joke with a long fuse: they
would agree today, which is the exact thing FR-POS-003A and FR-ORD-001B reject.

WHAT IT PROVES, AND WHY IT IS SHAPED THIS WAY.

The requirements say the channels use the SAME AGGREGATE AND POLICY MODEL with no
divergent order path, and reject "two implementations that agree today". A matrix that ran
every channel and compared outcomes would prove agreement on the cases it happened to try.
So the structural half derives the universe of rule functions FROM THE CATALOG and asserts
that each shared operation reaches the same single function whichever surface is asked —
the same NAME, so there is nothing for two implementations to agree about.

A CHANNEL IS AN ORIGIN, AND AN ORIGIN IS NOT A SURFACE. There are three origins and two
surfaces: a guest's own device, and the staff surface, which serves both the waiter and the
counter. That is the claim rather than an accident of layout — an origin that needed a
third surface would be the divergent path, so the mapping is stated once, here, and the
suites assert against it.
"""
from __future__ import annotations

import re

# The schemas whose functions ARE the rules. Enumerated from the catalog at run time; this
# names the schemas, never the functions, so a rule a later gate adds is covered without
# anybody remembering to extend a list.
RULE_SCHEMAS = ("menu", "safety", "ordering", "service")

RULE_FUNCTION_QUERY = f"""
    SELECT n.nspname || '.' || p.proname
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN {RULE_SCHEMAS};"""

ORIGIN_QUERY = "SELECT unnest(enum_range(NULL::ordering.order_origin))::text ORDER BY 1;"

# Which SURFACE serves each origin, and the route each shared operation lives at on it.
# The counter's row is deliberately identical to the waiter's: FR-ORD-001B's "no divergent
# order path" means there is no counter route to compare, and a differential that expected
# one would be asking for the divergence it exists to forbid.
SURFACES = {
    "guest": {
        "source": "api/src/routes/customer.ts",
        "a priced cart line": "/c/v1/cart/lines",
        "the order preview": "/c/v1/orders/preview",
        "the submission": "/c/v1/orders",
    },
    "staff": {
        "source": "api/src/routes/staff.ts",
        "a priced cart line": "/s/v1/cart/lines",
        "the order preview": "/s/v1/orders/preview",
        "the submission": "/s/v1/orders",
    },
}

ORIGIN_SURFACE = {
    "guest_qr": "guest",
    "waiter_entered": "staff",
    "counter": "staff",
}

OPERATIONS = ("a priced cart line", "the order preview", "the submission")


class DifferentialUnusable(RuntimeError):
    """The instrument could not run. Never returned as a passing comparison.

    An empty comparison is satisfied by everything, so a differential that could not find
    a route must stop rather than report that the routes agree.
    """


def strip_comments(source: str) -> str:
    """What the code CALLS, not what the file mentions.

    Without this the check reads prose. The comment in customer.ts explaining why the
    route no longer calls menu.effective_price() contains the words
    'menu.effective_price(' — and the first version of this counted it as a call, which
    would have made the route look guilty of the thing the comment says it stopped doing.
    """
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", source)


# EVERY VERB, AND THE REASON THIS IS NOT `get|post`.
#
# A handler block ends at the NEXT registration, so a verb this pattern does not know is a
# registration that does not end the block — and the handler then swallows the one after
# it. OP-C added the first DELETE route this repository has ever had, immediately after
# POST /c/v1/cart/lines, and the block for "a priced cart line" quietly grew to include it:
# the guest channel appeared to name service.remove_cart_line() as part of pricing a line,
# the staff channel did not, and this instrument reported a divergent order path that did
# not exist.
#
# It reported it CONFIDENTLY, which is the part worth recording. The message says "there is
# no second implementation for the two to agree about" — a claim about the code — while the
# real difference was in the reader.
#
# THE VERBS ARE STATED ONCE, HERE. route_paths() below used to carry its own copy of the
# list and the two disagreed twice over: this one knew get and post, that one knew get,
# post, patch and delete, and NEITHER knew put — which customer.ts has registered
# /c/v1/locale with since M2-C. Three readers of one fact in two files. Both now read this.
_VERBS = "get|post|put|patch|delete"
_REGISTRATION = re.compile(rf"app\.(?:{_VERBS})\s*[<(]")


def handler_block(source: str, path: str) -> str:
    """The source of one route handler: from its path literal to the next registration."""
    marker = f"'{path}'"
    if marker not in source:
        raise DifferentialUnusable(
            f"no route registered at {path}; the comparison would otherwise pass by "
            f"having nothing to compare")
    start = source.index(marker)
    following = [m.start() for m in _REGISTRATION.finditer(source) if m.start() > start]
    return source[start:following[0] if following else len(source)]


def named_rules(block: str, universe: set[str]) -> list[str]:
    return sorted(name for name in universe
                  if re.search(r"\b" + re.escape(name) + r"\s*\(", block))


def route_paths(source: str) -> list[str]:
    """Every path this file registers a route at, in registration order."""
    return re.findall(rf"app\.(?:{_VERBS})\s*(?:<[^>]*>)?\s*\(\s*'([^']+)'",
                      source, flags=re.S)


def origin_surfaces(origins: list[str]) -> dict[str, str]:
    """Which surface serves each origin the CATALOG knows about.

    Raises rather than defaulting. An origin nobody mapped is a channel with no stated
    home, and guessing 'staff' would let a future gate add a divergent path and have this
    instrument shrug at it.
    """
    unmapped = [o for o in origins if o not in ORIGIN_SURFACE]
    if unmapped:
        raise DifferentialUnusable(
            f"ordering.order_origin carries {unmapped}, which no surface claims. A "
            f"channel with no stated surface is a divergent order path waiting to be "
            f"written: add it to ORIGIN_SURFACE, or explain why it needs its own route")
    return {origin: ORIGIN_SURFACE[origin] for origin in origins}


def rules_by_surface(read_source, universe: set[str]) -> dict[str, dict[str, list[str]]]:
    """For each surface and each shared operation, the rule functions it names."""
    out: dict[str, dict[str, list[str]]] = {}
    for surface, table in SURFACES.items():
        source = strip_comments(read_source(table["source"]))
        out[surface] = {op: named_rules(handler_block(source, table[op]), universe)
                        for op in OPERATIONS}
    return out
