-- 0019 — Kazanchis has a manager, and the notices now reach a person
--
-- THIS IS A RULED OVERTURN, and the ruling is recorded rather than absorbed. seeds/0018
-- gave the demonstration floor a service policy naming OUTLET_MANAGER and deliberately
-- invented no member for it, on the reasoning that who is accountable is an operator's
-- decision and a seed granting somebody a role to make a check pass would be guessing on
-- their behalf. That was raised as F-M5B-8 for overturning and it was overturned: the
-- demonstration floor should have a manager.
--
-- The reasoning that survives the overturn is worth keeping straight. It was never wrong
-- that accountable_staff() must refuse rather than guess — it still does, and nothing here
-- changes it. What was wrong was applying that caution to a DEMONSTRATION FLOOR, which is
-- exactly the place where a complete outlet is the point. Sarbet has had a manager since
-- 0003; Kazanchis is where every golden journey runs and it had no product staff at all.
--
-- A SEPARATE SEED RATHER THAN AN EDIT TO 0018, for the reason 0007, 0014 and 0016 all give:
-- seeds are checksum-locked, and a seed that has run has run. 0018 is not wrong and is not
-- rewritten — it named the role, and this fills it.
--
-- WHAT A SEEDED PERSON IS, and it is four things rather than one. A membership alone would
-- satisfy notify.accountable_staff() and produce a manager who cannot sign in, which is a
-- name in a table rather than somebody who can act on what they are told. So this seeds the
-- account, the verified channel FR-AUTH-001 requires, the credential, and the membership.
--
-- THE SCRYPT PARAMETERS ARE THE REPOSITORY'S, verified rather than copied: N=16384, r=8,
-- p=1, 32-byte key, per-credential salt. The digest below was produced by re-deriving
-- Sarbet manager's stored digest from its stored salt first and checking it matched, so
-- these parameters are what identity.authenticate_credential() actually uses and not what a
-- comment says it uses.
--
--     email    manager@kazanchis.habesha.example
--     password Habesha!Kazanchis1
--
-- The password is in the clear here for the same reason Sarbet's is in tests/opa: this is a
-- demonstration floor, the credential exists to be used by whoever walks it, and a seeded
-- secret that pretends to be a secret is worse than one that says what it is.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_kazanchis '''33330001-0000-4000-8000-000000000001'''
\set u_kaz_mgr  '''3333cccc-0000-4000-8000-000000000004'''

SELECT set_config('app.tenant_id', :t_habesha, false),
       set_config('app.outlet_id', :o_kazanchis, false);

INSERT INTO identity.user_account (id, tenant_id, staff_number, display_name) VALUES
    (:u_kaz_mgr::uuid, :t_habesha::uuid, 'MGR-0002', 'Kazanchis Manager')
ON CONFLICT (id) DO NOTHING;

-- FR-AUTH-001 asks for a VERIFIED phone or email. A channel with a null verified_at is
-- exactly what identity.authenticate_credential() refuses, so this carries the moment.
INSERT INTO identity.identity_channel
    (tenant_id, user_account_id, channel, channel_value, verified_at) VALUES
    (:t_habesha::uuid, :u_kaz_mgr::uuid, 'email',
     'manager@kazanchis.habesha.example', now())
ON CONFLICT DO NOTHING;

INSERT INTO identity.credential
    (tenant_id, outlet_id, user_account_id, kind, secret_digest, digest_algorithm,
     salt, kdf_params, confers_strength) VALUES
    (:t_habesha::uuid, NULL, :u_kaz_mgr::uuid, 'password',
     '\x9fde6add6c5002bed337f08d86c2ef0e1afcd25e003fbfa443f41555bac049ff'::bytea, 'scrypt',
     '\xca2a4c47150000000000000000000001'::bytea,
     '{"cost":16384,"blockSize":8,"parallelization":1}'::jsonb, 'standard')
ON CONFLICT DO NOTHING;

-- AND THE MEMBERSHIP THAT MAKES THE NOTICES LAND. OUTLET_MANAGER is the role seeds/0018's
-- service policy names as critical_alert_role_code, and it is the role 0003 created as the
-- one a manager holds. Kazanchis's other memberships all belong to test fixtures; this is
-- the first product one at this outlet.
INSERT INTO identity.membership (tenant_id, outlet_id, user_account_id, role_id)
SELECT :t_habesha::uuid, :o_kazanchis::uuid, :u_kaz_mgr::uuid, r.id
  FROM identity.role r
 WHERE r.tenant_id = :t_habesha::uuid AND r.role_code = 'OUTLET_MANAGER'
   AND NOT EXISTS (
        SELECT 1 FROM identity.membership m
         WHERE m.tenant_id = :t_habesha::uuid
           AND m.outlet_id = :o_kazanchis::uuid
           AND m.user_account_id = :u_kaz_mgr::uuid
           AND m.role_id = r.id);

-- IT HAS TO ACTUALLY REACH SOMEBODY, checked here rather than assumed. The whole point of
-- the overturn is that a critical edge notice at this outlet is addressed to a person, and
-- a seed that produced a membership the accountability lookup could not see would leave
-- exactly the state 0018 was criticised for.
DO $$
DECLARE v_n integer;
BEGIN
    SELECT count(*) INTO v_n
      FROM notify.accountable_staff('33333333-3333-3333-3333-333333333333'::uuid,
                                    '33330001-0000-4000-8000-000000000001'::uuid);
    IF v_n < 1 THEN
        RAISE EXCEPTION
            'ACCOUNTABLE_STAFF_STILL_EMPTY: the demonstration floor was given a manager and '
            'notify.accountable_staff() still returns nobody, so a critical notice here is '
            'still addressed to no one'
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
