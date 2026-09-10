-- 0017_the_two_nodes_are_given_a_lease_policy_and_the_authority_to_write.provision.sql
--
-- FR-EDG-023 and FR-EDG-024 both landed as a schema, a set of functions and nothing in
-- the tables. GJ-09 is what found it: edge.lease_policy held ZERO rows and edge.authority
-- held zero rows, on a floor with two registered nodes.
--
-- WHAT THAT MEANT IN PRACTICE, and it is worse than "a check had nothing to read".
--
--   edge.evaluate_lease() had no policy to evaluate against, so the whole of FR-EDG-023's
--   5/10/20/3 schedule existed as four DEFAULT clauses on a table nobody had inserted into.
--   The defaults are right. Nothing was using them.
--
--   edge.assert_authority() refused every write at both outlets with AUTHORITY_ABSENT,
--   because no node had ever been granted a sequence. Nothing broke, and that is the
--   uncomfortable part: no write path calls assert_authority() yet, so a mechanism that
--   refuses everything looked exactly like a mechanism that was working.
--
-- THIS IS THE THIRD-THING PATTERN AGAIN, in its third variation this gate. seeds/0010
-- wrote it down for governed actions: a new mechanism needs the schema, a way to install
-- it for what already exists, and a caller. 0052 and seeds/0015 were the trigger-and-
-- installer version. This is the plain one — the schema shipped, the callers shipped, and
-- the rows for the outlets that already existed did not.
--
-- IT IS A SEPARATE SEED FOR THE REASON 0014 AND 0016 GAVE. Seeds are checksum-locked and
-- the tables did not exist until 0049 and 0050.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set o_kazanchis '''33330001-0000-4000-8000-000000000001'''
\set o_sarbet    '''33330002-0000-4000-8000-000000000002'''

SELECT set_config('app.tenant_id', :t_habesha, false);

-- ---------------------------------------------------------------------------
-- THE LEASE POLICY, WRITTEN OUT RATHER THAN LEFT TO THE DEFAULTS
-- ---------------------------------------------------------------------------
--
-- The four values match 0049's column defaults exactly, and stating them here is the
-- point rather than duplication. A policy that exists only as a DEFAULT is a policy that
-- appears when somebody inserts a row and never otherwise; FR-EDG-023 names 5, 10 and 20
-- seconds and three consecutive proofs as the outlet's behaviour, and behaviour nobody
-- has written down for a particular outlet is behaviour nobody can change for one either.

SELECT set_config('app.outlet_id', :o_kazanchis, false);
INSERT INTO edge.lease_policy
    (tenant_id, outlet_id, proof_interval_seconds, degrade_after_seconds,
     expire_after_seconds, proofs_required_to_resume)
VALUES (:t_habesha::uuid, :o_kazanchis::uuid, 5, 10, 20, 3);

SELECT set_config('app.outlet_id', :o_sarbet, false);
INSERT INTO edge.lease_policy
    (tenant_id, outlet_id, proof_interval_seconds, degrade_after_seconds,
     expire_after_seconds, proofs_required_to_resume)
VALUES (:t_habesha::uuid, :o_sarbet::uuid, 5, 10, 20, 3);

-- ---------------------------------------------------------------------------
-- AND EACH NODE IS GIVEN SEQUENCE 1
-- ---------------------------------------------------------------------------
--
-- Through edge.grant_first_authority() rather than by inserting into edge.authority, for
-- the reason seeds/0016 gives about certificates: a seeded floor should demonstrate a
-- state that a code path produces. It is also the only function that may grant a FIRST
-- authority — every later sequence goes through edge.claim_authority(), which demands the
-- four proofs. That asymmetry is deliberate and is why the first grant is a separate
-- function: there is no node to fence when an outlet has never had one.

SELECT set_config('app.outlet_id', :o_kazanchis, false);
SELECT edge.grant_first_authority(
    :t_habesha::uuid,
    (SELECT id FROM edge.node WHERE tenant_id = :t_habesha::uuid AND node_code = 'NODE-H1'));

SELECT set_config('app.outlet_id', :o_sarbet, false);
SELECT edge.grant_first_authority(
    :t_habesha::uuid,
    (SELECT id FROM edge.node WHERE tenant_id = :t_habesha::uuid AND node_code = 'NODE-H2'));

SELECT set_config('app.outlet_id', '', false);
SELECT set_config('app.tenant_id', '', false);
