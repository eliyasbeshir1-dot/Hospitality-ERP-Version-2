# Issuing a table QR

> **Owner:** OUTLET_MANAGER
> **When this is used:** A new table, a replaced placard, or a QR that has stopped working.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The outlet has a hostname in `edge.outlet_hostname`. Without one the QR has no
  name to carry and `edge.resolve_customer_entry()` refuses with
  OUTLET_HOSTNAME_UNDECLARED
- There is an installed certificate. Check `edge.certificate_posture()`

## Steps

1. Confirm the table exists in `org.org_node` with `kind = 'dining_table'`.
2. Print the placard carrying the OUTLET HOSTNAME, never an IP address. A raw
   address cannot be on a public certificate a phone trusts, and
   `outlet_hostname_is_a_name_not_an_address` refuses one at the source.
3. Scan it yourself, on the outlet Wi-Fi and on cellular. Both must work: that is
   what same-QR means.

## How you know it worked

The same placard reaches the node from the dining room and the cloud from the
street, with no certificate warning in either.

## If it does not work

If a phone shows a warning, STOP and do not tell the guest to continue. That
is the one outcome FR-EDG-022C forbids. Fall back to the cloud-served journey
or take the order on paper.
