-- 0054: the four ways a real phone resolves a name, and what each one is told
--
-- FR-EDG-028 is the acceptance requirement for same-QR routing, and it is written against
-- REAL CLIENT BEHAVIOUR rather than against the happy path. It names four conditions:
--
--   a device joining outlet Wi-Fi while holding a CACHED PUBLIC DNS ANSWER
--   a device with ENCRYPTED DNS (Android Private DNS, DNS-over-HTTPS) bypassing split DNS
--   a DUAL-STACK IPv4/IPv6 device that must not reach a stale or untrusted endpoint
--   the resolver-cache flush and TTL behaviour of the cloud-to-LAN transition
--
-- and it ends with the sentence the whole thing is for:
--
--   "Every unsupported client configuration fails safe to a clear instruction, never to a
--    certificate warning or a bypass prompt."
--
-- THAT SENTENCE IS WHY THE OUTCOME TYPE HAS NO VALUE FOR A BYPASS. The same argument as
-- 0053's missing private-key column: a mechanism that cannot express an outcome cannot
-- produce it by accident, which is stronger than a rule saying it must not. There are
-- three outcomes — the trusted local endpoint, the cloud-served one, or an instruction a
-- person can read in their own language — and adding a fourth would take a migration and
-- an argument.
--
-- WHAT 0053 GOT WRONG AND THIS CORRECTS. 0053 gave each horizon ONE answer. FR-EDG-028
-- requires IPv4 and IPv6 answers to be CONSISTENT, and the failure it is describing is
-- precise: split-horizon DNS answers A for the LAN while AAAA falls through to the public
-- zone, so a dual-stack phone opens the public address over IPv6 while sitting in the
-- dining room with the internet down. One answer per horizon cannot express that at all,
-- so it could not refuse it either. Forward-only, so this corrects rather than edits.

-- ---------------------------------------------------------------------------
-- 1. BOTH FAMILIES, BOTH HORIZONS
-- ---------------------------------------------------------------------------

ALTER TABLE edge.outlet_hostname DROP COLUMN public_answer;
ALTER TABLE edge.outlet_hostname DROP COLUMN lan_answer;

ALTER TABLE edge.outlet_hostname
    ADD COLUMN public_answer_v4 inet NOT NULL,
    ADD COLUMN public_answer_v6 inet NOT NULL,
    ADD COLUMN lan_answer_v4    inet NOT NULL,
    ADD COLUMN lan_answer_v6    inet NOT NULL;

-- outlet_hostname_answers_are_stated is already gone: it was a check OVER the two columns
-- dropped above, and PostgreSQL drops a constraint with its last remaining column. Naming
-- it here would fail, and a migration that says DROP IF EXISTS about something it just
-- dropped is a migration hedging about its own effect.

-- EACH FAMILY IS THE FAMILY IT CLAIMS TO BE. Putting an IPv4 literal in the AAAA column is
-- how a zone ends up serving one family and not the other.
ALTER TABLE edge.outlet_hostname
    ADD CONSTRAINT outlet_hostname_families_are_what_they_say CHECK (
        family(public_answer_v4) = 4 AND family(lan_answer_v4) = 4
    AND family(public_answer_v6) = 6 AND family(lan_answer_v6) = 6);

-- THE LAN ANSWERS ARE LAN ADDRESSES AND THE PUBLIC ANSWERS ARE NOT. This is what makes
-- the two horizons actually different, and a LAN answer that is publicly routable means
-- the split is not a split — every device gets the same answer and the outage journey
-- silently never happens.
ALTER TABLE edge.outlet_hostname
    ADD CONSTRAINT outlet_hostname_horizons_are_actually_split CHECK (
        (lan_answer_v4 << inet '10.0.0.0/8'
      OR lan_answer_v4 << inet '172.16.0.0/12'
      OR lan_answer_v4 << inet '192.168.0.0/16')
    AND lan_answer_v6 << inet 'fc00::/7'
    AND NOT (public_answer_v4 << inet '10.0.0.0/8'
          OR public_answer_v4 << inet '172.16.0.0/12'
          OR public_answer_v4 << inet '192.168.0.0/16'
          OR public_answer_v4 << inet '127.0.0.0/8')
    AND NOT public_answer_v6 << inet 'fc00::/7');

COMMENT ON CONSTRAINT outlet_hostname_horizons_are_actually_split ON edge.outlet_hostname IS
    'FR-EDG-028. Both families are answered on both horizons, the LAN answers are private '
    'and the public ones are not. The dual-stack failure this refuses is exact: split DNS '
    'answering A for the LAN while AAAA falls through to the public zone, so a phone in '
    'the dining room opens the public address over IPv6 during an outage. One answer per '
    'horizon — which is what 0053 had — could not express that, so it could not refuse it.';

-- ---------------------------------------------------------------------------
-- 2. THE DOCUMENTED SUPPORTED-NETWORK CONFIGURATION
-- ---------------------------------------------------------------------------
--
-- FR-EDG-028 asks for encrypted DNS to be "handled with a DOCUMENTED supported-network
-- configuration". A document nobody can query is a document nobody checks against, so the
-- statement lives here and the guidance below is derived from it.

CREATE TABLE edge.supported_network (
    tenant_id uuid NOT NULL,
    outlet_id uuid NOT NULL,

    -- The DHCP-advertised resolver a joining device is expected to use. This is the thing
    -- encrypted DNS bypasses, which is why it is named.
    advertised_resolver_v4 inet NOT NULL,
    advertised_resolver_v6 inet NOT NULL,

    -- Whether the outlet network blocks well-known public DoH endpoints at the gateway.
    -- FALSE IS THE HONEST DEFAULT and it is not a failing: blocking DoH is a decision an
    -- operator makes about their own network, and recording that it is NOT blocked is what
    -- makes the encrypted-DNS branch below reachable rather than theoretical.
    blocks_public_doh boolean NOT NULL DEFAULT false,

    -- What a device that has just joined is told to do, and how long the transition takes.
    -- FR-EDG-028's "resolver-cache flush and TTL behaviour is specified".
    expected_flush_seconds integer NOT NULL DEFAULT 60,

    documented_at timestamptz NOT NULL DEFAULT now(),
    documented_by_user_id uuid NOT NULL,

    CONSTRAINT supported_network_pkey PRIMARY KEY (tenant_id, outlet_id),
    CONSTRAINT supported_network_outlet_fk FOREIGN KEY (tenant_id, outlet_id)
        REFERENCES edge.outlet_hostname (tenant_id, outlet_id) ON DELETE CASCADE,
    CONSTRAINT supported_network_documenter_fk FOREIGN KEY (tenant_id, documented_by_user_id)
        REFERENCES identity.user_account (tenant_id, id) ON DELETE RESTRICT,
    CONSTRAINT supported_network_resolver_families CHECK (
        family(advertised_resolver_v4) = 4 AND family(advertised_resolver_v6) = 6),
    CONSTRAINT supported_network_flush_is_sane CHECK (
        expected_flush_seconds BETWEEN 1 AND 3600)
);

COMMENT ON TABLE edge.supported_network IS
    'FR-EDG-028. The documented supported-network configuration, as a row rather than a '
    'page: the resolver the outlet advertises, whether public DoH is blocked at the '
    'gateway, and how long the cloud-to-LAN transition is expected to take. A document '
    'nobody can query is a document nobody checks against.';

ALTER TABLE edge.supported_network ENABLE ROW LEVEL SECURITY;
ALTER TABLE edge.supported_network FORCE ROW LEVEL SECURITY;
CREATE POLICY supported_network_isolation ON edge.supported_network FOR ALL
    USING (app.row_in_scope(tenant_id, outlet_id))
    WITH CHECK (app.row_in_scope(tenant_id, outlet_id));

-- ---------------------------------------------------------------------------
-- 3. THE CONDITIONS, AND THE THREE THINGS THAT MAY HAPPEN
-- ---------------------------------------------------------------------------

CREATE TYPE edge.client_condition AS ENUM (
    -- Joined the outlet network and asked the advertised resolver. The intended path.
    'lan_resolver',
    -- On the outlet network but still holding the public answer it got on cellular.
    -- FR-EDG-028's first named condition, and the common one: it is what happens to
    -- everybody who walks in with the page already open.
    'cached_public_answer',
    -- Android Private DNS or a browser's DNS-over-HTTPS, resolving past the outlet
    -- entirely. FR-EDG-028's second, and the one that CANNOT be fixed by waiting.
    'encrypted_dns',
    -- Dual-stack, asking both families. FR-EDG-028's third.
    'dual_stack',
    -- Not on the outlet network at all.
    'public_internet');

-- THREE OUTCOMES AND THERE IS NO FOURTH. FR-EDG-028: "never to a certificate warning or a
-- bypass prompt." A type with no value for a bypass cannot return one, and adding one
-- would take a migration and an argument — which is the point.
CREATE TYPE edge.resolution_outcome AS ENUM (
    'trusted_local',   -- the node, over the certificate 0053 verified from the LAN
    'cloud_served',    -- the cloud, which is correct whenever the cloud is reachable
    'staff_guidance'); -- a sentence a person reads, in their language

CREATE FUNCTION edge.resolve_customer_entry(
    p_tenant_id uuid,
    p_outlet_id uuid,
    p_condition edge.client_condition,
    p_seconds_since_join integer,
    p_locale menu.customer_locale,
    p_cloud_reachable boolean)
RETURNS TABLE (
    outcome     edge.resolution_outcome,
    endpoint    text,
    guidance    text,
    phrase_code text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'menu', 'public'
AS $$
DECLARE
    h edge.outlet_hostname%ROWTYPE;
    s edge.supported_network%ROWTYPE;
    v_posture edge.renewal_posture;
    v_code text;
BEGIN
    SELECT * INTO h FROM edge.outlet_hostname
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'OUTLET_HOSTNAME_UNDECLARED: outlet % has no hostname, so there is no name for '
            'a QR to carry and nothing to resolve', p_outlet_id
            USING ERRCODE = 'HS404';
    END IF;
    SELECT * INTO s FROM edge.supported_network
      WHERE tenant_id = p_tenant_id AND outlet_id = p_outlet_id;

    SELECT p.posture INTO v_posture
      FROM edge.certificate_posture(p_tenant_id, p_outlet_id) p;

    -- THE CERTIFICATE IS CHECKED BEFORE THE CONDITION, because it dominates every branch.
    -- Sending a phone to the node without a valid certificate is precisely the warning
    -- FR-EDG-022C prohibits, and it does not become acceptable because the customer is on
    -- the right network or because the cloud is down. If the cloud is reachable, use it.
    -- If it is not, say so — an outage a guest is told about is a worse afternoon than one
    -- they are not, and it is not a security decision they have been handed.
    IF v_posture IN ('absent', 'expired') THEN
        IF p_cloud_reachable THEN
            RETURN QUERY SELECT 'cloud_served'::edge.resolution_outcome,
                host(h.public_answer_v4), NULL::text, NULL::text;
            RETURN;
        END IF;
        v_code := 'resolution.no_local_certificate';
        RETURN QUERY SELECT 'staff_guidance'::edge.resolution_outcome, NULL::text,
               edge.say(p_tenant_id, v_code, p_locale), v_code;
        RETURN;
    END IF;

    CASE p_condition
        -- The intended path, and the dual-stack one, which is the same path: 0054's
        -- constraint means both families answer to the same horizon, so a dual-stack
        -- device gets the node twice rather than the node and the cloud.
        WHEN 'lan_resolver', 'dual_stack' THEN
            RETURN QUERY SELECT 'trusted_local'::edge.resolution_outcome,
                   h.hostname, NULL::text, NULL::text;

        -- A CACHED PUBLIC ANSWER RESOLVES ITSELF, AND THE ONLY QUESTION IS WHETHER IT HAS
        -- HAD TIME TO. Inside the TTL the device still holds the public address; if the
        -- cloud is up that address works and the guest notices nothing, and if it is down
        -- the honest answer is to wait the documented window rather than to send them
        -- somewhere their cache will not take them.
        WHEN 'cached_public_answer' THEN
            IF p_seconds_since_join >= COALESCE(s.expected_flush_seconds, h.ttl_seconds) THEN
                RETURN QUERY SELECT 'trusted_local'::edge.resolution_outcome,
                       h.hostname, NULL::text, NULL::text;
            ELSIF p_cloud_reachable THEN
                RETURN QUERY SELECT 'cloud_served'::edge.resolution_outcome,
                       host(h.public_answer_v4), NULL::text, NULL::text;
            ELSE
                v_code := 'resolution.cached_answer_wait';
                RETURN QUERY SELECT 'staff_guidance'::edge.resolution_outcome, NULL::text,
                       edge.say(p_tenant_id, v_code, p_locale), v_code;
            END IF;

        -- ENCRYPTED DNS IS THE ONE THAT CANNOT BE WAITED OUT, and pretending otherwise is
        -- how a guest ends up refreshing for ten minutes. The device is asking a resolver
        -- the outlet does not run and cannot answer, so it will keep receiving the public
        -- address for as long as that setting is on. If the gateway blocks public DoH the
        -- device falls back to the advertised resolver on its own and this is the LAN path;
        -- if it does not, the only thing that changes the outcome is a person changing a
        -- setting, and the guidance says which setting.
        WHEN 'encrypted_dns' THEN
            IF COALESCE(s.blocks_public_doh, false) THEN
                RETURN QUERY SELECT 'trusted_local'::edge.resolution_outcome,
                       h.hostname, NULL::text, NULL::text;
            ELSIF p_cloud_reachable THEN
                RETURN QUERY SELECT 'cloud_served'::edge.resolution_outcome,
                       host(h.public_answer_v4), NULL::text, NULL::text;
            ELSE
                v_code := 'resolution.encrypted_dns_blocks_local';
                RETURN QUERY SELECT 'staff_guidance'::edge.resolution_outcome, NULL::text,
                       edge.say(p_tenant_id, v_code, p_locale), v_code;
            END IF;

        WHEN 'public_internet' THEN
            IF p_cloud_reachable THEN
                RETURN QUERY SELECT 'cloud_served'::edge.resolution_outcome,
                       host(h.public_answer_v4), NULL::text, NULL::text;
            ELSE
                v_code := 'resolution.join_outlet_wifi';
                RETURN QUERY SELECT 'staff_guidance'::edge.resolution_outcome, NULL::text,
                       edge.say(p_tenant_id, v_code, p_locale), v_code;
            END IF;
    END CASE;
END;
$$;

COMMENT ON FUNCTION edge.resolve_customer_entry(uuid, uuid, edge.client_condition, integer,
                                                menu.customer_locale, boolean) IS
    'FR-EDG-004B, FR-EDG-021, FR-EDG-028. Where a customer''s browser should go, given how '
    'their phone actually resolved the name. Three outcomes and no fourth: the node, the '
    'cloud, or a sentence in their language. The certificate is checked before the '
    'condition because sending a phone to a node without one is the warning FR-EDG-022C '
    'prohibits, and that does not stop being true because the cloud is down.';

-- ---------------------------------------------------------------------------
-- 4. THE WORDS
-- ---------------------------------------------------------------------------
--
-- 0047 did this once already, for the same reason and in the same shape: a new namespace
-- in edge.plain_language means widening the shape check, and edge.say() then refuses any
-- phrase that has not been worded in all three locales.
ALTER TABLE edge.plain_language
    DROP CONSTRAINT plain_language_code_shape;

ALTER TABLE edge.plain_language
    ADD CONSTRAINT plain_language_code_shape CHECK (
        phrase_code ~ '^(restriction|sync_state|connectivity|resolution)\.[a-z][a-z0-9_]*$');

COMMENT ON CONSTRAINT plain_language_code_shape ON edge.plain_language IS
    'Four namespaces now. resolution.* is FR-EDG-028''s "translated staff guidance", and '
    'it is here rather than in a new table for the reason 0045 gave about the first two: '
    'two tables would be two places to forget Amharic.';

-- WHAT THE FOUR SENTENCES MUST SAY, as a check rather than as a hope. FR-EDG-028's guidance
-- must be an INSTRUCTION — something a guest or a member of staff can act on — and the one
-- thing it must never be is an invitation to click through a warning. A phrase that is
-- missing already fails at edge.say(); this is about a phrase that exists and says the
-- wrong thing.
CREATE FUNCTION edge.assert_resolution_guidance_is_safe(p_tenant_id uuid)
RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'menu', 'public'
AS $$
DECLARE
    v_required text[] := ARRAY['resolution.no_local_certificate',
                               'resolution.cached_answer_wait',
                               'resolution.encrypted_dns_blocks_local',
                               'resolution.join_outlet_wifi'];
    v_code   text;
    v_locale menu.customer_locale;
    v_text   text;
    v_checked integer := 0;
BEGIN
    FOREACH v_code IN ARRAY v_required LOOP
        FOREACH v_locale IN ARRAY ARRAY['en','am','ar']::menu.customer_locale[] LOOP
            -- Refuses on its own if the wording is absent, in all three locales.
            v_text := edge.say(p_tenant_id, v_code, v_locale);

            -- AND IT MAY NOT TELL SOMEBODY TO CLICK THROUGH. Deliberately in English only:
            -- the words below are the ones an engineer writes by accident when translating
            -- a browser dialog, and a genuine Amharic or Arabic instruction will not
            -- contain them. A check that tried to detect the sentiment in three languages
            -- would be a check that gave false confidence in two of them.
            IF v_text ~* '(proceed anyway|continue anyway|advanced|accept the risk'
                       || '|ignore the warning|not secure|unsafe|bypass)' THEN
                RAISE EXCEPTION
                    'RESOLUTION_GUIDANCE_OFFERS_A_BYPASS: % (%) reads "%". FR-EDG-028 says '
                    'an unsupported configuration fails safe to a clear instruction, NEVER '
                    'to a certificate warning or a bypass prompt. Telling a guest to tap '
                    'past a warning teaches them to tap past the next one',
                    v_code, v_locale, v_text
                    USING ERRCODE = 'HS422';
            END IF;
            v_checked := v_checked + 1;
        END LOOP;
    END LOOP;
    RETURN v_checked;
END;
$$;

COMMENT ON FUNCTION edge.assert_resolution_guidance_is_safe(uuid) IS
    'FR-EDG-028, FR-EDG-022C. All four resolution phrases exist in all three locales and '
    'none of them tells anybody to click through a warning. The bypass check is English-'
    'only on purpose: those are the words an engineer writes by accident, and a check that '
    'claimed to detect the sentiment in Amharic and Arabic would give false confidence.';

GRANT SELECT ON edge.supported_network TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.resolve_customer_entry(uuid, uuid, edge.client_condition,
        integer, menu.customer_locale, boolean) TO hospitality_app;
GRANT EXECUTE ON FUNCTION edge.assert_resolution_guidance_is_safe(uuid) TO hospitality_app;
