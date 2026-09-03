# Schema and Domain Catalog

**Generated from the live database by `tools/generate_schema_catalog.py`.**
Do not edit by hand: the verification suite regenerates this file and fails on any
difference, so a hand edit is reported as drift (FR-DAT-015).

Schemas covered: `app`, `audit`, `billing`, `cash`, `config`, `docs`, `fiscal`, `fulfillment`, `identity`, `integration`, `menu`, `money`, `notify`, `ordering`, `org`, `payments`, `pos`, `safety`, `service`, discovered from the database rather than listed here.

---

## Domains

| Domain | Base type | Purpose |
|---|---|---|
| `money.amount_minor` | `bigint` | A monetary amount in integer minor units of an explicit currency (for ETB, cents). Never a float, never a bare decimal. Any column of this type must sit beside a currency_code column; money.assert_currency_paired() proves it. |
| `money.percentage` | `numeric(7,4)` |  |
| `money.quantity` | `numeric(14,4)` |  |

## Enumerated types

| Type | Values |
|---|---|
| `billing.bill_event_kind` | issued, component_calculated, disposition_recorded, finalized, voided, credited, reissued |
| `billing.bill_state` | issued, finalized, voided, credited, reissued |
| `billing.check_state` | open, billed, merged, void |
| `billing.disposition_kind` | comped, written_off, transferred |
| `billing.split_mode` | by_item, by_participant, equal_share, custom_amount, separate_orders |
| `billing.tip_correction_kind` | reversal, refund, correction |
| `cash.count_phase` | opening, closing, recount |
| `cash.custody_destination` | safe, bank |
| `cash.exception_kind` | missing_close, excessive_cash_difference, unusual_refund, unusual_payout, late_settlement, reopened_not_resolved |
| `cash.movement_kind` | sales_receipt, refund, payout, drop, float_adjustment, transfer_in, transfer_out |
| `cash.shift_state` | open, submitted, verified, finalized, reopened, resolved |
| `config.configuration_category` | branding, locale, currency, timezone, tax, calendar, numbering, payment_method, service, feature, connector |
| `config.policy_category` | ordering, service, cancellation, discount, refund, tip, cash, approval, local_continuity |
| `config.reason_code_category` | order_cancellation, void, refund, discount, complimentary_item, payment_reversal, tip_correction, service_failure, printer_failure, manager_override |
| `config.retention_action` | archive, purge, anonymize |
| `config.scope_kind` | tenant, legal_entity, outlet |
| `docs.connection_kind` | character_device, network_socket, file |
| `docs.document_kind` | receipt, kitchen_ticket, label, operational |
| `docs.print_outcome` | printed, failed |
| `docs.receipt_line_kind` | bill_component, bill_total, tip, total_paid, payment_method |
| `docs.render_outcome` | rendered, failed |
| `docs.sink_kind` | device, preview |
| `fiscal.adapter_mode` | live, simulated |
| `fiscal.document_state` | requested, submitted, accepted, rejected, reconciled |
| `fulfillment.document_trigger` | kds_unavailable, policy_requires_paper |
| `fulfillment.priority_level` | ordinary, rush, service_access |
| `fulfillment.serve_exception` | missing_item, wrong_item |
| `fulfillment.station_kind` | kitchen, bar, coffee, bakery, dessert, expo |
| `fulfillment.ticket_event_kind` | released, transitioned, reprioritised, transferred, recalled, unit_progress, acknowledged_allergy, document_generated, served, waste, amended |
| `fulfillment.ticket_state` | queued, acknowledged, held, preparing, partially_completed, ready, collected, completed, rework, cancelled, exception |
| `fulfillment.waste_kind` | rework, remake, service_waste |
| `identity.auth_strength` | low, standard, strong |
| `identity.channel_kind` | phone, email |
| `identity.credential_kind` | password, otp, quick_pin, service_secret |
| `identity.principal_class` | worker, integration, edge_node, print_agent |
| `identity.revocation_reason` | signed_out, expired, membership_withdrawn, security_event, rotated, administrator_revoked, recovery |
| `identity.transmission_mode` | simulated, live |
| `integration.dead_letter_state` | open, replayed, abandoned |
| `integration.job_kind` | notification_notice |
| `menu.availability_state` | available, limited, temporarily_unavailable, scheduled_later, hidden |
| `menu.customer_locale` | en, am, ar |
| `menu.image_format` | webp, avif, jpeg, png |
| `menu.menu_entity` | menu, category, item_group, item, variant, modifier_group, modifier, image, allergen, dietary_claim, service_request_type, notification_template, order_status_wording, bill_component_wording, receipt_line_wording |
| `menu.publication_state` | draft, review, scheduled, published, paused, archived |
| `menu.sales_channel` | dine_in, counter, room_service, kiosk |
| `menu.translation_provenance` | human, machine_assisted |
| `menu.translation_state` | draft, in_review, approved, rejected |
| `menu.variant_axis` | size, portion, temperature, preparation_style |
| `money.rounding_mode` | half_up, half_even, floor, ceiling |
| `notify.audience` | customer, staff |
| `notify.event_class` | order, kitchen, service_request, bill, payment, tip, outage, sync |
| `notify.failure_reason` | recipient_not_authorized, recipient_out_of_scope, template_missing |
| `notify.notice_state` | pending, sent, read, failed, dead_lettered |
| `ordering.acceptance_mode` | automatic, staff_confirmed, payment_dependent |
| `ordering.actor_kind` | guest, staff, system |
| `ordering.artifact_kind` | request, cart, table_session, order, fulfillment_ticket, service_request, check, bill, payment, tip, receipt |
| `ordering.charge_kind` | item_subtotal, discount, tax, fee |
| `ordering.charge_source_kind` | menu_price, tax_configuration, discount_policy, service_configuration |
| `ordering.event_kind` | submitted, accepted, rejected, amended, cancelled, voided, note_added, allergy_declared, session_merged, session_moved, tickets_released, station_acknowledged, station_preparing, station_ready, items_collected, items_served, station_exception |
| `ordering.note_kind` | customer, allergy_declaration, kitchen_instruction, private_staff |
| `ordering.order_origin` | guest_qr, waiter_entered, counter |
| `ordering.order_state` | submitted, accepted, rejected, cancelled, voided |
| `org.lifecycle_status` | active, inactive, archived |
| `org.node_kind` | brand, legal_entity, outlet, service_area, preparation_station, dining_table, device |
| `org.record_concern` | menu, orders, billing, payments, cash, fiscal_documents, identity |
| `payments.adapter_mode` | live, simulated |
| `payments.allocation_target` | bill_balance, tip |
| `payments.live_outcome` | approved, declined |
| `payments.payment_event_kind` | captured, reversed |
| `payments.payment_state` | captured, reversed |
| `payments.proof_state` | pending, verified, rejected |
| `payments.provider` | cash, external_terminal, telebirr_proof, cbe_birr_proof, telebirr_direct, cbe_birr_direct |
| `payments.reversal_kind` | refund, reversal, correction |
| `payments.simulated_outcome` | approved, declined |
| `pos.consequence` | routine, elevated, deliberate |
| `pos.handover_item_kind` | table_session, service_request |
| `pos.handover_state` | proposed, acknowledged, cancelled |
| `pos.terminal_profile` | point_of_sale, waiter_handheld, kitchen_display |
| `safety.declaration_class` | contains, may_contain, cross_contact |
| `safety.reference_context` | publication_snapshot, cart_line |
| `safety.review_state` | draft, in_review, approved |
| `service.cart_kind` | personal, shared |
| `service.cart_state` | open, abandoned, expired |
| `service.completion_status` | done, partially_done, not_possible |
| `service.concern_source` | guest, waiter |
| `service.occupancy_state` | open, closed |
| `service.opening_source` | qr_scan, staff, host_stand |
| `service.presence_state` | available, temporarily_unavailable, offline |
| `service.request_event_kind` | raised, routed, acknowledged, started, completed, cancelled, expired, escalated, unresolved, reassigned, session_changed |
| `service.request_origin` | guest, staff |
| `service.request_state` | new, routed, acknowledged, in_progress, completed, cancelled, expired, escalated, unresolved |
| `service.transfer_state` | proposed, acknowledged, supervisor_reassigned, declined |
| `service.verification_method` | staff_confirmation, table_code, host_approval |

## Relationships

Foreign-key edges between tables, read from `pg_constraint`.

```mermaid
graph LR
  audit_operational_event["audit.operational_event"]
  org_org_node["org.org_node"]
  org_tenant["org.tenant"]
  audit_security_event["audit.security_event"]
  billing_bill["billing.bill"]
  billing_check["billing.check"]
  billing_bill_component["billing.bill_component"]
  billing_bill_disposition["billing.bill_disposition"]
  config_reason_code["config.reason_code"]
  identity_user_account["identity.user_account"]
  pos_override_approval["pos.override_approval"]
  billing_bill_event["billing.bill_event"]
  service_table_session["service.table_session"]
  billing_check_allocation["billing.check_allocation"]
  billing_component_wording["billing.component_wording"]
  billing_service_charge_setting["billing.service_charge_setting"]
  config_configuration_version["config.configuration_version"]
  billing_tip["billing.tip"]
  billing_bill_share["billing.bill_share"]
  billing_tip_correction["billing.tip_correction"]
  billing_tip_setting["billing.tip_setting"]
  billing_tip_suggestion["billing.tip_suggestion"]
  cash_custody_transfer["cash.custody_transfer"]
  cash_movement["cash.movement"]
  cash_shift["cash.shift"]
  cash_denomination_tally["cash.denomination_tally"]
  cash_drawer_count["cash.drawer_count"]
  identity_session["identity.session"]
  pos_terminal["pos.terminal"]
  cash_shift_transition["cash.shift_transition"]
  config_entitlement["config.entitlement"]
  config_issued_document_number["config.issued_document_number"]
  config_number_series["config.number_series"]
  config_policy["config.policy"]
  identity_governed_action["identity.governed_action"]
  config_reason_code_label["config.reason_code_label"]
  config_retention_policy["config.retention_policy"]
  docs_line_wording["docs.line_wording"]
  docs_print_attempt["docs.print_attempt"]
  docs_printer["docs.printer"]
  docs_receipt["docs.receipt"]
  docs_printer_test["docs.printer_test"]
  money_currency["money.currency"]
  docs_receipt_line["docs.receipt_line"]
  docs_render_attempt["docs.render_attempt"]
  fiscal_adapter["fiscal.adapter"]
  fiscal_document["fiscal.document"]
  fulfillment_priority_change["fulfillment.priority_change"]
  fulfillment_ticket["fulfillment.ticket"]
  fulfillment_ready_notice["fulfillment.ready_notice"]
  fulfillment_routing_rule["fulfillment.routing_rule"]
  fulfillment_routing_rule_set["fulfillment.routing_rule_set"]
  fulfillment_station_profile["fulfillment.station_profile"]
  menu_category["menu.category"]
  menu_item_variant["menu.item_variant"]
  menu_sellable_item["menu.sellable_item"]
  fulfillment_serve_record["fulfillment.serve_record"]
  fulfillment_station_ticket_document["fulfillment.station_ticket_document"]
  fulfillment_station_transfer["fulfillment.station_transfer"]
  ordering_customer_order["ordering.customer_order"]
  fulfillment_ticket_event["fulfillment.ticket_event"]
  fulfillment_ticket_line["fulfillment.ticket_line"]
  ordering_order_line["ordering.order_line"]
  fulfillment_ticket_recall["fulfillment.ticket_recall"]
  fulfillment_waste_event["fulfillment.waste_event"]
  identity_auth_attempt["identity.auth_attempt"]
  identity_auth_lockout["identity.auth_lockout"]
  identity_auth_provider_binding["identity.auth_provider_binding"]
  identity_credential["identity.credential"]
  identity_identity_channel["identity.identity_channel"]
  identity_membership["identity.membership"]
  identity_role["identity.role"]
  identity_otp_transmission["identity.otp_transmission"]
  identity_recovery_request["identity.recovery_request"]
  identity_role_action["identity.role_action"]
  identity_service_principal["identity.service_principal"]
  identity_service_principal_scope["identity.service_principal_scope"]
  identity_step_up_grant["identity.step_up_grant"]
  identity_terminal_trust["identity.terminal_trust"]
  integration_dead_letter["integration.dead_letter"]
  menu_assignment["menu.assignment"]
  menu_daypart["menu.daypart"]
  menu_menu["menu.menu"]
  menu_availability["menu.availability"]
  menu_modifier["menu.modifier"]
  menu_availability_pause["menu.availability_pause"]
  menu_image["menu.image"]
  menu_image_derivative["menu.image_derivative"]
  menu_item_group["menu.item_group"]
  menu_item_group_member["menu.item_group_member"]
  menu_item_modifier_group["menu.item_modifier_group"]
  menu_modifier_group["menu.modifier_group"]
  menu_modifier_incompatibility["menu.modifier_incompatibility"]
  menu_price["menu.price"]
  menu_publication_snapshot["menu.publication_snapshot"]
  menu_publication_snapshot_line["menu.publication_snapshot_line"]
  menu_translation["menu.translation"]
  menu_translatable_field["menu.translatable_field"]
  notify_deep_link["notify.deep_link"]
  notify_notice["notify.notice"]
  notify_notification["notify.notification"]
  service_guest_session["service.guest_session"]
  notify_catalog_event["notify.catalog_event"]
  notify_status_wording["notify.status_wording"]
  notify_template["notify.template"]
  ordering_charge_rule["ordering.charge_rule"]
  ordering_correlation_link["ordering.correlation_link"]
  service_cart["service.cart"]
  ordering_duplicate_signal["ordering.duplicate_signal"]
  ordering_order_charge_component["ordering.order_charge_component"]
  ordering_order_event["ordering.order_event"]
  ordering_order_line_modifier["ordering.order_line_modifier"]
  ordering_order_note["ordering.order_note"]
  safety_allergen["safety.allergen"]
  safety_allergy_concern["safety.allergy_concern"]
  safety_approved_wording["safety.approved_wording"]
  ordering_order_timeline_entry["ordering.order_timeline_entry"]
  org_device_registration["org.device_registration"]
  org_org_closure["org.org_closure"]
  org_outlet_profile["org.outlet_profile"]
  org_system_of_record["org.system_of_record"]
  payments_allocation["payments.allocation"]
  payments_payment["payments.payment"]
  payments_payment_adapter["payments.payment_adapter"]
  payments_payment_intent["payments.payment_intent"]
  payments_proof_confirmation["payments.proof_confirmation"]
  payments_terminal_result["payments.terminal_result"]
  payments_payment_event["payments.payment_event"]
  payments_reversal["payments.reversal"]
  payments_simulated_attempt["payments.simulated_attempt"]
  pos_confirmation_requirement["pos.confirmation_requirement"]
  pos_fast_pick["pos.fast_pick"]
  pos_handover["pos.handover"]
  pos_handover_item["pos.handover_item"]
  safety_jurisdiction["safety.jurisdiction"]
  safety_declaration["safety.declaration"]
  safety_declaration_reference["safety.declaration_reference"]
  safety_dietary_claim["safety.dietary_claim"]
  safety_dietary_claim_outlet["safety.dietary_claim_outlet"]
  safety_item_dietary_claim["safety.item_dietary_claim"]
  safety_jurisdiction_requirement["safety.jurisdiction_requirement"]
  service_cart_line["service.cart_line"]
  service_cart_line_modifier["service.cart_line_modifier"]
  service_cart_line_transfer["service.cart_line_transfer"]
  service_idempotency_key["service.idempotency_key"]
  service_ownership_transfer["service.ownership_transfer"]
  service_qr_placard["service.qr_placard"]
  service_table_qr_token["service.table_qr_token"]
  service_qr_scan["service.qr_scan"]
  service_request_escalation["service.request_escalation"]
  service_service_request["service.service_request"]
  service_request_routing_decision["service.request_routing_decision"]
  service_request_type["service.request_type"]
  service_service_request_event["service.service_request_event"]
  service_session_closure_exception["service.session_closure_exception"]
  service_session_merge["service.session_merge"]
  service_session_move["service.session_move"]
  service_table_profile["service.table_profile"]
  service_session_participant["service.session_participant"]
  service_staff_presence["service.staff_presence"]
  service_table_ownership["service.table_ownership"]
  service_verification_policy["service.verification_policy"]
  audit_operational_event --> org_org_node
  audit_operational_event --> org_tenant
  audit_security_event --> org_org_node
  audit_security_event --> org_tenant
  billing_bill --> billing_bill
  billing_bill --> billing_check
  billing_bill --> org_org_node
  billing_bill --> org_tenant
  billing_bill_component --> billing_bill
  billing_bill_disposition --> billing_check
  billing_bill_disposition --> config_reason_code
  billing_bill_disposition --> identity_user_account
  billing_bill_disposition --> pos_override_approval
  billing_bill_event --> config_reason_code
  billing_bill_event --> identity_user_account
  billing_bill_event --> org_org_node
  billing_bill_event --> org_tenant
  billing_check --> billing_check
  billing_check --> identity_user_account
  billing_check --> org_org_node
  billing_check --> org_tenant
  billing_check --> service_table_session
  billing_check_allocation --> billing_check
  billing_component_wording --> org_org_node
  billing_component_wording --> org_tenant
  billing_service_charge_setting --> config_configuration_version
  billing_service_charge_setting --> org_org_node
  billing_tip --> billing_bill_share
  billing_tip_correction --> billing_tip
  billing_tip_correction --> config_reason_code
  billing_tip_correction --> identity_user_account
  billing_tip_correction --> pos_override_approval
  billing_tip_setting --> org_org_node
  billing_tip_suggestion --> billing_tip_setting
  cash_custody_transfer --> cash_movement
  cash_custody_transfer --> cash_shift
  cash_custody_transfer --> identity_user_account
  cash_custody_transfer --> org_org_node
  cash_custody_transfer --> org_tenant
  cash_denomination_tally --> cash_drawer_count
  cash_denomination_tally --> org_org_node
  cash_denomination_tally --> org_tenant
  cash_drawer_count --> cash_shift
  cash_drawer_count --> identity_user_account
  cash_drawer_count --> org_org_node
  cash_drawer_count --> org_tenant
  cash_movement --> cash_shift
  cash_movement --> identity_user_account
  cash_movement --> org_org_node
  cash_movement --> org_tenant
  cash_shift --> config_reason_code
  cash_shift --> identity_session
  cash_shift --> identity_user_account
  cash_shift --> org_org_node
  cash_shift --> org_tenant
  cash_shift --> pos_override_approval
  cash_shift --> pos_terminal
  cash_shift_transition --> cash_shift
  cash_shift_transition --> config_reason_code
  cash_shift_transition --> identity_user_account
  cash_shift_transition --> org_tenant
  cash_shift_transition --> pos_override_approval
  config_configuration_version --> identity_user_account
  config_configuration_version --> org_org_node
  config_configuration_version --> org_tenant
  config_entitlement --> org_org_node
  config_entitlement --> org_tenant
  config_issued_document_number --> org_tenant
  config_number_series --> org_org_node
  config_number_series --> org_tenant
  config_policy --> identity_governed_action
  config_policy --> identity_user_account
  config_policy --> org_org_node
  config_policy --> org_tenant
  config_reason_code --> org_tenant
  config_reason_code_label --> config_reason_code
  config_retention_policy --> org_org_node
  config_retention_policy --> org_tenant
  docs_line_wording --> org_tenant
  docs_print_attempt --> config_reason_code
  docs_print_attempt --> docs_printer
  docs_print_attempt --> docs_receipt
  docs_print_attempt --> identity_user_account
  docs_print_attempt --> org_org_node
  docs_print_attempt --> org_tenant
  docs_printer --> identity_user_account
  docs_printer --> org_org_node
  docs_printer --> org_tenant
  docs_printer_test --> docs_printer
  docs_printer_test --> identity_user_account
  docs_printer_test --> org_org_node
  docs_printer_test --> org_tenant
  docs_receipt --> identity_user_account
  docs_receipt --> money_currency
  docs_receipt --> org_org_node
  docs_receipt --> org_tenant
  docs_receipt_line --> docs_receipt
  docs_receipt_line --> org_tenant
  docs_render_attempt --> docs_printer
  docs_render_attempt --> docs_receipt
  docs_render_attempt --> identity_user_account
  docs_render_attempt --> org_org_node
  docs_render_attempt --> org_tenant
  fiscal_adapter --> identity_user_account
  fiscal_adapter --> org_tenant
  fiscal_document --> docs_receipt
  fiscal_document --> fiscal_adapter
  fiscal_document --> org_org_node
  fiscal_document --> org_tenant
  fulfillment_priority_change --> config_reason_code
  fulfillment_priority_change --> fulfillment_ticket
  fulfillment_priority_change --> identity_user_account
  fulfillment_priority_change --> org_org_node
  fulfillment_priority_change --> org_tenant
  fulfillment_ready_notice --> fulfillment_ticket
  fulfillment_ready_notice --> identity_user_account
  fulfillment_ready_notice --> org_org_node
  fulfillment_ready_notice --> org_tenant
  fulfillment_routing_rule --> fulfillment_routing_rule_set
  fulfillment_routing_rule --> fulfillment_station_profile
  fulfillment_routing_rule --> menu_category
  fulfillment_routing_rule --> menu_item_variant
  fulfillment_routing_rule --> menu_sellable_item
  fulfillment_routing_rule --> org_org_node
  fulfillment_routing_rule --> org_tenant
  fulfillment_routing_rule_set --> identity_user_account
  fulfillment_routing_rule_set --> org_org_node
  fulfillment_routing_rule_set --> org_tenant
  fulfillment_serve_record --> fulfillment_ticket
  fulfillment_serve_record --> identity_user_account
  fulfillment_serve_record --> org_org_node
  fulfillment_serve_record --> org_tenant
  fulfillment_station_profile --> org_org_node
  fulfillment_station_profile --> org_tenant
  fulfillment_station_ticket_document --> fulfillment_ticket
  fulfillment_station_ticket_document --> org_org_node
  fulfillment_station_ticket_document --> org_tenant
  fulfillment_station_transfer --> config_reason_code
  fulfillment_station_transfer --> fulfillment_station_profile
  fulfillment_station_transfer --> fulfillment_ticket
  fulfillment_station_transfer --> identity_user_account
  fulfillment_station_transfer --> org_org_node
  fulfillment_station_transfer --> org_tenant
  fulfillment_ticket --> fulfillment_routing_rule_set
  fulfillment_ticket --> fulfillment_station_profile
  fulfillment_ticket --> identity_user_account
  fulfillment_ticket --> ordering_customer_order
  fulfillment_ticket --> org_org_node
  fulfillment_ticket --> org_tenant
  fulfillment_ticket_event --> config_reason_code
  fulfillment_ticket_event --> identity_user_account
  fulfillment_ticket_event --> org_org_node
  fulfillment_ticket_event --> org_tenant
  fulfillment_ticket_line --> fulfillment_ticket
  fulfillment_ticket_line --> ordering_order_line
  fulfillment_ticket_line --> org_org_node
  fulfillment_ticket_line --> org_tenant
  fulfillment_ticket_recall --> config_reason_code
  fulfillment_ticket_recall --> fulfillment_ticket
  fulfillment_ticket_recall --> identity_user_account
  fulfillment_ticket_recall --> org_org_node
  fulfillment_ticket_recall --> org_tenant
  fulfillment_waste_event --> config_reason_code
  fulfillment_waste_event --> fulfillment_ticket
  fulfillment_waste_event --> identity_user_account
  fulfillment_waste_event --> ordering_customer_order
  fulfillment_waste_event --> org_org_node
  fulfillment_waste_event --> org_tenant
  identity_auth_attempt --> org_org_node
  identity_auth_attempt --> org_tenant
  identity_auth_lockout --> org_tenant
  identity_auth_provider_binding --> identity_user_account
  identity_credential --> identity_user_account
  identity_credential --> org_org_node
  identity_governed_action --> org_tenant
  identity_identity_channel --> identity_user_account
  identity_membership --> identity_role
  identity_membership --> identity_user_account
  identity_membership --> org_org_node
  identity_otp_transmission --> identity_identity_channel
  identity_otp_transmission --> org_tenant
  identity_recovery_request --> identity_user_account
  identity_recovery_request --> org_org_node
  identity_role --> org_tenant
  identity_role_action --> identity_role
  identity_service_principal --> org_tenant
  identity_service_principal_scope --> identity_service_principal
  identity_service_principal_scope --> org_org_node
  identity_session --> identity_user_account
  identity_session --> org_org_node
  identity_step_up_grant --> identity_session
  identity_step_up_grant --> org_org_node
  identity_terminal_trust --> org_org_node
  identity_user_account --> org_tenant
  integration_dead_letter --> identity_user_account
  integration_dead_letter --> org_org_node
  integration_dead_letter --> org_tenant
  menu_assignment --> menu_daypart
  menu_assignment --> menu_menu
  menu_assignment --> org_org_node
  menu_assignment --> org_tenant
  menu_availability --> menu_item_variant
  menu_availability --> menu_modifier
  menu_availability --> menu_sellable_item
  menu_availability --> org_org_node
  menu_availability --> org_tenant
  menu_availability_pause --> config_reason_code
  menu_availability_pause --> identity_user_account
  menu_availability_pause --> menu_availability
  menu_availability_pause --> org_org_node
  menu_availability_pause --> org_tenant
  menu_category --> menu_category
  menu_category --> menu_menu
  menu_category --> org_org_node
  menu_category --> org_tenant
  menu_daypart --> org_org_node
  menu_daypart --> org_tenant
  menu_image --> org_org_node
  menu_image --> org_tenant
  menu_image_derivative --> menu_image
  menu_image_derivative --> org_org_node
  menu_image_derivative --> org_tenant
  menu_item_group --> menu_menu
  menu_item_group --> org_org_node
  menu_item_group --> org_tenant
  menu_item_group_member --> menu_item_group
  menu_item_group_member --> menu_sellable_item
  menu_item_group_member --> org_tenant
  menu_item_modifier_group --> menu_modifier_group
  menu_item_modifier_group --> menu_sellable_item
  menu_item_modifier_group --> org_org_node
  menu_item_modifier_group --> org_tenant
  menu_item_variant --> menu_sellable_item
  menu_item_variant --> org_org_node
  menu_item_variant --> org_tenant
  menu_menu --> org_org_node
  menu_menu --> org_tenant
  menu_modifier --> menu_modifier_group
  menu_modifier --> org_org_node
  menu_modifier --> org_tenant
  menu_modifier_group --> org_org_node
  menu_modifier_group --> org_tenant
  menu_modifier_incompatibility --> menu_modifier
  menu_modifier_incompatibility --> org_org_node
  menu_modifier_incompatibility --> org_tenant
  menu_price --> menu_item_variant
  menu_price --> menu_modifier
  menu_price --> menu_sellable_item
  menu_price --> money_currency
  menu_price --> org_org_node
  menu_price --> org_tenant
  menu_publication_snapshot --> identity_user_account
  menu_publication_snapshot --> menu_menu
  menu_publication_snapshot --> org_org_node
  menu_publication_snapshot --> org_tenant
  menu_publication_snapshot_line --> menu_publication_snapshot
  menu_publication_snapshot_line --> money_currency
  menu_publication_snapshot_line --> org_org_node
  menu_publication_snapshot_line --> org_tenant
  menu_sellable_item --> menu_category
  menu_sellable_item --> menu_menu
  menu_sellable_item --> org_org_node
  menu_sellable_item --> org_tenant
  menu_translation --> identity_user_account
  menu_translation --> menu_translatable_field
  menu_translation --> org_org_node
  menu_translation --> org_tenant
  notify_deep_link --> notify_notice
  notify_deep_link --> org_org_node
  notify_deep_link --> org_tenant
  notify_deep_link --> service_table_session
  notify_notice --> identity_user_account
  notify_notice --> notify_notification
  notify_notice --> org_org_node
  notify_notice --> org_tenant
  notify_notice --> service_guest_session
  notify_notification --> notify_catalog_event
  notify_notification --> org_org_node
  notify_notification --> org_tenant
  notify_status_wording --> org_org_node
  notify_status_wording --> org_tenant
  notify_template --> notify_catalog_event
  notify_template --> org_tenant
  ordering_charge_rule --> config_configuration_version
  ordering_charge_rule --> config_policy
  ordering_charge_rule --> money_currency
  ordering_charge_rule --> org_org_node
  ordering_charge_rule --> org_tenant
  ordering_correlation_link --> org_org_node
  ordering_correlation_link --> org_tenant
  ordering_customer_order --> identity_user_account
  ordering_customer_order --> menu_publication_snapshot
  ordering_customer_order --> money_currency
  ordering_customer_order --> org_org_node
  ordering_customer_order --> org_tenant
  ordering_customer_order --> service_cart
  ordering_customer_order --> service_guest_session
  ordering_customer_order --> service_table_session
  ordering_duplicate_signal --> ordering_customer_order
  ordering_duplicate_signal --> org_org_node
  ordering_duplicate_signal --> org_tenant
  ordering_order_charge_component --> money_currency
  ordering_order_charge_component --> ordering_charge_rule
  ordering_order_charge_component --> ordering_customer_order
  ordering_order_charge_component --> org_org_node
  ordering_order_charge_component --> org_tenant
  ordering_order_event --> config_reason_code
  ordering_order_event --> identity_user_account
  ordering_order_event --> org_org_node
  ordering_order_event --> org_tenant
  ordering_order_event --> service_guest_session
  ordering_order_line --> menu_item_variant
  ordering_order_line --> menu_publication_snapshot_line
  ordering_order_line --> menu_sellable_item
  ordering_order_line --> money_currency
  ordering_order_line --> ordering_customer_order
  ordering_order_line --> org_org_node
  ordering_order_line --> org_tenant
  ordering_order_line --> service_guest_session
  ordering_order_line_modifier --> menu_modifier
  ordering_order_line_modifier --> money_currency
  ordering_order_line_modifier --> ordering_order_line
  ordering_order_line_modifier --> org_org_node
  ordering_order_line_modifier --> org_tenant
  ordering_order_note --> identity_user_account
  ordering_order_note --> ordering_customer_order
  ordering_order_note --> ordering_order_line
  ordering_order_note --> org_org_node
  ordering_order_note --> org_tenant
  ordering_order_note --> safety_allergen
  ordering_order_note --> safety_allergy_concern
  ordering_order_note --> safety_approved_wording
  ordering_order_note --> service_guest_session
  ordering_order_timeline_entry --> ordering_customer_order
  ordering_order_timeline_entry --> org_org_node
  ordering_order_timeline_entry --> org_tenant
  org_device_registration --> org_org_node
  org_org_closure --> org_org_node
  org_org_closure --> org_tenant
  org_org_node --> org_org_node
  org_org_node --> org_tenant
  org_outlet_profile --> org_org_node
  org_system_of_record --> identity_user_account
  org_system_of_record --> org_org_node
  org_system_of_record --> org_tenant
  payments_allocation --> org_org_node
  payments_allocation --> org_tenant
  payments_allocation --> payments_payment
  payments_payment --> identity_user_account
  payments_payment --> org_org_node
  payments_payment --> org_tenant
  payments_payment --> payments_payment_adapter
  payments_payment --> payments_payment_intent
  payments_payment --> payments_proof_confirmation
  payments_payment --> payments_terminal_result
  payments_payment_adapter --> org_org_node
  payments_payment_adapter --> org_tenant
  payments_payment_event --> config_reason_code
  payments_payment_event --> identity_user_account
  payments_payment_event --> org_org_node
  payments_payment_event --> org_tenant
  payments_payment_event --> pos_override_approval
  payments_payment_intent --> identity_user_account
  payments_payment_intent --> org_org_node
  payments_payment_intent --> org_tenant
  payments_proof_confirmation --> identity_session
  payments_proof_confirmation --> identity_user_account
  payments_proof_confirmation --> org_org_node
  payments_proof_confirmation --> org_tenant
  payments_reversal --> config_reason_code
  payments_reversal --> identity_user_account
  payments_reversal --> org_org_node
  payments_reversal --> org_tenant
  payments_reversal --> payments_allocation
  payments_reversal --> pos_override_approval
  payments_simulated_attempt --> identity_user_account
  payments_simulated_attempt --> org_org_node
  payments_simulated_attempt --> org_tenant
  payments_simulated_attempt --> payments_payment_adapter
  payments_terminal_result --> identity_user_account
  payments_terminal_result --> org_org_node
  payments_terminal_result --> org_tenant
  pos_confirmation_requirement --> org_tenant
  pos_fast_pick --> identity_user_account
  pos_fast_pick --> menu_sellable_item
  pos_fast_pick --> org_org_node
  pos_fast_pick --> org_tenant
  pos_handover --> identity_user_account
  pos_handover --> org_org_node
  pos_handover --> org_tenant
  pos_handover_item --> pos_handover
  pos_handover_item --> service_table_session
  pos_override_approval --> config_reason_code
  pos_override_approval --> identity_session
  pos_override_approval --> identity_step_up_grant
  pos_override_approval --> identity_user_account
  pos_override_approval --> org_org_node
  pos_override_approval --> org_tenant
  pos_terminal --> config_reason_code
  pos_terminal --> identity_user_account
  pos_terminal --> org_device_registration
  pos_terminal --> org_org_node
  pos_terminal --> org_tenant
  safety_allergen --> org_org_node
  safety_allergen --> org_tenant
  safety_allergen --> safety_jurisdiction
  safety_allergy_concern --> identity_user_account
  safety_allergy_concern --> org_org_node
  safety_allergy_concern --> org_tenant
  safety_allergy_concern --> safety_allergen
  safety_allergy_concern --> safety_approved_wording
  safety_allergy_concern --> service_guest_session
  safety_allergy_concern --> service_table_session
  safety_approved_wording --> identity_user_account
  safety_approved_wording --> org_org_node
  safety_approved_wording --> org_tenant
  safety_declaration --> identity_user_account
  safety_declaration --> org_org_node
  safety_declaration --> org_tenant
  safety_declaration --> safety_allergen
  safety_declaration_reference --> org_org_node
  safety_declaration_reference --> org_tenant
  safety_declaration_reference --> safety_declaration
  safety_dietary_claim --> identity_user_account
  safety_dietary_claim --> org_org_node
  safety_dietary_claim --> org_tenant
  safety_dietary_claim_outlet --> org_org_node
  safety_dietary_claim_outlet --> safety_dietary_claim
  safety_item_dietary_claim --> identity_user_account
  safety_item_dietary_claim --> org_org_node
  safety_item_dietary_claim --> org_tenant
  safety_item_dietary_claim --> safety_dietary_claim
  safety_jurisdiction_requirement --> safety_jurisdiction
  service_cart --> org_org_node
  service_cart --> org_tenant
  service_cart --> service_guest_session
  service_cart --> service_table_session
  service_cart_line --> menu_item_variant
  service_cart_line --> menu_sellable_item
  service_cart_line --> money_currency
  service_cart_line --> org_org_node
  service_cart_line --> org_tenant
  service_cart_line --> service_cart
  service_cart_line --> service_guest_session
  service_cart_line_modifier --> menu_modifier
  service_cart_line_modifier --> org_org_node
  service_cart_line_modifier --> org_tenant
  service_cart_line_modifier --> service_cart_line
  service_cart_line_transfer --> org_org_node
  service_cart_line_transfer --> org_tenant
  service_cart_line_transfer --> service_cart
  service_cart_line_transfer --> service_cart_line
  service_guest_session --> org_org_node
  service_guest_session --> org_tenant
  service_idempotency_key --> org_org_node
  service_idempotency_key --> org_tenant
  service_ownership_transfer --> config_reason_code
  service_ownership_transfer --> identity_user_account
  service_ownership_transfer --> org_org_node
  service_ownership_transfer --> org_tenant
  service_ownership_transfer --> service_table_session
  service_qr_placard --> identity_user_account
  service_qr_placard --> org_org_node
  service_qr_placard --> org_tenant
  service_qr_placard --> service_table_qr_token
  service_qr_scan --> org_org_node
  service_qr_scan --> org_tenant
  service_qr_scan --> service_guest_session
  service_qr_scan --> service_table_qr_token
  service_request_escalation --> identity_user_account
  service_request_escalation --> org_org_node
  service_request_escalation --> org_tenant
  service_request_escalation --> service_service_request
  service_request_routing_decision --> identity_role
  service_request_routing_decision --> identity_user_account
  service_request_routing_decision --> org_org_node
  service_request_routing_decision --> org_tenant
  service_request_routing_decision --> service_service_request
  service_request_type --> identity_role
  service_request_type --> org_org_node
  service_request_type --> org_tenant
  service_service_request --> config_reason_code
  service_service_request --> identity_role
  service_service_request --> identity_user_account
  service_service_request --> ordering_customer_order
  service_service_request --> org_org_node
  service_service_request --> org_tenant
  service_service_request --> service_request_type
  service_service_request --> service_table_session
  service_service_request_event --> config_reason_code
  service_service_request_event --> org_org_node
  service_service_request_event --> org_tenant
  service_session_closure_exception --> config_reason_code
  service_session_closure_exception --> identity_user_account
  service_session_closure_exception --> org_org_node
  service_session_closure_exception --> org_tenant
  service_session_closure_exception --> service_table_session
  service_session_merge --> config_reason_code
  service_session_merge --> identity_user_account
  service_session_merge --> org_org_node
  service_session_merge --> org_tenant
  service_session_merge --> service_table_session
  service_session_move --> identity_user_account
  service_session_move --> org_org_node
  service_session_move --> org_tenant
  service_session_move --> service_table_profile
  service_session_move --> service_table_session
  service_session_participant --> org_org_node
  service_session_participant --> org_tenant
  service_session_participant --> service_guest_session
  service_session_participant --> service_table_session
  service_staff_presence --> identity_session
  service_staff_presence --> identity_user_account
  service_staff_presence --> org_org_node
  service_staff_presence --> org_tenant
  service_table_ownership --> identity_user_account
  service_table_ownership --> org_org_node
  service_table_ownership --> org_tenant
  service_table_ownership --> service_table_session
  service_table_profile --> org_org_node
  service_table_qr_token --> config_reason_code
  service_table_qr_token --> identity_user_account
  service_table_qr_token --> org_org_node
  service_table_qr_token --> org_tenant
  service_table_qr_token --> service_table_profile
  service_table_session --> identity_user_account
  service_table_session --> org_org_node
  service_table_session --> org_tenant
  service_table_session --> service_table_profile
  service_verification_policy --> org_tenant
```

## Schemas

### `app`

Request-context accessors and shared trigger functions.

### `audit`

Append-only security and operational audit storage (FR-SEC-009).

#### `audit.operational_event`

Append-only operational audit. Every configuration and policy change writes a row here carrying the actor, the approval and the effective date (FR-TEN-010).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `event_code` | `text` | NOT NULL |  |  |
| `entity_schema` | `text` | NOT NULL |  |  |
| `entity_table` | `text` | NOT NULL |  |  |
| `entity_id` | `text` |  |  |  |
| `actor_id` | `uuid` |  |  |  |
| `approved_by_id` | `uuid` |  |  |  |
| `approved_at` | `timestamp with time zone` |  |  |  |
| `effective_from` | `timestamp with time zone` |  |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `detail` | `jsonb` | NOT NULL | `'{}'::jsonb` |  |

Constraints:

- `operational_event_code_not_blank` — `CHECK ((btrim(event_code) <> ''::text))`
- `operational_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `operational_event_pkey` — `PRIMARY KEY (id)`
- `operational_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `operational_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `audit.security_event`

Append-only security audit (FR-AUTH-010). identity.emit_security_event writes here; as of 0005 that is the only way rows arrive, so the store reflects what identity actually emitted rather than what a caller chose to insert. The 0003 comment saying "M1-B emits them, M1-C stores them" described an intention that no code implemented; this supersedes it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `event_code` | `text` | NOT NULL |  |  |
| `subject_id` | `uuid` |  |  |  |
| `actor_id` | `uuid` |  |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `detail` | `jsonb` | NOT NULL | `'{}'::jsonb` |  |

Constraints:

- `security_event_code_not_blank` — `CHECK ((btrim(event_code) <> ''::text))`
- `security_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `security_event_pkey` — `PRIMARY KEY (id)`
- `security_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `security_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `billing`

Checks, bills, splitting and tips (FR-BIL-001 through FR-BIL-016). Separate from ordering because a bill is a view onto an order rather than a part of one: the order ledger is append-only and untouched by anything here, which is what FR-BIL-001's "without changing order ownership or history" means in practice.

#### `billing.bill`

FR-BIL-005 through FR-BIL-009. The calculated document issued from a check. A projection: nothing writes it outside the writers that set the fold's marker, and the total is asserted to equal the sum of its components. THERE IS NO TIP COLUMN — a tip is a separate value and a separate record (FR-BIL-014), and the absence of a column is what makes that structural rather than a habit.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `check_id` | `uuid` | NOT NULL |  |  |
| `bill_number` | `text` | NOT NULL |  |  |
| `state` | `billing.bill_state` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `bill_total_minor` | `money.amount_minor` | NOT NULL |  |  |
| `disposed_minor` | `money.amount_minor` | NOT NULL | `0` |  |
| `calculation_version` | `text` | NOT NULL |  |  |
| `locale` | `menu.customer_locale` | NOT NULL |  |  |
| `issued_at` | `timestamp with time zone` | NOT NULL |  |  |
| `finalized_at` | `timestamp with time zone` |  |  |  |
| `reissued_as_bill_id` | `uuid` |  |  |  |
| `supersedes_bill_id` | `uuid` |  |  |  |
| `ledger_sequence` | `integer` | NOT NULL | `0` |  |

Constraints:

- `bill_calculation_version_stated` — `CHECK ((btrim(calculation_version) <> ''::text))`
- `bill_check_fk` — `FOREIGN KEY (tenant_id, check_id) REFERENCES billing."check"(tenant_id, id) ON DELETE RESTRICT`
- `bill_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `bill_disposed_within_total` — `CHECK ((((disposed_minor)::bigint >= 0) AND ((disposed_minor)::bigint <= (bill_total_minor)::bigint)))`
- `bill_does_not_supersede_itself` — `CHECK (((supersedes_bill_id IS DISTINCT FROM id) AND (reissued_as_bill_id IS DISTINCT FROM id)))`
- `bill_finalization_consistent` — `CHECK (((state = 'finalized'::billing.bill_state) = (finalized_at IS NOT NULL)))`
- `bill_ledger_sequence_not_negative` — `CHECK ((ledger_sequence >= 0))`
- `bill_number_unique` — `UNIQUE (tenant_id, outlet_id, bill_number)`
- `bill_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `bill_pkey` — `PRIMARY KEY (id)`
- `bill_reissue_fk` — `FOREIGN KEY (tenant_id, reissued_as_bill_id) REFERENCES billing.bill(tenant_id, id) ON DELETE RESTRICT`
- `bill_supersedes_fk` — `FOREIGN KEY (tenant_id, supersedes_bill_id) REFERENCES billing.bill(tenant_id, id) ON DELETE RESTRICT`
- `bill_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `bill_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `bill_total_not_negative` — `CHECK (((bill_total_minor)::bigint >= 0))`

Policies:

- `bill_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.bill_component`

FR-BIL-005. Item subtotal, discount, tax and fee, each computed exactly and each recording the basis it was computed from. One per kind per bill, so the total is a sum with no double-counted term.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `kind` | `ordering.charge_kind` | NOT NULL |  |  |
| `source_kind` | `ordering.charge_source_kind` | NOT NULL |  |  |
| `source_id` | `uuid` |  |  |  |
| `basis` | `jsonb` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |

Constraints:

- `bill_component_basis_is_an_object` — `CHECK ((jsonb_typeof(basis) = 'object'::text))`
- `bill_component_bill_fk` — `FOREIGN KEY (tenant_id, bill_id) REFERENCES billing.bill(tenant_id, id) ON DELETE CASCADE`
- `bill_component_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `bill_component_one_per_kind` — `UNIQUE (bill_id, kind)`
- `bill_component_pkey` — `PRIMARY KEY (id)`
- `bill_component_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `bill_total_is_the_sum_of_its_components` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`

Policies:

- `bill_component_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.bill_disposition`

FR-BIL-008's second branch. At M4-A it is the only branch: nothing here takes money, so a bill reaches a settled balance by being comped, written off or transferred, each with an override that names two people and a reason that names why.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `kind` | `billing.disposition_kind` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `override_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `reason_text` | `text` | NOT NULL |  |  |
| `actor_user_id` | `uuid` | NOT NULL |  |  |
| `disposed_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `transferred_to_check_id` | `uuid` |  |  |  |

Constraints:

- `bill_disposition_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `bill_disposition_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `bill_disposition_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `bill_disposition_override_fk` — `FOREIGN KEY (tenant_id, override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `bill_disposition_pkey` — `PRIMARY KEY (id)`
- `bill_disposition_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `bill_disposition_states_a_reason` — `CHECK ((btrim(reason_text) <> ''::text))`
- `bill_disposition_target_fk` — `FOREIGN KEY (tenant_id, transferred_to_check_id) REFERENCES billing."check"(tenant_id, id) ON DELETE RESTRICT`
- `bill_disposition_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `bill_disposition_transfer_names_a_destination` — `CHECK (((kind = 'transferred'::billing.disposition_kind) = (transferred_to_check_id IS NOT NULL)))`

Policies:

- `bill_disposition_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.bill_event`

FR-BIL-009 and FR-DAT-008A. The authoritative record of everything that happened to a bill. Append-only by trigger and by grant. Every projection below is folded from it, so a rebuild reproduces them and a correction is an event rather than an edit.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | `nextval('billing.bill_event_id_seq'::regclass)` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `kind` | `billing.bill_event_kind` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `actor_user_id` | `uuid` |  |  |  |
| `override_id` | `uuid` |  |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `reason_text` | `text` |  |  |  |
| `before` | `jsonb` |  |  |  |
| `after` | `jsonb` |  |  |  |
| `correlation_id` | `uuid` |  |  |  |

Constraints:

- `bill_event_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `bill_event_correction_states_a_reason` — `CHECK (((kind <> ALL (ARRAY['voided'::billing.bill_event_kind, 'credited'::billing.bill_event_kind, 'reissued'::billing.bill_event_kind])) OR ((reason_code_id IS NOT NULL) AND (btrim(COALESCE(reason_text, ''::text)) <> ''::text))))`
- `bill_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `bill_event_pkey` — `PRIMARY KEY (id)`
- `bill_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `bill_event_sequence_positive` — `CHECK ((sequence_number >= 1))`
- `bill_event_sequence_unique` — `UNIQUE (tenant_id, bill_id, sequence_number)`
- `bill_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `bill_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.bill_share`

FR-BIL-003. One payer's share of a bill. Shares sum to the bill total exactly — billing.assert_shares_sum_to_the_bill() refuses any set that does not — so a split can neither lose a minor unit nor create one.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `share_number` | `integer` | NOT NULL |  |  |
| `mode` | `billing.split_mode` | NOT NULL |  |  |
| `participant_guest_session_id` | `uuid` |  |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |

Constraints:

- `bill_share_amount_not_negative` — `CHECK (((amount_minor)::bigint >= 0))`
- `bill_share_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `bill_share_number_positive` — `CHECK ((share_number >= 1))`
- `bill_share_number_unique` — `UNIQUE (bill_id, share_number)`
- `bill_share_pkey` — `PRIMARY KEY (id)`
- `bill_share_sums_to_the_bill` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `bill_share_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `bill_share_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.check`

FR-BIL-001. What a party is being billed for: an allocation of order lines, created from accepted or served lines and changing nothing about them. A check may be split or merged while the money is still undecided; once a bill is issued from it the money is decided and corrections go through FR-BIL-009's void, credit and reissue instead.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `check_number` | `text` | NOT NULL |  |  |
| `state` | `billing.check_state` | NOT NULL | `'open'::billing.check_state` |  |
| `merged_into_check_id` | `uuid` |  |  |  |
| `split_from_check_id` | `uuid` |  |  |  |
| `opened_by_user_id` | `uuid` | NOT NULL |  |  |
| `opened_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `closed_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `check_closure_consistent` — `CHECK (((state = 'open'::billing.check_state) = (closed_at IS NULL)))`
- `check_does_not_merge_into_itself` — `CHECK ((merged_into_check_id IS DISTINCT FROM id))`
- `check_does_not_split_from_itself` — `CHECK ((split_from_check_id IS DISTINCT FROM id))`
- `check_merge_target_only_when_merged` — `CHECK (((state = 'merged'::billing.check_state) = (merged_into_check_id IS NOT NULL)))`
- `check_merged_into_fk` — `FOREIGN KEY (tenant_id, merged_into_check_id) REFERENCES billing."check"(tenant_id, id) ON DELETE RESTRICT`
- `check_number_unique` — `UNIQUE (tenant_id, outlet_id, check_number)`
- `check_opener_fk` — `FOREIGN KEY (tenant_id, opened_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `check_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `check_pkey` — `PRIMARY KEY (id)`
- `check_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `check_split_from_fk` — `FOREIGN KEY (tenant_id, split_from_check_id) REFERENCES billing."check"(tenant_id, id) ON DELETE RESTRICT`
- `check_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `check_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `"check"_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.check_allocation`

FR-BIL-002. Which order line units this check bills for. There is no amount column: an allocation says WHAT is billed and the bill says what it COSTS, so the price a guest is asked for is calculated once from the order's own snapshot rather than copied here where it could drift from it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `check_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `order_line_id` | `uuid` | NOT NULL |  |  |
| `quantity` | `integer` | NOT NULL |  |  |
| `allocated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `check_allocation_check_fk` — `FOREIGN KEY (tenant_id, check_id) REFERENCES billing."check"(tenant_id, id) ON DELETE CASCADE`
- `check_allocation_never_bills_a_unit_twice` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `check_allocation_once_per_line` — `UNIQUE (check_id, order_line_id)`
- `check_allocation_pkey` — `PRIMARY KEY (id)`
- `check_allocation_quantity_positive` — `CHECK ((quantity >= 1))`
- `check_allocation_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `check_allocation_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.component_wording`

FR-BIL-007. What a bill calls each of its components, in the language the order was placed in. Identity and the English source only; the Amharic and Arabic live in menu.translation where a person has to review and approve them. No migration writes one, because an approved translation asserts that somebody read it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `kind` | `ordering.charge_kind` | NOT NULL |  |  |
| `source_text` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `component_wording_one_per_kind` — `UNIQUE (tenant_id, kind)`
- `component_wording_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `component_wording_pkey` — `PRIMARY KEY (id)`
- `component_wording_row_version_positive` — `CHECK ((row_version > 0))`
- `component_wording_source_not_blank` — `CHECK ((btrim(source_text) <> ''::text))`
- `component_wording_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `component_wording_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `component_wording_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.service_charge_setting`

FR-CFG-001C and FR-ORD-003's fee component. The configured source 'fee' never had until now: it points at a config.configuration_version so the value a bill used is the approved one and stays recoverable, exactly as the tax component does.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `configuration_version_id` | `uuid` | NOT NULL |  |  |
| `percentage` | `money.percentage` | NOT NULL |  |  |
| `rounding` | `money.rounding_mode` | NOT NULL |  |  |
| `applies_to` | `ordering.charge_kind[]` | NOT NULL | `ARRAY['item_subtotal'::ordering.charge_kind]` |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `service_charge_applies_to_something` — `CHECK ((array_length(applies_to, 1) >= 1))`
- `service_charge_not_charged_on_itself` — `CHECK ((NOT ('fee'::ordering.charge_kind = ANY (applies_to))))`
- `service_charge_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `service_charge_percentage_sane` — `CHECK ((((percentage)::numeric >= (0)::numeric) AND ((percentage)::numeric <= (100)::numeric)))`
- `service_charge_setting_pkey` — `PRIMARY KEY (tenant_id, outlet_id)`
- `service_charge_version_fk` — `FOREIGN KEY (configuration_version_id) REFERENCES config.configuration_version(id) ON DELETE RESTRICT`

Policies:

- `service_charge_setting_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.tip`

FR-BIL-014 and FR-BIL-015. A tip, attached to one payer's share. It is in its own table with its own currency and amount because bill balance and tip are separate values and separate records; there is no column anywhere in billing.bill that could hold one, and the total's trigger sums components rather than tips.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_share_id` | `uuid` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `chosen_from_percentage` | `money.percentage` |  |  |  |
| `chosen_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `tip_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `tip_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `tip_one_per_share` — `UNIQUE (bill_share_id)`
- `tip_pkey` — `PRIMARY KEY (id)`
- `tip_share_fk` — `FOREIGN KEY (tenant_id, bill_share_id) REFERENCES billing.bill_share(tenant_id, id) ON DELETE RESTRICT`
- `tip_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `tip_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.tip_correction`

FR-BIL-016. A reversal, refund or correction of a tip, LINKED to the original rather than replacing it. It carries an override, so M3-D's rule that an approver is never the actor applies here without being written a second time — which is NC-M4-004's maker-checker for the half of it that exists at this gate.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `tip_id` | `uuid` | NOT NULL |  |  |
| `kind` | `billing.tip_correction_kind` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `reason_text` | `text` | NOT NULL |  |  |
| `actor_user_id` | `uuid` | NOT NULL |  |  |
| `override_id` | `uuid` | NOT NULL |  |  |
| `corrected_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `tip_correction_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `tip_correction_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `tip_correction_currency_is_iso` — `CHECK ((currency_code ~ '^[A-Z]{3}$'::text))`
- `tip_correction_override_fk` — `FOREIGN KEY (tenant_id, override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `tip_correction_pkey` — `PRIMARY KEY (id)`
- `tip_correction_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `tip_correction_states_a_reason` — `CHECK ((btrim(reason_text) <> ''::text))`
- `tip_correction_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `tip_correction_tip_fk` — `FOREIGN KEY (tenant_id, tip_id) REFERENCES billing.tip(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `tip_correction_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.tip_setting`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `offered` | `boolean` | NOT NULL | `true` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `tip_setting_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `tip_setting_pkey` — `PRIMARY KEY (tenant_id, outlet_id)`

Policies:

- `tip_setting_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `billing.tip_suggestion`

FR-BIL-013. Amounts a guest may tap, in a layout order. THERE IS NO COLUMN FOR A DEFAULT and that is the requirement: no tip is selected by default, so the model is given nowhere to say one is. NC-M4-001 plants the defect at the only level left — the surface preselecting one — and tests/m4a measures the rendered page for it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL |  |  |
| `percentage` | `money.percentage` | NOT NULL |  |  |

Constraints:

- `tip_suggestion_order_positive` — `CHECK ((display_order >= 1))`
- `tip_suggestion_percentage_sane` — `CHECK ((((percentage)::numeric > (0)::numeric) AND ((percentage)::numeric <= (100)::numeric)))`
- `tip_suggestion_pkey` — `PRIMARY KEY (tenant_id, outlet_id, display_order)`
- `tip_suggestion_setting_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES billing.tip_setting(tenant_id, outlet_id) ON DELETE CASCADE`

Policies:

- `tip_suggestion_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `cash`

FR-CSH-001 … FR-CSH-008. The drawer: who opened it with how much, every movement in and out, what was counted against what was expected, where the money went afterwards, and what somebody should look at. Separate from payments because a payment is what a guest handed over and a shift is what is physically in the till.

#### `cash.custody_transfer`

FR-CSH-007. Cash to the safe or the bank, with the sealed bag's reference and both people. It names the MOVEMENT that took the money out of the drawer rather than restating the amount independently, so the till and the safe cannot disagree about how much left.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `shift_id` | `uuid` | NOT NULL |  |  |
| `movement_id` | `uuid` | NOT NULL |  |  |
| `destination` | `cash.custody_destination` | NOT NULL |  |  |
| `sealed_bag_reference` | `text` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `released_by_user_id` | `uuid` | NOT NULL |  |  |
| `accepted_by_user_id` | `uuid` | NOT NULL |  |  |
| `transferred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `custody_accepter_fk` — `FOREIGN KEY (tenant_id, accepted_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `custody_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `custody_movement_fk` — `FOREIGN KEY (tenant_id, movement_id) REFERENCES cash.movement(tenant_id, id) ON DELETE RESTRICT`
- `custody_one_per_movement` — `UNIQUE (movement_id)`
- `custody_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `custody_reference_not_blank` — `CHECK ((btrim(sealed_bag_reference) <> ''::text))`
- `custody_reference_unique` — `UNIQUE (tenant_id, outlet_id, sealed_bag_reference)`
- `custody_releaser_fk` — `FOREIGN KEY (tenant_id, released_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `custody_shift_fk` — `FOREIGN KEY (tenant_id, shift_id) REFERENCES cash.shift(tenant_id, id) ON DELETE RESTRICT`
- `custody_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `custody_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `custody_transfer_pkey` — `PRIMARY KEY (id)`
- `custody_two_people` — `CHECK ((released_by_user_id <> accepted_by_user_id))`

Policies:

- `custody_transfer_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `cash.denomination_tally`

FR-CSH-003's denomination count: how many of each note and coin. The subtotal is generated so a tally cannot disagree with its own arithmetic, and cash.assert_tally_equals_the_count() requires the tallies to add up to the counted total — a denomination breakdown that does not reach the figure beside it is the shape a fudged count takes.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `count_id` | `uuid` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `denomination_minor` | `money.amount_minor` | NOT NULL |  |  |
| `piece_count` | `integer` | NOT NULL |  |  |
| `subtotal_minor` | `bigint` |  | `((denomination_minor)::bigint * piece_count)` |  |

Constraints:

- `denomination_tally_count_fk` — `FOREIGN KEY (tenant_id, count_id) REFERENCES cash.drawer_count(tenant_id, id) ON DELETE CASCADE`
- `denomination_tally_count_not_negative` — `CHECK ((piece_count >= 0))`
- `denomination_tally_one_row_per_denomination` — `UNIQUE (count_id, denomination_minor)`
- `denomination_tally_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `denomination_tally_pkey` — `PRIMARY KEY (id)`
- `denomination_tally_positive` — `CHECK (((denomination_minor)::bigint > 0))`
- `denomination_tally_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `tally_equals_the_count` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`

Policies:

- `denomination_tally_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `cash.drawer_count`

FR-CSH-003. What the drawer should have held, what it did hold, and the difference. The expected figure is stored rather than derived so that a count remains evidence about the moment it was taken. A recount after a reopening is its own row with phase 'recount', which is how NC-M4-006 can require one.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `shift_id` | `uuid` | NOT NULL |  |  |
| `phase` | `cash.count_phase` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `expected_minor` | `money.amount_minor` | NOT NULL |  |  |
| `counted_minor` | `money.amount_minor` | NOT NULL |  |  |
| `over_short_minor` | `bigint` |  | `((counted_minor)::bigint - (expected_minor)::bigint)` |  |
| `counted_by_user_id` | `uuid` | NOT NULL |  |  |
| `counted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `drawer_count_actor_fk` — `FOREIGN KEY (tenant_id, counted_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `drawer_count_not_negative` — `CHECK (((counted_minor)::bigint >= 0))`
- `drawer_count_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `drawer_count_pkey` — `PRIMARY KEY (id)`
- `drawer_count_shift_fk` — `FOREIGN KEY (tenant_id, shift_id) REFERENCES cash.shift(tenant_id, id) ON DELETE RESTRICT`
- `drawer_count_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `drawer_count_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `drawer_count_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `cash.movement`

FR-CSH-002. Six distinct kinds of money crossing the drawer, each with the direction its kind implies rather than a sign somebody chose. Append-only by trigger and by grant: a movement recorded wrongly is corrected by an opposing movement, because FR-DAT-008B says cash movements carry no destructive correction and a drawer that can be edited is a drawer nobody can count.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `shift_id` | `uuid` | NOT NULL |  |  |
| `kind` | `cash.movement_kind` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `payment_id` | `uuid` |  |  |  |
| `reversal_id` | `uuid` |  |  |  |
| `reference` | `text` |  |  |  |
| `actor_user_id` | `uuid` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `movement_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `movement_amount_not_zero` — `CHECK (((amount_minor)::bigint <> 0))`
- `movement_one_per_payment` — `UNIQUE (payment_id)`
- `movement_one_per_reversal` — `UNIQUE (reversal_id)`
- `movement_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `movement_pkey` — `PRIMARY KEY (id)`
- `movement_refund_names_a_reversal` — `CHECK (((kind <> 'refund'::cash.movement_kind) OR (reversal_id IS NOT NULL)))`
- `movement_sales_receipt_names_a_payment` — `CHECK (((kind <> 'sales_receipt'::cash.movement_kind) OR (payment_id IS NOT NULL)))`
- `movement_shift_fk` — `FOREIGN KEY (tenant_id, shift_id) REFERENCES cash.shift(tenant_id, id) ON DELETE RESTRICT`
- `movement_sign_matches_the_kind` — `CHECK (((kind = 'float_adjustment'::cash.movement_kind) OR ((sign((amount_minor)::double precision))::integer = cash.movement_direction(kind))))`
- `movement_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `movement_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `movement_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `cash.shift`

FR-CSH-001 and FR-CSH-004. A drawer session: counted float, assigned terminal, and the approval that closed it. The verifier is never the cashier, by CHECK; the verifier's SESSION is recorded beside them so that a manager typing a password into the cashier's terminal is caught by the same reasoning M3-D used for overrides; and a reopened shift cannot reach a terminal state other than 'resolved'.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `terminal_device_id` | `uuid` | NOT NULL |  |  |
| `cashier_user_id` | `uuid` | NOT NULL |  |  |
| `state` | `cash.shift_state` | NOT NULL | `'open'::cash.shift_state` |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `opening_float_minor` | `money.amount_minor` | NOT NULL |  |  |
| `opened_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `submitted_at` | `timestamp with time zone` |  |  |  |
| `submitted_by_user_id` | `uuid` |  |  |  |
| `verified_at` | `timestamp with time zone` |  |  |  |
| `verified_by_user_id` | `uuid` |  |  |  |
| `verified_by_session_id` | `uuid` |  |  |  |
| `finalized_at` | `timestamp with time zone` |  |  |  |
| `reopened_at` | `timestamp with time zone` |  |  |  |
| `reopen_override_id` | `uuid` |  |  |  |
| `reopen_reason_code_id` | `uuid` |  |  |  |
| `reopen_reason` | `text` |  |  |  |
| `resolved_at` | `timestamp with time zone` |  |  |  |
| `resolution_override_id` | `uuid` |  |  |  |

Constraints:

- `shift_cashier_fk` — `FOREIGN KEY (tenant_id, cashier_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `shift_finalized_has_a_time` — `CHECK (((state = ANY (ARRAY['finalized'::cash.shift_state, 'resolved'::cash.shift_state])) = (finalized_at IS NOT NULL)))`
- `shift_float_not_negative` — `CHECK (((opening_float_minor)::bigint >= 0))`
- `shift_only_a_reopened_shift_resolves` — `CHECK (((state <> 'resolved'::cash.shift_state) OR (reopened_at IS NOT NULL)))`
- `shift_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `shift_pkey` — `PRIMARY KEY (id)`
- `shift_reopen_is_authorized` — `CHECK (((reopened_at IS NULL) OR ((reopen_override_id IS NOT NULL) AND (reopen_reason_code_id IS NOT NULL) AND (btrim(COALESCE(reopen_reason, ''::text)) <> ''::text))))`
- `shift_reopen_override_fk` — `FOREIGN KEY (tenant_id, reopen_override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `shift_reopen_reason_fk` — `FOREIGN KEY (tenant_id, reopen_reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `shift_reopened_never_refinalizes` — `CHECK (((reopened_at IS NULL) OR (state <> 'finalized'::cash.shift_state)))`
- `shift_resolution_override_fk` — `FOREIGN KEY (tenant_id, resolution_override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `shift_resolved_is_authorized` — `CHECK (((state = 'resolved'::cash.shift_state) = ((resolved_at IS NOT NULL) AND (resolution_override_id IS NOT NULL))))`
- `shift_submitted_has_a_submitter` — `CHECK (((submitted_at IS NULL) = (submitted_by_user_id IS NULL)))`
- `shift_submitter_fk` — `FOREIGN KEY (tenant_id, submitted_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `shift_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `shift_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `shift_terminal_fk` — `FOREIGN KEY (tenant_id, terminal_device_id) REFERENCES pos.terminal(tenant_id, device_id) ON DELETE RESTRICT`
- `shift_verification_is_attributed` — `CHECK ((((verified_at IS NULL) AND (verified_by_user_id IS NULL) AND (verified_by_session_id IS NULL)) OR ((verified_at IS NOT NULL) AND (verified_by_user_id IS NOT NULL) AND (verified_by_session_id IS NOT NULL))))`
- `shift_verifier_fk` — `FOREIGN KEY (tenant_id, verified_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `shift_verifier_is_not_the_cashier` — `CHECK (((verified_by_user_id IS NULL) OR (verified_by_user_id <> cashier_user_id)))`
- `shift_verifier_session_fk` — `FOREIGN KEY (tenant_id, verified_by_session_id) REFERENCES identity.session(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `shift_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `cash.shift_transition`

Every state a drawer has been in, append-only. It exists because reopening a finalized shift would otherwise erase the finalization, and a shift that was closed, reopened and resolved is precisely the history somebody will ask about.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | `nextval('cash.shift_transition_id_seq'::regclass)` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `shift_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `from_state` | `cash.shift_state` |  |  |  |
| `to_state` | `cash.shift_state` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `actor_user_id` | `uuid` |  |  |  |
| `override_id` | `uuid` |  |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `reason_text` | `text` |  |  |  |

Constraints:

- `shift_transition_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `shift_transition_override_fk` — `FOREIGN KEY (tenant_id, override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `shift_transition_pkey` — `PRIMARY KEY (id)`
- `shift_transition_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `shift_transition_sequence_positive` — `CHECK ((sequence_number >= 1))`
- `shift_transition_sequence_unique` — `UNIQUE (tenant_id, shift_id, sequence_number)`
- `shift_transition_shift_fk` — `FOREIGN KEY (tenant_id, shift_id) REFERENCES cash.shift(tenant_id, id) ON DELETE RESTRICT`
- `shift_transition_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `shift_transition_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `config`

Versioned tenant configuration, policy, numbering, entitlements.

#### `config.anonymization_rule`

Which columns an "anonymize" retention policy empties, and where it records having done so. Anonymizing severs the identity and keeps the row, which is what a guest session needs: the allergy concern raised at a table is operational evidence that must outlive the guest identity attached to it (FR-CST-002).

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `target_schema` | `text` | NOT NULL |  |  |
| `target_table` | `text` | NOT NULL |  |  |
| `identity_columns` | `text[]` | NOT NULL |  |  |
| `stamp_column` | `text` | NOT NULL |  |  |

Constraints:

- `anonymization_rule_has_columns` — `CHECK ((cardinality(identity_columns) >= 1))`
- `anonymization_rule_never_targets_audit` — `CHECK ((lower(target_schema) <> 'audit'::text))`
- `anonymization_rule_pkey` — `PRIMARY KEY (target_schema, target_table)`
- `anonymization_rule_stamp_not_blank` — `CHECK ((btrim(stamp_column) <> ''::text))`

#### `config.configuration_version`

Versioned, effective-dated tenant configuration (FR-TEN-003). A change never edits a row: it closes the open version and inserts the next one, so history is intact.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `scope_kind` | `config.scope_kind` | NOT NULL |  |  |
| `scope_node_id` | `uuid` |  |  |  |
| `category` | `config.configuration_category` | NOT NULL |  |  |
| `version` | `integer` | NOT NULL |  |  |
| `payload` | `jsonb` | NOT NULL |  |  |
| `effective_from` | `timestamp with time zone` | NOT NULL |  |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `actor_id` | `uuid` | NOT NULL |  |  |
| `approved_by_id` | `uuid` | NOT NULL |  |  |
| `approved_at` | `timestamp with time zone` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `configuration_version_actor_fk` — `FOREIGN KEY (tenant_id, actor_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `configuration_version_approver_fk` — `FOREIGN KEY (tenant_id, approved_by_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `configuration_version_number_positive` — `CHECK ((version > 0))`
- `configuration_version_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `configuration_version_pkey` — `PRIMARY KEY (id)`
- `configuration_version_scope_consistent` — `CHECK ((((scope_kind = 'tenant'::config.scope_kind) AND (scope_node_id IS NULL)) OR ((scope_kind <> 'tenant'::config.scope_kind) AND (scope_node_id IS NOT NULL))))`
- `configuration_version_scope_fk` — `FOREIGN KEY (tenant_id, scope_node_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `configuration_version_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `configuration_version_unique` — `UNIQUE (tenant_id, scope_kind, scope_node_id, category, version)`
- `configuration_version_window_valid` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`

Policies:

- `configuration_version_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `config.entitlement`

Module and feature entitlements per tenant, legal entity or outlet (FR-TEN-004). A missing row is a denial, never an implicit grant.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `scope_kind` | `config.scope_kind` | NOT NULL |  |  |
| `scope_node_id` | `uuid` |  |  |  |
| `feature_key` | `text` | NOT NULL |  |  |
| `granted` | `boolean` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `entitlement_feature_key_not_blank` — `CHECK ((btrim(feature_key) <> ''::text))`
- `entitlement_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `entitlement_pkey` — `PRIMARY KEY (id)`
- `entitlement_scope_consistent` — `CHECK ((((scope_kind = 'tenant'::config.scope_kind) AND (scope_node_id IS NULL)) OR ((scope_kind <> 'tenant'::config.scope_kind) AND (scope_node_id IS NOT NULL))))`
- `entitlement_scope_fk` — `FOREIGN KEY (tenant_id, scope_node_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `entitlement_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `entitlement_unique` — `UNIQUE (tenant_id, scope_kind, scope_node_id, feature_key)`

Policies:

- `entitlement_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `config.issued_document_number`

Ledger of issued human document numbers. The unique constraint is the last line of defence: even a defective issuer cannot persist a duplicate.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `legal_entity_id` | `uuid` |  |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `document_type` | `text` | NOT NULL |  |  |
| `fiscal_period` | `text` | NOT NULL |  |  |
| `document_number` | `text` | NOT NULL |  |  |
| `issued_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `issued_document_number_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `issued_document_number_unique` — `UNIQUE (tenant_id, document_type, fiscal_period, document_number)`

Policies:

- `issued_document_number_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `config.number_series`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `legal_entity_id` | `uuid` |  |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `document_type` | `text` | NOT NULL |  |  |
| `fiscal_period` | `text` | NOT NULL |  |  |
| `prefix` | `text` | NOT NULL | `''::text` |  |
| `next_value` | `bigint` | NOT NULL | `1` |  |

Constraints:

- `number_series_document_type_not_blank` — `CHECK ((btrim(document_type) <> ''::text))`
- `number_series_entity_fk` — `FOREIGN KEY (tenant_id, legal_entity_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `number_series_fiscal_period_not_blank` — `CHECK ((btrim(fiscal_period) <> ''::text))`
- `number_series_next_value_positive` — `CHECK ((next_value > 0))`
- `number_series_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `number_series_pkey` — `PRIMARY KEY (id)`
- `number_series_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `number_series_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `config.policy`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `category` | `config.policy_category` | NOT NULL |  |  |
| `version` | `integer` | NOT NULL |  |  |
| `payload` | `jsonb` | NOT NULL |  |  |
| `governed_action_code` | `text` |  |  | Foreign key into identity.governed_action. Configuration reads that registry; it never creates a second source of truth for it. |
| `effective_from` | `timestamp with time zone` | NOT NULL |  |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `actor_id` | `uuid` | NOT NULL |  |  |
| `approved_by_id` | `uuid` | NOT NULL |  |  |
| `approved_at` | `timestamp with time zone` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `policy_actor_fk` — `FOREIGN KEY (tenant_id, actor_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `policy_approver_fk` — `FOREIGN KEY (tenant_id, approved_by_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `policy_governed_action_fk` — `FOREIGN KEY (tenant_id, governed_action_code) REFERENCES identity.governed_action(tenant_id, action_code) ON DELETE RESTRICT`
- `policy_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `policy_pkey` — `PRIMARY KEY (id)`
- `policy_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `policy_unique` — `UNIQUE (tenant_id, outlet_id, category, version)`
- `policy_version_positive` — `CHECK ((version > 0))`
- `policy_window_valid` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`

Policies:

- `policy_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `config.reason_code`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `category` | `config.reason_code_category` | NOT NULL |  |  |
| `code` | `text` | NOT NULL |  |  |
| `requires_approval` | `boolean` | NOT NULL | `false` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `reason_code_not_blank` — `CHECK ((btrim(code) <> ''::text))`
- `reason_code_pkey` — `PRIMARY KEY (id)`
- `reason_code_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `reason_code_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `reason_code_unique` — `UNIQUE (tenant_id, category, code)`

Policies:

- `reason_code_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `config.reason_code_label`

One row per locale. M1 seeds the structure; Amharic and Arabic content arrives at M2 as additional rows, with no schema change.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `locale` | `text` | NOT NULL |  |  |
| `label` | `text` | NOT NULL |  |  |

Constraints:

- `reason_code_label_code_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE CASCADE`
- `reason_code_label_locale_valid` — `CHECK ((locale ~ '^[a-z]{2}(-[A-Z]{2})?$'::text))`
- `reason_code_label_not_blank` — `CHECK ((btrim(label) <> ''::text))`
- `reason_code_label_pkey` — `PRIMARY KEY (reason_code_id, locale)`

Policies:

- `reason_code_label_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `config.retention_policy`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `target_schema` | `text` | NOT NULL |  |  |
| `target_table` | `text` | NOT NULL |  |  |
| `age_column` | `text` | NOT NULL |  |  |
| `retain_for` | `interval` | NOT NULL |  |  |
| `action` | `config.retention_action` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `retention_policy_age_column_not_blank` — `CHECK ((btrim(age_column) <> ''::text))`
- `retention_policy_never_targets_audit` — `CHECK ((lower(target_schema) <> 'audit'::text))`
- `retention_policy_never_targets_financial_ledgers` — `CHECK ((target_schema <> ALL (ARRAY['billing'::text, 'payments'::text, 'cash'::text, 'docs'::text])))`
- `retention_policy_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `retention_policy_pkey` — `PRIMARY KEY (id)`
- `retention_policy_retain_for_positive` — `CHECK ((retain_for > '00:00:00'::interval))`
- `retention_policy_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `retention_policy_unique` — `UNIQUE (tenant_id, target_schema, target_table)`

Policies:

- `retention_policy_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `docs`

Documents this system produces for somebody outside it to read: receipts now, and the previews FR-UX-018 asks for of the kitchen, label and operational documents that already exist. Its own schema rather than a corner of billing because a bill states what is owed and a receipt states what happened, and the second must not become editable by living beside the first.

#### `docs.line_wording`

The English source text for the four receipt lines that are not charge components, translated through menu.translation under entity receipt_line_wording — M2-A's approval workflow unchanged, because a second store for safety-relevant text is how two copies come to disagree (M2-B's finding). The component lines take their wording from billing.component_wording_for(), which already exists and is already proved.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `kind` | `docs.receipt_line_kind` | NOT NULL |  |  |
| `source_text` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `line_wording_one_per_kind` — `UNIQUE (tenant_id, kind, status)`
- `line_wording_pkey` — `PRIMARY KEY (id)`
- `line_wording_source_not_blank` — `CHECK ((btrim(source_text) <> ''::text))`
- `line_wording_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `line_wording_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `line_wording_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.print_attempt`

FR-BIL-017's physical print, recorded, and FR-BIL-011's reprint. Its outcome is docs.print_outcome so only a device can produce one; a partial unique index permits exactly one non-reprint per receipt; and a reprint must carry an operator and a reason code. The bytes are recorded by DIGEST, never stored: a receipt names a person and what they bought, and a print log is a log.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `receipt_id` | `uuid` | NOT NULL |  |  |
| `printer_id` | `uuid` | NOT NULL |  |  |
| `outcome` | `docs.print_outcome` | NOT NULL |  |  |
| `is_reprint` | `boolean` | NOT NULL | `false` |  |
| `reason_code_id` | `uuid` |  |  |  |
| `reason_text` | `text` |  |  |  |
| `operator_user_id` | `uuid` | NOT NULL |  |  |
| `bytes_sha256` | `character(64)` | NOT NULL |  |  |
| `byte_count` | `integer` | NOT NULL |  |  |
| `detail` | `text` |  |  |  |
| `attempted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `print_attempt_byte_count_positive` — `CHECK ((byte_count > 0))`
- `print_attempt_digest_is_a_digest` — `CHECK ((bytes_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `print_attempt_operator_fk` — `FOREIGN KEY (tenant_id, operator_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `print_attempt_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `print_attempt_pkey` — `PRIMARY KEY (id)`
- `print_attempt_printer_fk` — `FOREIGN KEY (tenant_id, printer_id) REFERENCES docs.printer(tenant_id, id) ON DELETE RESTRICT`
- `print_attempt_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `print_attempt_receipt_fk` — `FOREIGN KEY (tenant_id, receipt_id) REFERENCES docs.receipt(tenant_id, id) ON DELETE RESTRICT`
- `print_attempt_reprint_carries_its_reason` — `CHECK (((is_reprint AND (reason_code_id IS NOT NULL) AND (btrim(COALESCE(reason_text, ''::text)) <> ''::text)) OR ((NOT is_reprint) AND (reason_code_id IS NULL) AND (reason_text IS NULL))))`
- `print_attempt_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `print_attempt_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `print_attempt_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.printer`

FR-CFG-001D's registered printer. Its SINK is derived from its connection by CHECK and its identity is immutable by trigger, so a preview cannot be promoted into a device by an UPDATE — the two locks payments.payment_adapter carries, for the same reason. command_set records what the bytes are written for: generic ESC/POS, because no pilot device has been chosen, and that is a gap this build states rather than hides.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `connection` | `docs.connection_kind` | NOT NULL |  |  |
| `sink` | `docs.sink_kind` | NOT NULL |  |  |
| `device_path` | `text` |  |  |  |
| `host_and_port` | `text` |  |  |  |
| `command_set` | `text` | NOT NULL | `'esc_pos_generic'::text` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `registered_by_user_id` | `uuid` | NOT NULL |  |  |
| `registered_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `printer_destination_matches_the_connection` — `CHECK ((((connection = 'network_socket'::docs.connection_kind) AND (host_and_port IS NOT NULL) AND (device_path IS NULL)) OR ((connection = ANY (ARRAY['character_device'::docs.connection_kind, 'file'::docs.connection_kind])) AND (device_path IS NOT NULL) AND (host_and_port IS NULL))))`
- `printer_name_not_blank` — `CHECK ((btrim(display_name) <> ''::text))`
- `printer_name_unique_per_outlet` — `UNIQUE (tenant_id, outlet_id, display_name, status)`
- `printer_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `printer_pkey` — `PRIMARY KEY (id)`
- `printer_registrar_fk` — `FOREIGN KEY (tenant_id, registered_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `printer_sink_is_derived_from_the_connection` — `CHECK ((((connection = ANY (ARRAY['character_device'::docs.connection_kind, 'network_socket'::docs.connection_kind])) AND (sink = 'device'::docs.sink_kind)) OR ((connection = 'file'::docs.connection_kind) AND (sink = 'preview'::docs.sink_kind))))`
- `printer_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `printer_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `printer_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.printer_test`

FR-CFG-001D's test, recorded. Its outcome is docs.print_outcome, so only a device sink can produce a row here at all — a preview cannot be tested into looking like a printer, because the value would not fit the column.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `printer_id` | `uuid` | NOT NULL |  |  |
| `outcome` | `docs.print_outcome` | NOT NULL |  |  |
| `bytes_sha256` | `character(64)` | NOT NULL |  |  |
| `byte_count` | `integer` | NOT NULL |  |  |
| `detail` | `text` |  |  |  |
| `tested_by_user_id` | `uuid` | NOT NULL |  |  |
| `tested_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `printer_test_actor_fk` — `FOREIGN KEY (tenant_id, tested_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `printer_test_byte_count_positive` — `CHECK ((byte_count > 0))`
- `printer_test_digest_is_a_digest` — `CHECK ((bytes_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `printer_test_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `printer_test_pkey` — `PRIMARY KEY (id)`
- `printer_test_printer_fk` — `FOREIGN KEY (tenant_id, printer_id) REFERENCES docs.printer(tenant_id, id) ON DELETE RESTRICT`
- `printer_test_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `printer_test_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `printer_test_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.receipt`

FR-BIL-010's digital receipt and the record of FR-BIL-017's physical one. Durable, append-only, and snapshotted: it holds no key into billing.bill because that is a projection, and it stores its own figures because paper does not change when a row does. Its locale is the BILL'S, never the reader's — M4-A's rule, which is why a reprint for a manager is in the customer's language.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `receipt_number` | `text` | NOT NULL |  |  |
| `revision` | `integer` | NOT NULL | `1` |  |
| `locale` | `menu.customer_locale` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `bill_total_minor` | `money.amount_minor` | NOT NULL |  |  |
| `tip_total_minor` | `money.amount_minor` | NOT NULL | `0` |  |
| `paid_total_minor` | `money.amount_minor` | NOT NULL |  |  |
| `payment_method` | `text` | NOT NULL |  |  |
| `calculation_version` | `text` | NOT NULL |  |  |
| `generated_by_user_id` | `uuid` | NOT NULL |  |  |
| `generated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `receipt_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `receipt_generator_fk` — `FOREIGN KEY (tenant_id, generated_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `receipt_method_not_blank` — `CHECK ((btrim(payment_method) <> ''::text))`
- `receipt_number_not_blank` — `CHECK ((btrim(receipt_number) <> ''::text))`
- `receipt_number_unique` — `UNIQUE (tenant_id, receipt_number)`
- `receipt_one_per_bill_revision` — `UNIQUE (tenant_id, bill_id, revision)`
- `receipt_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `receipt_pkey` — `PRIMARY KEY (id)`
- `receipt_revision_positive` — `CHECK ((revision >= 1))`
- `receipt_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `receipt_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `receipt_totals_not_negative` — `CHECK ((((bill_total_minor)::bigint >= 0) AND ((tip_total_minor)::bigint >= 0) AND ((paid_total_minor)::bigint >= 0)))`

Policies:

- `receipt_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.receipt_line`

The receipt as printed, one row per line. FR-BIL-010 requires bill total, optional tip and total paid to be SEPARATE lines and FR-BIL-017 adds the payment method; the kinds are separate values and the singleton kinds are unique per receipt, so a merged line is a structural impossibility rather than a style guideline.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `receipt_id` | `uuid` | NOT NULL |  |  |
| `kind` | `docs.receipt_line_kind` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL |  |  |
| `label` | `text` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` |  |  |  |

Constraints:

- `receipt_line_amount_present_unless_method` — `CHECK ((((kind = 'payment_method'::docs.receipt_line_kind) AND (amount_minor IS NULL)) OR ((kind <> 'payment_method'::docs.receipt_line_kind) AND (amount_minor IS NOT NULL))))`
- `receipt_line_is_complete_in_its_locale` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `receipt_line_is_faithful` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `receipt_line_label_not_blank` — `CHECK ((btrim(label) <> ''::text))`
- `receipt_line_order_unique` — `UNIQUE (tenant_id, receipt_id, display_order)`
- `receipt_line_pkey` — `PRIMARY KEY (id)`
- `receipt_line_receipt_fk` — `FOREIGN KEY (tenant_id, receipt_id) REFERENCES docs.receipt(tenant_id, id) ON DELETE RESTRICT`
- `receipt_line_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `receipt_line_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `receipt_line_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `docs.render_attempt`

FR-UX-018's preview. Bytes reached a file, and that is all this records — its outcome type says rendered, not printed, and no value of it fits the column a print is recorded in. A preview can be taken as often as anybody likes, so nothing here is unique.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `kind` | `docs.document_kind` | NOT NULL |  |  |
| `receipt_id` | `uuid` |  |  |  |
| `printer_id` | `uuid` | NOT NULL |  |  |
| `outcome` | `docs.render_outcome` | NOT NULL |  |  |
| `bytes_sha256` | `character(64)` | NOT NULL |  |  |
| `byte_count` | `integer` | NOT NULL |  |  |
| `requested_by_user_id` | `uuid` | NOT NULL |  |  |
| `rendered_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `render_attempt_actor_fk` — `FOREIGN KEY (tenant_id, requested_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `render_attempt_byte_count_positive` — `CHECK ((byte_count > 0))`
- `render_attempt_digest_is_a_digest` — `CHECK ((bytes_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `render_attempt_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `render_attempt_pkey` — `PRIMARY KEY (id)`
- `render_attempt_printer_fk` — `FOREIGN KEY (tenant_id, printer_id) REFERENCES docs.printer(tenant_id, id) ON DELETE RESTRICT`
- `render_attempt_receipt_fk` — `FOREIGN KEY (tenant_id, receipt_id) REFERENCES docs.receipt(tenant_id, id) ON DELETE RESTRICT`
- `render_attempt_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `render_attempt_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `render_attempt_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `fiscal`

FR-BIL-012's port. What a fiscal document IS to this platform — a request, an outcome and a reconciliation status — with no provider's schema inside it. The provider is configuration.

#### `fiscal.adapter`

A fiscal provider, as configuration. Its mode is simulated BY CHECK and not by default: no Ethiopian fiscal integration is contracted, so no adapter may claim to be live, and the day one is contracted that CHECK is the line that has to change — visibly, in a migration, rather than in a row.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `provider` | `text` | NOT NULL |  |  |
| `mode` | `fiscal.adapter_mode` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `registered_by_user_id` | `uuid` | NOT NULL |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `adapter_pkey` — `PRIMARY KEY (id)`
- `fiscal_adapter_actor_fk` — `FOREIGN KEY (tenant_id, registered_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `fiscal_adapter_mode_is_derived` — `CHECK ((mode = 'simulated'::fiscal.adapter_mode))`
- `fiscal_adapter_mode_unique` — `UNIQUE (id, mode)`
- `fiscal_adapter_one_per_provider` — `UNIQUE (tenant_id, provider, status)`
- `fiscal_adapter_provider_shape` — `CHECK ((provider ~ '^[a-z][a-z0-9_]*$'::text))`
- `fiscal_adapter_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `fiscal_adapter_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `adapter_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fiscal.document`

FR-BIL-012's port. A fiscal document is a request against a receipt, an outcome, and a reconciliation status — and nothing in this table names a provider's field. provider_reference and provider_payload are opaque and the platform never parses them. One document per receipt, because two would make the fiscal record of a sale ambiguous.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `legal_entity_id` | `uuid` | NOT NULL |  |  |
| `adapter_id` | `uuid` | NOT NULL |  |  |
| `adapter_mode` | `fiscal.adapter_mode` | NOT NULL |  |  |
| `receipt_id` | `uuid` | NOT NULL |  |  |
| `state` | `fiscal.document_state` | NOT NULL | `'requested'::fiscal.document_state` |  |
| `provider_reference` | `text` |  |  |  |
| `provider_payload` | `jsonb` |  |  |  |
| `requested_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `submitted_at` | `timestamp with time zone` |  |  |  |
| `settled_at` | `timestamp with time zone` |  |  |  |
| `reconciled_at` | `timestamp with time zone` |  |  |  |
| `rejection_reason` | `text` |  |  |  |

Constraints:

- `document_pkey` — `PRIMARY KEY (id)`
- `fiscal_document_adapter_fk` — `FOREIGN KEY (adapter_id, adapter_mode) REFERENCES fiscal.adapter(id, mode) ON DELETE RESTRICT`
- `fiscal_document_entity_fk` — `FOREIGN KEY (tenant_id, legal_entity_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `fiscal_document_one_per_receipt` — `UNIQUE (tenant_id, receipt_id)`
- `fiscal_document_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `fiscal_document_receipt_fk` — `FOREIGN KEY (tenant_id, receipt_id) REFERENCES docs.receipt(tenant_id, id) ON DELETE RESTRICT`
- `fiscal_document_states_carry_their_times` — `CHECK ((((state = 'requested'::fiscal.document_state) AND (submitted_at IS NULL) AND (settled_at IS NULL)) OR ((state = 'submitted'::fiscal.document_state) AND (submitted_at IS NOT NULL) AND (settled_at IS NULL)) OR ((state = 'accepted'::fiscal.document_state) AND (submitted_at IS NOT NULL) AND (settled_at IS NOT NULL)) OR ((state = 'rejected'::fiscal.document_state) AND (submitted_at IS NOT NULL) AND (settled_at IS NOT NULL) AND (btrim(COALESCE(rejection_reason, ''::text)) <> ''::text)) OR ((state = 'reconciled'::fiscal.document_state) AND (submitted_at IS NOT NULL) AND (settled_at IS NOT NULL) AND (reconciled_at IS NOT NULL))))`
- `fiscal_document_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `fiscal_document_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `document_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `fulfillment`

What a station must do, and what it did (FR-FUL-001 … FR-FUL-016A). Separate from ordering by design: the order is what the customer agreed, the ticket is the work.

#### `fulfillment.priority_change`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `from_priority` | `fulfillment.priority_level` | NOT NULL |  |  |
| `to_priority` | `fulfillment.priority_level` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `applied_by_user_id` | `uuid` | NOT NULL |  |  |
| `applied_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `priority_change_actor_fk` — `FOREIGN KEY (tenant_id, applied_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `priority_change_actually_changes` — `CHECK ((from_priority <> to_priority))`
- `priority_change_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `priority_change_pkey` — `PRIMARY KEY (id)`
- `priority_change_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `priority_change_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `priority_change_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `priority_change_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.ready_notice`

FR-FUL-010, the half this gate owns: the EVENT that a ticket is ready and who it is for. Delivery is FR-NOT-001 at M3-C: there is no channel, transport or template here, and no delivery-status column for it to be mistaken for.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `assigned_user_id` | `uuid` |  |  |  |
| `became_ready_at` | `timestamp with time zone` | NOT NULL |  |  |
| `escalated_at` | `timestamp with time zone` |  |  |  |
| `escalation_after_seconds` | `integer` |  |  |  |

Constraints:

- `ready_notice_escalation_after_ready` — `CHECK (((escalated_at IS NULL) OR (escalated_at >= became_ready_at)))`
- `ready_notice_escalation_recorded_together` — `CHECK (((escalated_at IS NULL) = (escalation_after_seconds IS NULL)))`
- `ready_notice_one_per_ticket` — `UNIQUE (tenant_id, ticket_id)`
- `ready_notice_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ready_notice_pkey` — `PRIMARY KEY (id)`
- `ready_notice_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `ready_notice_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`
- `ready_notice_user_fk` — `FOREIGN KEY (tenant_id, assigned_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `ready_notice_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.routing_rule`

Where a line unit goes (FR-FUL-001). Rules belong to a VERSIONED set and a ticket records the version that routed it, so a rule change does not rewrite history. Precedence is explicit: a rule set whose meaning depended on row order would change behaviour when it was reseeded.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `rule_set_id` | `uuid` | NOT NULL |  |  |
| `precedence` | `integer` | NOT NULL |  |  |
| `item_id` | `uuid` |  |  |  |
| `variant_id` | `uuid` |  |  |  |
| `category_id` | `uuid` |  |  |  |
| `target_station_node_id` | `uuid` | NOT NULL |  |  |

Constraints:

- `routing_rule_at_most_one_subject` — `CHECK ((((((item_id IS NOT NULL))::integer + ((variant_id IS NOT NULL))::integer) + ((category_id IS NOT NULL))::integer) <= 1))`
- `routing_rule_category_fk` — `FOREIGN KEY (category_id) REFERENCES menu.category(id) ON DELETE RESTRICT`
- `routing_rule_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE RESTRICT`
- `routing_rule_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `routing_rule_pkey` — `PRIMARY KEY (id)`
- `routing_rule_precedence_positive` — `CHECK ((precedence > 0))`
- `routing_rule_precedence_unique` — `UNIQUE (rule_set_id, precedence)`
- `routing_rule_set_fk` — `FOREIGN KEY (tenant_id, rule_set_id) REFERENCES fulfillment.routing_rule_set(tenant_id, id) ON DELETE RESTRICT`
- `routing_rule_station_fk` — `FOREIGN KEY (tenant_id, target_station_node_id) REFERENCES fulfillment.station_profile(tenant_id, station_node_id) ON DELETE RESTRICT`
- `routing_rule_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `routing_rule_variant_fk` — `FOREIGN KEY (variant_id) REFERENCES menu.item_variant(id) ON DELETE RESTRICT`

Policies:

- `routing_rule_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.routing_rule_set`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `version` | `integer` | NOT NULL |  |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `approved_by_user_id` | `uuid` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `routing_rule_set_approver_fk` — `FOREIGN KEY (tenant_id, approved_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `routing_rule_set_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `routing_rule_set_pkey` — `PRIMARY KEY (id)`
- `routing_rule_set_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `routing_rule_set_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `routing_rule_set_version_positive` — `CHECK ((version > 0))`
- `routing_rule_set_version_unique` — `UNIQUE (tenant_id, outlet_id, version)`
- `routing_rule_set_window_valid` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`

Policies:

- `routing_rule_set_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.serve_record`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `collected_by_user_id` | `uuid` | NOT NULL |  |  |
| `collected_at` | `timestamp with time zone` | NOT NULL |  |  |
| `served_by_user_id` | `uuid` |  |  |  |
| `served_at` | `timestamp with time zone` |  |  |  |
| `exception_kind` | `fulfillment.serve_exception` |  |  |  |
| `exception_note` | `text` |  |  |  |

Constraints:

- `serve_record_collector_fk` — `FOREIGN KEY (tenant_id, collected_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `serve_record_exception_explained` — `CHECK ((((exception_kind IS NULL) AND (exception_note IS NULL)) OR ((exception_kind IS NOT NULL) AND (btrim(COALESCE(exception_note, ''::text)) <> ''::text))))`
- `serve_record_one_per_ticket` — `UNIQUE (tenant_id, ticket_id)`
- `serve_record_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `serve_record_pkey` — `PRIMARY KEY (id)`
- `serve_record_server_fk` — `FOREIGN KEY (tenant_id, served_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `serve_record_service_recorded_together` — `CHECK (((served_at IS NULL) = (served_by_user_id IS NULL)))`
- `serve_record_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `serve_record_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `serve_record_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.station_profile`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `station_node_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `station_kind` | `fulfillment.station_kind` | NOT NULL |  |  |
| `sla_minutes` | `integer` |  |  |  |
| `concurrent_ticket_threshold` | `integer` |  |  |  |
| `allergy_acknowledgement_required` | `boolean` | NOT NULL | `true` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `station_profile_node_fk` — `FOREIGN KEY (tenant_id, station_node_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `station_profile_one_per_outlet` — `UNIQUE (tenant_id, outlet_id, station_node_id)`
- `station_profile_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `station_profile_pkey` — `PRIMARY KEY (station_node_id)`
- `station_profile_sla_sane` — `CHECK (((sla_minutes IS NULL) OR ((sla_minutes > 0) AND (sla_minutes <= 600))))`
- `station_profile_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `station_profile_tenant_id_unique` — `UNIQUE (tenant_id, station_node_id)`
- `station_profile_threshold_positive` — `CHECK (((concurrent_ticket_threshold IS NULL) OR (concurrent_ticket_threshold > 0)))`

Policies:

- `station_profile_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.station_ticket_document`

FR-FUL-014. Deduplicated by a unique key on (ticket, revision), so a second request for the same revision cannot store a second document however many times it is made. A document, not a print job — the resilient local print path is M5a.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `revision` | `integer` | NOT NULL |  |  |
| `trigger_reason` | `fulfillment.document_trigger` | NOT NULL |  |  |
| `content` | `text` | NOT NULL |  |  |
| `content_digest` | `bytea` | NOT NULL |  |  |
| `allergy_line_count` | `integer` | NOT NULL |  |  |
| `generated_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `station_ticket_document_allergy_count_sane` — `CHECK ((allergy_line_count >= 0))`
- `station_ticket_document_content_not_blank` — `CHECK ((btrim(content) <> ''::text))`
- `station_ticket_document_digest_is_sha256` — `CHECK ((octet_length(content_digest) = 32))`
- `station_ticket_document_one_per_revision` — `UNIQUE (tenant_id, ticket_id, revision)`
- `station_ticket_document_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `station_ticket_document_pkey` — `PRIMARY KEY (id)`
- `station_ticket_document_revision_positive` — `CHECK ((revision > 0))`
- `station_ticket_document_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `station_ticket_document_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `station_ticket_document_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.station_transfer`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `from_station_node_id` | `uuid` | NOT NULL |  |  |
| `to_station_node_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `transferred_by_user_id` | `uuid` | NOT NULL |  |  |
| `transferred_at` | `timestamp with time zone` | NOT NULL |  |  |
| `units_moved` | `integer` | NOT NULL |  |  |

Constraints:

- `station_transfer_actor_fk` — `FOREIGN KEY (tenant_id, transferred_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `station_transfer_actually_moves` — `CHECK ((from_station_node_id <> to_station_node_id))`
- `station_transfer_from_fk` — `FOREIGN KEY (tenant_id, from_station_node_id) REFERENCES fulfillment.station_profile(tenant_id, station_node_id) ON DELETE RESTRICT`
- `station_transfer_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `station_transfer_pkey` — `PRIMARY KEY (id)`
- `station_transfer_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `station_transfer_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `station_transfer_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`
- `station_transfer_to_fk` — `FOREIGN KEY (tenant_id, to_station_node_id) REFERENCES fulfillment.station_profile(tenant_id, station_node_id) ON DELETE RESTRICT`
- `station_transfer_units_positive` — `CHECK ((units_moved > 0))`

Policies:

- `station_transfer_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.ticket`

What one station must do for one order (FR-FUL-002). A projection of fulfillment.ticket_event: nothing writes here except fulfillment.apply_ticket_event(), and the state column is additionally guarded by a trigger that consults fulfillment.transition — so the fold itself cannot write an illegal state.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `station_node_id` | `uuid` | NOT NULL |  |  |
| `state` | `fulfillment.ticket_state` | NOT NULL |  |  |
| `priority` | `fulfillment.priority_level` | NOT NULL |  |  |
| `routing_rule_set_id` | `uuid` | NOT NULL |  |  |
| `station_sequence` | `integer` | NOT NULL |  |  |
| `released_at` | `timestamp with time zone` | NOT NULL |  |  |
| `sla_due_at` | `timestamp with time zone` |  |  |  |
| `acknowledged_at` | `timestamp with time zone` |  |  |  |
| `preparation_started_at` | `timestamp with time zone` |  |  |  |
| `ready_at` | `timestamp with time zone` |  |  |  |
| `collected_at` | `timestamp with time zone` |  |  |  |
| `completed_at` | `timestamp with time zone` |  |  |  |
| `allergy_acknowledged_at` | `timestamp with time zone` |  |  |  |
| `allergy_acknowledged_by_user_id` | `uuid` |  |  |  |
| `ledger_sequence` | `integer` | NOT NULL |  |  |

Constraints:

- `ticket_ack_recorded_together` — `CHECK (((allergy_acknowledged_at IS NULL) = (allergy_acknowledged_by_user_id IS NULL)))`
- `ticket_ack_user_fk` — `FOREIGN KEY (tenant_id, allergy_acknowledged_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `ticket_ledger_sequence_positive` — `CHECK ((ledger_sequence > 0))`
- `ticket_one_per_order_station` — `UNIQUE (tenant_id, order_id, station_node_id)`
- `ticket_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `ticket_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ticket_pkey` — `PRIMARY KEY (id)`
- `ticket_rule_set_fk` — `FOREIGN KEY (tenant_id, routing_rule_set_id) REFERENCES fulfillment.routing_rule_set(tenant_id, id) ON DELETE RESTRICT`
- `ticket_sequence_positive` — `CHECK ((station_sequence > 0))`
- `ticket_station_fk` — `FOREIGN KEY (tenant_id, station_node_id) REFERENCES fulfillment.station_profile(tenant_id, station_node_id) ON DELETE RESTRICT`
- `ticket_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `ticket_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `ticket_timestamps_ordered` — `CHECK ((((acknowledged_at IS NULL) OR (acknowledged_at >= released_at)) AND ((preparation_started_at IS NULL) OR (acknowledged_at IS NOT NULL)) AND ((ready_at IS NULL) OR (preparation_started_at IS NOT NULL)) AND ((collected_at IS NULL) OR (ready_at IS NOT NULL)) AND ((completed_at IS NULL) OR (collected_at IS NOT NULL))))`

Policies:

- `ticket_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.ticket_event`

The authoritative, append-only fulfillment ledger (FR-FUL-002, FR-FUL-005). Every ticket projection and every station timeline entry is folded out of it, so a station's history has no destructive edit path and rebuilds deterministically alongside the order projections it belongs beside.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `kind` | `fulfillment.ticket_event_kind` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `actor_kind` | `ordering.actor_kind` | NOT NULL |  |  |
| `actor_user_id` | `uuid` |  |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `before` | `jsonb` |  |  |  |
| `after` | `jsonb` | NOT NULL |  |  |

Constraints:

- `ticket_event_actor_consistent` — `CHECK ((((actor_kind = 'staff'::ordering.actor_kind) AND (actor_user_id IS NOT NULL)) OR ((actor_kind = 'system'::ordering.actor_kind) AND (actor_user_id IS NULL))))`
- `ticket_event_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `ticket_event_before_required` — `CHECK (((kind = 'released'::fulfillment.ticket_event_kind) = (before IS NULL)))`
- `ticket_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ticket_event_pkey` — `PRIMARY KEY (id)`
- `ticket_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `ticket_event_reason_required` — `CHECK (((kind = ANY (ARRAY['recalled'::fulfillment.ticket_event_kind, 'reprioritised'::fulfillment.ticket_event_kind, 'transferred'::fulfillment.ticket_event_kind, 'waste'::fulfillment.ticket_event_kind])) = (reason_code_id IS NOT NULL)))`
- `ticket_event_sequence_positive` — `CHECK ((sequence_number > 0))`
- `ticket_event_sequence_unique` — `UNIQUE (tenant_id, ticket_id, sequence_number)`
- `ticket_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `ticket_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.ticket_line`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `order_line_id` | `uuid` | NOT NULL |  |  |
| `quantity` | `integer` | NOT NULL |  |  |
| `ready_quantity` | `integer` | NOT NULL | `0` |  |
| `item_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |

Constraints:

- `ticket_line_one_per_order_line` — `UNIQUE (ticket_id, order_line_id)`
- `ticket_line_order_line_fk` — `FOREIGN KEY (tenant_id, order_line_id) REFERENCES ordering.order_line(tenant_id, id) DEFERRABLE INITIALLY DEFERRED`
- `ticket_line_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ticket_line_pkey` — `PRIMARY KEY (id)`
- `ticket_line_quantity_positive` — `CHECK ((quantity > 0))`
- `ticket_line_readiness_within_quantity` — `CHECK (((ready_quantity >= 0) AND (ready_quantity <= quantity)))`
- `ticket_line_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `ticket_line_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `ticket_line_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`
- `ticket_line_units_within_order` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`

Policies:

- `ticket_line_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.ticket_recall`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `recalled_from` | `fulfillment.ticket_state` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `recalled_by_user_id` | `uuid` | NOT NULL |  |  |
| `recalled_at` | `timestamp with time zone` | NOT NULL |  |  |
| `seconds_since_completion` | `integer` | NOT NULL |  |  |

Constraints:

- `ticket_recall_actor_fk` — `FOREIGN KEY (tenant_id, recalled_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `ticket_recall_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ticket_recall_pkey` — `PRIMARY KEY (id)`
- `ticket_recall_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `ticket_recall_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `ticket_recall_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`
- `ticket_recall_window_not_negative` — `CHECK ((seconds_since_completion >= 0))`

Policies:

- `ticket_recall_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `fulfillment.transition`

The thirteen edges of SM-FULFILLMENT-TICKET. Consulted by a trigger on every state change, so an illegal transition is refused by the database and not merely by the function that meant to write it (the package's fourth invariant). Read-only to the application role: a machine an application can rewrite is not a machine.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `from_state` | `fulfillment.ticket_state` | NOT NULL |  |  |
| `to_state` | `fulfillment.ticket_state` | NOT NULL |  |  |
| `reason` | `text` | NOT NULL |  |  |

Constraints:

- `transition_is_a_move` — `CHECK ((from_state <> to_state))`
- `transition_pkey` — `PRIMARY KEY (from_state, to_state)`
- `transition_reason_not_blank` — `CHECK ((btrim(reason) <> ''::text))`

#### `fulfillment.waste_event`

FR-FUL-016A. Rework, remake and SERVICE waste, each with reason, actor and the linked order and ticket. The package's third invariant is explicit that Phase 1 posts no consumption against any of this, and there is nothing in this schema it could post against.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `ticket_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `kind` | `fulfillment.waste_kind` | NOT NULL |  |  |
| `units_affected` | `integer` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `recorded_by_user_id` | `uuid` | NOT NULL |  |  |
| `recorded_at` | `timestamp with time zone` | NOT NULL |  |  |
| `note` | `text` | NOT NULL |  |  |

Constraints:

- `waste_event_actor_fk` — `FOREIGN KEY (tenant_id, recorded_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `waste_event_note_not_blank` — `CHECK ((btrim(note) <> ''::text))`
- `waste_event_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `waste_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `waste_event_pkey` — `PRIMARY KEY (id)`
- `waste_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `waste_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `waste_event_ticket_fk` — `FOREIGN KEY (tenant_id, ticket_id) REFERENCES fulfillment.ticket(tenant_id, id) ON DELETE RESTRICT`
- `waste_event_units_positive` — `CHECK ((units_affected > 0))`

Policies:

- `waste_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `identity`

Identity, memberships, sessions, step-up authentication and service principals.

#### `identity.auth_attempt`

Authentication attempts, keyed by a digest of the identifier so no phone number or email address is stored here. Per-node counters only.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `subject_digest` | `bytea` | NOT NULL |  |  |
| `succeeded` | `boolean` | NOT NULL |  |  |
| `attempted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `auth_attempt_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `auth_attempt_pkey` — `PRIMARY KEY (id)`
- `auth_attempt_subject_is_a_digest` — `CHECK ((octet_length(subject_digest) = 32))`
- `auth_attempt_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE CASCADE`

Policies:

- `auth_attempt_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.auth_lockout`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `subject_digest` | `bytea` | NOT NULL |  |  |
| `locked_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `locked_until` | `timestamp with time zone` | NOT NULL |  |  |
| `failure_count` | `integer` | NOT NULL |  |  |

Constraints:

- `auth_lockout_failure_count_positive` — `CHECK ((failure_count > 0))`
- `auth_lockout_pkey` — `PRIMARY KEY (tenant_id, subject_digest)`
- `auth_lockout_subject_is_a_digest` — `CHECK ((octet_length(subject_digest) = 32))`
- `auth_lockout_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE CASCADE`
- `auth_lockout_window_valid` — `CHECK ((locked_until > locked_at))`

Policies:

- `auth_lockout_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.auth_provider_binding`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `user_account_id` | `uuid` | NOT NULL |  |  |
| `provider_name` | `text` | NOT NULL |  |  |
| `provider_subject_ref` | `text` | NOT NULL |  | Opaque provider-side identifier. Never parsed, never given meaning here. |
| `bound_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `auth_provider_binding_pkey` — `PRIMARY KEY (id)`
- `auth_provider_binding_row_version_positive` — `CHECK ((row_version > 0))`
- `auth_provider_binding_unique` — `UNIQUE (tenant_id, provider_name, provider_subject_ref)`
- `auth_provider_binding_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `auth_provider_binding_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.credential`

Password, one-time code, quick PIN and service secret digests. Plaintext never enters this table: the 32-byte length CHECK makes it structurally impossible.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `user_account_id` | `uuid` |  |  |  |
| `kind` | `identity.credential_kind` | NOT NULL |  |  |
| `secret_digest` | `bytea` | NOT NULL |  |  |
| `digest_algorithm` | `text` | NOT NULL |  |  |
| `confers_strength` | `identity.auth_strength` | NOT NULL |  |  |
| `expires_at` | `timestamp with time zone` |  |  |  |
| `rotated_at` | `timestamp with time zone` |  |  |  |
| `revoked_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `credential_algorithm_not_blank` — `CHECK ((btrim(digest_algorithm) <> ''::text))`
- `credential_digest_is_a_digest` — `CHECK ((octet_length(secret_digest) = 32))`
- `credential_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `credential_pkey` — `PRIMARY KEY (id)`
- `credential_quick_pin_is_low_strength` — `CHECK (((kind <> 'quick_pin'::identity.credential_kind) OR (confers_strength = 'low'::identity.auth_strength)))`
- `credential_quick_pin_is_outlet_scoped` — `CHECK (((kind <> 'quick_pin'::identity.credential_kind) OR (outlet_id IS NOT NULL)))`
- `credential_row_version_positive` — `CHECK ((row_version > 0))`
- `credential_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `credential_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.governed_action`

Actions requiring more than routine authentication. Registered at M1 for role and configuration changes; refunds, reversals and payouts are registered for M4 and exports for M6 so those gates inherit the enforcement point.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `minimum_strength` | `identity.auth_strength` | NOT NULL |  |  |
| `step_up_required` | `boolean` | NOT NULL | `false` |  |
| `step_up_max_age` | `interval` |  |  |  |
| `governed_from_gate` | `text` | NOT NULL |  |  |

Constraints:

- `governed_action_code_not_blank` — `CHECK ((btrim(action_code) <> ''::text))`
- `governed_action_pkey` — `PRIMARY KEY (tenant_id, action_code)`
- `governed_action_step_up_has_window` — `CHECK (((step_up_required = false) OR (step_up_max_age IS NOT NULL)))`
- `governed_action_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE CASCADE`

Policies:

- `governed_action_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.identity_channel`

Login channels. Either a verified phone or a verified email is sufficient to identify a user (FR-AUTH-001); an unverified channel authenticates nobody.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `user_account_id` | `uuid` | NOT NULL |  |  |
| `channel` | `identity.channel_kind` | NOT NULL |  |  |
| `channel_value` | `text` | NOT NULL |  |  |
| `verified_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `identity_channel_pkey` — `PRIMARY KEY (id)`
- `identity_channel_row_version_positive` — `CHECK ((row_version > 0))`
- `identity_channel_unique` — `UNIQUE (tenant_id, channel, channel_value)`
- `identity_channel_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `identity_channel_value_not_blank` — `CHECK ((btrim(channel_value) <> ''::text))`

Policies:

- `identity_channel_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.membership`

Explicit tenant/outlet role assignment (FR-AUTH-008). Staff access derives from these rows and nowhere else. Withdrawing one revokes dependent sessions at once.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `user_account_id` | `uuid` | NOT NULL |  |  |
| `role_id` | `uuid` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `withdrawn_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `membership_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `membership_pkey` — `PRIMARY KEY (id)`
- `membership_role_fk` — `FOREIGN KEY (tenant_id, role_id) REFERENCES identity.role(tenant_id, id) ON DELETE RESTRICT`
- `membership_row_version_positive` — `CHECK ((row_version > 0))`
- `membership_unique` — `UNIQUE (tenant_id, user_account_id, outlet_id, role_id)`
- `membership_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `membership_withdrawal_consistent` — `CHECK ((((status = 'active'::org.lifecycle_status) AND (withdrawn_at IS NULL)) OR (status <> 'active'::org.lifecycle_status)))`

Policies:

- `membership_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.otp_transmission`

Record of one-time-code transmissions. Never stores the code itself. The mode column is immutable (see the trigger below) so a simulated result cannot be promoted to a live one.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `identity_channel_id` | `uuid` | NOT NULL |  |  |
| `mode` | `identity.transmission_mode` | NOT NULL |  |  |
| `provider_name` | `text` | NOT NULL |  |  |
| `provider_result_ref` | `text` |  |  |  |
| `requested_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `otp_transmission_channel_fk` — `FOREIGN KEY (identity_channel_id) REFERENCES identity.identity_channel(id) ON DELETE RESTRICT`
- `otp_transmission_pkey` — `PRIMARY KEY (id)`
- `otp_transmission_simulated_has_no_provider_result` — `CHECK (((mode <> 'simulated'::identity.transmission_mode) OR (provider_result_ref IS NULL)))`
- `otp_transmission_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `otp_transmission_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.recovery_request`

Administrator-controlled recovery. Emits a security event on completion; durable audit storage is M1-C and is deliberately not built here.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `subject_user_id` | `uuid` | NOT NULL |  |  |
| `requested_by_user_id` | `uuid` | NOT NULL |  |  |
| `identity_verified_at` | `timestamp with time zone` |  |  |  |
| `old_factors_revoked_at` | `timestamp with time zone` |  |  |  |
| `completed_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `recovery_completion_requires_verification_and_revocation` — `CHECK (((completed_at IS NULL) OR ((identity_verified_at IS NOT NULL) AND (old_factors_revoked_at IS NOT NULL))))`
- `recovery_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `recovery_request_pkey` — `PRIMARY KEY (id)`
- `recovery_requester_fk` — `FOREIGN KEY (tenant_id, requested_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `recovery_row_version_positive` — `CHECK ((row_version > 0))`
- `recovery_subject_fk` — `FOREIGN KEY (tenant_id, subject_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `recovery_request_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.role`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `role_code` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `role_code_unique` — `UNIQUE (tenant_id, role_code)`
- `role_pkey` — `PRIMARY KEY (id)`
- `role_row_version_positive` — `CHECK ((row_version > 0))`
- `role_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `role_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `role_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.role_action`

Which actions a role may perform. Absence of a row denies the action: there is no implicit grant.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `role_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `granted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `role_action_code_not_blank` — `CHECK ((btrim(action_code) <> ''::text))`
- `role_action_pkey` — `PRIMARY KEY (role_id, action_code)`
- `role_action_role_fk` — `FOREIGN KEY (tenant_id, role_id) REFERENCES identity.role(tenant_id, id) ON DELETE CASCADE`

Policies:

- `role_action_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.service_principal`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `principal_code` | `text` | NOT NULL |  |  |
| `class` | `identity.principal_class` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `rotated_at` | `timestamp with time zone` |  |  |  |
| `revoked_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `service_principal_code_unique` — `UNIQUE (tenant_id, principal_code)`
- `service_principal_pkey` — `PRIMARY KEY (id)`
- `service_principal_row_version_positive` — `CHECK ((row_version > 0))`
- `service_principal_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `service_principal_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `service_principal_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `identity.service_principal_scope`

Exhaustive list of what a principal may do and where. Absence denies.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `service_principal_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `granted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `service_principal_scope_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `service_principal_scope_pkey` — `PRIMARY KEY (service_principal_id, action_code, outlet_id)`
- `service_principal_scope_principal_fk` — `FOREIGN KEY (tenant_id, service_principal_id) REFERENCES identity.service_principal(tenant_id, id) ON DELETE CASCADE`

Policies:

- `service_principal_scope_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.session`

Live sessions, listable and revocable per user and per device (FR-AUTH-004). Stores only the token digest; the token itself never reaches the database.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `user_account_id` | `uuid` |  |  |  |
| `service_principal_id` | `uuid` |  |  |  |
| `device_id` | `uuid` |  |  |  |
| `token_digest` | `bytea` | NOT NULL |  |  |
| `established_with` | `identity.auth_strength` | NOT NULL |  |  |
| `issued_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `expires_at` | `timestamp with time zone` | NOT NULL |  |  |
| `last_rotated_at` | `timestamp with time zone` |  |  |  |
| `revoked_at` | `timestamp with time zone` |  |  |  |
| `revoked_reason` | `identity.revocation_reason` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `session_device_fk` — `FOREIGN KEY (tenant_id, device_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `session_expires_after_issue` — `CHECK ((expires_at > issued_at))`
- `session_has_exactly_one_subject` — `CHECK (((user_account_id IS NOT NULL) <> (service_principal_id IS NOT NULL)))`
- `session_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `session_pkey` — `PRIMARY KEY (id)`
- `session_revocation_consistent` — `CHECK (((revoked_at IS NULL) = (revoked_reason IS NULL)))`
- `session_row_version_positive` — `CHECK ((row_version > 0))`
- `session_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `session_token_digest_unique` — `UNIQUE (token_digest)`
- `session_token_is_a_digest` — `CHECK ((octet_length(token_digest) = 32))`
- `session_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `session_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.step_up_grant`

Evidence that stronger authentication happened recently. Age is compared against the governed action window at the moment of use; a grant is never evergreen.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `session_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `granted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `consumed_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `step_up_grant_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `step_up_grant_pkey` — `PRIMARY KEY (id)`
- `step_up_grant_session_fk` — `FOREIGN KEY (tenant_id, session_id) REFERENCES identity.session(tenant_id, id) ON DELETE CASCADE`

Policies:

- `step_up_grant_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.terminal_trust`

Terminals at which a quick PIN may be presented. A quick PIN offered anywhere else authenticates nobody.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `device_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `trusted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `withdrawn_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `terminal_trust_device_fk` — `FOREIGN KEY (tenant_id, device_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `terminal_trust_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `terminal_trust_pkey` — `PRIMARY KEY (device_id)`

Policies:

- `terminal_trust_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `identity.user_account`

A staff identity within one tenant. Access is not conferred here — it comes entirely from identity.membership (FR-AUTH-008).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `staff_number` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `deactivated_at` | `timestamp with time zone` |  |  |  |
| `archived_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `user_account_lifecycle_consistent` — `CHECK ((((status = 'active'::org.lifecycle_status) AND (deactivated_at IS NULL) AND (archived_at IS NULL)) OR ((status = 'inactive'::org.lifecycle_status) AND (deactivated_at IS NOT NULL) AND (archived_at IS NULL)) OR ((status = 'archived'::org.lifecycle_status) AND (archived_at IS NOT NULL))))`
- `user_account_pkey` — `PRIMARY KEY (id)`
- `user_account_row_version_positive` — `CHECK ((row_version > 0))`
- `user_account_staff_number_unique` — `UNIQUE (tenant_id, staff_number)`
- `user_account_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `user_account_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `user_account_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

### `integration`

FR-INT-005, FR-INT-007, FR-INT-014. Idempotency, the dead-letter queue and the correlation chain's newest link. Its own schema because M4's payment adapters and M5a's synchronization use the same queue, and a queue inside notify would have to move before they could.

#### `integration.dead_letter`

FR-INT-007. Operator-visible, with the reason and the attempt count that got it here. It holds the work by REFERENCE: a copy would let a replay act on a stale version of something that has since moved on. M4 and M5a extend job_kind; the queue, the door and the replay control are these.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `job_kind` | `integration.job_kind` | NOT NULL |  |  |
| `subject_id` | `uuid` | NOT NULL |  |  |
| `failure_reason` | `text` | NOT NULL |  |  |
| `attempts` | `integer` | NOT NULL |  |  |
| `first_failed_at` | `timestamp with time zone` | NOT NULL |  |  |
| `last_failed_at` | `timestamp with time zone` | NOT NULL |  |  |
| `state` | `integration.dead_letter_state` | NOT NULL | `'open'::integration.dead_letter_state` |  |
| `resolved_at` | `timestamp with time zone` |  |  |  |
| `resolved_by_user_id` | `uuid` |  |  |  |
| `resolution_note` | `text` |  |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |

Constraints:

- `dead_letter_attempts_positive` — `CHECK ((attempts > 0))`
- `dead_letter_one_per_subject` — `UNIQUE (tenant_id, job_kind, subject_id)`
- `dead_letter_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `dead_letter_pkey` — `PRIMARY KEY (id)`
- `dead_letter_reason_not_blank` — `CHECK ((btrim(failure_reason) <> ''::text))`
- `dead_letter_resolution_is_attributed` — `CHECK ((((state = 'open'::integration.dead_letter_state) = (resolved_at IS NULL)) AND ((state = 'open'::integration.dead_letter_state) = (resolved_by_user_id IS NULL))))`
- `dead_letter_resolver_fk` — `FOREIGN KEY (tenant_id, resolved_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `dead_letter_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `dead_letter_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `dead_letter_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `integration.protocol`

FR-INT-013. Which protocols this system speaks and the version range it understands for each. Only the protocols that EXIST are here: the outlet-node synchronization protocol is M5a's and is absent rather than declared at version zero, because M1-D's rule is that health and capability advertise what exists.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `protocol` | `text` | NOT NULL |  |  |
| `current_version` | `integer` | NOT NULL |  |  |
| `minimum_supported_version` | `integer` | NOT NULL |  |  |
| `description` | `text` | NOT NULL |  |  |

Constraints:

- `protocol_name_shape` — `CHECK ((protocol ~ '^[a-z][a-z0-9_.]*$'::text))`
- `protocol_pkey` — `PRIMARY KEY (protocol)`
- `protocol_range_is_a_range` — `CHECK ((current_version >= minimum_supported_version))`
- `protocol_versions_positive` — `CHECK ((minimum_supported_version >= 1))`

### `menu`

Menu structure, pricing, availability and translation storage (M2-A). Independent of recipe and inventory identities: no column here references either, and the verification suite proves it against the pinned fenced vocabulary rather than a list written by hand.

#### `menu.assignment`

Where and when a menu applies (FR-MNU-002A): outlet, service area, channel, daypart and date range. Customer-segment targeting is Phase 2 CRM, was removed at v2.0.9 and is fenced — no column here can express it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `menu_id` | `uuid` | NOT NULL |  |  |
| `service_area_id` | `uuid` |  |  |  |
| `channel` | `menu.sales_channel` | NOT NULL |  |  |
| `daypart_id` | `uuid` |  |  |  |
| `effective_from` | `date` | NOT NULL |  |  |
| `effective_to` | `date` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `assignment_daypart_fk` — `FOREIGN KEY (daypart_id) REFERENCES menu.daypart(id) ON DELETE RESTRICT`
- `assignment_menu_fk` — `FOREIGN KEY (menu_id) REFERENCES menu.menu(id) ON DELETE RESTRICT`
- `assignment_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `assignment_pkey` — `PRIMARY KEY (id)`
- `assignment_range_ordered` — `CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)))`
- `assignment_service_area_fk` — `FOREIGN KEY (tenant_id, service_area_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `assignment_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `assignment_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.availability`

Availability as a state (FR-MNU-007). There is no numeric column here and none anywhere else in this schema that could hold a remaining count, so the exact figure cannot be disclosed by this model — it does not exist in it. "limited" signals scarcity without quantifying it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `item_id` | `uuid` |  |  |  |
| `variant_id` | `uuid` |  |  |  |
| `modifier_id` | `uuid` |  |  |  |
| `state` | `menu.availability_state` | NOT NULL | `'available'::menu.availability_state` |  |
| `available_from` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `availability_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE CASCADE`
- `availability_modifier_fk` — `FOREIGN KEY (modifier_id) REFERENCES menu.modifier(id) ON DELETE CASCADE`
- `availability_one_subject` — `CHECK ((((((item_id IS NOT NULL))::integer + ((variant_id IS NOT NULL))::integer) + ((modifier_id IS NOT NULL))::integer) = 1))`
- `availability_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `availability_pkey` — `PRIMARY KEY (id)`
- `availability_scheduled_has_time` — `CHECK (((state = 'scheduled_later'::menu.availability_state) = (available_from IS NOT NULL)))`
- `availability_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `availability_variant_fk` — `FOREIGN KEY (variant_id) REFERENCES menu.item_variant(id) ON DELETE CASCADE`

Policies:

- `availability_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.availability_pause`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `availability_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `paused_by_user_id` | `uuid` | NOT NULL |  |  |
| `paused_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `expected_return_at` | `timestamp with time zone` |  |  |  |
| `released_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `availability_pause_actor_fk` — `FOREIGN KEY (tenant_id, paused_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `availability_pause_availability_fk` — `FOREIGN KEY (availability_id) REFERENCES menu.availability(id) ON DELETE CASCADE`
- `availability_pause_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `availability_pause_pkey` — `PRIMARY KEY (id)`
- `availability_pause_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `availability_pause_release_after_pause` — `CHECK (((released_at IS NULL) OR (released_at >= paused_at)))`
- `availability_pause_return_after_pause` — `CHECK (((expected_return_at IS NULL) OR (expected_return_at > paused_at)))`
- `availability_pause_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `availability_pause_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.category`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `menu_id` | `uuid` | NOT NULL |  |  |
| `parent_category_id` | `uuid` |  |  |  |
| `category_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `category_code_not_blank` — `CHECK ((btrim(category_code) <> ''::text))`
- `category_code_unique` — `UNIQUE (tenant_id, menu_id, category_code)`
- `category_menu_fk` — `FOREIGN KEY (menu_id) REFERENCES menu.menu(id) ON DELETE RESTRICT`
- `category_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `category_parent_fk` — `FOREIGN KEY (parent_category_id) REFERENCES menu.category(id) ON DELETE RESTRICT`
- `category_pkey` — `PRIMARY KEY (id)`
- `category_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `category_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.daypart`

Tenant-defined service windows (FR-MNU-010): breakfast, lunch, dinner, late-night and any window a tenant names. Times are OUTLET-LOCAL wall clock. A window whose end is before its start crosses midnight and is read that way.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `daypart_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `starts_at_local` | `time without time zone` | NOT NULL |  |  |
| `ends_at_local` | `time without time zone` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `daypart_code_not_blank` — `CHECK ((btrim(daypart_code) <> ''::text))`
- `daypart_code_unique` — `UNIQUE (tenant_id, outlet_id, daypart_code)`
- `daypart_not_empty` — `CHECK ((starts_at_local <> ends_at_local))`
- `daypart_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `daypart_pkey` — `PRIMARY KEY (id)`
- `daypart_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `daypart_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.image`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `entity` | `menu.menu_entity` | NOT NULL |  |  |
| `entity_id` | `uuid` | NOT NULL |  |  |
| `storage_key` | `text` | NOT NULL |  |  |
| `canonical_alt_text` | `text` | NOT NULL |  |  |
| `focal_x` | `money.percentage` | NOT NULL | `50` | Focal point as a percentage of width, exact (money.percentage, numeric with declared scale). A crop that moved because a float drifted would be a visible defect. |
| `focal_y` | `money.percentage` | NOT NULL | `50` |  |
| `source_width_px` | `integer` | NOT NULL |  |  |
| `source_height_px` | `integer` | NOT NULL |  |  |
| `is_private` | `boolean` | NOT NULL | `true` |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `image_alt_text_not_blank` — `CHECK ((btrim(canonical_alt_text) <> ''::text))`
- `image_dimensions_positive` — `CHECK (((source_width_px > 0) AND (source_height_px > 0)))`
- `image_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `image_pkey` — `PRIMARY KEY (id)`
- `image_source_is_private` — `CHECK (is_private)`
- `image_storage_key_not_blank` — `CHECK ((btrim(storage_key) <> ''::text))`
- `image_storage_key_unique` — `UNIQUE (tenant_id, storage_key)`
- `image_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `image_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.image_derivative`

Responsive derivatives of a source asset (FR-MNU-011). Each is a stored object with its own key; none is public. Access to any of them goes through the same signed, expiring, authorized URL path as the source.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `image_id` | `uuid` | NOT NULL |  |  |
| `width_px` | `integer` | NOT NULL |  |  |
| `height_px` | `integer` | NOT NULL |  |  |
| `format` | `menu.image_format` | NOT NULL |  |  |
| `storage_key` | `text` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `image_derivative_dimensions_positive` — `CHECK (((width_px > 0) AND (height_px > 0)))`
- `image_derivative_image_fk` — `FOREIGN KEY (image_id) REFERENCES menu.image(id) ON DELETE CASCADE`
- `image_derivative_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `image_derivative_pkey` — `PRIMARY KEY (id)`
- `image_derivative_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `image_derivative_unique` — `UNIQUE (image_id, width_px, format)`

Policies:

- `image_derivative_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.item_group`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `menu_id` | `uuid` | NOT NULL |  |  |
| `group_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `item_group_code_unique` — `UNIQUE (tenant_id, menu_id, group_code)`
- `item_group_menu_fk` — `FOREIGN KEY (menu_id) REFERENCES menu.menu(id) ON DELETE RESTRICT`
- `item_group_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `item_group_pkey` — `PRIMARY KEY (id)`
- `item_group_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `item_group_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.item_group_member`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `item_group_id` | `uuid` | NOT NULL |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `outlet_id` | `uuid` |  |  |  |

Constraints:

- `item_group_member_group_fk` — `FOREIGN KEY (item_group_id) REFERENCES menu.item_group(id) ON DELETE CASCADE`
- `item_group_member_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE CASCADE`
- `item_group_member_pkey` — `PRIMARY KEY (item_group_id, item_id)`
- `item_group_member_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `item_group_member_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.item_modifier_group`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `modifier_group_id` | `uuid` | NOT NULL |  |  |
| `display_order` | `integer` | NOT NULL | `0` |  |

Constraints:

- `item_modifier_group_group_fk` — `FOREIGN KEY (modifier_group_id) REFERENCES menu.modifier_group(id) ON DELETE RESTRICT`
- `item_modifier_group_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE CASCADE`
- `item_modifier_group_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `item_modifier_group_pkey` — `PRIMARY KEY (item_id, modifier_group_id)`
- `item_modifier_group_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `item_modifier_group_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.item_variant`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `axis` | `menu.variant_axis` | NOT NULL |  |  |
| `variant_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `is_default` | `boolean` | NOT NULL | `false` |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `item_variant_code_unique` — `UNIQUE (tenant_id, item_id, variant_code)`
- `item_variant_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE RESTRICT`
- `item_variant_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `item_variant_pkey` — `PRIMARY KEY (id)`
- `item_variant_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `item_variant_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.menu`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `menu_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `state` | `menu.publication_state` | NOT NULL | `'draft'::menu.publication_state` |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `menu_code_not_blank` — `CHECK ((btrim(menu_code) <> ''::text))`
- `menu_code_unique` — `UNIQUE (tenant_id, outlet_id, menu_code)`
- `menu_name_not_blank` — `CHECK ((btrim(canonical_name) <> ''::text))`
- `menu_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `menu_pkey` — `PRIMARY KEY (id)`
- `menu_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `menu_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.modifier`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `modifier_group_id` | `uuid` | NOT NULL |  |  |
| `modifier_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `is_default` | `boolean` | NOT NULL | `false` |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `modifier_code_unique` — `UNIQUE (tenant_id, modifier_group_id, modifier_code)`
- `modifier_group_ref_fk` — `FOREIGN KEY (modifier_group_id) REFERENCES menu.modifier_group(id) ON DELETE RESTRICT`
- `modifier_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `modifier_pkey` — `PRIMARY KEY (id)`
- `modifier_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `modifier_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.modifier_group`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `group_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `is_required` | `boolean` | NOT NULL | `false` |  |
| `min_selections` | `integer` | NOT NULL | `0` |  |
| `max_selections` | `integer` |  |  |  |
| `included_selections` | `integer` | NOT NULL | `0` |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `modifier_group_code_unique` — `UNIQUE (tenant_id, group_code)`
- `modifier_group_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `modifier_group_pkey` — `PRIMARY KEY (id)`
- `modifier_group_required_means_one` — `CHECK (((NOT is_required) OR (min_selections >= 1)))`
- `modifier_group_selection_bounds` — `CHECK (((min_selections >= 0) AND ((max_selections IS NULL) OR (max_selections >= min_selections)) AND (included_selections >= 0) AND ((max_selections IS NULL) OR (included_selections <= max_selections))))`
- `modifier_group_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `modifier_group_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.modifier_incompatibility`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `modifier_id` | `uuid` | NOT NULL |  |  |
| `incompatible_with_id` | `uuid` | NOT NULL |  |  |
| `note` | `text` |  |  |  |

Constraints:

- `modifier_incompatibility_left_fk` — `FOREIGN KEY (modifier_id) REFERENCES menu.modifier(id) ON DELETE CASCADE`
- `modifier_incompatibility_not_self` — `CHECK ((modifier_id <> incompatible_with_id))`
- `modifier_incompatibility_ordered` — `CHECK ((modifier_id < incompatible_with_id))`
- `modifier_incompatibility_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `modifier_incompatibility_pkey` — `PRIMARY KEY (modifier_id, incompatible_with_id)`
- `modifier_incompatibility_right_fk` — `FOREIGN KEY (incompatible_with_id) REFERENCES menu.modifier(id) ON DELETE CASCADE`
- `modifier_incompatibility_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `modifier_incompatibility_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.price`

Effective-dated prices by outlet, channel, variant, currency and tax context (FR-MNU-009). amount_minor is money.amount_minor — integer minor units of the currency named beside it. No floating point type appears in this schema and the verification suite fails if one ever does.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `item_id` | `uuid` |  |  |  |
| `variant_id` | `uuid` |  |  |  |
| `modifier_id` | `uuid` |  |  |  |
| `channel` | `menu.sales_channel` |  |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  | Integer minor units. Never a float, never a bare decimal. The currency_code column beside it is what money.assert_currency_paired() requires, and this is the first money.amount_minor column in the database — the check was vacuous until now. |
| `tax_context` | `text` | NOT NULL | `'standard'::text` |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `price_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `price_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE RESTRICT`
- `price_modifier_fk` — `FOREIGN KEY (modifier_id) REFERENCES menu.modifier(id) ON DELETE RESTRICT`
- `price_one_subject` — `CHECK ((((((item_id IS NOT NULL))::integer + ((variant_id IS NOT NULL))::integer) + ((modifier_id IS NOT NULL))::integer) = 1))`
- `price_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `price_pkey` — `PRIMARY KEY (id)`
- `price_range_ordered` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`
- `price_tax_context_not_blank` — `CHECK ((btrim(tax_context) <> ''::text))`
- `price_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `price_variant_fk` — `FOREIGN KEY (variant_id) REFERENCES menu.item_variant(id) ON DELETE RESTRICT`

Policies:

- `price_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.publication_snapshot`

An immutable record of exactly what was published, and when (FR-MNU-003). M3 orders reference it for price evidence, so it is append-only twice over: the application role holds INSERT and SELECT only, and a trigger refuses UPDATE, DELETE and TRUNCATE whoever asks. content_digest covers the lines, so a line changed by a privileged identity no longer matches the header.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `menu_id` | `uuid` | NOT NULL |  |  |
| `published_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `published_by_user_id` | `uuid` | NOT NULL |  |  |
| `content_digest` | `bytea` | NOT NULL |  |  |

Constraints:

- `publication_snapshot_digest_length` — `CHECK ((octet_length(content_digest) = 32))`
- `publication_snapshot_menu_fk` — `FOREIGN KEY (menu_id) REFERENCES menu.menu(id) ON DELETE RESTRICT`
- `publication_snapshot_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `publication_snapshot_pkey` — `PRIMARY KEY (id)`
- `publication_snapshot_publisher_fk` — `FOREIGN KEY (tenant_id, published_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `publication_snapshot_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `publication_snapshot_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.publication_snapshot_line`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `snapshot_id` | `uuid` | NOT NULL |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `variant_id` | `uuid` |  |  |  |
| `item_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `channel` | `menu.sales_channel` |  |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `tax_context` | `text` | NOT NULL |  |  |
| `availability` | `menu.availability_state` | NOT NULL |  |  |

Constraints:

- `publication_snapshot_line_pkey` — `PRIMARY KEY (id)`
- `snapshot_line_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `snapshot_line_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `snapshot_line_snapshot_fk` — `FOREIGN KEY (snapshot_id) REFERENCES menu.publication_snapshot(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED`
- `snapshot_line_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `publication_snapshot_line_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.sellable_item`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `menu_id` | `uuid` | NOT NULL |  |  |
| `category_id` | `uuid` |  |  |  |
| `item_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `canonical_short_description` | `text` |  |  |  |
| `canonical_long_description` | `text` |  |  |  |
| `customer_visible_ingredients` | `text` |  |  | The ingredient sentence a guest reads (FR-MNU-004). Not a recipe: no quantity, no unit, no yield, no cost and no reference to any production record. Marked safety-critical in menu.translatable_field, so a machine-assisted translation of it can never be approved without a human. |
| `preparation_minutes` | `integer` |  |  |  |
| `display_order` | `integer` | NOT NULL | `0` |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `sellable_item_category_fk` — `FOREIGN KEY (category_id) REFERENCES menu.category(id) ON DELETE RESTRICT`
- `sellable_item_code_not_blank` — `CHECK ((btrim(item_code) <> ''::text))`
- `sellable_item_code_unique` — `UNIQUE (tenant_id, menu_id, item_code)`
- `sellable_item_menu_fk` — `FOREIGN KEY (menu_id) REFERENCES menu.menu(id) ON DELETE RESTRICT`
- `sellable_item_name_not_blank` — `CHECK ((btrim(canonical_name) <> ''::text))`
- `sellable_item_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `sellable_item_pkey` — `PRIMARY KEY (id)`
- `sellable_item_preparation_sane` — `CHECK (((preparation_minutes IS NULL) OR ((preparation_minutes >= 0) AND (preparation_minutes <= 600))))`
- `sellable_item_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `sellable_item_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `menu.translatable_field`

The registry of what must be translated before a menu may publish, and which of those fields is safety-critical. Reference data, not tenant data: the same fields are required of every tenant, so this table is deliberately not tenant-scoped and the application role holds SELECT only.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `entity` | `menu.menu_entity` | NOT NULL |  |  |
| `field_name` | `text` | NOT NULL |  |  |
| `required_for_publication` | `boolean` | NOT NULL | `true` |  |
| `safety_critical` | `boolean` | NOT NULL | `false` |  |

Constraints:

- `translatable_field_name_not_blank` — `CHECK ((btrim(field_name) <> ''::text))`
- `translatable_field_pkey` — `PRIMARY KEY (entity, field_name)`

#### `menu.translation`

Approved customer translations, stored separately from the canonical record (FR-I18N-003, FR-I18N-011). Machine assistance is permitted for a draft with its engine recorded; approval always names a human reviewer. There is no live runtime translation anywhere in this system — a locale is either stored and approved, or it is missing and publication is blocked.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `entity` | `menu.menu_entity` | NOT NULL |  |  |
| `entity_id` | `uuid` | NOT NULL |  |  |
| `field_name` | `text` | NOT NULL |  |  |
| `locale` | `menu.customer_locale` | NOT NULL |  |  |
| `translated_text` | `text` | NOT NULL |  |  |
| `state` | `menu.translation_state` | NOT NULL | `'draft'::menu.translation_state` |  |
| `provenance` | `menu.translation_provenance` | NOT NULL | `'human'::menu.translation_provenance` |  |
| `machine_engine` | `text` |  |  |  |
| `translated_by_user_id` | `uuid` |  |  |  |
| `reviewed_by_user_id` | `uuid` |  |  |  |
| `approved_at` | `timestamp with time zone` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `translation_approval_is_reviewed` — `CHECK (((state = 'approved'::menu.translation_state) = ((reviewed_by_user_id IS NOT NULL) AND (approved_at IS NOT NULL))))`
- `translation_engine_matches_provenance` — `CHECK (((provenance = 'machine_assisted'::menu.translation_provenance) = (machine_engine IS NOT NULL)))`
- `translation_field_fk` — `FOREIGN KEY (entity, field_name) REFERENCES menu.translatable_field(entity, field_name) ON DELETE RESTRICT`
- `translation_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `translation_pkey` — `PRIMARY KEY (id)`
- `translation_reviewer_fk` — `FOREIGN KEY (tenant_id, reviewed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `translation_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `translation_text_not_blank` — `CHECK ((btrim(translated_text) <> ''::text))`
- `translation_translator_fk` — `FOREIGN KEY (tenant_id, translated_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `translation_unique` — `UNIQUE (tenant_id, entity, entity_id, field_name, locale)`

Policies:

- `translation_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `money`

Exact money and quantity types (FR-DAT-005, FR-DAT-006).

#### `money.currency`

ISO 4217 reference data. Deliberately NOT tenant-scoped: a currency is not a tenant's property. The application role holds SELECT only and cannot write here, which the verification suite proves.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `code` | `character(3)` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `minor_unit_digits` | `smallint` | NOT NULL |  |  |

Constraints:

- `currency_code_is_uppercase_alpha` — `CHECK ((code ~ '^[A-Z]{3}$'::text))`
- `currency_minor_unit_digits_sane` — `CHECK (((minor_unit_digits >= 0) AND (minor_unit_digits <= 4)))`
- `currency_pkey` — `PRIMARY KEY (code)`

### `notify`

FR-NOT-001 … FR-NOT-012. What happened, who should be told, in which language, and whether they were told. The CHANNEL is not here: outlet-local notice is M5a, and this gate sends in-app only.

#### `notify.catalog_event`

The package's event catalog, for the classes FR-NOT-001 names. has_producer = false marks a kind whose domain is a later gate: the kind is real and nothing emits it. tests/m3c requires this table to equal events.json and fails closed if it cannot read the package.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `event_id` | `text` | NOT NULL |  |  |
| `event_class` | `notify.event_class` | NOT NULL |  |  |
| `milestone` | `text` | NOT NULL |  |  |
| `severity` | `text` | NOT NULL | `'informational'::text` |  |
| `has_producer` | `boolean` | NOT NULL |  |  |

Constraints:

- `catalog_event_id_shape` — `CHECK ((event_id ~ '^EVT-[A-Z0-9-]+$'::text))`
- `catalog_event_milestone_shape` — `CHECK ((milestone ~ '^M[0-9][A-Za-z]?$'::text))`
- `catalog_event_pkey` — `PRIMARY KEY (event_id)`
- `catalog_event_producer_only_when_landed` — `CHECK (((NOT has_producer) OR (milestone = ANY (ARRAY['M1'::text, 'M2'::text, 'M3'::text, 'M4'::text]))))`
- `catalog_event_severity_known` — `CHECK ((severity = ANY (ARRAY['informational'::text, 'critical'::text])))`

#### `notify.deep_link`

FR-NOT-009. An opaque token, a target and the scope a caller must be inside to follow it. The token is stored as sha256 and never in the clear, and the target is not derivable from it — a link that could be edited into another table's request would fail no authorization check because it would never reach one.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `notice_id` | `uuid` | NOT NULL |  |  |
| `token_digest` | `bytea` | NOT NULL |  |  |
| `target_kind` | `ordering.artifact_kind` | NOT NULL |  |  |
| `target_id` | `uuid` | NOT NULL |  |  |
| `scope_table_session_id` | `uuid` |  |  |  |
| `expires_at` | `timestamp with time zone` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `deep_link_digest_is_sha256` — `CHECK ((octet_length(token_digest) = 32))`
- `deep_link_digest_unique` — `UNIQUE (token_digest)`
- `deep_link_notice_fk` — `FOREIGN KEY (tenant_id, notice_id) REFERENCES notify.notice(tenant_id, id) ON DELETE RESTRICT`
- `deep_link_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `deep_link_pkey` — `PRIMARY KEY (id)`
- `deep_link_session_fk` — `FOREIGN KEY (tenant_id, scope_table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `deep_link_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `deep_link_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `deep_link_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `notify.notice`

One person being told one thing. FR-NOT-007's deduplication is a UNIQUE index over (notification, recipient) rather than a check the emitter performs, because an emitter that forgot would produce exactly the duplicate alert the requirement forbids.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `notification_id` | `uuid` | NOT NULL |  |  |
| `audience` | `notify.audience` | NOT NULL |  |  |
| `recipient_user_id` | `uuid` |  |  |  |
| `recipient_guest_session_id` | `uuid` |  |  |  |
| `locale` | `menu.customer_locale` | NOT NULL |  |  |
| `rendered_text` | `text` |  |  |  |
| `state` | `notify.notice_state` | NOT NULL | `'pending'::notify.notice_state` |  |
| `attempts` | `integer` | NOT NULL | `0` |  |
| `last_failure` | `notify.failure_reason` |  |  |  |
| `last_failed_at` | `timestamp with time zone` |  |  |  |
| `sent_at` | `timestamp with time zone` |  |  |  |
| `read_at` | `timestamp with time zone` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `notice_attempts_not_negative` — `CHECK ((attempts >= 0))`
- `notice_audience_names_its_recipient` — `CHECK ((((audience = 'staff'::notify.audience) AND (recipient_user_id IS NOT NULL) AND (recipient_guest_session_id IS NULL)) OR ((audience = 'customer'::notify.audience) AND (recipient_guest_session_id IS NOT NULL) AND (recipient_user_id IS NULL))))`
- `notice_failure_is_explained` — `CHECK (((state = ANY (ARRAY['failed'::notify.notice_state, 'dead_lettered'::notify.notice_state])) = (last_failure IS NOT NULL)))`
- `notice_guest_fk` — `FOREIGN KEY (tenant_id, recipient_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `notice_notification_fk` — `FOREIGN KEY (tenant_id, notification_id) REFERENCES notify.notification(tenant_id, id) ON DELETE RESTRICT`
- `notice_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `notice_pkey` — `PRIMARY KEY (id)`
- `notice_read_after_sent` — `CHECK (((read_at IS NULL) OR (sent_at IS NOT NULL)))`
- `notice_sent_has_text` — `CHECK (((state <> ALL (ARRAY['sent'::notify.notice_state, 'read'::notify.notice_state])) OR (rendered_text IS NOT NULL)))`
- `notice_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `notice_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `notice_user_fk` — `FOREIGN KEY (tenant_id, recipient_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `notice_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `notify.notification`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `event_id` | `text` | NOT NULL |  |  |
| `subject_kind` | `ordering.artifact_kind` | NOT NULL |  |  |
| `subject_id` | `uuid` | NOT NULL |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `dedup_key` | `text` | NOT NULL |  |  |
| `payload` | `jsonb` | NOT NULL | `'{}'::jsonb` |  |
| `emitted_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `notification_dedup_key_not_blank` — `CHECK ((btrim(dedup_key) <> ''::text))`
- `notification_event_fk` — `FOREIGN KEY (event_id) REFERENCES notify.catalog_event(event_id) ON DELETE RESTRICT`
- `notification_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `notification_payload_within_bounds` — `CHECK (notify.payload_within_bounds(payload))`
- `notification_pkey` — `PRIMARY KEY (id)`
- `notification_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `notification_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `notification_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `notify.status_wording`

FR-NOT-012, FR-I18N-001B, FR-I18N-008. What a guest is told when their order reaches a state, in the language they chose. Identity and the English source only: the Amharic and Arabic bodies live in menu.translation under entity order_status_wording, where a human has to review and approve them and menu.enforce_translation_review() refuses an approval nobody reviewed. That is also why no migration installs the wording: an approved translation asserts that a person read it, and a migration writing one would be forging that assertion.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `event_kind` | `ordering.event_kind` | NOT NULL |  |  |
| `source_text` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `status_wording_one_per_kind` — `UNIQUE (tenant_id, event_kind)`
- `status_wording_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `status_wording_pkey` — `PRIMARY KEY (id)`
- `status_wording_row_version_positive` — `CHECK ((row_version > 0))`
- `status_wording_source_not_blank` — `CHECK ((btrim(source_text) <> ''::text))`
- `status_wording_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `status_wording_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `status_wording_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `notify.template`

FR-NOT-003. Identity only: the approved BODY in each customer language lives in menu.translation under entity notification_template, so M2-A's human approval workflow governs it unchanged rather than being written a second time.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `event_id` | `text` | NOT NULL |  |  |
| `audience` | `notify.audience` | NOT NULL |  |  |
| `source_text` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `template_event_fk` — `FOREIGN KEY (event_id) REFERENCES notify.catalog_event(event_id) ON DELETE RESTRICT`
- `template_one_per_event_audience` — `UNIQUE (tenant_id, event_id, audience)`
- `template_pkey` — `PRIMARY KEY (id)`
- `template_source_not_blank` — `CHECK ((btrim(source_text) <> ''::text))`
- `template_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `template_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `template_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `ordering`

The commercial order: submission, snapshots, notes, timeline and the append-only ledger they are all projections of (FR-ORD-001A, FR-DAT-008A, FR-DAT-010).

#### `ordering.charge_rule`

Where a tax, discount or fee figure comes from (FR-ORD-003). Every row names the M1 configuration or policy it was derived from, so no amount on an order is a number somebody chose. There is no fee row at M3-A and no path that creates one: the configuration a fee resolves to is FR-CFG-001C at M4.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `kind` | `ordering.charge_kind` | NOT NULL |  |  |
| `source_kind` | `ordering.charge_source_kind` | NOT NULL |  |  |
| `source_configuration_id` | `uuid` |  |  |  |
| `source_policy_id` | `uuid` |  |  |  |
| `tax_context` | `text` |  |  |  |
| `rate_percentage` | `money.percentage` |  |  |  |
| `fixed_amount_minor` | `money.amount_minor` |  |  |  |
| `currency_code` | `character(3)` |  |  |  |
| `rounding_mode` | `money.rounding_mode` | NOT NULL |  |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `effective_to` | `timestamp with time zone` |  |  |  |

Constraints:

- `charge_rule_configuration_fk` — `FOREIGN KEY (source_configuration_id) REFERENCES config.configuration_version(id) ON DELETE RESTRICT`
- `charge_rule_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `charge_rule_fixed_amount_has_currency` — `CHECK (((fixed_amount_minor IS NULL) = (currency_code IS NULL)))`
- `charge_rule_fixed_amount_is_a_magnitude` — `CHECK (((fixed_amount_minor IS NULL) OR ((fixed_amount_minor)::bigint >= 0)))`
- `charge_rule_not_a_line_price` — `CHECK ((kind <> 'item_subtotal'::ordering.charge_kind))`
- `charge_rule_one_basis` — `CHECK (((((rate_percentage IS NOT NULL))::integer + ((fixed_amount_minor IS NOT NULL))::integer) = 1))`
- `charge_rule_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `charge_rule_pkey` — `PRIMARY KEY (id)`
- `charge_rule_policy_fk` — `FOREIGN KEY (source_policy_id) REFERENCES config.policy(id) ON DELETE RESTRICT`
- `charge_rule_source_matches_kind` — `CHECK ((((kind = 'tax'::ordering.charge_kind) AND (source_kind = 'tax_configuration'::ordering.charge_source_kind) AND (source_configuration_id IS NOT NULL) AND (source_policy_id IS NULL)) OR ((kind = 'discount'::ordering.charge_kind) AND (source_kind = 'discount_policy'::ordering.charge_source_kind) AND (source_policy_id IS NOT NULL) AND (source_configuration_id IS NULL)) OR ((kind = 'fee'::ordering.charge_kind) AND (source_kind = 'service_configuration'::ordering.charge_source_kind) AND (source_configuration_id IS NOT NULL) AND (source_policy_id IS NULL))))`
- `charge_rule_tax_context_not_blank` — `CHECK (((tax_context IS NULL) OR (btrim(tax_context) <> ''::text)))`
- `charge_rule_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `charge_rule_window_valid` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`

Policies:

- `charge_rule_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.correlation_link`

The stable chain linking a request, a cart, a table session and an order (FR-ORD-019A), rebuilt from ordering.order_event so it survives a projection rebuild by construction. artifact_id is deliberately not a foreign key: the chain must be able to name an artifact kind whose table a later slice builds.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `artifact_kind` | `ordering.artifact_kind` | NOT NULL |  |  |
| `artifact_id` | `uuid` | NOT NULL |  |  |
| `linked_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `correlation_link_pkey` — `PRIMARY KEY (correlation_id, artifact_kind, artifact_id)`
- `correlation_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `correlation_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `correlation_link_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.customer_order`

ONE order aggregate for QR dine-in and waiter-entered dine-in (FR-ORD-001A), with the origin as the channel-specific policy dimension rather than a second model. A projection of ordering.order_event: nothing writes here except ordering.apply_event(), and the whole table can be discarded and rebuilt from the ledger byte for byte (FR-DAT-010).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `cart_id` | `uuid` | NOT NULL |  |  |
| `origin` | `ordering.order_origin` | NOT NULL |  |  |
| `channel` | `menu.sales_channel` | NOT NULL |  |  |
| `state` | `ordering.order_state` | NOT NULL |  |  |
| `placed_by_guest_session_id` | `uuid` |  |  |  |
| `placed_by_user_id` | `uuid` |  |  |  |
| `order_number` | `text` | NOT NULL |  |  |
| `customer_locale` | `menu.customer_locale` | NOT NULL |  |  |
| `publication_snapshot_id` | `uuid` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `total_amount_minor` | `money.amount_minor` | NOT NULL |  | The sum of ordering.order_charge_component for this order, and nothing else. A deferred constraint trigger refuses to commit a row where it is not, so a total and its components cannot drift apart. It is never a figure a client supplied (FR-ORD-003). |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `idempotency_key` | `text` | NOT NULL |  |  |
| `submitted_at` | `timestamp with time zone` | NOT NULL |  |  |
| `acceptance_mode` | `ordering.acceptance_mode` |  |  |  |
| `accepted_at` | `timestamp with time zone` |  |  |  |
| `accepted_by_user_id` | `uuid` |  |  |  |
| `resolved_at` | `timestamp with time zone` |  |  |  |
| `ledger_sequence` | `integer` | NOT NULL |  |  |

Constraints:

- `customer_order_acceptance_recorded_together` — `CHECK (((accepted_at IS NULL) = (acceptance_mode IS NULL)))`
- `customer_order_accepted_and_voided_name_the_acceptance` — `CHECK (((state <> ALL (ARRAY['accepted'::ordering.order_state, 'voided'::ordering.order_state])) OR (accepted_at IS NOT NULL)))`
- `customer_order_accepter_fk` — `FOREIGN KEY (tenant_id, accepted_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `customer_order_automatic_has_no_confirmer` — `CHECK (((acceptance_mode IS DISTINCT FROM 'automatic'::ordering.acceptance_mode) OR (accepted_by_user_id IS NULL)))`
- `customer_order_cart_fk` — `FOREIGN KEY (tenant_id, cart_id) REFERENCES service.cart(tenant_id, id) ON DELETE RESTRICT`
- `customer_order_confirmer_named` — `CHECK (((acceptance_mode IS DISTINCT FROM 'staff_confirmed'::ordering.acceptance_mode) OR (accepted_by_user_id IS NOT NULL)))`
- `customer_order_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `customer_order_guest_fk` — `FOREIGN KEY (tenant_id, placed_by_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `customer_order_idempotency_key_not_blank` — `CHECK ((btrim(idempotency_key) <> ''::text))`
- `customer_order_number_not_blank` — `CHECK ((btrim(order_number) <> ''::text))`
- `customer_order_one_per_key` — `UNIQUE (tenant_id, outlet_id, idempotency_key)`
- `customer_order_origin_consistent` — `CHECK ((((origin = 'guest_qr'::ordering.order_origin) AND (placed_by_guest_session_id IS NOT NULL) AND (placed_by_user_id IS NULL)) OR ((origin = ANY (ARRAY['waiter_entered'::ordering.order_origin, 'counter'::ordering.order_origin])) AND (placed_by_user_id IS NOT NULL) AND (placed_by_guest_session_id IS NULL))))`
- `customer_order_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `customer_order_pkey` — `PRIMARY KEY (id)`
- `customer_order_resolution_consistent` — `CHECK (((state = ANY (ARRAY['submitted'::ordering.order_state, 'accepted'::ordering.order_state])) = (resolved_at IS NULL)))`
- `customer_order_sequence_positive` — `CHECK ((ledger_sequence > 0))`
- `customer_order_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `customer_order_snapshot_fk` — `FOREIGN KEY (publication_snapshot_id) REFERENCES menu.publication_snapshot(id) ON DELETE RESTRICT`
- `customer_order_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `customer_order_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `customer_order_total_reconciles` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `customer_order_unaccepted_states_claim_nothing` — `CHECK (((state <> ALL (ARRAY['submitted'::ordering.order_state, 'rejected'::ordering.order_state])) OR (accepted_at IS NULL)))`
- `customer_order_user_fk` — `FOREIGN KEY (tenant_id, placed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `customer_order_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.duplicate_signal`

A suspected duplicate order, flagged and never refused (FR-ORD-017). A control that blocked a legitimate second round of drinks would be wrong in the other direction, so a declared repeat produces NO ROW here at all. There is deliberately no "repeat_intent_declared" column: it could only ever hold false, and a column with one possible value reads like a real value while carrying nothing. The absence of the row is the record, and tests/m3a asserts the absence rather than a flag.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `matched_order_id` | `uuid` | NOT NULL |  |  |
| `content_digest` | `bytea` | NOT NULL |  |  |
| `seconds_apart` | `integer` | NOT NULL |  |  |
| `raised_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `duplicate_signal_digest_is_sha256` — `CHECK ((octet_length(content_digest) = 32))`
- `duplicate_signal_distinct_orders` — `CHECK ((order_id <> matched_order_id))`
- `duplicate_signal_interval_not_negative` — `CHECK ((seconds_apart >= 0))`
- `duplicate_signal_matched_fk` — `FOREIGN KEY (tenant_id, matched_order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `duplicate_signal_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `duplicate_signal_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `duplicate_signal_pkey` — `PRIMARY KEY (id)`
- `duplicate_signal_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `duplicate_signal_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_charge_component`

One row per charge that applied to an order (FR-ORD-005). The order total is SUM(amount_minor) over these rows — a component whose source does not exist yet produces no row, never a zero. Discounts are stored negative so the summation has no per-kind sign logic and cannot get a new kind's sign wrong.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `kind` | `ordering.charge_kind` | NOT NULL |  |  |
| `source_kind` | `ordering.charge_source_kind` | NOT NULL |  |  |
| `charge_rule_id` | `uuid` |  |  |  |
| `basis` | `jsonb` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |

Constraints:

- `order_charge_additions_add` — `CHECK (((kind = 'discount'::ordering.charge_kind) OR ((amount_minor)::bigint >= 0)))`
- `order_charge_component_pkey` — `PRIMARY KEY (id)`
- `order_charge_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `order_charge_discount_reduces` — `CHECK (((kind <> 'discount'::ordering.charge_kind) OR ((amount_minor)::bigint <= 0)))`
- `order_charge_one_per_rule` — `UNIQUE (order_id, kind, charge_rule_id)`
- `order_charge_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `order_charge_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `order_charge_rule_fk` — `FOREIGN KEY (charge_rule_id) REFERENCES ordering.charge_rule(id) ON DELETE RESTRICT`
- `order_charge_rule_required` — `CHECK ((((kind = 'item_subtotal'::ordering.charge_kind) AND (source_kind = 'menu_price'::ordering.charge_source_kind) AND (charge_rule_id IS NULL)) OR ((kind <> 'item_subtotal'::ordering.charge_kind) AND (charge_rule_id IS NOT NULL))))`
- `order_charge_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `order_charge_total_reconciles` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`

Policies:

- `order_charge_component_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_event`

The authoritative, append-only order ledger (FR-DAT-008A). Every other table in this schema is a projection rebuilt from it by ordering.apply_event(), so an order has no destructive edit path: there is nothing to edit that is not derived. Enforced twice over — the application role holds INSERT and SELECT only, and ordering.refuse_ledger_mutation() refuses UPDATE, DELETE and TRUNCATE whoever asks.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `kind` | `ordering.event_kind` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `actor_kind` | `ordering.actor_kind` | NOT NULL |  |  |
| `actor_user_id` | `uuid` |  |  |  |
| `actor_guest_session_id` | `uuid` |  |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `before` | `jsonb` |  |  |  |
| `after` | `jsonb` | NOT NULL |  |  |

Constraints:

- `order_event_actor_consistent` — `CHECK ((((actor_kind = 'guest'::ordering.actor_kind) AND (actor_guest_session_id IS NOT NULL) AND (actor_user_id IS NULL)) OR ((actor_kind = 'staff'::ordering.actor_kind) AND (actor_user_id IS NOT NULL) AND (actor_guest_session_id IS NULL)) OR ((actor_kind = 'system'::ordering.actor_kind) AND (actor_user_id IS NULL) AND (actor_guest_session_id IS NULL))))`
- `order_event_actor_guest_fk` — `FOREIGN KEY (tenant_id, actor_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `order_event_actor_user_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `order_event_amends_tickets` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `order_event_before_required_for_changes` — `CHECK ((((kind = ANY (ARRAY['amended'::ordering.event_kind, 'cancelled'::ordering.event_kind, 'voided'::ordering.event_kind, 'session_merged'::ordering.event_kind, 'session_moved'::ordering.event_kind])) AND (before IS NOT NULL)) OR ((kind = ANY (ARRAY['submitted'::ordering.event_kind, 'accepted'::ordering.event_kind, 'rejected'::ordering.event_kind, 'note_added'::ordering.event_kind, 'allergy_declared'::ordering.event_kind])) AND (before IS NULL))))`
- `order_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `order_event_pkey` — `PRIMARY KEY (id)`
- `order_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `order_event_reason_required` — `CHECK (((kind = ANY (ARRAY['cancelled'::ordering.event_kind, 'voided'::ordering.event_kind])) = (reason_code_id IS NOT NULL)))`
- `order_event_releases_work` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `order_event_sequence_positive` — `CHECK ((sequence_number > 0))`
- `order_event_sequence_unique` — `UNIQUE (tenant_id, order_id, sequence_number)`
- `order_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `order_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_line`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `line_number` | `integer` | NOT NULL |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `variant_id` | `uuid` | NOT NULL |  |  |
| `quantity` | `integer` | NOT NULL |  |  |
| `participant_guest_session_id` | `uuid` |  |  |  |
| `snapshot_line_id` | `bigint` | NOT NULL |  |  |
| `item_code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  | The dish name in the language the order was placed in, resolved from the approved translation at submission. canonical_name travels beside it unchanged: M2-C found that showing a translated warning next to an untranslated name is a defect a SQL suite cannot see, and an order carries both so neither question needs a join. |
| `tax_context` | `text` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `unit_amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `line_amount_minor` | `money.amount_minor` | NOT NULL |  |  |

Constraints:

- `order_line_code_not_blank` — `CHECK ((btrim(item_code) <> ''::text))`
- `order_line_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `order_line_display_name_not_blank` — `CHECK ((btrim(display_name) <> ''::text))`
- `order_line_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE RESTRICT`
- `order_line_name_not_blank` — `CHECK ((btrim(canonical_name) <> ''::text))`
- `order_line_number_positive` — `CHECK ((line_number > 0))`
- `order_line_number_unique` — `UNIQUE (tenant_id, order_id, line_number)`
- `order_line_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `order_line_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `order_line_participant_fk` — `FOREIGN KEY (tenant_id, participant_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `order_line_pkey` — `PRIMARY KEY (id)`
- `order_line_quantity_positive` — `CHECK ((quantity > 0))`
- `order_line_snapshot_fk` — `FOREIGN KEY (snapshot_line_id) REFERENCES menu.publication_snapshot_line(id) ON DELETE RESTRICT`
- `order_line_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `order_line_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `order_line_variant_fk` — `FOREIGN KEY (variant_id) REFERENCES menu.item_variant(id) ON DELETE RESTRICT`

Policies:

- `order_line_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_line_modifier`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_line_id` | `uuid` | NOT NULL |  |  |
| `modifier_id` | `uuid` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `unit_amount_minor` | `money.amount_minor` | NOT NULL |  |  |

Constraints:

- `order_line_modifier_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `order_line_modifier_line_fk` — `FOREIGN KEY (tenant_id, order_line_id) REFERENCES ordering.order_line(tenant_id, id) ON DELETE RESTRICT`
- `order_line_modifier_modifier_fk` — `FOREIGN KEY (modifier_id) REFERENCES menu.modifier(id) ON DELETE RESTRICT`
- `order_line_modifier_name_not_blank` — `CHECK ((btrim(canonical_name) <> ''::text))`
- `order_line_modifier_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `order_line_modifier_pkey` — `PRIMARY KEY (id)`
- `order_line_modifier_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `order_line_modifier_unique` — `UNIQUE (order_line_id, modifier_id)`

Policies:

- `order_line_modifier_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_note`

Four note kinds with four required shapes (FR-ORD-013), so the distinction is structural rather than a label. The application role holds NO direct SELECT here: reads go through the audience functions below, and the one a customer surface can call takes no audience argument, so it cannot be asked for a private staff note.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `order_line_id` | `uuid` |  |  |  |
| `kind` | `ordering.note_kind` | NOT NULL |  |  |
| `body` | `text` | NOT NULL |  |  |
| `author_user_id` | `uuid` |  |  |  |
| `author_guest_session_id` | `uuid` |  |  |  |
| `allergen_id` | `uuid` |  |  |  |
| `allergy_concern_id` | `uuid` |  |  |  |
| `acknowledgement_wording_id` | `uuid` |  |  |  |
| `acknowledgement_text` | `text` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `order_note_allergen_fk` — `FOREIGN KEY (tenant_id, allergen_id) REFERENCES safety.allergen(tenant_id, id) ON DELETE RESTRICT`
- `order_note_allergy_shape` — `CHECK ((((kind = 'allergy_declaration'::ordering.note_kind) AND (allergen_id IS NOT NULL) AND (allergy_concern_id IS NOT NULL) AND (acknowledgement_wording_id IS NOT NULL) AND (acknowledgement_text IS NOT NULL) AND (btrim(acknowledgement_text) <> ''::text)) OR ((kind <> 'allergy_declaration'::ordering.note_kind) AND (allergen_id IS NULL) AND (allergy_concern_id IS NULL) AND (acknowledgement_wording_id IS NULL) AND (acknowledgement_text IS NULL))))`
- `order_note_author_fk` — `FOREIGN KEY (tenant_id, author_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `order_note_authorship_matches_kind` — `CHECK ((((kind = ANY (ARRAY['kitchen_instruction'::ordering.note_kind, 'private_staff'::ordering.note_kind])) AND (author_user_id IS NOT NULL) AND (author_guest_session_id IS NULL)) OR ((kind = ANY (ARRAY['customer'::ordering.note_kind, 'allergy_declaration'::ordering.note_kind])) AND ((author_guest_session_id IS NOT NULL) OR (author_user_id IS NOT NULL)))))`
- `order_note_body_not_blank` — `CHECK ((btrim(body) <> ''::text))`
- `order_note_concern_fk` — `FOREIGN KEY (allergy_concern_id) REFERENCES safety.allergy_concern(id) ON DELETE RESTRICT`
- `order_note_guest_fk` — `FOREIGN KEY (tenant_id, author_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `order_note_line_fk` — `FOREIGN KEY (tenant_id, order_line_id) REFERENCES ordering.order_line(tenant_id, id) ON DELETE RESTRICT`
- `order_note_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `order_note_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `order_note_pkey` — `PRIMARY KEY (id)`
- `order_note_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `order_note_wording_fk` — `FOREIGN KEY (tenant_id, acknowledgement_wording_id) REFERENCES safety.approved_wording(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `order_note_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `ordering.order_timeline_entry`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL |  |  |
| `kind` | `ordering.event_kind` | NOT NULL |  |  |
| `visible_to_customer` | `boolean` | NOT NULL |  |  |
| `visible_to_staff` | `boolean` | NOT NULL |  |  |
| `customer_summary` | `text` |  |  |  |
| `staff_summary` | `text` | NOT NULL |  |  |

Constraints:

- `order_timeline_entry_pkey` — `PRIMARY KEY (id)`
- `timeline_customer_text_matches_visibility` — `CHECK ((visible_to_customer = ((customer_summary IS NOT NULL) AND (btrim(COALESCE(customer_summary, ''::text)) <> ''::text))))`
- `timeline_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `timeline_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `timeline_sequence_unique` — `UNIQUE (tenant_id, order_id, sequence_number)`
- `timeline_staff_always_see_it` — `CHECK (visible_to_staff)`
- `timeline_staff_summary_not_blank` — `CHECK ((btrim(staff_summary) <> ''::text))`
- `timeline_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `order_timeline_entry_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `org`

Phase 1 organizational model (FR-TEN-002A).

#### `org.device_registration`

Registered device attributes. Device authentication and service principals are M1-B.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `device_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `registration_code` | `text` | NOT NULL |  |  |
| `registered_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `device_registration_code_unique` — `UNIQUE (tenant_id, registration_code)`
- `device_registration_node_fk` — `FOREIGN KEY (tenant_id, device_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `device_registration_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `device_registration_pkey` — `PRIMARY KEY (device_id)`
- `device_registration_row_version_positive` — `CHECK ((row_version > 0))`

Policies:

- `device_registration_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `org.org_closure`

Transitive closure of org.org_node, maintained by trigger. Depth 0 is the self row.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `ancestor_id` | `uuid` | NOT NULL |  |  |
| `descendant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `depth` | `integer` | NOT NULL |  |  |

Constraints:

- `org_closure_ancestor_fk` — `FOREIGN KEY (tenant_id, ancestor_id) REFERENCES org.org_node(tenant_id, id) ON DELETE CASCADE`
- `org_closure_depth_non_negative` — `CHECK ((depth >= 0))`
- `org_closure_descendant_fk` — `FOREIGN KEY (tenant_id, descendant_id) REFERENCES org.org_node(tenant_id, id) ON DELETE CASCADE`
- `org_closure_pkey` — `PRIMARY KEY (ancestor_id, descendant_id)`
- `org_closure_self_is_depth_zero` — `CHECK (((ancestor_id = descendant_id) = (depth = 0)))`
- `org_closure_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `org_closure_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `org.org_node`

Organizational hierarchy of configurable depth (FR-TEN-002A). No fixed-level assumption: traverse org.org_closure rather than joining a fixed number of parents.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `parent_id` | `uuid` |  |  |  |
| `outlet_id` | `uuid` |  |  | Nearest ancestor-or-self outlet; NULL above the outlet boundary. Derived by trigger. Presence of this column obliges the table to carry an outlet-aware policy (NC-M1-003). |
| `kind` | `org.node_kind` | NOT NULL |  |  |
| `reference_code` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `deactivated_at` | `timestamp with time zone` |  |  |  |
| `archived_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `org_node_display_name_not_blank` — `CHECK ((btrim(display_name) <> ''::text))`
- `org_node_lifecycle_consistent` — `CHECK ((((status = 'active'::org.lifecycle_status) AND (deactivated_at IS NULL) AND (archived_at IS NULL)) OR ((status = 'inactive'::org.lifecycle_status) AND (deactivated_at IS NOT NULL) AND (archived_at IS NULL)) OR ((status = 'archived'::org.lifecycle_status) AND (archived_at IS NOT NULL))))`
- `org_node_not_own_parent` — `CHECK ((parent_id IS DISTINCT FROM id))`
- `org_node_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `org_node_outlet_is_self` — `CHECK (((kind <> 'outlet'::org.node_kind) OR (outlet_id = id)))`
- `org_node_parent_fk` — `FOREIGN KEY (tenant_id, parent_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `org_node_pkey` — `PRIMARY KEY (id)`
- `org_node_reference_code_not_blank` — `CHECK ((btrim(reference_code) <> ''::text))`
- `org_node_reference_code_unique` — `UNIQUE (tenant_id, kind, reference_code)`
- `org_node_row_version_positive` — `CHECK ((row_version > 0))`
- `org_node_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `org_node_tenant_id_kind_unique` — `UNIQUE (tenant_id, id, kind)`
- `org_node_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `org_node_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `org.outlet_profile`

Outlet timezone context. Instants are stored UTC; this supplies the local rendering context required by FR-DAT-004.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `timezone` | `text` | NOT NULL |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `outlet_profile_node_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `outlet_profile_pkey` — `PRIMARY KEY (outlet_id)`
- `outlet_profile_row_version_positive` — `CHECK ((row_version > 0))`
- `outlet_profile_timezone_not_blank` — `CHECK ((btrim(timezone) <> ''::text))`

Policies:

- `outlet_profile_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `org.system_of_record`

FR-TEN-009A. Which system is authoritative for each Phase 1 concern, per tenant and legal entity. The fiscal port below READS it: a fiscal document may only be issued by the platform for an entity that says this platform is of record for fiscal_documents, so the registry governs behaviour rather than describing it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `legal_entity_id` | `uuid` | NOT NULL |  |  |
| `concern` | `org.record_concern` | NOT NULL |  |  |
| `system_name` | `text` | NOT NULL |  |  |
| `is_this_platform` | `boolean` | NOT NULL |  |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `recorded_by_user_id` | `uuid` | NOT NULL |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `system_of_record_actor_fk` — `FOREIGN KEY (tenant_id, recorded_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `system_of_record_entity_fk` — `FOREIGN KEY (tenant_id, legal_entity_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `system_of_record_name_not_blank` — `CHECK ((btrim(system_name) <> ''::text))`
- `system_of_record_one_per_concern` — `UNIQUE (tenant_id, legal_entity_id, concern)`
- `system_of_record_pkey` — `PRIMARY KEY (id)`
- `system_of_record_platform_names_itself` — `CHECK ((is_this_platform = (system_name = 'this_platform'::text)))`
- `system_of_record_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `system_of_record_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `system_of_record_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `org.tenant`

Isolation root. Every tenant-owned row references exactly one tenant (FR-TEN-001).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_code` | `text` | NOT NULL |  | Human-facing code. Never used as a key; the opaque id is (FR-DAT-003). |
| `display_name` | `text` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `deactivated_at` | `timestamp with time zone` |  |  |  |
| `archived_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `tenant_code_not_blank` — `CHECK ((btrim(tenant_code) <> ''::text))`
- `tenant_code_unique` — `UNIQUE (tenant_code)`
- `tenant_display_name_not_blank` — `CHECK ((btrim(display_name) <> ''::text))`
- `tenant_lifecycle_consistent` — `CHECK ((((status = 'active'::org.lifecycle_status) AND (deactivated_at IS NULL) AND (archived_at IS NULL)) OR ((status = 'inactive'::org.lifecycle_status) AND (deactivated_at IS NOT NULL) AND (archived_at IS NULL)) OR ((status = 'archived'::org.lifecycle_status) AND (archived_at IS NOT NULL))))`
- `tenant_pkey` — `PRIMARY KEY (id)`
- `tenant_row_version_positive` — `CHECK ((row_version > 0))`

Policies:

- `tenant_isolation` — `((app.current_tenant_id() IS NOT NULL) AND (id = app.current_tenant_id()))`

### `payments`

FR-PAY-001 … FR-PAY-017. What was tendered, by whom, through which adapter, verified how, and allocated separately to the bill balance and to the tip. Its own schema rather than a corner of billing because a bill is a document that states what is owed and a payment is an event that says what arrived; M4-A's doctrine only holds if the second cannot quietly become part of the first.

#### `payments.allocation`

FR-PAY-017. Where one payment went: some to the bill balance, some to a tip, as separate rows so each can be reversed without the other. The amount is what was allocated AT CAPTURE and is never recalculated — payments.allocation_view() returns this column, and tests/m4b proves from the catalog that no function in this schema derives an allocation figure from a bill instead of reading it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `payment_id` | `uuid` | NOT NULL |  |  |
| `target` | `payments.allocation_target` | NOT NULL |  |  |
| `bill_id` | `uuid` |  |  |  |
| `tip_id` | `uuid` |  |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `allocated_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `allocation_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `allocation_is_earned` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `allocation_one_per_target` — `UNIQUE (payment_id, target)`
- `allocation_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `allocation_payment_fk` — `FOREIGN KEY (tenant_id, payment_id) REFERENCES payments.payment(tenant_id, id) ON DELETE CASCADE`
- `allocation_pkey` — `PRIMARY KEY (id)`
- `allocation_subject_matches_target` — `CHECK ((((target = 'bill_balance'::payments.allocation_target) AND (bill_id IS NOT NULL) AND (tip_id IS NULL)) OR ((target = 'tip'::payments.allocation_target) AND (tip_id IS NOT NULL) AND (bill_id IS NULL))))`
- `allocation_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `allocation_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `tender_is_fully_accounted` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`

Policies:

- `allocation_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.payment`

FR-PAY-002, FR-PAY-003, FR-PAY-014. One tender: what arrived, through which adapter, with which evidence. The figures are STORED — FR-PAY-017 forbids hidden recomputation, and a payment whose amounts were derived at read time would follow the bill rather than the drawer. Folded from payments.payment_event and written by payments.apply_event() alone.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `intent_id` | `uuid` | NOT NULL |  |  |
| `adapter_id` | `uuid` | NOT NULL |  |  |
| `adapter_mode` | `payments.adapter_mode` | NOT NULL |  |  |
| `provider` | `payments.provider` | NOT NULL |  |  |
| `outcome` | `payments.live_outcome` |  |  | What a LIVE adapter reported. Typed payments.live_outcome, a type no simulator can produce a value of. NULL exactly when the adapter is simulated, by CHECK — so NC-M4-003's claim has neither a column to be written into nor a flag to be flipped. |
| `state` | `payments.payment_state` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `tendered_minor` | `money.amount_minor` | NOT NULL |  |  |
| `change_minor` | `money.amount_minor` | NOT NULL | `0` |  |
| `proof_id` | `uuid` |  |  |  |
| `proof_state` | `payments.proof_state` |  |  |  |
| `terminal_result_id` | `uuid` |  |  |  |
| `captured_by_user_id` | `uuid` | NOT NULL |  |  |
| `captured_at` | `timestamp with time zone` | NOT NULL |  |  |
| `correlation_id` | `uuid` |  |  |  |
| `ledger_sequence` | `integer` | NOT NULL |  |  |

Constraints:

- `payment_actor_fk` — `FOREIGN KEY (tenant_id, captured_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `payment_adapter_fk` — `FOREIGN KEY (adapter_id, adapter_mode) REFERENCES payments.payment_adapter(id, mode) ON DELETE RESTRICT`
- `payment_change_is_cash_only` — `CHECK ((((change_minor)::bigint = 0) OR (provider = 'cash'::payments.provider)))`
- `payment_change_not_negative` — `CHECK (((change_minor)::bigint >= 0))`
- `payment_evidence_matches_the_provider` — `CHECK (`
- `payment_intent_fk` — `FOREIGN KEY (tenant_id, intent_id) REFERENCES payments.payment_intent(tenant_id, id) ON DELETE RESTRICT`
- `payment_ledger_sequence_positive` — `CHECK ((ledger_sequence >= 1))`
- `payment_live_outcome_only_when_live` — `CHECK ((((adapter_mode = 'live'::payments.adapter_mode) AND (outcome IS NOT NULL)) OR ((adapter_mode = 'simulated'::payments.adapter_mode) AND (outcome IS NULL))))`
- `payment_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `payment_pkey` — `PRIMARY KEY (id)`
- `payment_proof_fk` — `FOREIGN KEY (proof_id, proof_state) REFERENCES payments.proof_confirmation(id, state) ON DELETE RESTRICT`
- `payment_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `payment_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `payment_tendered_positive` — `CHECK (((tendered_minor)::bigint > 0))`
- `payment_terminal_result_fk` — `FOREIGN KEY (tenant_id, terminal_result_id) REFERENCES payments.terminal_result(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `payment_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.payment_adapter`

FR-PAY-015 and FR-INT-011. Which payment adapters this outlet has and which world each is in. mode is DERIVED from provider by CHECK and neither column may be updated, so NC-M4-003's "label a direct-provider simulator as live" has no path through configuration at all — the promotion it attempts is not a value that exists.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `provider` | `payments.provider` | NOT NULL |  |  |
| `mode` | `payments.adapter_mode` | NOT NULL |  |  |
| `active` | `boolean` | NOT NULL | `true` | Whether this outlet can actually use it (FR-INT-011). Distinct from mode on purpose: an outlet without a card terminal deactivates the external-terminal adapter, and that is an operator's decision. Nobody decides whether a direct API is simulated. |
| `activated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `payment_adapter_identity_includes_mode` — `UNIQUE (id, mode)`
- `payment_adapter_mode_is_derived_from_the_provider` — `CHECK ((mode =`
- `payment_adapter_one_per_provider` — `UNIQUE (tenant_id, outlet_id, provider)`
- `payment_adapter_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `payment_adapter_pkey` — `PRIMARY KEY (id)`
- `payment_adapter_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `payment_adapter_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `payment_adapter_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.payment_event`

FR-DAT-008B. Everything that happened to a payment, append-only by trigger and by grant. The projections below are folded from it, so a correction is another event rather than an edit and a rebuild reproduces every figure.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL | `nextval('payments.payment_event_id_seq'::regclass)` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `payment_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `kind` | `payments.payment_event_kind` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `actor_user_id` | `uuid` |  |  |  |
| `override_id` | `uuid` |  |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `reason_text` | `text` |  |  |  |
| `before` | `jsonb` |  |  |  |
| `after` | `jsonb` |  |  |  |
| `correlation_id` | `uuid` |  |  |  |

Constraints:

- `payment_event_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `payment_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `payment_event_override_fk` — `FOREIGN KEY (tenant_id, override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `payment_event_pkey` — `PRIMARY KEY (id)`
- `payment_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `payment_event_reversal_states_a_reason` — `CHECK (((kind <> 'reversed'::payments.payment_event_kind) OR ((reason_code_id IS NOT NULL) AND (btrim(COALESCE(reason_text, ''::text)) <> ''::text))))`
- `payment_event_sequence_positive` — `CHECK ((sequence_number >= 1))`
- `payment_event_sequence_unique` — `UNIQUE (tenant_id, payment_id, sequence_number)`
- `payment_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `payment_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.payment_intent`

FR-PAY-001. What a specific payer is about to pay, for a specific bill balance, with the tip kept as its own figure from the first record onward. Idempotent by unique key so FR-PAY-012's retry cannot produce a second one, and expiring so an abandoned intent does not authorize a payment tomorrow.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `bill_id` | `uuid` | NOT NULL |  |  |
| `bill_share_id` | `uuid` |  |  |  |
| `tip_id` | `uuid` |  |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `bill_amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `tip_amount_minor` | `money.amount_minor` | NOT NULL | `0` |  |
| `permitted_providers` | `payments.provider[]` | NOT NULL |  |  |
| `idempotency_key` | `text` | NOT NULL |  |  |
| `expires_at` | `timestamp with time zone` | NOT NULL |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `created_by_user_id` | `uuid` | NOT NULL |  |  |

Constraints:

- `payment_intent_actor_fk` — `FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `payment_intent_bill_amount_not_negative` — `CHECK (((bill_amount_minor)::bigint >= 0))`
- `payment_intent_expires` — `CHECK ((expires_at > created_at))`
- `payment_intent_idempotent` — `UNIQUE (tenant_id, idempotency_key)`
- `payment_intent_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `payment_intent_pays_for_something` — `CHECK ((((bill_amount_minor)::bigint > 0) OR ((tip_amount_minor)::bigint > 0)))`
- `payment_intent_permits_a_method` — `CHECK ((array_length(permitted_providers, 1) >= 1))`
- `payment_intent_pkey` — `PRIMARY KEY (id)`
- `payment_intent_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `payment_intent_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `payment_intent_tip_amount_names_a_tip` — `CHECK (((((tip_amount_minor)::bigint = 0) AND (tip_id IS NULL)) OR (((tip_amount_minor)::bigint > 0) AND (tip_id IS NOT NULL))))`
- `payment_intent_tip_amount_not_negative` — `CHECK (((tip_amount_minor)::bigint >= 0))`

Policies:

- `payment_intent_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.proof_confirmation`

FR-PAY-014 and FR-PAY-015. A member of staff opened Telebirr or CBE Birr, saw a receipt, and said so. The attestation is the artifact: who, what they saw, and when, all four required together by CHECK. An unverified proof stays pending and cannot settle anything, because payments.assert_allocation_is_earned() reads the state through a foreign key that pins it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `provider` | `payments.provider` | NOT NULL |  |  |
| `state` | `payments.proof_state` | NOT NULL | `'pending'::payments.proof_state` |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `provider_reference` | `text` | NOT NULL |  |  |
| `masked_identifier` | `text` |  |  |  |
| `verified_by_user_id` | `uuid` |  |  |  |
| `verified_by_session_id` | `uuid` |  |  |  |
| `verified_at` | `timestamp with time zone` |  |  |  |
| `what_the_verifier_saw` | `text` |  |  |  |
| `raised_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `proof_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `proof_confirmation_pkey` — `PRIMARY KEY (id)`
- `proof_identity_includes_state` — `UNIQUE (id, state)`
- `proof_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `proof_provider_is_proof_based` — `CHECK ((provider = ANY (ARRAY['telebirr_proof'::payments.provider, 'cbe_birr_proof'::payments.provider])))`
- `proof_reference_not_blank` — `CHECK ((btrim(provider_reference) <> ''::text))`
- `proof_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `proof_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `proof_unverified_carries_no_attestation` — `CHECK (((state = 'verified'::payments.proof_state) OR ((verified_by_user_id IS NULL) AND (verified_by_session_id IS NULL) AND (verified_at IS NULL) AND (what_the_verifier_saw IS NULL))))`
- `proof_verified_is_attributed` — `CHECK (((state <> 'verified'::payments.proof_state) OR ((verified_by_user_id IS NOT NULL) AND (verified_by_session_id IS NOT NULL) AND (verified_at IS NOT NULL) AND (btrim(COALESCE(what_the_verifier_saw, ''::text)) <> ''::text))))`
- `proof_verifier_fk` — `FOREIGN KEY (tenant_id, verified_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `proof_verifier_session_fk` — `FOREIGN KEY (tenant_id, verified_by_session_id) REFERENCES identity.session(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `proof_confirmation_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.reversal`

FR-PAY-009. Money going back, against ONE allocation, so a tip and a bill payment are refunded independently. Permissions, reason code and approval threshold are all required; the threshold is read from config.policy, and the approval reuses M3-D's override, whose approver is derived from the approving session rather than supplied.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `allocation_id` | `uuid` | NOT NULL |  |  |
| `kind` | `payments.reversal_kind` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `override_id` | `uuid` |  |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `reason_text` | `text` | NOT NULL |  |  |
| `actor_user_id` | `uuid` | NOT NULL |  |  |
| `reversed_at` | `timestamp with time zone` | NOT NULL |  |  |
| `ledger_sequence` | `integer` | NOT NULL |  |  |

Constraints:

- `reversal_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `reversal_allocation_fk` — `FOREIGN KEY (tenant_id, allocation_id) REFERENCES payments.allocation(tenant_id, id) ON DELETE CASCADE`
- `reversal_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `reversal_is_authorized` — `TRIGGER`
- `reversal_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `reversal_override_fk` — `FOREIGN KEY (tenant_id, override_id) REFERENCES pos.override_approval(tenant_id, id) ON DELETE RESTRICT`
- `reversal_override_used_once` — `UNIQUE (override_id)`
- `reversal_pkey` — `PRIMARY KEY (id)`
- `reversal_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `reversal_reason_not_blank` — `CHECK ((btrim(reason_text) <> ''::text))`
- `reversal_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `reversal_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `reversal_within_the_allocation` — `TRIGGER`

Policies:

- `reversal_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.simulated_attempt`

What a direct-provider simulator returned (FR-PAY-015). A real record of a real call to a thing that is not contracted. It carries simulated_outcome and no live_outcome column exists here, so the row cannot be mistaken for a provider result even by something reading it carelessly.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `adapter_id` | `uuid` | NOT NULL |  |  |
| `adapter_mode` | `payments.adapter_mode` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `result` | `payments.simulated_outcome` | NOT NULL |  |  |
| `simulated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `requested_by_user_id` | `uuid` |  |  |  |

Constraints:

- `simulated_attempt_actor_fk` — `FOREIGN KEY (tenant_id, requested_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `simulated_attempt_adapter_fk` — `FOREIGN KEY (adapter_id, adapter_mode) REFERENCES payments.payment_adapter(id, mode) ON DELETE RESTRICT`
- `simulated_attempt_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `simulated_attempt_is_simulated` — `CHECK ((adapter_mode = 'simulated'::payments.adapter_mode))`
- `simulated_attempt_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `simulated_attempt_pkey` — `PRIMARY KEY (id)`
- `simulated_attempt_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `simulated_attempt_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `simulated_attempt_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `payments.terminal_result`

FR-PAY-003. What an external card terminal reported, recorded by the person who read it off the slip. There is no column for a primary account number, a verification value or a cryptogram, and payments.refuse_card_data() walks every string on the row in case a later column forgets. During an outage this method stays available exactly when the terminal itself can complete the payment, which is a fact about the terminal and is why the record is of a RESULT rather than of a request.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `terminal_reference` | `text` | NOT NULL |  |  |
| `scheme` | `text` | NOT NULL |  |  |
| `masked_tail` | `text` |  |  |  |
| `approval_code` | `text` |  |  |  |
| `outcome` | `payments.live_outcome` | NOT NULL |  |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `recorded_by_user_id` | `uuid` | NOT NULL |  |  |
| `recorded_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `terminal_result_actor_fk` — `FOREIGN KEY (tenant_id, recorded_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `terminal_result_amount_positive` — `CHECK (((amount_minor)::bigint > 0))`
- `terminal_result_approval_code_is_short` — `CHECK (((approval_code IS NULL) OR (approval_code ~ '^[A-Za-z0-9]{1,12}$'::text)))`
- `terminal_result_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `terminal_result_pkey` — `PRIMARY KEY (id)`
- `terminal_result_scheme_not_blank` — `CHECK ((btrim(scheme) <> ''::text))`
- `terminal_result_tail_is_at_most_four_digits` — `CHECK (((masked_tail IS NULL) OR (masked_tail ~ '^[0-9]{4}$'::text)))`
- `terminal_result_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `terminal_result_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `terminal_result_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `pos`

The staff surface: terminals, role home, table view, operational search, manager override and handover. Ordering is NOT here — a waiter-entered order goes through ordering.submit_order() exactly as a guest-entered one does (FR-POS-003A).

#### `pos.confirmation_requirement`

FR-UX-015, FR-POS-009. How much friction an action carries, graded by its consequence. Read by the staff surface; never decided by it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `consequence` | `pos.consequence` | NOT NULL |  |  |
| `requires_reason` | `boolean` | NOT NULL |  |  |
| `graded_from_gate` | `text` | NOT NULL |  |  |

Constraints:

- `confirmation_action_not_blank` — `CHECK ((btrim(action_code) <> ''::text))`
- `confirmation_deliberate_states_a_reason` — `CHECK (((consequence <> 'deliberate'::pos.consequence) OR (requires_reason = true)))`
- `confirmation_requirement_pkey` — `PRIMARY KEY (tenant_id, action_code)`
- `confirmation_routine_asks_for_nothing` — `CHECK (((consequence <> 'routine'::pos.consequence) OR (requires_reason = false)))`
- `confirmation_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE CASCADE`

Policies:

- `confirmation_requirement_isolation` — `app.row_in_scope(tenant_id, NULL::uuid)`

#### `pos.fast_pick`

FR-POS-005. Favourites for fast entry. A row with no user is the outlet's shared set; a row with one is personal.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `user_account_id` | `uuid` |  |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `position` | `integer` | NOT NULL |  |  |

Constraints:

- `fast_pick_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE CASCADE`
- `fast_pick_once` — `UNIQUE (tenant_id, outlet_id, user_account_id, item_id)`
- `fast_pick_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `fast_pick_pkey` — `PRIMARY KEY (id)`
- `fast_pick_position_positive` — `CHECK (("position" > 0))`
- `fast_pick_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `fast_pick_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE CASCADE`

Policies:

- `fast_pick_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `pos.handover`

FR-POS-007. Responsibility for open tables and tasks moving between two named people, acknowledged by the recipient. Not a shift and not a schedule: it records a transfer that happened, never when anybody is due to work.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `from_user_id` | `uuid` | NOT NULL |  |  |
| `to_user_id` | `uuid` | NOT NULL |  |  |
| `state` | `pos.handover_state` | NOT NULL | `'proposed'::pos.handover_state` |  |
| `proposed_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `proposed_by_user_id` | `uuid` | NOT NULL |  |  |
| `acknowledged_at` | `timestamp with time zone` |  |  |  |
| `acknowledged_by_user_id` | `uuid` |  |  |  |
| `cancelled_at` | `timestamp with time zone` |  |  |  |
| `note` | `text` |  |  |  |

Constraints:

- `handover_acknowledged_is_stated` — `CHECK (((state = 'acknowledged'::pos.handover_state) = ((acknowledged_at IS NOT NULL) AND (acknowledged_by_user_id IS NOT NULL))))`
- `handover_acknowledger_fk` — `FOREIGN KEY (tenant_id, acknowledged_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `handover_acknowledger_is_recipient` — `CHECK (((acknowledged_by_user_id IS NULL) OR (acknowledged_by_user_id = to_user_id)))`
- `handover_cancelled_is_stated` — `CHECK (((state = 'cancelled'::pos.handover_state) = (cancelled_at IS NOT NULL)))`
- `handover_from_fk` — `FOREIGN KEY (tenant_id, from_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `handover_moves_between_people` — `CHECK ((from_user_id <> to_user_id))`
- `handover_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `handover_pkey` — `PRIMARY KEY (id)`
- `handover_proposer_fk` — `FOREIGN KEY (tenant_id, proposed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `handover_responsibility_survives` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `handover_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `handover_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `handover_to_fk` — `FOREIGN KEY (tenant_id, to_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `handover_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `pos.handover_item`

What a handover carries: the open tables and the open service requests. Captured when the handover is proposed, so what was accepted is what was offered.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `handover_id` | `uuid` | NOT NULL |  |  |
| `item_kind` | `pos.handover_item_kind` | NOT NULL |  |  |
| `table_session_id` | `uuid` |  |  |  |
| `service_request_id` | `uuid` |  |  |  |

Constraints:

- `handover_item_handover_fk` — `FOREIGN KEY (tenant_id, handover_id) REFERENCES pos.handover(tenant_id, id) ON DELETE CASCADE`
- `handover_item_names_its_subject` — `CHECK ((((item_kind = 'table_session'::pos.handover_item_kind) AND (table_session_id IS NOT NULL) AND (service_request_id IS NULL)) OR ((item_kind = 'service_request'::pos.handover_item_kind) AND (service_request_id IS NOT NULL) AND (table_session_id IS NULL))))`
- `handover_item_once` — `UNIQUE (handover_id, item_kind, table_session_id, service_request_id)`
- `handover_item_pkey` — `PRIMARY KEY (id)`
- `handover_item_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `handover_item_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `pos.override_approval`

FR-POS-006. Supervisor approval with both identities and the step-up grant it rested on. approver_user_id is DERIVED from the grant's session and is never a parameter, so a manager authenticating into the waiter's session produces an approver equal to the actor and is refused by constraint rather than by policy.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `action_code` | `text` | NOT NULL |  |  |
| `actor_user_id` | `uuid` | NOT NULL |  |  |
| `actor_session_id` | `uuid` | NOT NULL |  |  |
| `approver_user_id` | `uuid` | NOT NULL |  |  |
| `approver_session_id` | `uuid` | NOT NULL |  |  |
| `step_up_grant_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `reason_text` | `text` |  |  |  |
| `subject_kind` | `text` | NOT NULL |  |  |
| `subject_id` | `uuid` | NOT NULL |  |  |
| `approved_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `override_action_not_blank` — `CHECK ((btrim(action_code) <> ''::text))`
- `override_actor_fk` — `FOREIGN KEY (tenant_id, actor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `override_actor_session_fk` — `FOREIGN KEY (tenant_id, actor_session_id) REFERENCES identity.session(tenant_id, id) ON DELETE RESTRICT`
- `override_approval_pkey` — `PRIMARY KEY (id)`
- `override_approver_fk` — `FOREIGN KEY (tenant_id, approver_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `override_approver_is_not_the_actor` — `CHECK ((approver_user_id <> actor_user_id))`
- `override_approver_session_fk` — `FOREIGN KEY (tenant_id, approver_session_id) REFERENCES identity.session(tenant_id, id) ON DELETE RESTRICT`
- `override_grant_fk` — `FOREIGN KEY (step_up_grant_id) REFERENCES identity.step_up_grant(id) ON DELETE RESTRICT`
- `override_grant_used_once` — `UNIQUE (step_up_grant_id)`
- `override_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `override_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `override_sessions_are_not_the_same` — `CHECK ((approver_session_id <> actor_session_id))`
- `override_subject_kind_not_blank` — `CHECK ((btrim(subject_kind) <> ''::text))`
- `override_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `override_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `override_approval_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `pos.terminal`

FR-POS-001. A registered device bound to a tenant, an outlet and a profile, and the record of its revocation. Revoking is not a flag: pos.revoke_terminal() also ends every live session on the device and withdraws its terminal trust, because a compromised terminal whose sessions keep working has not been revoked.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `device_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `profile` | `pos.terminal_profile` | NOT NULL |  |  |
| `registered_by_user_id` | `uuid` | NOT NULL |  |  |
| `registered_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `revoked_at` | `timestamp with time zone` |  |  |  |
| `revoked_by_user_id` | `uuid` |  |  |  |
| `revocation_reason_code_id` | `uuid` |  |  |  |

Constraints:

- `terminal_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `terminal_pkey` — `PRIMARY KEY (device_id)`
- `terminal_registrar_fk` — `FOREIGN KEY (tenant_id, registered_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `terminal_registration_fk` — `FOREIGN KEY (device_id) REFERENCES org.device_registration(device_id) ON DELETE RESTRICT`
- `terminal_revocation_is_explained` — `CHECK ((((revoked_at IS NULL) = (revoked_by_user_id IS NULL)) AND ((revoked_at IS NULL) = (revocation_reason_code_id IS NULL))))`
- `terminal_revocation_reason_fk` — `FOREIGN KEY (tenant_id, revocation_reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `terminal_revoker_fk` — `FOREIGN KEY (tenant_id, revoked_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `terminal_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `terminal_tenant_id_unique` — `UNIQUE (tenant_id, device_id)`

Policies:

- `terminal_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

### `safety`

Allergen and dietary safety: the tenant- and jurisdiction-configurable catalog, declarations by item, variant and modifier, and live resolution. Nothing here is cached or pinned into a customer-facing read path.

#### `safety.allergen`

The tenant and jurisdiction configurable allergen catalog (FR-SAF-001). Customer text lives in menu.translation as a safety-critical field, so it inherits the human-reviewer requirement and blocks publication when absent. The icon is stored here but is not readable by the application role: icons supplement written warnings and never replace them (FR-SAF-002), which is enforced by there being no query path that returns one without the other.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `jurisdiction_code` | `text` | NOT NULL |  |  |
| `kitchen_code` | `text` | NOT NULL |  |  |
| `icon_key` | `text` |  |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `allergen_icon_key_not_blank` — `CHECK (((icon_key IS NULL) OR (btrim(icon_key) <> ''::text)))`
- `allergen_jurisdiction_fk` — `FOREIGN KEY (jurisdiction_code) REFERENCES safety.jurisdiction(code) ON DELETE RESTRICT`
- `allergen_kitchen_code_not_blank` — `CHECK ((btrim(kitchen_code) <> ''::text))`
- `allergen_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `allergen_pkey` — `PRIMARY KEY (id)`
- `allergen_row_version_positive` — `CHECK ((row_version > 0))`
- `allergen_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `allergen_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `allergen_unique` — `UNIQUE (tenant_id, jurisdiction_code, kitchen_code)`

Policies:

- `allergen_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.allergy_concern`

An allergy concern flagged for a table by a guest or a waiter (FR-SAF-003), with the exact acknowledgement wording the guest was shown. The order-level flag and the waiter workflow around it arrive at M3; the table-level record is this. guest_session_id is ON DELETE SET NULL so anonymizing a guest severs the identity and leaves the concern, which is operational evidence rather than personal data.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `raised_by` | `service.concern_source` | NOT NULL |  |  |
| `guest_session_id` | `uuid` |  |  |  |
| `raised_by_user_id` | `uuid` |  |  |  |
| `allergen_id` | `uuid` |  |  |  |
| `note` | `text` |  |  |  |
| `acknowledgement_wording_id` | `uuid` | NOT NULL |  |  |
| `acknowledgement_text` | `text` | NOT NULL |  |  |
| `acknowledged_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `acknowledged_by_user_id` | `uuid` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `allergy_concern_allergen_fk` — `FOREIGN KEY (tenant_id, allergen_id) REFERENCES safety.allergen(tenant_id, id) ON DELETE RESTRICT`
- `allergy_concern_attributed` — `CHECK ((((raised_by = 'waiter'::service.concern_source) AND (raised_by_user_id IS NOT NULL)) OR ((raised_by = 'guest'::service.concern_source) AND (guest_session_id IS NOT NULL))))`
- `allergy_concern_guest_fk` — `FOREIGN KEY (tenant_id, guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE SET NULL`
- `allergy_concern_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `allergy_concern_pkey` — `PRIMARY KEY (id)`
- `allergy_concern_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `allergy_concern_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `allergy_concern_text_not_blank` — `CHECK ((btrim(acknowledgement_text) <> ''::text))`
- `allergy_concern_user_fk` — `FOREIGN KEY (tenant_id, raised_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `allergy_concern_wording_fk` — `FOREIGN KEY (tenant_id, acknowledgement_wording_id) REFERENCES safety.approved_wording(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `allergy_concern_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.approved_wording`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `purpose` | `text` | NOT NULL |  |  |
| `locale` | `menu.customer_locale` | NOT NULL |  |  |
| `wording` | `text` | NOT NULL |  |  |
| `approved_by_user_id` | `uuid` | NOT NULL |  |  |
| `approved_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `approved_wording_approver_fk` — `FOREIGN KEY (tenant_id, approved_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `approved_wording_not_blank` — `CHECK ((btrim(wording) <> ''::text))`
- `approved_wording_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `approved_wording_pkey` — `PRIMARY KEY (id)`
- `approved_wording_purpose_not_blank` — `CHECK ((btrim(purpose) <> ''::text))`
- `approved_wording_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `approved_wording_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `approved_wording_unique` — `UNIQUE (tenant_id, purpose, locale)`

Policies:

- `approved_wording_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.declaration`

What an item, variant or modifier declares about an allergen, in one of three classes, with the version history intact (FR-SAF-002). The currently effective row is the one with effective_to IS NULL. There is no derived or cached table beside this one: safety.effective_allergens() computes from these rows on every call, because a stored answer that does not move when its inputs move is a safety defect rather than a caching bug (FR-SAF-005).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `subject` | `menu.menu_entity` | NOT NULL |  |  |
| `subject_id` | `uuid` | NOT NULL |  |  |
| `allergen_id` | `uuid` | NOT NULL |  |  |
| `declaration_class` | `safety.declaration_class` | NOT NULL |  |  |
| `effective_version` | `integer` | NOT NULL | `1` |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `review_state` | `safety.review_state` | NOT NULL | `'draft'::safety.review_state` |  |
| `created_by_user_id` | `uuid` | NOT NULL |  |  |
| `reviewed_by_user_id` | `uuid` |  |  |  |
| `reviewed_at` | `timestamp with time zone` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `declaration_allergen_fk` — `FOREIGN KEY (tenant_id, allergen_id) REFERENCES safety.allergen(tenant_id, id) ON DELETE RESTRICT`
- `declaration_approval_is_reviewed` — `CHECK (((review_state = 'approved'::safety.review_state) = ((reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL))))`
- `declaration_author_fk` — `FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `declaration_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `declaration_pkey` — `PRIMARY KEY (id)`
- `declaration_range_ordered` — `CHECK (((effective_to IS NULL) OR (effective_to > effective_from)))`
- `declaration_reviewer_fk` — `FOREIGN KEY (tenant_id, reviewed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `declaration_subject_can_carry_ingredients` — `CHECK ((subject = ANY (ARRAY['item'::menu.menu_entity, 'variant'::menu.menu_entity, 'modifier'::menu.menu_entity])))`
- `declaration_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `declaration_version_positive` — `CHECK ((effective_version > 0))`

Policies:

- `declaration_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.declaration_reference`

What was believed at publication, or when a line was added to a cart. It exists so a later dispute can establish what the kitchen had declared at that moment, and for no other purpose. The application role holds INSERT and nothing else: it cannot SELECT these rows, and no function it may execute returns them. That is deliberate and it is the point — a readable pinned value becomes a cache the first time a display path is under deadline, and a cached allergen is exactly the defect FR-SAF-005 names. Reading this table is an audit activity performed by an identity that is not serving a guest.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `context` | `safety.reference_context` | NOT NULL |  |  |
| `context_id` | `uuid` | NOT NULL |  |  |
| `declaration_id` | `uuid` | NOT NULL |  |  |
| `effective_version` | `integer` | NOT NULL |  |  |
| `recorded_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `declaration_reference_declaration_fk` — `FOREIGN KEY (declaration_id) REFERENCES safety.declaration(id) ON DELETE RESTRICT`
- `declaration_reference_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `declaration_reference_pkey` — `PRIMARY KEY (id)`
- `declaration_reference_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `declaration_reference_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.dietary_claim`

Vegetarian, vegan, fasting, halal and whatever else a tenant defines (FR-SAF-006). Fasting is a first-class claim rather than a note: in the pilot market a large share of the calendar is fasting, and an outlet that cannot state it loses the business.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `code` | `text` | NOT NULL |  |  |
| `definition` | `text` | NOT NULL |  |  |
| `evidence_owner_user_id` | `uuid` | NOT NULL |  |  |
| `review_due_on` | `date` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `dietary_claim_code_not_blank` — `CHECK ((btrim(code) <> ''::text))`
- `dietary_claim_definition_not_blank` — `CHECK ((btrim(definition) <> ''::text))`
- `dietary_claim_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `dietary_claim_owner_fk` — `FOREIGN KEY (tenant_id, evidence_owner_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `dietary_claim_pkey` — `PRIMARY KEY (id)`
- `dietary_claim_row_version_positive` — `CHECK ((row_version > 0))`
- `dietary_claim_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `dietary_claim_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `dietary_claim_unique` — `UNIQUE (tenant_id, code)`

Policies:

- `dietary_claim_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.dietary_claim_outlet`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `claim_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |

Constraints:

- `dietary_claim_outlet_claim_fk` — `FOREIGN KEY (tenant_id, claim_id) REFERENCES safety.dietary_claim(tenant_id, id) ON DELETE RESTRICT`
- `dietary_claim_outlet_node_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `dietary_claim_outlet_pkey` — `PRIMARY KEY (claim_id, outlet_id)`

Policies:

- `dietary_claim_outlet_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.item_dietary_claim`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` |  |  |  |
| `subject` | `menu.menu_entity` | NOT NULL |  |  |
| `subject_id` | `uuid` | NOT NULL |  |  |
| `claim_id` | `uuid` | NOT NULL |  |  |
| `effective_version` | `integer` | NOT NULL | `1` |  |
| `effective_from` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `effective_to` | `timestamp with time zone` |  |  |  |
| `review_state` | `safety.review_state` | NOT NULL | `'draft'::safety.review_state` |  |
| `created_by_user_id` | `uuid` | NOT NULL |  |  |
| `reviewed_by_user_id` | `uuid` |  |  |  |
| `reviewed_at` | `timestamp with time zone` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `item_dietary_claim_approval_is_reviewed` — `CHECK (((review_state = 'approved'::safety.review_state) = ((reviewed_by_user_id IS NOT NULL) AND (reviewed_at IS NOT NULL))))`
- `item_dietary_claim_author_fk` — `FOREIGN KEY (tenant_id, created_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `item_dietary_claim_claim_fk` — `FOREIGN KEY (tenant_id, claim_id) REFERENCES safety.dietary_claim(tenant_id, id) ON DELETE RESTRICT`
- `item_dietary_claim_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `item_dietary_claim_pkey` — `PRIMARY KEY (id)`
- `item_dietary_claim_reviewer_fk` — `FOREIGN KEY (tenant_id, reviewed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `item_dietary_claim_subject` — `CHECK ((subject = ANY (ARRAY['item'::menu.menu_entity, 'variant'::menu.menu_entity, 'modifier'::menu.menu_entity])))`
- `item_dietary_claim_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `item_dietary_claim_version_positive` — `CHECK ((effective_version > 0))`

Policies:

- `item_dietary_claim_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `safety.jurisdiction`

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `code` | `text` | NOT NULL |  |  |
| `display_name` | `text` | NOT NULL |  |  |

Constraints:

- `jurisdiction_code_not_blank` — `CHECK ((btrim(code) <> ''::text))`
- `jurisdiction_display_name_not_blank` — `CHECK ((btrim(display_name) <> ''::text))`
- `jurisdiction_pkey` — `PRIMARY KEY (code)`

#### `safety.jurisdiction_requirement`

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `jurisdiction_code` | `text` | NOT NULL |  |  |
| `kitchen_code` | `text` | NOT NULL |  |  |

Constraints:

- `jurisdiction_requirement_fk` — `FOREIGN KEY (jurisdiction_code) REFERENCES safety.jurisdiction(code) ON DELETE RESTRICT`
- `jurisdiction_requirement_pkey` — `PRIMARY KEY (jurisdiction_code, kitchen_code)`

### `service`

Table service: QR resolution, occupancy, guest sessions, carts before submission, and table ownership. Submission itself is M3 and has no representation here.

#### `service.cart`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `kind` | `service.cart_kind` | NOT NULL |  |  |
| `owner_guest_session_id` | `uuid` |  |  |  |
| `state` | `service.cart_state` | NOT NULL | `'open'::service.cart_state` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `cart_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `cart_owner_fk` — `FOREIGN KEY (tenant_id, owner_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `cart_ownership_matches_kind` — `CHECK (((kind = 'personal'::service.cart_kind) = (owner_guest_session_id IS NOT NULL)))`
- `cart_pkey` — `PRIMARY KEY (id)`
- `cart_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `cart_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `cart_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `cart_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.cart_line`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `cart_id` | `uuid` | NOT NULL |  |  |
| `item_id` | `uuid` | NOT NULL |  |  |
| `variant_id` | `uuid` | NOT NULL |  |  |
| `quantity` | `integer` | NOT NULL | `1` |  |
| `currency_code` | `character(3)` | NOT NULL |  |  |
| `unit_amount_minor` | `money.amount_minor` | NOT NULL |  |  |
| `added_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `added_by_guest_session_id` | `uuid` |  |  |  |

Constraints:

- `cart_line_cart_fk` — `FOREIGN KEY (tenant_id, cart_id) REFERENCES service.cart(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_currency_fk` — `FOREIGN KEY (currency_code) REFERENCES money.currency(code) ON DELETE RESTRICT`
- `cart_line_guest_fk` — `FOREIGN KEY (tenant_id, added_by_guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_item_fk` — `FOREIGN KEY (item_id) REFERENCES menu.sellable_item(id) ON DELETE RESTRICT`
- `cart_line_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_pkey` — `PRIMARY KEY (id)`
- `cart_line_quantity_positive` — `CHECK ((quantity > 0))`
- `cart_line_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `cart_line_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `cart_line_variant_fk` — `FOREIGN KEY (variant_id) REFERENCES menu.item_variant(id) ON DELETE RESTRICT`

Policies:

- `cart_line_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.cart_line_modifier`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `cart_line_id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `modifier_id` | `uuid` | NOT NULL |  |  |

Constraints:

- `cart_line_modifier_line_fk` — `FOREIGN KEY (tenant_id, cart_line_id) REFERENCES service.cart_line(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_modifier_modifier_fk` — `FOREIGN KEY (modifier_id) REFERENCES menu.modifier(id) ON DELETE RESTRICT`
- `cart_line_modifier_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_modifier_pkey` — `PRIMARY KEY (cart_line_id, modifier_id)`
- `cart_line_modifier_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `cart_line_modifier_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.cart_line_transfer`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `cart_line_id` | `uuid` | NOT NULL |  |  |
| `from_cart_id` | `uuid` | NOT NULL |  |  |
| `to_cart_id` | `uuid` | NOT NULL |  |  |
| `moved_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `moved_by_guest_session_id` | `uuid` |  |  |  |

Constraints:

- `cart_line_transfer_from_fk` — `FOREIGN KEY (tenant_id, from_cart_id) REFERENCES service.cart(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_transfer_line_fk` — `FOREIGN KEY (tenant_id, cart_line_id) REFERENCES service.cart_line(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_transfer_moves` — `CHECK ((from_cart_id <> to_cart_id))`
- `cart_line_transfer_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `cart_line_transfer_pkey` — `PRIMARY KEY (id)`
- `cart_line_transfer_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `cart_line_transfer_to_fk` — `FOREIGN KEY (tenant_id, to_cart_id) REFERENCES service.cart(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `cart_line_transfer_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.guest_session`

A privacy-minimized guest session for QR ordering (FR-AUTH-003): no phone, no email, no registration, no link to a user account. It expires on a date it carries, and config.apply_retention anonymizes it under an "anonymize" policy rather than deleting it, because the allergy concerns raised at a table outlive the identity that raised them (FR-CST-002).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `display_nickname` | `text` |  |  |  |
| `locale` | `menu.customer_locale` | NOT NULL | `'en'::menu.customer_locale` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `expires_at` | `timestamp with time zone` | NOT NULL |  |  |
| `anonymized_at` | `timestamp with time zone` |  |  |  |
| `token_hash` | `bytea` |  |  | SHA-256 of the bearer token the browser holds. The token itself is returned once by service.mint_guest_session() and stored nowhere, so a dump of this table lets nobody resume a guest's session (FR-SEC-007). Nullable because M2-B creates guest sessions from the staff side too, and those have no browser to hold anything. |

Constraints:

- `guest_session_anonymization_is_real` — `CHECK (((anonymized_at IS NULL) OR (display_nickname IS NULL)))`
- `guest_session_expiry_after_creation` — `CHECK ((expires_at > created_at))`
- `guest_session_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `guest_session_pkey` — `PRIMARY KEY (id)`
- `guest_session_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `guest_session_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `guest_session_token_is_sha256` — `CHECK (((token_hash IS NULL) OR (octet_length(token_hash) = 32)))`
- `guest_session_token_unique` — `UNIQUE (token_hash)`

Policies:

- `guest_session_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.idempotency_key`

One row per customer write that a browser may retry. The row is claimed BEFORE the work is done and carries the result afterwards, so a retry arriving while the first attempt is still in flight is refused rather than racing it. Nothing at M2-C is committed in the sense M3 and M4 mean, which is exactly why this is the cheap moment to build it: a duplicate cart line is an annoyance and a duplicate payment is not.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `scope` | `text` | NOT NULL |  |  |
| `idem_key` | `text` | NOT NULL |  |  |
| `request_digest` | `bytea` | NOT NULL |  |  |
| `result_id` | `uuid` |  |  |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `idempotency_digest_is_sha256` — `CHECK ((octet_length(request_digest) = 32))`
- `idempotency_key_not_blank` — `CHECK ((btrim(idem_key) <> ''::text))`
- `idempotency_key_pkey` — `PRIMARY KEY (tenant_id, scope, idem_key)`
- `idempotency_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `idempotency_scope_not_blank` — `CHECK ((btrim(scope) <> ''::text))`
- `idempotency_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `idempotency_key_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.ownership_transfer`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `from_user_id` | `uuid` | NOT NULL |  |  |
| `to_user_id` | `uuid` | NOT NULL |  |  |
| `state` | `service.transfer_state` | NOT NULL | `'proposed'::service.transfer_state` |  |
| `reason_code_id` | `uuid` |  |  |  |
| `proposed_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `proposed_by_user_id` | `uuid` | NOT NULL |  |  |
| `acknowledged_at` | `timestamp with time zone` |  |  |  |
| `acknowledged_by_user_id` | `uuid` |  |  |  |
| `supervisor_user_id` | `uuid` |  |  |  |

Constraints:

- `ownership_transfer_pkey` — `PRIMARY KEY (id)`
- `transfer_acknowledgement_is_by_the_receiver` — `CHECK (((state = 'acknowledged'::service.transfer_state) = ((acknowledged_at IS NOT NULL) AND (acknowledged_by_user_id IS NOT NULL))))`
- `transfer_acknowledger_fk` — `FOREIGN KEY (tenant_id, acknowledged_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `transfer_acknowledger_is_recipient` — `CHECK (((acknowledged_by_user_id IS NULL) OR (acknowledged_by_user_id = to_user_id)))`
- `transfer_from_fk` — `FOREIGN KEY (tenant_id, from_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `transfer_not_to_self` — `CHECK ((from_user_id <> to_user_id))`
- `transfer_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `transfer_proposer_fk` — `FOREIGN KEY (tenant_id, proposed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `transfer_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `transfer_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `transfer_supervisor_fk` — `FOREIGN KEY (tenant_id, supervisor_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `transfer_supervisor_named_when_reassigned` — `CHECK (((state = 'supervisor_reassigned'::service.transfer_state) = (supervisor_user_id IS NOT NULL)))`
- `transfer_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `transfer_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `transfer_to_fk` — `FOREIGN KEY (tenant_id, to_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `ownership_transfer_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.qr_placard`

Printable version history (FR-TAB-002): which version of a table's code was put on a placard, when and by whom. It records that a placard was produced, never the code on it. Named for the placard rather than the printing because M1-B guards against any table whose name reads as print-agent or edge behaviour, and it was right to: that is M5a's, and this is a history of physical signs.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `token_id` | `uuid` | NOT NULL |  |  |
| `version` | `integer` | NOT NULL |  |  |
| `printed_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `printed_by_user_id` | `uuid` | NOT NULL |  |  |
| `note` | `text` |  |  |  |

Constraints:

- `qr_placard_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `qr_placard_pkey` — `PRIMARY KEY (id)`
- `qr_placard_printer_fk` — `FOREIGN KEY (tenant_id, printed_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `qr_placard_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `qr_placard_token_fk` — `FOREIGN KEY (tenant_id, token_id) REFERENCES service.table_qr_token(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `qr_placard_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.qr_scan`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `token_id` | `uuid` | NOT NULL |  |  |
| `guest_session_id` | `uuid` | NOT NULL |  |  |
| `scanned_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `occupancy_at_scan` | `integer` |  |  |  |

Constraints:

- `qr_scan_guest_fk` — `FOREIGN KEY (tenant_id, guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `qr_scan_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `qr_scan_pkey` — `PRIMARY KEY (id)`
- `qr_scan_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `qr_scan_token_fk` — `FOREIGN KEY (tenant_id, token_id) REFERENCES service.table_qr_token(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `qr_scan_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.request_escalation`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `service_request_id` | `uuid` | NOT NULL |  |  |
| `from_user_id` | `uuid` |  |  |  |
| `to_user_id` | `uuid` | NOT NULL |  |  |
| `sla_due_at` | `timestamp with time zone` | NOT NULL |  |  |
| `escalated_at` | `timestamp with time zone` | NOT NULL |  |  |
| `overdue_seconds` | `integer` | NOT NULL |  |  |
| `basis` | `text` | NOT NULL |  |  |

Constraints:

- `request_escalation_basis_not_blank` — `CHECK ((btrim(basis) <> ''::text))`
- `request_escalation_from_fk` — `FOREIGN KEY (tenant_id, from_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `request_escalation_moves_it` — `CHECK ((from_user_id IS DISTINCT FROM to_user_id))`
- `request_escalation_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `request_escalation_pkey` — `PRIMARY KEY (id)`
- `request_escalation_request_fk` — `FOREIGN KEY (tenant_id, service_request_id) REFERENCES service.service_request(tenant_id, id) ON DELETE RESTRICT`
- `request_escalation_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `request_escalation_to_fk` — `FOREIGN KEY (tenant_id, to_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `request_escalation_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.request_routing_decision`

FR-SRV-002. The table assignment, service area, role and candidate count that produced an assignment, kept beside the assignment. Without them a routing defect and a staffing gap look identical afterwards.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `service_request_id` | `uuid` | NOT NULL |  |  |
| `table_node_id` | `uuid` | NOT NULL |  |  |
| `service_area_id` | `uuid` |  |  |  |
| `required_role_id` | `uuid` | NOT NULL |  |  |
| `considered_count` | `integer` | NOT NULL |  |  |
| `chosen_user_id` | `uuid` |  |  |  |
| `basis` | `text` | NOT NULL |  |  |
| `decided_at` | `timestamp with time zone` | NOT NULL |  |  |

Constraints:

- `request_routing_decision_pkey` — `PRIMARY KEY (id)`
- `routing_decision_basis_not_blank` — `CHECK ((btrim(basis) <> ''::text))`
- `routing_decision_considered_not_negative` — `CHECK ((considered_count >= 0))`
- `routing_decision_one_per_request` — `UNIQUE (tenant_id, service_request_id)`
- `routing_decision_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `routing_decision_request_fk` — `FOREIGN KEY (tenant_id, service_request_id) REFERENCES service.service_request(tenant_id, id) ON DELETE RESTRICT`
- `routing_decision_role_fk` — `FOREIGN KEY (tenant_id, required_role_id) REFERENCES identity.role(tenant_id, id) ON DELETE RESTRICT`
- `routing_decision_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `routing_decision_user_fk` — `FOREIGN KEY (tenant_id, chosen_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `request_routing_decision_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.request_type`

FR-SRV-001. The seven request types the requirement names are seeded rows, not enum labels: an outlet configures its own. Nothing downstream branches on the code, so an eighth type needs no code change — which is the test of whether this is really configuration.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `code` | `text` | NOT NULL |  |  |
| `canonical_name` | `text` | NOT NULL |  |  |
| `sla_seconds` | `integer` | NOT NULL |  |  |
| `dedup_window_seconds` | `integer` | NOT NULL |  |  |
| `handled_by_role_id` | `uuid` | NOT NULL |  |  |
| `status` | `org.lifecycle_status` | NOT NULL | `'active'::org.lifecycle_status` |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `request_type_code_not_blank` — `CHECK ((btrim(code) <> ''::text))`
- `request_type_code_unique` — `UNIQUE (tenant_id, outlet_id, code)`
- `request_type_dedup_window_not_negative` — `CHECK ((dedup_window_seconds >= 0))`
- `request_type_name_not_blank` — `CHECK ((btrim(canonical_name) <> ''::text))`
- `request_type_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `request_type_pkey` — `PRIMARY KEY (id)`
- `request_type_role_fk` — `FOREIGN KEY (tenant_id, handled_by_role_id) REFERENCES identity.role(tenant_id, id) ON DELETE RESTRICT`
- `request_type_sla_positive` — `CHECK ((sla_seconds > 0))`
- `request_type_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `request_type_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `request_type_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.service_request`

FR-SRV-001 … FR-SRV-009 and FR-SRV-008's staff tasks, which are the same aggregate with origin = staff. Bound to the TABLE SESSION rather than the order, because a guest who has ordered nothing can still need something.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `order_id` | `uuid` |  |  |  |
| `request_type_id` | `uuid` | NOT NULL |  |  |
| `origin` | `service.request_origin` | NOT NULL |  |  |
| `state` | `service.request_state` | NOT NULL |  |  |
| `raised_by_guest_session_id` | `uuid` |  |  |  |
| `raised_by_user_id` | `uuid` |  |  |  |
| `note` | `text` |  |  |  |
| `assigned_user_id` | `uuid` |  |  |  |
| `assigned_role_id` | `uuid` |  |  |  |
| `customer_locale` | `menu.customer_locale` | NOT NULL |  |  |
| `dedup_group` | `uuid` | NOT NULL |  |  |
| `repeat_ordinal` | `integer` | NOT NULL | `1` |  |
| `raised_at` | `timestamp with time zone` | NOT NULL |  |  |
| `sla_due_at` | `timestamp with time zone` | NOT NULL |  |  |
| `acknowledged_at` | `timestamp with time zone` |  |  |  |
| `started_at` | `timestamp with time zone` |  |  |  |
| `completed_at` | `timestamp with time zone` |  |  |  |
| `escalated_at` | `timestamp with time zone` |  |  |  |
| `completion_status` | `service.completion_status` |  |  |  |
| `completion_reason_code_id` | `uuid` |  |  |  |
| `completion_note` | `text` |  |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `ledger_sequence` | `integer` | NOT NULL |  |  |

Constraints:

- `service_request_active_has_an_assignee` — `CHECK (((state = ANY (ARRAY['new'::service.request_state, 'cancelled'::service.request_state, 'expired'::service.request_state])) OR (assigned_user_id IS NOT NULL)))`
- `service_request_assignee_fk` — `FOREIGN KEY (tenant_id, assigned_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `service_request_completion_is_stated` — `CHECK (((state = ANY (ARRAY['completed'::service.request_state, 'unresolved'::service.request_state])) = (completion_status IS NOT NULL)))`
- `service_request_completion_reason_fk` — `FOREIGN KEY (tenant_id, completion_reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `service_request_impossible_is_explained` — `CHECK (((completion_status IS DISTINCT FROM 'not_possible'::service.completion_status) OR (completion_reason_code_id IS NOT NULL)))`
- `service_request_note_not_blank` — `CHECK (((note IS NULL) OR (btrim(note) <> ''::text)))`
- `service_request_order_fk` — `FOREIGN KEY (tenant_id, order_id) REFERENCES ordering.customer_order(tenant_id, id) ON DELETE RESTRICT`
- `service_request_origin_names_its_actor` — `CHECK ((((origin = 'guest'::service.request_origin) AND (raised_by_guest_session_id IS NOT NULL) AND (raised_by_user_id IS NULL)) OR ((origin = 'staff'::service.request_origin) AND (raised_by_user_id IS NOT NULL) AND (raised_by_guest_session_id IS NULL))))`
- `service_request_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `service_request_pkey` — `PRIMARY KEY (id)`
- `service_request_repeat_ordinal_positive` — `CHECK ((repeat_ordinal > 0))`
- `service_request_role_fk` — `FOREIGN KEY (tenant_id, assigned_role_id) REFERENCES identity.role(tenant_id, id) ON DELETE RESTRICT`
- `service_request_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `service_request_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `service_request_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `service_request_type_fk` — `FOREIGN KEY (tenant_id, request_type_id) REFERENCES service.request_type(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `service_request_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.service_request_event`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `bigint` | NOT NULL |  |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `service_request_id` | `uuid` | NOT NULL |  |  |
| `sequence_number` | `integer` | NOT NULL |  |  |
| `kind` | `service.request_event_kind` | NOT NULL |  |  |
| `actor_kind` | `ordering.actor_kind` | NOT NULL |  |  |
| `actor_user_id` | `uuid` |  |  |  |
| `actor_guest_session_id` | `uuid` |  |  |  |
| `correlation_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `before` | `jsonb` |  |  |  |
| `after` | `jsonb` | NOT NULL |  |  |
| `occurred_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `service_request_event_actor_matches_kind` — `CHECK ((((actor_kind = 'guest'::ordering.actor_kind) AND (actor_guest_session_id IS NOT NULL) AND (actor_user_id IS NULL)) OR ((actor_kind = 'staff'::ordering.actor_kind) AND (actor_user_id IS NOT NULL) AND (actor_guest_session_id IS NULL)) OR ((actor_kind = 'system'::ordering.actor_kind) AND (actor_user_id IS NULL) AND (actor_guest_session_id IS NULL))))`
- `service_request_event_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `service_request_event_pkey` — `PRIMARY KEY (id)`
- `service_request_event_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `service_request_event_sequence_positive` — `CHECK ((sequence_number > 0))`
- `service_request_event_sequence_unique` — `UNIQUE (tenant_id, service_request_id, sequence_number)`
- `service_request_event_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `service_request_event_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.session_closure_exception`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` | NOT NULL |  |  |
| `authorized_by_user_id` | `uuid` | NOT NULL |  |  |
| `outstanding_orders` | `integer` | NOT NULL |  |  |
| `note` | `text` | NOT NULL |  |  |
| `recorded_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `unsettled_bills` | `integer` | NOT NULL | `0` | FR-TAB-009's financial condition: how many live bills on this occupancy still owed money when it was closed over an exception. Separate from outstanding_orders because they are different reasons and a manager reading the record needs to know which. |

Constraints:

- `closure_exception_actor_fk` — `FOREIGN KEY (tenant_id, authorized_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `closure_exception_had_something_outstanding` — `CHECK ((outstanding_orders > 0))`
- `closure_exception_note_not_blank` — `CHECK ((btrim(note) <> ''::text))`
- `closure_exception_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `closure_exception_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `closure_exception_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `closure_exception_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `session_closure_exception_pkey` — `PRIMARY KEY (id)`

Policies:

- `session_closure_exception_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.session_merge`

Two physical tables merged into one service session (FR-TAB-007A), audited with the count of orders consolidated so the record itself states what moved.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `surviving_session_id` | `uuid` | NOT NULL |  |  |
| `absorbed_session_id` | `uuid` | NOT NULL |  |  |
| `merged_by_user_id` | `uuid` | NOT NULL |  |  |
| `reason_code_id` | `uuid` |  |  |  |
| `orders_moved` | `integer` | NOT NULL |  |  |
| `merged_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `session_merge_absorbed_fk` — `FOREIGN KEY (tenant_id, absorbed_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `session_merge_absorbed_once` — `UNIQUE (tenant_id, absorbed_session_id)`
- `session_merge_actor_fk` — `FOREIGN KEY (tenant_id, merged_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `session_merge_distinct` — `CHECK ((surviving_session_id <> absorbed_session_id))`
- `session_merge_orders_not_negative` — `CHECK ((orders_moved >= 0))`
- `session_merge_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `session_merge_pkey` — `PRIMARY KEY (id)`
- `session_merge_reason_fk` — `FOREIGN KEY (tenant_id, reason_code_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `session_merge_surviving_fk` — `FOREIGN KEY (tenant_id, surviving_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `session_merge_takes_the_requests` — `TRIGGER DEFERRABLE INITIALLY DEFERRED`
- `session_merge_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `session_merge_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.session_move`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `from_table_node_id` | `uuid` | NOT NULL |  |  |
| `to_table_node_id` | `uuid` | NOT NULL |  |  |
| `from_occupancy_number` | `integer` | NOT NULL |  |  |
| `to_occupancy_number` | `integer` | NOT NULL |  |  |
| `moved_by_user_id` | `uuid` | NOT NULL |  |  |
| `orders_carried` | `integer` | NOT NULL |  |  |
| `moved_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `session_move_actor_fk` — `FOREIGN KEY (tenant_id, moved_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `session_move_actually_moves` — `CHECK ((from_table_node_id <> to_table_node_id))`
- `session_move_from_fk` — `FOREIGN KEY (tenant_id, from_table_node_id) REFERENCES service.table_profile(tenant_id, table_node_id) ON DELETE RESTRICT`
- `session_move_orders_not_negative` — `CHECK ((orders_carried >= 0))`
- `session_move_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `session_move_pkey` — `PRIMARY KEY (id)`
- `session_move_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `session_move_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `session_move_to_fk` — `FOREIGN KEY (tenant_id, to_table_node_id) REFERENCES service.table_profile(tenant_id, table_node_id) ON DELETE RESTRICT`

Policies:

- `session_move_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.session_participant`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `guest_session_id` | `uuid` | NOT NULL |  |  |
| `joined_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `left_at` | `timestamp with time zone` |  |  |  |
| `shares_basket` | `boolean` | NOT NULL | `true` |  |

Constraints:

- `participant_guest_fk` — `FOREIGN KEY (tenant_id, guest_session_id) REFERENCES service.guest_session(tenant_id, id) ON DELETE RESTRICT`
- `participant_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `participant_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `participant_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `participant_unique` — `UNIQUE (table_session_id, guest_session_id)`
- `session_participant_pkey` — `PRIMARY KEY (id)`

Policies:

- `session_participant_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.staff_presence`

FR-SRV-007A. Three states, current only. The primary key is the PERSON, so a second row for the same person cannot exist and a history cannot accumulate: there is no previous state, no ended_at and no closed row, because FR-SRV-007B's fence is about what EXISTS rather than how long it lasts. A retained record of when staff were available would be no less an attendance record for having a window on it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `user_account_id` | `uuid` | NOT NULL |  |  |
| `state` | `service.presence_state` | NOT NULL |  |  |
| `observed_at` | `timestamp with time zone` | NOT NULL | `now()` | When this state became true — overwritten in place, never appended to. It is the age column config.retention_policy sweeps, which is what gives FR-SRV-007B its retention bound. |
| `asserted_by_session_id` | `uuid` |  |  |  |

Constraints:

- `staff_presence_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `staff_presence_pkey` — `PRIMARY KEY (tenant_id, outlet_id, user_account_id)`
- `staff_presence_session_fk` — `FOREIGN KEY (asserted_by_session_id) REFERENCES identity.session(id) ON DELETE SET NULL`
- `staff_presence_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `staff_presence_user_fk` — `FOREIGN KEY (tenant_id, user_account_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`

Policies:

- `staff_presence_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.table_ownership`

Who is answerable for a table, right now and historically (FR-TAB-006). Rows are superseded, never edited: a trigger refuses any UPDATE that changes the waiter or the section, so ownership can only move through service.transfer_ownership(), which requires an acknowledgement or a named supervisor. A reassignment nobody acknowledged is not auditable, and an unauditable handover is the requirement unmet rather than a lesser form of it.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_session_id` | `uuid` | NOT NULL |  |  |
| `primary_waiter_user_id` | `uuid` | NOT NULL |  |  |
| `section_code` | `text` |  |  |  |
| `assigned_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `assigned_by_user_id` | `uuid` | NOT NULL |  |  |
| `effective_to` | `timestamp with time zone` |  |  |  |

Constraints:

- `ownership_assigner_fk` — `FOREIGN KEY (tenant_id, assigned_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `ownership_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `ownership_session_fk` — `FOREIGN KEY (tenant_id, table_session_id) REFERENCES service.table_session(tenant_id, id) ON DELETE RESTRICT`
- `ownership_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `ownership_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `ownership_waiter_fk` — `FOREIGN KEY (tenant_id, primary_waiter_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `table_ownership_pkey` — `PRIMARY KEY (id)`

Policies:

- `table_ownership_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.table_profile`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `table_node_id` | `uuid` | NOT NULL |  |  |
| `node_kind` | `org.node_kind` | NOT NULL | `'dining_table'::org.node_kind` |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `service_area_id` | `uuid` |  |  |  |
| `seat_count` | `integer` |  |  |  |
| `row_version` | `bigint` | NOT NULL | `1` |  |
| `created_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `table_profile_area_fk` — `FOREIGN KEY (tenant_id, service_area_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `table_profile_is_a_table` — `CHECK ((node_kind = 'dining_table'::org.node_kind))`
- `table_profile_node_fk` — `FOREIGN KEY (tenant_id, table_node_id, node_kind) REFERENCES org.org_node(tenant_id, id, kind) ON DELETE RESTRICT`
- `table_profile_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `table_profile_pkey` — `PRIMARY KEY (table_node_id)`
- `table_profile_row_version_positive` — `CHECK ((row_version > 0))`
- `table_profile_seats_positive` — `CHECK (((seat_count IS NULL) OR (seat_count > 0)))`
- `table_profile_tenant_id_unique` — `UNIQUE (tenant_id, table_node_id)`

Policies:

- `table_profile_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.table_qr_token`

The signed reference a QR encodes (FR-TAB-001). The reference carries no internal identifier: it is 244 bits drawn from the server CSPRNG, so it is not sequential, not guessable from a neighbouring table's code, and does not decode to a primary key. Only its hash is stored. Tokens rotate by issuing a new version and revoking the old, and every version printed is recorded so staff can tell which placard is current (FR-TAB-002).

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_node_id` | `uuid` | NOT NULL |  |  |
| `token_hash` | `bytea` | NOT NULL |  |  |
| `version` | `integer` | NOT NULL |  |  |
| `issued_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `issued_by_user_id` | `uuid` | NOT NULL |  |  |
| `revoked_at` | `timestamp with time zone` |  |  |  |
| `revoked_by_user_id` | `uuid` |  |  |  |
| `revoke_reason_id` | `uuid` |  |  |  |

Constraints:

- `qr_token_hash_is_sha256` — `CHECK ((octet_length(token_hash) = 32))`
- `qr_token_hash_unique` — `UNIQUE (token_hash)`
- `qr_token_issuer_fk` — `FOREIGN KEY (tenant_id, issued_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `qr_token_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `qr_token_revocation_is_attributed` — `CHECK (((revoked_at IS NULL) = (revoked_by_user_id IS NULL)))`
- `qr_token_revoke_reason_fk` — `FOREIGN KEY (tenant_id, revoke_reason_id) REFERENCES config.reason_code(tenant_id, id) ON DELETE RESTRICT`
- `qr_token_revoker_fk` — `FOREIGN KEY (tenant_id, revoked_by_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `qr_token_table_fk` — `FOREIGN KEY (tenant_id, table_node_id) REFERENCES service.table_profile(tenant_id, table_node_id) ON DELETE RESTRICT`
- `qr_token_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `qr_token_tenant_id_unique` — `UNIQUE (tenant_id, id)`
- `qr_token_version_positive` — `CHECK ((version > 0))`
- `qr_token_version_unique` — `UNIQUE (tenant_id, table_node_id, version)`
- `table_qr_token_pkey` — `PRIMARY KEY (id)`

Policies:

- `table_qr_token_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.table_session`

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` |  |
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `outlet_id` | `uuid` | NOT NULL |  |  |
| `table_node_id` | `uuid` | NOT NULL |  |  |
| `occupancy_number` | `integer` | NOT NULL |  |  |
| `state` | `service.occupancy_state` | NOT NULL | `'open'::service.occupancy_state` |  |
| `opening_source` | `service.opening_source` | NOT NULL |  |  |
| `host_staff_user_id` | `uuid` |  |  |  |
| `opened_at` | `timestamp with time zone` | NOT NULL | `now()` |  |
| `closed_at` | `timestamp with time zone` |  |  |  |
| `customer_locale` | `menu.customer_locale` |  |  | The language the customer explicitly chose, snapshotted for M3's order communications and M4's receipts (FR-I18N-005). Nullable on purpose: no default is written, because a customer who has not chosen has not chosen English. |
| `customer_locale_selected_at` | `timestamp with time zone` |  |  |  |

Constraints:

- `table_session_closure_consistent` — `CHECK ((((state = 'open'::service.occupancy_state) AND (closed_at IS NULL)) OR ((state = 'closed'::service.occupancy_state) AND (closed_at IS NOT NULL))))`
- `table_session_host_fk` — `FOREIGN KEY (tenant_id, host_staff_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `table_session_host_named_when_staff_opened` — `CHECK (((opening_source = 'qr_scan'::service.opening_source) OR (host_staff_user_id IS NOT NULL)))`
- `table_session_locale_snapshot_is_a_choice` — `CHECK (((customer_locale IS NULL) = (customer_locale_selected_at IS NULL)))`
- `table_session_occupancy_positive` — `CHECK ((occupancy_number > 0))`
- `table_session_occupancy_unique` — `UNIQUE (tenant_id, table_node_id, occupancy_number)`
- `table_session_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `table_session_pkey` — `PRIMARY KEY (id)`
- `table_session_table_fk` — `FOREIGN KEY (tenant_id, table_node_id) REFERENCES service.table_profile(tenant_id, table_node_id) ON DELETE RESTRICT`
- `table_session_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `table_session_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `table_session_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

#### `service.transition`

SM-SERVICE-REQUEST's nine edges, and the only definition of them in this system. Not tenant data: no tenant column, no row level security, and immutable at runtime by the trigger below. tests/m3c derives the same nine from the pinned package and requires this table to equal them.

Row level security: **DISABLED**, **not forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `from_state` | `service.request_state` | NOT NULL |  |  |
| `to_state` | `service.request_state` | NOT NULL |  |  |
| `reason` | `text` | NOT NULL |  |  |

Constraints:

- `service_transition_is_a_move` — `CHECK ((from_state <> to_state))`
- `service_transition_reason_not_blank` — `CHECK ((btrim(reason) <> ''::text))`
- `transition_pkey` — `PRIMARY KEY (from_state, to_state)`

#### `service.verification_policy`

Which verification methods a tenant accepts when a scan from an earlier occupancy is presented against a later one (FR-TAB-010). Method only. Nothing in this schema can express "do not verify": the array cannot be empty, there is no boolean beside it, and service.join_table_session() refuses when no policy row exists at all. The guarantee is an invariant rather than a default, for the same reason row level security is not a tenant preference.

Row level security: **enabled**, **forced**.

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `tenant_id` | `uuid` | NOT NULL |  |  |
| `accepted_methods` | `service.verification_method[]` | NOT NULL |  |  |
| `updated_at` | `timestamp with time zone` | NOT NULL | `now()` |  |

Constraints:

- `verification_policy_at_least_one_method` — `CHECK ((cardinality(accepted_methods) >= 1))`
- `verification_policy_pkey` — `PRIMARY KEY (tenant_id)`
- `verification_policy_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`

Policies:

- `verification_policy_isolation` — `(tenant_id = app.current_tenant_id())`

