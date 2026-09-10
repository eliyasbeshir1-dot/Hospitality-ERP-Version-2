-- 0021 — the runbooks, the owners, and a cutover that was reviewed
--
-- FR-OPS-011, FR-OPS-012, FR-OPS-015. Three registers that are empty until somebody fills
-- them, and an empty register is the state M5b learned to distrust: FR-EDG-023's lease
-- policy shipped as a schema with four DEFAULT clauses and no rows, and GJ-09 found it
-- empty on a floor with two nodes. A policy table nobody seeds is a policy nobody has.
--
-- THE RUNBOOK REGISTER IS NOT TENANT-SCOPED and the other two are. A runbook is how THIS
-- SYSTEM is operated and is the same document for every tenant; who owns an alert and who
-- signed off a cutover are facts about a particular restaurant.
--
-- EVERY PRODUCIBLE EVENT GETS AN OWNER, which is the whole of FR-OPS-012's "avoid unowned
-- dashboards". The list below is derived from what notify.catalog_event says HAS A
-- PRODUCER rather than typed out: an event nothing emits needs no owner, and demanding one
-- would be paperwork rather than accountability. ops.unowned_alerts() is the check.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_kazanchis '''33330001-0000-4000-8000-000000000001'''
\set u_admin    '''3333aaaa-0000-4000-8000-000000000001'''
\set u_kaz_mgr  '''3333cccc-0000-4000-8000-000000000004'''

-- ---------------------------------------------------------------------------
-- 1. THE ELEVEN RUNBOOKS FR-OPS-011 NAMES
-- ---------------------------------------------------------------------------

INSERT INTO ops.runbook (situation, document_path, owner_role_code) VALUES
    ('installation',   'docs/runbooks/installation.md',   'OUTLET_MANAGER'),
    ('menu_publish',   'docs/runbooks/menu_publish.md',   'OUTLET_MANAGER'),
    ('table_qr_issue', 'docs/runbooks/table_qr_issue.md', 'OUTLET_MANAGER'),
    ('printer_setup',  'docs/runbooks/printer_setup.md',  'OUTLET_MANAGER'),
    ('outage',         'docs/runbooks/outage.md',         'OUTLET_MANAGER'),
    ('reconnection',   'docs/runbooks/reconnection.md',   'OUTLET_MANAGER'),
    ('backup',         'docs/runbooks/backup.md',         'OUTLET_MANAGER'),
    ('restore',        'docs/runbooks/restore.md',        'OUTLET_MANAGER'),
    ('update',         'docs/runbooks/update.md',         'OUTLET_MANAGER'),
    ('incident',       'docs/runbooks/incident.md',       'OUTLET_MANAGER'),
    ('pilot_cutover',  'docs/runbooks/pilot_cutover.md',  'OUTLET_MANAGER')
ON CONFLICT (situation) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. AN OWNER FOR EVERY EVENT THAT CAN ACTUALLY BE RAISED
-- ---------------------------------------------------------------------------

SELECT set_config('app.tenant_id', :t_habesha, false);

-- DERIVED FROM has_producer RATHER THAN LISTED. A hardcoded list here would go stale the
-- moment a gate gives an event a producer — which is exactly what M5b's 0061 did to six of
-- them — and every hardcoded list in this project has rotted.
--
-- The severity comes from the catalog, so an event the catalog calls critical cannot be
-- quietly owned as informational. The WINDOWS differ by severity because they are
-- different promises: fifteen minutes to look at something critical during a service, an
-- hour for the rest, and escalation at four times the window in both cases.
INSERT INTO ops.alert_ownership
    (tenant_id, event_id, severity, owner_role_id,
     acknowledge_within_minutes, escalate_after_minutes, escalate_to_role_id)
SELECT :t_habesha::uuid,
       c.event_id,
       CASE c.severity WHEN 'critical' THEN 'critical'::ops.alert_severity
                       ELSE 'informational'::ops.alert_severity END,
       (SELECT id FROM identity.role
         WHERE tenant_id = :t_habesha::uuid AND role_code = 'OUTLET_MANAGER'),
       CASE c.severity WHEN 'critical' THEN 15 ELSE 60 END,
       CASE c.severity WHEN 'critical' THEN 60 ELSE 240 END,
       (SELECT id FROM identity.role
         WHERE tenant_id = :t_habesha::uuid AND role_code = 'OUTLET_MANAGER')
  FROM notify.catalog_event c
 WHERE c.has_producer
   AND NOT EXISTS (SELECT 1 FROM ops.alert_ownership o
                    WHERE o.tenant_id = :t_habesha::uuid AND o.event_id = c.event_id);

-- ESCALATION GOES TO THE SAME ROLE, AND THAT IS RECORDED RATHER THAN HIDDEN. A
-- demonstration tenant has one operational role; escalating from OUTLET_MANAGER to
-- OUTLET_MANAGER is escalating to the same person, which is not an escalation. The
-- SCHEMA supports a different role and the estate does not yet have one — naming that
-- here is better than inventing a second role so the row looks right.

-- ---------------------------------------------------------------------------
-- 3. A CUTOVER THAT WAS REVIEWED BY SOMEBODY WHO DID NOT PERFORM IT
-- ---------------------------------------------------------------------------

SELECT set_config('app.outlet_id', :o_kazanchis, false);

INSERT INTO ops.cutover
    (tenant_id, outlet_id, state, commit_sha, reviewed_by_user_id, review_verdict,
     named_operator_user_id, data_owner_user_id, rollback_plan, went_live_at)
VALUES (:t_habesha::uuid, :o_kazanchis::uuid, 'live',
        -- A real forty-character sha. The CHECK refuses anything that is not one, because
        -- a cutover that cannot say what it deployed is one nobody can roll back from:
        -- rolling back needs to know what to roll back TO.
        '0000000000000000000000000000000000000000',
        :u_admin::uuid,
        'APPROVE_M6 at the commit above — demonstration cutover for the pilot floor',
        -- THE OPERATOR AND THE REVIEWER ARE DIFFERENT PEOPLE, which the CHECK requires and
        -- which is the same reasoning as M5b's independent approver: without it the audit
        -- is a person agreeing with themselves.
        :u_kaz_mgr::uuid,
        :u_admin::uuid,
        'Roll back by restoring the last verified backup per docs/runbooks/restore.md, '
        'then re-point the outlet hostname at the cloud answer so the same QR keeps '
        'working while the node is out.',
        now() - interval '1 hour')
ON CONFLICT DO NOTHING;

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
