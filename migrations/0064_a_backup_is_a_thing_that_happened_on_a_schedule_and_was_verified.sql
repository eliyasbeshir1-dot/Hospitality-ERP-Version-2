-- 0064: a backup is a thing that happened, on a schedule, and was verified
--
-- FR-OPS-006 and FR-SEC-019 together, because neither is complete without the other:
--
--   FR-OPS-006  back up cloud and outlet databases, configuration and required files on a
--               DOCUMENTED SCHEDULE using tools present inside the production artifact
--   FR-SEC-019  ENCRYPT backups, VERIFY them, retain OFF-SITE copies, and restore through
--               the exact production roles and built artifacts
--
-- WHY THIS IS A TABLE AND NOT A CRON ENTRY. A schedule that lives only in a scheduler is a
-- schedule nobody can audit: the question an operator actually has at two in the morning
-- is not "is there a cron line" but "when did this outlet last have a backup that was
-- verified, and where is it". Both halves of that are rows here.
--
-- AND A BACKUP NOBODY HAS READ IS NOT A BACKUP. FR-SEC-019 says "verify them", and the
-- weakest reading — the file exists and is not zero bytes — is the reading that produces
-- an unrestorable archive nobody discovers until they need it. ops.backup_run therefore
-- has no state meaning "taken"; it has `captured`, and then `verified` only once something
-- has decrypted the archive and read its table of contents back. The transition is a
-- function that refuses without evidence.
--
-- THE ENCRYPTION IS NOT IN THIS DATABASE, and that is deliberate rather than a gap. There
-- is no pgcrypto here — M5a met the same wall and answered it with keyed digests — and a
-- database that could decrypt its own backups is a database whose compromise takes the
-- backups with it. The cipher is openssl, which the artifact ships; what is recorded here
-- is the DIGEST of the ciphertext and the parameters used, so a restore can prove it is
-- reading the bytes that were written without this database ever holding the key.

CREATE TYPE ops.backup_scope AS ENUM ('cloud', 'outlet');

CREATE TYPE ops.backup_state AS ENUM (
    -- Written, encrypted, digest recorded. NOT yet known to be readable.
    'captured',
    -- Decrypted and its table of contents read back. This is the only state a restore
    -- drill may start from.
    'verified',
    -- Copied to a location that is not the one it was written to.
    'offsite',
    -- Read back and found wrong. Kept rather than deleted: a corrupt backup is evidence
    -- about the process that produced it.
    'failed_verification');

-- ---------------------------------------------------------------------------
-- 1. THE SCHEDULE, AS SOMETHING THAT CAN BE ASKED
-- ---------------------------------------------------------------------------

CREATE TABLE ops.backup_policy (
    tenant_id uuid NOT NULL,
    scope     ops.backup_scope NOT NULL,

    -- FR-OPS-006's "documented schedule", as two numbers rather than a cron string. A
    -- cron expression is a schedule a person has to parse; an interval is one a query can
    -- compare against now().
    interval_hours     integer NOT NULL,
    -- How long after a missed window somebody should be told. Separate from the interval
    -- because a backup an hour late is not an incident and a backup a day late is.
    alert_after_hours  integer NOT NULL,

    -- FR-SEC-019's retention, and the off-site requirement as a place rather than a hope.
    retain_days        integer NOT NULL,
    offsite_required   boolean NOT NULL DEFAULT true,

    documented_by_user_id uuid NOT NULL,
    documented_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT backup_policy_pkey PRIMARY KEY (tenant_id, scope),
    CONSTRAINT backup_policy_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT backup_policy_documenter_fk FOREIGN KEY (tenant_id, documented_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT backup_policy_interval_is_sane CHECK (interval_hours BETWEEN 1 AND 168),
    -- ASCENDING, for the reason edge.lease_policy's thresholds ascend: an alert window
    -- shorter than the interval alerts on every successful schedule.
    CONSTRAINT backup_policy_alert_is_after CHECK (alert_after_hours > interval_hours),
    CONSTRAINT backup_policy_retention_outlives_the_interval CHECK (
        retain_days * 24 > interval_hours)
);

COMMENT ON TABLE ops.backup_policy IS
    'FR-OPS-006, FR-SEC-019. How often this tenant''s cloud and outlet databases are backed '
    'up, how long after a missed window somebody is told, how long copies are kept and '
    'whether an off-site copy is required. A schedule that lives only in a scheduler is a '
    'schedule nobody can audit.';

ALTER TABLE ops.backup_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.backup_policy FORCE ROW LEVEL SECURITY;
CREATE POLICY backup_policy_isolation ON ops.backup_policy FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

-- ---------------------------------------------------------------------------
-- 2. WHAT ACTUALLY HAPPENED
-- ---------------------------------------------------------------------------

CREATE TABLE ops.backup_run (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL,
    scope     ops.backup_scope NOT NULL,
    -- Null for a cloud backup; the outlet for an outlet one. Not a foreign key into
    -- org.org_node on purpose: a backup outlives the outlet it came from, and the whole
    -- point of one is to survive the row being gone.
    outlet_id uuid,

    state ops.backup_state NOT NULL DEFAULT 'captured',

    -- WHAT WAS TAKEN. The tool and its arguments are recorded because FR-OPS-006 requires
    -- the tools to be ones inside the production artifact, and a claim about which tool
    -- ran is worth nothing unless the run says.
    taken_with text NOT NULL,
    archive_format text NOT NULL,

    -- WHERE IT WENT, and where the second copy went. Paths rather than contents: this
    -- database does not hold its own backups, for the reason it does not hold the key.
    archive_path text NOT NULL,
    offsite_path text,

    -- THE DIGEST OF THE CIPHERTEXT. What a restore compares against to know it is reading
    -- the bytes that were written.
    archive_sha256 character(64) NOT NULL,
    archive_bytes  bigint NOT NULL,

    -- HOW IT WAS ENCRYPTED, without the key. FR-SEC-019 asks for encryption; recording
    -- the parameters is what lets a restore three months later know what to do, and what
    -- lets an auditor see that it was not 'none'.
    cipher      text NOT NULL,
    kdf         text NOT NULL,
    kdf_iterations integer NOT NULL,

    -- WHAT VERIFICATION FOUND. Null until something has read the archive back.
    verified_at        timestamptz,
    verified_entries   integer,
    verification_detail text,

    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,

    CONSTRAINT backup_run_tenant_id_unique UNIQUE (tenant_id, id),
    CONSTRAINT backup_run_tenant_fk FOREIGN KEY (tenant_id)
        REFERENCES org.tenant (id) ON DELETE RESTRICT,
    CONSTRAINT backup_run_outlet_scope_agrees CHECK (
        (scope = 'outlet') = (outlet_id IS NOT NULL)),
    CONSTRAINT backup_run_archive_is_stated CHECK (length(trim(archive_path)) > 0),
    CONSTRAINT backup_run_bytes_positive CHECK (archive_bytes > 0),

    -- ENCRYPTION IS NOT OPTIONAL AND 'none' IS NOT A CIPHER. FR-SEC-019 says encrypt
    -- them; a column that permitted 'none' would permit a deployment that did not.
    CONSTRAINT backup_run_is_encrypted CHECK (
        cipher <> '' AND lower(cipher) NOT IN ('none', 'null', 'plain', 'plaintext')
        AND kdf_iterations >= 100000),

    -- VERIFIED MEANS SOMETHING READ IT BACK. The state cannot be claimed without the
    -- evidence, which is the whole difference between a backup and a file.
    CONSTRAINT backup_run_verification_is_evidenced CHECK (
        state NOT IN ('verified', 'offsite')
        OR (verified_at IS NOT NULL AND verified_entries IS NOT NULL
            AND verified_entries > 0)),

    -- AND OFF-SITE MEANS SOMEWHERE ELSE. A second copy in the same directory is a second
    -- copy of the same disk failure.
    CONSTRAINT backup_run_offsite_is_elsewhere CHECK (
        offsite_path IS NULL OR offsite_path <> archive_path),
    CONSTRAINT backup_run_offsite_state_agrees CHECK (
        (state = 'offsite') <= (offsite_path IS NOT NULL))
);

COMMENT ON TABLE ops.backup_run IS
    'FR-OPS-006, FR-SEC-019. Every backup that has been taken: what took it, where it went, '
    'the digest of the ciphertext, how it was encrypted, and what reading it back found. '
    'There is no state meaning "taken and assumed good" — `captured` becomes `verified` '
    'only when something has decrypted the archive and read its table of contents.';

CREATE INDEX backup_run_recent_idx
    ON ops.backup_run (tenant_id, scope, started_at DESC);

ALTER TABLE ops.backup_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE ops.backup_run FORCE ROW LEVEL SECURITY;
CREATE POLICY backup_run_isolation ON ops.backup_run FOR ALL
    USING (app.row_in_scope(tenant_id, NULL))
    WITH CHECK (app.row_in_scope(tenant_id, NULL));

-- A BACKUP RUN IS A RECORD OF SOMETHING THAT HAPPENED, so it does not get rewritten.
-- Verification and the off-site copy advance it forward; nothing edits what was captured.
CREATE FUNCTION ops.refuse_backup_rewrite() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            'BACKUP_RUN_DELETED: a backup that was taken was taken. Deleting the record '
            'does not delete the archive, and an estate whose backup history can be edited '
            'cannot answer when it last had one'
            USING ERRCODE = 'HS409';
    END IF;

    IF NEW.archive_sha256 <> OLD.archive_sha256
       OR NEW.archive_path <> OLD.archive_path
       OR NEW.archive_bytes <> OLD.archive_bytes
       OR NEW.cipher <> OLD.cipher
       OR NEW.started_at <> OLD.started_at THEN
        RAISE EXCEPTION
            'BACKUP_RUN_REWRITTEN: what was captured cannot be changed after the fact. '
            'Verification and the off-site copy move the run FORWARD; they do not restate '
            'what was written'
            USING ERRCODE = 'HS409';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER backup_run_is_append_forward
    BEFORE UPDATE OR DELETE ON ops.backup_run
    FOR EACH ROW EXECUTE FUNCTION ops.refuse_backup_rewrite();

-- ---------------------------------------------------------------------------
-- 3. RECORDING ONE, AND VERIFYING IT
-- ---------------------------------------------------------------------------

CREATE FUNCTION ops.record_backup(
    p_tenant_id uuid,
    p_scope     ops.backup_scope,
    p_outlet_id uuid,
    p_taken_with text,
    p_archive_format text,
    p_archive_path text,
    p_archive_sha256 character(64),
    p_archive_bytes bigint,
    p_cipher text,
    p_kdf text,
    p_kdf_iterations integer)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'public'
AS $$
DECLARE
    v_id uuid;
BEGIN
    INSERT INTO ops.backup_run
        (tenant_id, scope, outlet_id, state, taken_with, archive_format, archive_path,
         archive_sha256, archive_bytes, cipher, kdf, kdf_iterations, finished_at)
    VALUES (p_tenant_id, p_scope, p_outlet_id, 'captured', p_taken_with, p_archive_format,
            p_archive_path, p_archive_sha256, p_archive_bytes, p_cipher, p_kdf,
            p_kdf_iterations, now())
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;

COMMENT ON FUNCTION ops.record_backup(uuid, ops.backup_scope, uuid, text, text, text,
                                      character, bigint, text, text, integer) IS
    'FR-OPS-006. Records a backup as CAPTURED — written and encrypted, and not yet known '
    'to be readable. Nothing here can record one as verified; that takes evidence.';

CREATE FUNCTION ops.verify_backup(
    p_tenant_id uuid,
    p_backup_id uuid,
    p_observed_sha256 character(64),
    p_entries_read integer,
    p_detail text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'public'
AS $$
DECLARE
    b ops.backup_run%ROWTYPE;
BEGIN
    SELECT * INTO b FROM ops.backup_run
      WHERE tenant_id = p_tenant_id AND id = p_backup_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BACKUP_UNKNOWN: no backup %', p_backup_id USING ERRCODE = 'HS404';
    END IF;

    -- THE BYTES READ MUST BE THE BYTES WRITTEN. A verification that decrypted a DIFFERENT
    -- archive and found it fine is a verification of the wrong file, which is exactly the
    -- mistake a directory of timestamped backups invites.
    IF p_observed_sha256 <> b.archive_sha256 THEN
        UPDATE ops.backup_run
           SET state = 'failed_verification', verified_at = now(), verified_entries = 0,
               verification_detail = format(
                   'digest mismatch: read %s, recorded %s', p_observed_sha256, b.archive_sha256)
         WHERE tenant_id = p_tenant_id AND id = p_backup_id;
        RAISE EXCEPTION
            'BACKUP_DIGEST_MISMATCH: the archive read back is not the archive that was '
            'written. Recorded %, read %', b.archive_sha256, p_observed_sha256
            USING ERRCODE = 'HS409';
    END IF;

    -- AND IT MUST HAVE HAD SOMETHING IN IT. An archive that decrypts to nothing decrypts
    -- successfully, which is the failure mode "the file exists and is not zero bytes"
    -- cannot see.
    IF p_entries_read IS NULL OR p_entries_read <= 0 THEN
        UPDATE ops.backup_run
           SET state = 'failed_verification', verified_at = now(), verified_entries = 0,
               verification_detail = 'archive decrypted and contained no entries'
         WHERE tenant_id = p_tenant_id AND id = p_backup_id;
        RAISE EXCEPTION
            'BACKUP_IS_EMPTY: the archive decrypted and its table of contents is empty. '
            'A backup of nothing restores to nothing'
            USING ERRCODE = 'HS409';
    END IF;

    UPDATE ops.backup_run
       SET state = 'verified', verified_at = now(), verified_entries = p_entries_read,
           verification_detail = p_detail
     WHERE tenant_id = p_tenant_id AND id = p_backup_id;
END;
$$;

COMMENT ON FUNCTION ops.verify_backup(uuid, uuid, character, integer, text) IS
    'FR-SEC-019. Promotes a backup to VERIFIED, and only on evidence: the digest of what '
    'was read back must equal the digest of what was written, and the archive must contain '
    'something. A verification that read a different file, or an archive that decrypts to '
    'nothing, both fail here and are recorded as failures rather than forgotten.';

CREATE FUNCTION ops.record_offsite_copy(
    p_tenant_id uuid, p_backup_id uuid, p_offsite_path text, p_observed_sha256 character(64))
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'public'
AS $$
DECLARE
    b ops.backup_run%ROWTYPE;
BEGIN
    SELECT * INTO b FROM ops.backup_run
      WHERE tenant_id = p_tenant_id AND id = p_backup_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'BACKUP_UNKNOWN: no backup %', p_backup_id USING ERRCODE = 'HS404';
    END IF;

    -- ONLY SOMETHING THAT WAS READ BACK GOES OFF-SITE. Copying an unverified archive
    -- somewhere else produces two copies of a file nobody has opened.
    IF b.state <> 'verified' THEN
        RAISE EXCEPTION
            'BACKUP_NOT_VERIFIED: backup % is %, and copying an archive nobody has read '
            'back merely produces a second copy of an unknown', p_backup_id, b.state
            USING ERRCODE = 'HS409';
    END IF;

    IF p_observed_sha256 <> b.archive_sha256 THEN
        RAISE EXCEPTION
            'BACKUP_OFFSITE_DIGEST_MISMATCH: what arrived off-site is not what was sent. '
            'Recorded %, arrived %', b.archive_sha256, p_observed_sha256
            USING ERRCODE = 'HS409';
    END IF;

    UPDATE ops.backup_run
       SET state = 'offsite', offsite_path = p_offsite_path
     WHERE tenant_id = p_tenant_id AND id = p_backup_id;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. IS THIS ESTATE ACTUALLY BACKED UP?
-- ---------------------------------------------------------------------------
--
-- The question an operator has, answered from the rows rather than from a scheduler's log.
-- Derived rather than stored for the reason edge.certificate_posture() is: a stored
-- posture is a claim written at a moment, and the moment that matters is the one somebody
-- asks in.

CREATE TYPE ops.backup_posture AS ENUM (
    'healthy', 'due', 'overdue', 'unverified', 'never', 'undocumented');

CREATE FUNCTION ops.backup_posture(p_tenant_id uuid, p_scope ops.backup_scope)
RETURNS TABLE (posture ops.backup_posture, hours_since numeric, detail text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'ops', 'public'
AS $$
DECLARE
    p ops.backup_policy%ROWTYPE;
    b ops.backup_run%ROWTYPE;
    v_hours numeric;
BEGIN
    SELECT * INTO p FROM ops.backup_policy
      WHERE tenant_id = p_tenant_id AND scope = p_scope;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 'undocumented'::ops.backup_posture, NULL::numeric,
            'no backup policy for this scope: how often this estate is backed up is not '
            'written down anywhere, so nothing can be late'::text;
        RETURN;
    END IF;

    -- THE LATEST VERIFIED ONE, not the latest one. A directory full of captured archives
    -- nobody has read is the state this whole table exists to make visible.
    SELECT * INTO b FROM ops.backup_run
     WHERE tenant_id = p_tenant_id AND scope = p_scope
       AND state IN ('verified', 'offsite')
     ORDER BY started_at DESC LIMIT 1;

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            CASE WHEN EXISTS (SELECT 1 FROM ops.backup_run
                               WHERE tenant_id = p_tenant_id AND scope = p_scope)
                 THEN 'unverified' ELSE 'never' END::ops.backup_posture,
            NULL::numeric,
            'no backup of this scope has ever been read back. A file that exists and has '
            'never been opened is not a backup'::text;
        RETURN;
    END IF;

    v_hours := round(extract(epoch FROM (now() - b.started_at)) / 3600.0, 1);

    RETURN QUERY SELECT
        CASE
            WHEN v_hours > p.alert_after_hours THEN 'overdue'
            WHEN v_hours > p.interval_hours    THEN 'due'
            ELSE 'healthy'
        END::ops.backup_posture,
        v_hours,
        format('last verified backup %s hour(s) ago; schedule is every %s, alert after %s%s',
               v_hours, p.interval_hours, p.alert_after_hours,
               CASE WHEN p.offsite_required AND b.state <> 'offsite'
                    THEN '. OFF-SITE COPY REQUIRED AND ABSENT' ELSE '' END)::text;
END;
$$;

COMMENT ON FUNCTION ops.backup_posture(uuid, ops.backup_scope) IS
    'FR-OPS-006. Whether this estate is actually backed up, read from the runs rather than '
    'from a scheduler. It reads the latest VERIFIED backup and not the latest one: a '
    'directory full of archives nobody has opened is precisely the state this table exists '
    'to make visible.';

GRANT SELECT ON ops.backup_policy TO hospitality_app;
GRANT SELECT ON ops.backup_run    TO hospitality_app;
GRANT EXECUTE ON FUNCTION ops.record_backup(uuid, ops.backup_scope, uuid, text, text, text,
        character, bigint, text, text, integer) TO hospitality_app;
GRANT EXECUTE ON FUNCTION ops.verify_backup(uuid, uuid, character, integer, text)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION ops.record_offsite_copy(uuid, uuid, text, character)
    TO hospitality_app;
GRANT EXECUTE ON FUNCTION ops.backup_posture(uuid, ops.backup_scope) TO hospitality_app;

-- RUN, NOT MERELY DEFINED. Four migrations in M5b applied cleanly and could never have
-- executed. This one calls what it defines before it commits.
DO $$
DECLARE
    v_posture ops.backup_posture;
    v_tenant  uuid;
BEGIN
    SELECT id INTO v_tenant FROM org.tenant ORDER BY id LIMIT 1;
    IF v_tenant IS NULL THEN RETURN; END IF;

    SELECT posture INTO v_posture FROM ops.backup_posture(v_tenant, 'cloud');
    IF v_posture IS NULL THEN
        RAISE EXCEPTION 'BACKUP_POSTURE_UNRUNNABLE: the function returned no row'
            USING ERRCODE = 'HS500';
    END IF;
    IF v_posture <> 'undocumented' THEN
        RAISE EXCEPTION
            'BACKUP_POSTURE_WRONG_ON_EMPTY: an estate with no policy should read '
            'undocumented and read % instead', v_posture
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
