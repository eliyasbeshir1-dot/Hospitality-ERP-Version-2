-- 0016_a_name_a_certificate_and_the_four_things_a_phone_is_told.provision.sql
--
-- 0053 and 0054 give the two node-backed outlets somewhere to record a hostname, a
-- certificate and a documented network. This writes them, and writes the twelve phrases —
-- four conditions, three locales — that edge.say() refuses to invent.
--
-- IT IS A SEPARATE SEED FOR THE REASON 0014 GAVE. Seeds are checksum-locked: a seed that
-- has run has run. The rows could not have gone into 0012 anyway, because the tables and
-- the widened CHECK that admit them did not exist until 0053 and 0054.
--
-- ONLY THE TWO NODE-BACKED OUTLETS GET A HOSTNAME. OUT-N1 has no node, and a hostname
-- whose LAN answer points at nothing is worse than no hostname: edge.resolve_customer_entry()
-- would find a name, find no certificate, and send a guest to staff guidance during an
-- outage that the cloud could have served. With no hostname it raises
-- OUTLET_HOSTNAME_UNDECLARED, which is the true statement.
--
-- THE CERTIFICATE DIGESTS ARE FIXTURES AND SAY SO. There is no domain, no CA account and
-- no DNS-01 automation here, so nothing below is a real chain — csr_sha256 and
-- certificate_sha256 are stable fabricated digests, and planning/M5B_FINDINGS.md carries
-- the bound with what closes it. They are still 64 HEX characters, because character(64)
-- SPACE-PADS anything shorter without complaining: a digest that is quietly 63 characters
-- and a space is a fixture that can never match itself, and the first draft of this seed
-- had two of them. What IS real is the lifecycle around them: the state
-- machine, the LAN-served comparison, the renewal schedule and the four prohibitions.
--
-- THE ADDRESSES ARE DOCUMENTATION RANGES ON THE PUBLIC SIDE (RFC 5737 / RFC 3849) and
-- ordinary private ranges on the LAN side. A real public address would be somebody's.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_kazanchis '''33330001-0000-4000-8000-000000000001'''
\set o_sarbet    '''33330002-0000-4000-8000-000000000002'''
\set u_habesha_admin '''3333aaaa-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false);

-- ---------------------------------------------------------------------------
-- KAZANCHIS AND SARBET EACH GET A NAME, ANSWERED TWO WAYS IN BOTH FAMILIES
-- ---------------------------------------------------------------------------

SELECT set_config('app.outlet_id', :o_kazanchis, false);

INSERT INTO edge.outlet_hostname
    (tenant_id, outlet_id, hostname,
     public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,
     ttl_seconds, declared_by_user_id)
VALUES (:t_habesha::uuid, :o_kazanchis::uuid, 'kazanchis.habesha.example',
        '203.0.113.10', '2001:db8:113::10', '192.168.10.10', 'fd00:10::10',
        60, :u_habesha_admin::uuid);

INSERT INTO edge.supported_network
    (tenant_id, outlet_id, advertised_resolver_v4, advertised_resolver_v6,
     blocks_public_doh, expected_flush_seconds, documented_by_user_id)
VALUES (:t_habesha::uuid, :o_kazanchis::uuid, '192.168.10.1', 'fd00:10::1',
        -- KAZANCHIS DOES NOT BLOCK PUBLIC DoH, and that is the honest default rather than
        -- a failing. It is also what makes FR-EDG-028's encrypted-DNS branch reachable on
        -- the demonstration floor instead of theoretical: a phone with Private DNS on gets
        -- the guidance here, and a reader can see the sentence it gets.
        false, 60, :u_habesha_admin::uuid);

SELECT set_config('app.outlet_id', :o_sarbet, false);

INSERT INTO edge.outlet_hostname
    (tenant_id, outlet_id, hostname,
     public_answer_v4, public_answer_v6, lan_answer_v4, lan_answer_v6,
     ttl_seconds, declared_by_user_id)
VALUES (:t_habesha::uuid, :o_sarbet::uuid, 'sarbet.habesha.example',
        '203.0.113.20', '2001:db8:113::20', '192.168.20.10', 'fd00:20::10',
        60, :u_habesha_admin::uuid);

INSERT INTO edge.supported_network
    (tenant_id, outlet_id, advertised_resolver_v4, advertised_resolver_v6,
     blocks_public_doh, expected_flush_seconds, documented_by_user_id)
VALUES (:t_habesha::uuid, :o_sarbet::uuid, '192.168.20.1', 'fd00:20::1',
        -- SARBET DOES BLOCK IT, so the two outlets differ in the one way FR-EDG-028 cares
        -- about and the difference is visible on the floor: the same phone, the same
        -- setting, two outcomes, and the reason is a row somebody can point at.
        true, 60, :u_habesha_admin::uuid);

-- ---------------------------------------------------------------------------
-- AND A CERTIFICATE EACH, INSTALLED THE ONLY WAY 0053 PERMITS
-- ---------------------------------------------------------------------------
--
-- THE TENANT IS WRITTEN OUT INSIDE THE BLOCKS BELOW, and that is not an oversight: psql
-- does NOT substitute :variables inside dollar quoting. `:t_habesha` in a DO block reaches
-- the server as the three characters it is and fails with a syntax error at ':'. The \set
-- above still governs everything outside them, so there is exactly one place the literal
-- appears twice, and it appears rather than silently not being substituted.
--
-- A DO BLOCK AND A LOCAL VARIABLE, NOT A TEMP TABLE. The first draft held the returned
-- certificate id in `CREATE TEMP TABLE`, which worked against a superuser scratch database
-- and failed in the chain with `permission denied to create temporary tables`: the
-- provisioning identity has no TEMP privilege on the database, and it should not — a seed
-- that needs to create objects is a seed doing more than seeding. The whole-chain run from
-- empty is what surfaced it, which is the difference between running a seed and running it
-- AS THE ROLE THAT WILL RUN IT.
--
-- Requested, issued and installed through the three functions, rather than inserted at
-- the state it ends in. The constraints would have allowed a hand-filled `installed` row,
-- and taking that shortcut would mean the seeded floor demonstrates a state no code path
-- produces. Writing this seed is also what surfaced that edge.node_certificate had an
-- install path and no request path; 0055 added one.

SELECT set_config('app.outlet_id', :o_kazanchis, false);

DO $cert_kazanchis$
DECLARE
    v_id uuid;
BEGIN
    v_id := edge.request_certificate(
        '33333333-3333-3333-3333-333333333333'::uuid,
        (SELECT id FROM edge.node
          WHERE tenant_id = '33333333-3333-3333-3333-333333333333'::uuid AND node_code = 'NODE-H1'),
        'c5c500010000000000000000000000000000000000000000000000000000ca01');

    PERFORM edge.record_certificate_issued(
        '33333333-3333-3333-3333-333333333333'::uuid, v_id, 'ce4700010000000000000000000000000000000000000000000000000000ca01',
        'Demonstration CA R3 (fixture — not a real issuer)',
        now() - interval '3 days', now() + interval '87 days');

    PERFORM edge.verify_and_install_certificate('33333333-3333-3333-3333-333333333333'::uuid, v_id, 'ce4700010000000000000000000000000000000000000000000000000000ca01');
END
$cert_kazanchis$;

SELECT set_config('app.outlet_id', :o_sarbet, false);

DO $cert_sarbet$
DECLARE
    v_id uuid;
BEGIN
    v_id := edge.request_certificate(
        '33333333-3333-3333-3333-333333333333'::uuid,
        (SELECT id FROM edge.node
          WHERE tenant_id = '33333333-3333-3333-3333-333333333333'::uuid AND node_code = 'NODE-H2'),
        'c5c5000200000000000000000000000000000000000000000000000000005a02');

    PERFORM edge.record_certificate_issued(
        '33333333-3333-3333-3333-333333333333'::uuid, v_id, 'ce47000200000000000000000000000000000000000000000000000000005a02',
        'Demonstration CA R3 (fixture — not a real issuer)',
        now() - interval '3 days', now() + interval '87 days');

    PERFORM edge.verify_and_install_certificate('33333333-3333-3333-3333-333333333333'::uuid, v_id, 'ce47000200000000000000000000000000000000000000000000000000005a02');
END
$cert_sarbet$;

-- ---------------------------------------------------------------------------
-- THE TWELVE SENTENCES
-- ---------------------------------------------------------------------------
--
-- Four conditions, three locales, all at once — for the reason 0014 gave about the nine
-- connectivity phrases: edge.say() raises on a missing one, so a partial set is a screen
-- that stops rather than a screen that lies, and English-first-and-the-rest-later means
-- Amharic never arrives.
--
-- EVERY ONE OF THEM IS AN INSTRUCTION AND NONE OF THEM MENTIONS A WARNING.
-- edge.assert_resolution_guidance_is_safe() checks that, and it is the only wording in
-- this repository with a check on what it may NOT say.

SELECT set_config('app.outlet_id', '', false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 -- No certificate and no cloud. There is nothing the phone can be sent to, so the
 -- instruction is to ask a person — which is a real answer in a restaurant.
 (:t_habesha::uuid, 'resolution.no_local_certificate', 'en',
  'Ordering from your phone is unavailable right now. Please ask your server — they can take your order.'),
 (:t_habesha::uuid, 'resolution.no_local_certificate', 'am',
  'በስልክዎ ማዘዝ አሁን አይቻልም። እባክዎ አስተናጋጅዎን ይጠይቁ — ትዕዛዝዎን ሊወስዱ ይችላሉ።'),
 (:t_habesha::uuid, 'resolution.no_local_certificate', 'ar',
  'الطلب من هاتفك غير متاح حالياً. من فضلك اسأل النادل — يمكنه أخذ طلبك.'),

 -- A cached public answer, inside the window. Waiting genuinely fixes this one, and
 -- saying how long turns a broken page into a short wait.
 (:t_habesha::uuid, 'resolution.cached_answer_wait', 'en',
  'Almost ready. Wait about a minute after joining our Wi-Fi, then reload this page.'),
 (:t_habesha::uuid, 'resolution.cached_answer_wait', 'am',
  'ዝግጁ ሊሆን ነው። ወደ ዋይ-ፋያችን ከተገናኙ በኋላ አንድ ደቂቃ ያህል ይጠብቁ፣ ከዚያ ይህን ገጽ እንደገና ይጫኑ።'),
 (:t_habesha::uuid, 'resolution.cached_answer_wait', 'ar',
  'على وشك الجاهزية. انتظر دقيقة تقريباً بعد الاتصال بشبكتنا، ثم أعد تحميل هذه الصفحة.'),

 -- Encrypted DNS. Waiting does NOT fix this, so the sentence must not suggest it does.
 -- It names the setting, because a guest who is told "turn off Private DNS" can, and a
 -- guest who is told "there is a network problem" cannot.
 (:t_habesha::uuid, 'resolution.encrypted_dns_blocks_local', 'en',
  'Your phone''s private DNS setting is keeping it off our network. Turn off Private DNS or DNS-over-HTTPS, or ask your server to take your order.'),
 (:t_habesha::uuid, 'resolution.encrypted_dns_blocks_local', 'am',
  'የስልክዎ የግል DNS ቅንብር ከአውታረ መረባችን ውጭ እያደረገው ነው። Private DNS ወይም DNS-over-HTTPS ያጥፉ፣ ወይም አስተናጋጅዎ ትዕዛዝዎን እንዲወስድ ይጠይቁ።'),
 (:t_habesha::uuid, 'resolution.encrypted_dns_blocks_local', 'ar',
  'إعداد DNS الخاص في هاتفك يمنعه من الوصول إلى شبكتنا. أوقف Private DNS أو DNS-over-HTTPS، أو اطلب من النادل أخذ طلبك.'),

 -- Not on the outlet network, and no cloud. One step, and it is a step a guest can take.
 (:t_habesha::uuid, 'resolution.join_outlet_wifi', 'en',
  'Connect to our Wi-Fi to order from your phone. Your server can give you the network name.'),
 (:t_habesha::uuid, 'resolution.join_outlet_wifi', 'am',
  'በስልክዎ ለማዘዝ ወደ ዋይ-ፋያችን ይገናኙ። አስተናጋጅዎ የአውታረ መረቡን ስም ሊሰጥዎ ይችላል።'),
 (:t_habesha::uuid, 'resolution.join_outlet_wifi', 'ar',
  'اتصل بشبكتنا للطلب من هاتفك. يمكن للنادل أن يعطيك اسم الشبكة.');

-- ---------------------------------------------------------------------------
-- NILE GETS THE WORDS AND NO HOSTNAME
-- ---------------------------------------------------------------------------
--
-- OUT-N1 has no node, so it gets no name and no certificate — see the header. It gets the
-- twelve phrases anyway, because the wording belongs to the TENANT and a tenant that
-- later provisions a node should not discover its Amharic is missing on the day it does.
--
-- WRITTEN OUT RATHER THAN COPIED FROM HABESHA. An INSERT ... SELECT from the other
-- tenant's rows is the obvious way to write this and it would have inserted NOTHING:
-- app.tenant_id is Nile by the time it runs, edge.plain_language carries FORCE row level
-- security, and the SELECT would match zero rows and insert zero rows without erroring.
-- Twelve phrases would be missing and the first sign of it would be edge.say() raising
-- PHRASE_UNWORDED at a guest's phone. 0014 wrote both tenants out longhand for the same
-- reason, and this is the same reason.

SELECT set_config('app.tenant_id', :t_nile, false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 (:t_nile::uuid, 'resolution.no_local_certificate', 'en',
  'Ordering from your phone is unavailable right now. Please ask your server — they can take your order.'),
 (:t_nile::uuid, 'resolution.no_local_certificate', 'am',
  'በስልክዎ ማዘዝ አሁን አይቻልም። እባክዎ አስተናጋጅዎን ይጠይቁ — ትዕዛዝዎን ሊወስዱ ይችላሉ።'),
 (:t_nile::uuid, 'resolution.no_local_certificate', 'ar',
  'الطلب من هاتفك غير متاح حالياً. من فضلك اسأل النادل — يمكنه أخذ طلبك.'),
 (:t_nile::uuid, 'resolution.cached_answer_wait', 'en',
  'Almost ready. Wait about a minute after joining our Wi-Fi, then reload this page.'),
 (:t_nile::uuid, 'resolution.cached_answer_wait', 'am',
  'ዝግጁ ሊሆን ነው። ወደ ዋይ-ፋያችን ከተገናኙ በኋላ አንድ ደቂቃ ያህል ይጠብቁ፣ ከዚያ ይህን ገጽ እንደገና ይጫኑ።'),
 (:t_nile::uuid, 'resolution.cached_answer_wait', 'ar',
  'على وشك الجاهزية. انتظر دقيقة تقريباً بعد الاتصال بشبكتنا، ثم أعد تحميل هذه الصفحة.'),
 (:t_nile::uuid, 'resolution.encrypted_dns_blocks_local', 'en',
  'Your phone''s private DNS setting is keeping it off our network. Turn off Private DNS or DNS-over-HTTPS, or ask your server to take your order.'),
 (:t_nile::uuid, 'resolution.encrypted_dns_blocks_local', 'am',
  'የስልክዎ የግል DNS ቅንብር ከአውታረ መረባችን ውጭ እያደረገው ነው። Private DNS ወይም DNS-over-HTTPS ያጥፉ፣ ወይም አስተናጋጅዎ ትዕዛዝዎን እንዲወስድ ይጠይቁ።'),
 (:t_nile::uuid, 'resolution.encrypted_dns_blocks_local', 'ar',
  'إعداد DNS الخاص في هاتفك يمنعه من الوصول إلى شبكتنا. أوقف Private DNS أو DNS-over-HTTPS، أو اطلب من النادل أخذ طلبك.'),
 (:t_nile::uuid, 'resolution.join_outlet_wifi', 'en',
  'Connect to our Wi-Fi to order from your phone. Your server can give you the network name.'),
 (:t_nile::uuid, 'resolution.join_outlet_wifi', 'am',
  'በስልክዎ ለማዘዝ ወደ ዋይ-ፋያችን ይገናኙ። አስተናጋጅዎ የአውታረ መረቡን ስም ሊሰጥዎ ይችላል።'),
 (:t_nile::uuid, 'resolution.join_outlet_wifi', 'ar',
  'اتصل بشبكتنا للطلب من هاتفك. يمكن للنادل أن يعطيك اسم الشبكة.');

SELECT set_config('app.tenant_id', '', false);
