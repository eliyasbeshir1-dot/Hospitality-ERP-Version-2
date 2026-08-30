# Schema and Domain Catalog

**Generated from the live database by `tools/generate_schema_catalog.py`.**
Do not edit by hand: the verification suite regenerates this file and fails on any
difference, so a hand edit is reported as drift (FR-DAT-015).

Schemas covered: `app`, `audit`, `config`, `identity`, `menu`, `money`, `org`, `safety`, `service`, discovered from the database rather than listed here.

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
| `config.configuration_category` | branding, locale, currency, timezone, tax, calendar, numbering, payment_method, service, feature, connector |
| `config.policy_category` | ordering, service, cancellation, discount, refund, tip, cash, approval, local_continuity |
| `config.reason_code_category` | order_cancellation, void, refund, discount, complimentary_item, payment_reversal, tip_correction, service_failure, printer_failure, manager_override |
| `config.retention_action` | archive, purge, anonymize |
| `config.scope_kind` | tenant, legal_entity, outlet |
| `identity.auth_strength` | low, standard, strong |
| `identity.channel_kind` | phone, email |
| `identity.credential_kind` | password, otp, quick_pin, service_secret |
| `identity.principal_class` | worker, integration, edge_node, print_agent |
| `identity.revocation_reason` | signed_out, expired, membership_withdrawn, security_event, rotated, administrator_revoked, recovery |
| `identity.transmission_mode` | simulated, live |
| `menu.availability_state` | available, limited, temporarily_unavailable, scheduled_later, hidden |
| `menu.customer_locale` | en, am, ar |
| `menu.image_format` | webp, avif, jpeg, png |
| `menu.menu_entity` | menu, category, item_group, item, variant, modifier_group, modifier, image, allergen, dietary_claim |
| `menu.publication_state` | draft, review, scheduled, published, paused, archived |
| `menu.sales_channel` | dine_in, counter, room_service, kiosk |
| `menu.translation_provenance` | human, machine_assisted |
| `menu.translation_state` | draft, in_review, approved, rejected |
| `menu.variant_axis` | size, portion, temperature, preparation_style |
| `money.rounding_mode` | half_up, half_even, floor, ceiling |
| `org.lifecycle_status` | active, inactive, archived |
| `org.node_kind` | brand, legal_entity, outlet, service_area, preparation_station, dining_table, device |
| `safety.declaration_class` | contains, may_contain, cross_contact |
| `safety.reference_context` | publication_snapshot, cart_line |
| `safety.review_state` | draft, in_review, approved |
| `service.cart_kind` | personal, shared |
| `service.cart_state` | open, abandoned, expired |
| `service.concern_source` | guest, waiter |
| `service.occupancy_state` | open, closed |
| `service.opening_source` | qr_scan, staff, host_stand |
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
  config_configuration_version["config.configuration_version"]
  identity_user_account["identity.user_account"]
  config_entitlement["config.entitlement"]
  config_issued_document_number["config.issued_document_number"]
  config_number_series["config.number_series"]
  config_policy["config.policy"]
  identity_governed_action["identity.governed_action"]
  config_reason_code["config.reason_code"]
  config_reason_code_label["config.reason_code_label"]
  config_retention_policy["config.retention_policy"]
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
  identity_session["identity.session"]
  identity_step_up_grant["identity.step_up_grant"]
  identity_terminal_trust["identity.terminal_trust"]
  menu_assignment["menu.assignment"]
  menu_daypart["menu.daypart"]
  menu_menu["menu.menu"]
  menu_availability["menu.availability"]
  menu_item_variant["menu.item_variant"]
  menu_modifier["menu.modifier"]
  menu_sellable_item["menu.sellable_item"]
  menu_availability_pause["menu.availability_pause"]
  menu_category["menu.category"]
  menu_image["menu.image"]
  menu_image_derivative["menu.image_derivative"]
  menu_item_group["menu.item_group"]
  menu_item_group_member["menu.item_group_member"]
  menu_item_modifier_group["menu.item_modifier_group"]
  menu_modifier_group["menu.modifier_group"]
  menu_modifier_incompatibility["menu.modifier_incompatibility"]
  menu_price["menu.price"]
  money_currency["money.currency"]
  menu_publication_snapshot["menu.publication_snapshot"]
  menu_publication_snapshot_line["menu.publication_snapshot_line"]
  menu_translation["menu.translation"]
  menu_translatable_field["menu.translatable_field"]
  org_device_registration["org.device_registration"]
  org_org_closure["org.org_closure"]
  org_outlet_profile["org.outlet_profile"]
  safety_allergen["safety.allergen"]
  safety_jurisdiction["safety.jurisdiction"]
  safety_allergy_concern["safety.allergy_concern"]
  safety_approved_wording["safety.approved_wording"]
  service_guest_session["service.guest_session"]
  service_table_session["service.table_session"]
  safety_declaration["safety.declaration"]
  safety_declaration_reference["safety.declaration_reference"]
  safety_dietary_claim["safety.dietary_claim"]
  safety_dietary_claim_outlet["safety.dietary_claim_outlet"]
  safety_item_dietary_claim["safety.item_dietary_claim"]
  safety_jurisdiction_requirement["safety.jurisdiction_requirement"]
  service_cart["service.cart"]
  service_cart_line["service.cart_line"]
  service_cart_line_modifier["service.cart_line_modifier"]
  service_cart_line_transfer["service.cart_line_transfer"]
  service_ownership_transfer["service.ownership_transfer"]
  service_qr_placard["service.qr_placard"]
  service_table_qr_token["service.table_qr_token"]
  service_qr_scan["service.qr_scan"]
  service_session_participant["service.session_participant"]
  service_table_ownership["service.table_ownership"]
  service_table_profile["service.table_profile"]
  service_verification_policy["service.verification_policy"]
  audit_operational_event --> org_org_node
  audit_operational_event --> org_tenant
  audit_security_event --> org_org_node
  audit_security_event --> org_tenant
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
  org_device_registration --> org_org_node
  org_org_closure --> org_org_node
  org_org_closure --> org_tenant
  org_org_node --> org_org_node
  org_org_node --> org_tenant
  org_outlet_profile --> org_org_node
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
  service_session_participant --> org_org_node
  service_session_participant --> org_tenant
  service_session_participant --> service_guest_session
  service_session_participant --> service_table_session
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
- `retention_policy_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `retention_policy_pkey` — `PRIMARY KEY (id)`
- `retention_policy_retain_for_positive` — `CHECK ((retain_for > '00:00:00'::interval))`
- `retention_policy_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `retention_policy_unique` — `UNIQUE (tenant_id, target_schema, target_table)`

Policies:

- `retention_policy_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

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

Constraints:

- `guest_session_anonymization_is_real` — `CHECK (((anonymized_at IS NULL) OR (display_nickname IS NULL)))`
- `guest_session_expiry_after_creation` — `CHECK ((expires_at > created_at))`
- `guest_session_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `guest_session_pkey` — `PRIMARY KEY (id)`
- `guest_session_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `guest_session_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `guest_session_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

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

Constraints:

- `table_session_closure_consistent` — `CHECK ((((state = 'open'::service.occupancy_state) AND (closed_at IS NULL)) OR ((state = 'closed'::service.occupancy_state) AND (closed_at IS NOT NULL))))`
- `table_session_host_fk` — `FOREIGN KEY (tenant_id, host_staff_user_id) REFERENCES identity.user_account(tenant_id, id) ON DELETE RESTRICT`
- `table_session_host_named_when_staff_opened` — `CHECK (((opening_source = 'qr_scan'::service.opening_source) OR (host_staff_user_id IS NOT NULL)))`
- `table_session_occupancy_positive` — `CHECK ((occupancy_number > 0))`
- `table_session_occupancy_unique` — `UNIQUE (tenant_id, table_node_id, occupancy_number)`
- `table_session_outlet_fk` — `FOREIGN KEY (tenant_id, outlet_id) REFERENCES org.org_node(tenant_id, id) ON DELETE RESTRICT`
- `table_session_pkey` — `PRIMARY KEY (id)`
- `table_session_table_fk` — `FOREIGN KEY (tenant_id, table_node_id) REFERENCES service.table_profile(tenant_id, table_node_id) ON DELETE RESTRICT`
- `table_session_tenant_fk` — `FOREIGN KEY (tenant_id) REFERENCES org.tenant(id) ON DELETE RESTRICT`
- `table_session_tenant_id_unique` — `UNIQUE (tenant_id, id)`

Policies:

- `table_session_isolation` — `app.row_in_scope(tenant_id, outlet_id)`

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

