# Phase 1 Product Definition

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## Product purpose

Hospitality OS is a configurable multi-tenant operating system for restaurants, cafés, bakeries, bars, food courts, hotel outlets and related hospitality operators. Phase 1 covers the complete dine-in customer-service journey from QR discovery through ordering, kitchen execution, billing, payment, tip and receipt, including controlled outlet continuity.

## Personas

- Guest customer
- Waiter and supervisor
- Kitchen, bar and expo staff
- Cashier and manager
- Tenant, legal-entity and outlet administrator
- Platform operations and security staff

## Phase 1 capabilities

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

## Explicit exclusions

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

## Customer-language contract

English, Amharic and Arabic are complete customer launch languages. Staff applications launch in English on a translation-ready architecture. Browser language is a suggestion; the customer chooses the session language.

## Payment and tip contract

Tips are separate from the bill and from bill allocation. No percentage or amount is selected by default. A payer may add a tip independently, and a tip cannot hide an unpaid bill balance.

## Continuity promise and boundary

The same QR can resolve to the cloud or the outlet node under supported system-resolver conditions. Unsupported strict custom encrypted resolvers receive translated captive-portal/signage/staff guidance. No self-signed certificate, browser bypass or writable cloud fallback is permitted.
