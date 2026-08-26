# M0R Repository Conformance Plan

## Purpose

Create the first clean repository without implementing the product.

## Allowed

- Approved Package M0 documents and machine-readable registers
- Traceability and ownership plans
- CI design and forbidden-surface scanner design
- Code-reuse provenance register
- Review evidence templates

## Forbidden

- Database or schema
- Executable migration, including `0001`
- Application route, worker, screen, UI or runtime service
- Hidden or feature-flagged Phase 2/3 surface
- Reused prototype code

## Exit

A scan proves the repository is documentation-only, every planned unit maps to an active requirement and no deferred-domain surface exists.
