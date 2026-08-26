# Mandatory Golden Journeys

**16 slices**

- Package: `Hospitality_OS_Phase_1_Clean_Build_Package_v2.0.9`
- Canonical source root: `cd6b8cfc2175004cc2057deb7d9de1ad0d6264a23c82f00e15e96faa526c0c96`
- Status: **Package M0 candidate - M0R and implementation are not authorized**

## GJ-01A - English guest QR dine-in order through service

**Milestone:** M3  
**Mandatory:** Yes  
**Predecessors:** M2 approved  
**Personas:** Guest customer, waiter, kitchen

**Steps:** Scan opaque table QR; open English; continue as guest; browse menu; select modifiers; submit order; the current approved cloud authority persists and no local-authority claim is made before M5b; kitchen accepts and prepares; waiter serves; customer sees served status.

**Pass:** One table session, one accepted order, linked fulfillment and service timeline exist with no duplicate effect and correct English customer text. The cloud remains the current approved authority at M3. No check, payment, receipt or local-authority capability is required.

## GJ-01B - English bill, cash settlement and receipt

**Milestone:** M4  
**Mandatory:** Yes  
**Predecessors:** GJ-01A  
**Personas:** Guest customer, cashier

**Steps:** Open the served English table session from GJ-01A; customer requests bill; cashier presents check; customer leaves no tip; cashier settles cash; issue the English digital receipt and print the English physical receipt through the minimum M4 production printer path.

**Pass:** Check, cash payment, no-tip decision, digital receipt, one physical receipt and audit timeline are linked to the predecessor order; bill, tip and total paid are shown separately; the physical receipt is printed without relying on M5a outage resilience.

## GJ-02 - Amharic customer order and service

**Milestone:** M3  
**Mandatory:** Yes  
**Predecessors:** M2 approved  
**Personas:** Guest customer, waiter, kitchen

**Steps:** Select Amharic; browse approved menu and allergen text; place order; receive localized statuses; call waiter; add another order; waiter serves.

**Pass:** Customer-facing text and snapshots are Amharic; staff screens remain English; cart/session/order identity is preserved; no M4 settlement dependency exists; settlement is proven by GJ-02B at M4.

## GJ-02B - Amharic bill, tip, settlement and receipt

**Milestone:** M4  
**Mandatory:** Yes  
**Predecessors:** GJ-02  
**Personas:** Guest customer, cashier

**Steps:** Open the served Amharic table session from GJ-02; customer requests the bill; present the Amharic check with the separate optional tip box; customer adds a tip; settle by verified Telebirr proof confirmation; issue the Amharic digital receipt and print the Amharic physical receipt through the minimum M4 production printer path.

**Pass:** Bill, tip and total paid are separate values and separate visual sections in Amharic; ETB and numerals follow the approved locale policy; packaged Ethiopic fonts render on screen and on the printed receipt with no fallback loss or clipping; the receipt states the actual method, provider and permitted masked/reference identifier; the payment remains proof_pending until staff verify it in the provider app. The M4 print proves a real physical receipt but does not claim M5a durable queue or outage resilience.

## GJ-03A - Arabic RTL menu, order and service

**Milestone:** M3  
**Mandatory:** Yes  
**Predecessors:** M2 approved  
**Personas:** Guest customer, waiter, kitchen

**Steps:** Select Arabic; browse true RTL menu; use search/modifiers containing Latin SKUs or item codes; view ETB prices/numerals; submit order; view Arabic status timeline; waiter serves.

**Pass:** Customer PWA mirrors correctly; mixed-direction strings preserve reading order; ETB and numerals follow approved locale policy; no bill or receipt capability is required.

## GJ-03B - Arabic RTL bill, tip, payment and receipt

**Milestone:** M4  
**Mandatory:** Yes  
**Predecessors:** GJ-03A  
**Personas:** Guest customer, cashier

**Steps:** Open the served Arabic session from GJ-03A; request bill; view separate optional tip box; choose a tip; settle using a permitted live method; view the digital Arabic receipt and print the physical Arabic receipt through the minimum M4 production printer path.

**Pass:** Bill/tip/payment/receipt layout mirrors correctly; mixed Arabic/Latin provider/reference text, ETB values and numerals preserve reading order; no clipping or string-substitution-only pass is accepted. The physical receipt is real M4 output; durable local print recovery is reserved for M5a.

## GJ-04 - Multi-participant table and service requests

**Milestone:** M3  
**Mandatory:** Yes  
**Predecessors:** M2 approved  
**Personas:** Two guest customers, waiter

**Steps:** Two devices join one table; keep personal carts; place separate orders; call waiter; waiter acknowledges; one guest adds an order later; authorized staff move the session to another table.

**Pass:** Participant ownership, service SLA, add-on orders and table move are preserved without exposing another table or duplicating orders.

## GJ-05 - Waiter-entered order to KDS and service

**Milestone:** M3  
**Mandatory:** Yes  
**Predecessors:** M2 approved  
**Personas:** Waiter, kitchen/bar, expo, manager

**Steps:** Waiter opens table; enters dine-in order; routes lines to kitchen/bar; stations acknowledge; allergy is emphasized; expo marks ready; waiter confirms served; manager handles one authorized amendment.

**Pass:** Order, tickets and customer-facing statuses remain separate and consistent; unauthorized state jumps fail; no M4 check or settlement dependency exists.

## GJ-06 - Split bill with separate tips

**Milestone:** M4  
**Mandatory:** Yes  
**Predecessors:** At least one M3 served order  
**Personas:** Two payers, cashier

**Steps:** Split check by item; payer A pays cash and chooses no tip; payer B pays external card terminal and adds a custom tip; print one physical receipt for each payer through the minimum M4 production printer path.

**Pass:** Bill allocations equal bill total; each payment has independent bill and tip allocations; receipt shows bill, tip and total paid separately; no tip is selected by default. Each physical receipt is produced exactly once.

## GJ-07 - Void, refund and tip correction controls

**Milestone:** M4  
**Mandatory:** Yes  
**Predecessors:** GJ-06  
**Personas:** Cashier, manager

**Steps:** Attempt cashier self-approval and fail; manager performs purpose-specific step-up; reverse one payment allocation; partially refund bill and tip separately; reconcile the final receipt and print the corrected physical receipt with reprint/correction audit.

**Pass:** Maker-checker, exact independent bill/tip corrections, reason codes, one-time approval and append-only audit evidence are preserved. The corrected physical receipt is marked and auditable.

## GJ-08 - Same QR customer service during internet outage

**Milestone:** M5b  
**Mandatory:** Yes  
**Predecessors:** M5a approved  
**Personas:** Guest customer, waiter, kitchen, cashier

**Steps:** Use a real per-outlet public hostname and valid public-CA certificate; disconnect internet; connect customer to restaurant Wi-Fi; scan the same QR; browse cached menu; order; call waiter; prepare/serve; request bill; settle using an available local live method; print receipt; repeat the same-QR entry on a device that joined outlet Wi-Fi holding a cached public DNS answer, on a device with encrypted DNS (Private DNS/DoH) enabled, and on a dual-stack IPv4/IPv6 device.

**Pass:** Browser shows no certificate warning; local service completes without cloud; IDs and evidence persist for later synchronization; cloud-side new writes are blocked after lease expiry; cached-answer, encrypted-DNS and dual-stack devices either resolve to the trusted local endpoint or fail safe to translated staff guidance, never to a certificate warning or a manual bypass prompt; the served certificate fingerprint and expiry are verified from the LAN.

## GJ-09 - Asymmetric partition and emergency authority replacement

**Milestone:** M5b  
**Mandatory:** Yes  
**Predecessors:** M5a approved  
**Personas:** Outlet operator, platform operator, guest customer

**Steps:** Cut cloud-to-node and node-to-cloud paths independently; verify challenge/ack failures and 5/10/20 timing; keep LAN node serving; request replacement; record independent approval; power off or network-isolate old node; run LAN-unreachability probe; issue next monotonic signed authority sequence; activate replacement; attempt direct LAN write to old node; reconnect stale node.

**Pass:** Cloud forwarding expires safely while LAN authority continues; replacement is not writable before fence evidence; direct old-node LAN write fails; every writer rejects rollback; stale events quarantine; recovery requires three valid bidirectional proofs.

## GJ-10 - Outlet node durability, synchronization and printing

**Milestone:** M5a  
**Mandatory:** Yes  
**Predecessors:** M4 approved  
**Personas:** Waiter, kitchen, cashier, outlet operator

**Steps:** Use staff/POS/KDS endpoints directly on the outlet network; create local session/order/check/payment/tip and print jobs; restart browser, API, worker and node database; replay outbox/inbox with parent-before-child ordering; inject one conflict; reconnect to cloud. Queue a customer receipt, lose internet, restart the local print service, recover the queue, print exactly once, reconnect and reconcile the print-job status.

**Pass:** Local records and queues survive restart; print retries do not create unmarked duplicates; sync is idempotent and dependency ordered; conflict is visible; no same-QR public hostname, browser TLS or authority replacement claim is required. Receipt printing survives outage and restart through the M5a durable local queue with no lost or duplicate physical output.

## GJ-11 - Backup and destructive restore

**Milestone:** M6  
**Mandatory:** Yes  
**Predecessors:** M5b approved  
**Personas:** Platform operator, outlet operator

**Steps:** Create cloud and outlet backups from built non-root images using production roles; destroy disposable environments; restore database, configuration, queues, certificates and print evidence; start exact production services.

**Pass:** Post-restore M3/M4/M5a business slices pass; tenant/outlet isolation, audit, synchronization and recovery time are evidenced; missing grant/script/client makes the drill fail.

## GJ-12 - Clean deployment and production-role readiness

**Milestone:** M6  
**Mandatory:** Yes  
**Predecessors:** M5b approved  
**Personas:** Platform operator, support operator

**Steps:** Delete generated output and databases; execute ordinary Windows and Linux commands; build production images; start API, workers, outlet node and print agent using least-privileged roles; inspect routes, jobs, users and health.

**Pass:** All discovered tests run with zero skips; images are non-root and complete; readiness is truthful; no deferred route/table/worker exists; command order does not alter artifacts.

## GJ-13 - Second-tenant commercial isolation

**Milestone:** M6  
**Mandatory:** Yes  
**Predecessors:** M5b approved  
**Personas:** Two tenant administrators, platform support

**Steps:** Configure two differently branded tenants with sibling outlets, menus, staff, tables, devices and reports; attempt cross-tenant/outlet reads and writes; use time-bound support access; export permitted Phase 1 operational evidence only.

**Pass:** Branding/configuration are independent; production-role isolation blocks every unauthorized CRUD path; support access is time-bound and audited; no Phase 2 portability product is activated.
