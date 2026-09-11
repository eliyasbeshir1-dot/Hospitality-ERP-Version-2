# Publishing a menu

> **Owner:** OUTLET_MANAGER
> **When this is used:** Prices, dishes, availability or translations change.
>
> This runbook is registered in `ops.runbook`. If you are reading it because something is
> wrong, the register is what pointed you here.

## Before you start

- The change is decided. A menu publish is not where a price is negotiated.
- You know which locales are affected. A dish published in English only is a dish
  the Amharic and Arabic surfaces cannot render, and that is caught in
  `menu.translation` rather than at a guest's phone

## Steps

1. Stage the change against `menu.*` under a new configuration version.
2. Publish. The snapshot is immutable once orders reference it.
3. Confirm the guest surface renders it in all three locales.

## How you know it worked

A guest session opened after the publish sees the new prices, and one opened
before it still sees the old ones. An order is priced by the snapshot it was
placed against, not by the menu as it is now.

## If it does not work

Publish a further version. Menus are versioned precisely so that correcting
one is a forward act; nothing edits a published snapshot.
