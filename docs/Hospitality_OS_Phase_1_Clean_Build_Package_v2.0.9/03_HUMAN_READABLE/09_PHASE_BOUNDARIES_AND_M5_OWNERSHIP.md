# Phase Boundaries and M5 Ownership

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Phase 1 active scope

- QR dine-in
- English/Amharic/Arabic
- waiter
- KDS
- counter POS
- bill
- separate optional tip
- cash
- external terminal recording
- verified Telebirr/CBE Birr proof confirmation
- receipt
- cash shift
- local Wi-Fi continuity
- printing
- operational reports

## Excluded scope

- pickup
- delivery
- loyalty
- CRM
- purchasing
- inventory
- accounting
- HR/workforce
- operational recipes
- costing
- intelligence
- supplier/Horeca runtime
- Phase 2 data portability product

## Repository boundary

- **Package M0:** documents only
- **M0R:** empty repository, docs, plans, CI/scanner design; no database/schema/executable migration/application code
- **M1:** create PostgreSQL database and executable migration 0001 after M0R approval/adjudication

## M5a ownership

**Requirements:** FR-CFG-001E, FR-DAT-008C, FR-EDG-001, FR-EDG-002A, FR-EDG-004A, FR-EDG-005, FR-EDG-008, FR-EDG-009, FR-EDG-010, FR-EDG-012, FR-EDG-015A, FR-EDG-016, FR-EDG-017, FR-EDG-018, FR-EDG-025, FR-EDG-027, FR-EDG-029, FR-INT-003, FR-INT-004, FR-OPS-010, FR-OPS-018, FR-POS-008, FR-SEC-002B, FR-TST-008

**Journeys:** GJ-10

**Services:** outlet_api, outlet_postgresql, sync_worker, realtime_gateway, print_agent

**Forbidden Claims:** same_qr_public_hostname, browser_public_tls, cloud_forwarding_lease, emergency_authority_replacement

**Exact service boundary:** exactly five services; `local_backup_agent` is excluded. Backup scheduling and destructive restore remain M6 obligations.

## M5b ownership

**Requirements:** FR-EDG-003, FR-EDG-004B, FR-EDG-015B, FR-EDG-021, FR-EDG-022A, FR-EDG-022B, FR-EDG-022C, FR-EDG-023, FR-EDG-024, FR-EDG-026, FR-EDG-028, FR-OPS-017

**Journeys:** GJ-08, GJ-09

**Services:** public_dns, outlet_split_horizon_dns, dns01_certificate_service, authority_control_plane, reachability_challenge_service, fence_evidence_service

**Forbidden Claims:** replacement_writable_without_fence, one_way_heartbeat_as_healthy, self_signed_browser_bypass, shared_cross_outlet_private_key, writable_cloud_fallback
