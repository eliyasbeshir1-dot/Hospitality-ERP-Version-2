-- 0012_the_demonstration_floor_can_stand_alone.provision.sql — profile, node and wording
--
-- The privileged third of M5a's seeding, and each of the three things here is a decision
-- an installer makes rather than something trade produces.
--
--   edge.deployment_profile  whether this outlet may run cloud-only. A screen that could
--                            write it could change the answer to "is this production",
--                            which is why it is SELECT-only to the application role and
--                            why the row goes in here.
--   edge.register_node       allowlisted in tools/seed.py as a vetted call rather than
--                            written as statements, because the point of the function is
--                            that a node and its five services arrive together —
--                            FR-EDG-002A's "exactly five" is enforced inside it, and a
--                            seed writing the rows itself could write four.
--   edge.plain_language      the words a restriction and a synchronization state are
--                            given. Installed, revisited by a manager, read by every
--                            surface that has to tell somebody why a button did nothing.
--
-- THE ENVIRONMENT IS `pilot`, NOT `production`. This is a demonstration floor, and saying
-- otherwise in the table that governs deployment would be the first lie in the record.
-- FR-EDG-001 does not forbid a node outside production; it forbids production WITHOUT
-- one. Pilot with a node is the shape a real outlet has the week before it opens.
--
-- WHY BOTH HABESHA OUTLETS. The chain leaves work at Kazanchis as well as Sarbet — M4-A's
-- counter orders are entered there — so an outlet with tickets and no node would be an
-- outlet whose print jobs could never reconcile. Giving one outlet a node and not its
-- sibling is also how a reviewer comes to believe a single-outlet result generalises.
--
-- WHY NILE GETS THE WORDING AND NO NODE. Nile has no floor and no menu, so a node there
-- would serve nothing. It gets the phrases for the reason seeds/0008 grades its actions:
-- the tenants that exist should not differ in whether a restriction can be EXPLAINED, or
-- the next person to give Nile a floor meets PHRASE_UNWORDED with no clue it was already
-- met once.
--
-- THE FINGERPRINTS LOOK LIKE DEMONSTRATION FINGERPRINTS ON PURPOSE. A real node presents
-- the digest of a key it holds. Nothing in this repository mints one, and a
-- plausible-looking random digest here would invite somebody to believe it came from
-- somewhere.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''
\set o_h1       '''33330001-0000-4000-8000-000000000001'''
\set o_h2       '''33330002-0000-4000-8000-000000000002'''
\set u_habesha  '''3333aaaa-0000-4000-8000-000000000001'''

SELECT set_config('app.tenant_id', :t_habesha, false);
SELECT set_config('app.outlet_id', :o_h1, false);

INSERT INTO edge.deployment_profile
    (tenant_id, outlet_id, environment_class, serving_mode, declared_by_user_id)
VALUES (:t_habesha::uuid, :o_h1::uuid, 'pilot', 'continuity_node', :u_habesha::uuid);

SELECT edge.register_node(
    :t_habesha::uuid, :o_h1::uuid, 'NODE-H1',
    '3333ed01-0000-4000-8000-0000000ed001'::uuid,
    'de505eed0000000000000000000000000000000000000000000000000000h101'::character(64),
    '3333ed11-0000-4000-8000-0000000ed011'::uuid,
    'http://kazanchis.node.local:7101',
    'file:///etc/hospitality/kazanchis/secrets',
    'de505eed0000000000000000000000000000000000000000000000000000anch'::character(64),
    'demonstration-host-profile-v1',
    :u_habesha::uuid,
    '{"local_api":"hospitality_node_api",
      "database":"hospitality_node_db",
      "sync_worker":"hospitality_node_sync",
      "realtime_gateway":"hospitality_node_realtime",
      "print_agent":"hospitality_node_print"}'::jsonb) AS kazanchis_node;

SELECT set_config('app.outlet_id', :o_h2, false);

INSERT INTO edge.deployment_profile
    (tenant_id, outlet_id, environment_class, serving_mode, declared_by_user_id)
VALUES (:t_habesha::uuid, :o_h2::uuid, 'pilot', 'continuity_node', :u_habesha::uuid);

SELECT edge.register_node(
    :t_habesha::uuid, :o_h2::uuid, 'NODE-H2',
    '3333ed02-0000-4000-8000-0000000ed002'::uuid,
    'de505eed0000000000000000000000000000000000000000000000000000h202'::character(64),
    '3333ed12-0000-4000-8000-0000000ed012'::uuid,
    'http://sarbet.node.local:7101',
    'file:///etc/hospitality/sarbet/secrets',
    'de505eed0000000000000000000000000000000000000000000000000000anch'::character(64),
    'demonstration-host-profile-v1',
    :u_habesha::uuid,
    '{"local_api":"hospitality_node_api",
      "database":"hospitality_node_db",
      "sync_worker":"hospitality_node_sync",
      "realtime_gateway":"hospitality_node_realtime",
      "print_agent":"hospitality_node_print"}'::jsonb) AS sarbet_node;

-- ---------------------------------------------------------------------------
-- THE WORDING, FOR BOTH TENANTS AND ALL THREE LOCALES
-- ---------------------------------------------------------------------------
--
-- edge.say() RAISES rather than returning a blank, so a locale missing here is a screen
-- that stops rather than a screen that lies. That refusal is only worth having if the
-- rows are complete, so every phrase is written in all three locales together rather than
-- a locale at a time.

SELECT set_config('app.outlet_id', '', false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 (:t_habesha::uuid, 'restriction.external_payment_authority', 'en', 'Card payments cannot be authorised while the outlet is offline. Take cash, or use the card terminal and record the result.'),
 (:t_habesha::uuid, 'restriction.external_payment_authority', 'am', 'መሻጫው ከመስመር ውጭ በሆነበት ጊዜ የካርድ ክፍያ ማረጋገጥ አይቻል። ጥሬ ገንዘብ ይቀበሉ፣ ወይም የካርድ ተርሚናሉን ተጠቅመው ውጤቱን ይመዝግቡ።'),
 (:t_habesha::uuid, 'restriction.external_payment_authority', 'ar', 'لا يمكن اعتماد الدفع بالبطاقة أثناء انقطاع الاتصال. اقبل النقد، أو استخدم جهاز البطاقات وسجّل النتيجة.'),
 (:t_habesha::uuid, 'restriction.fiscal_authority', 'en', 'The fiscal document will be issued when the connection returns. The sale is complete and the receipt has printed.'),
 (:t_habesha::uuid, 'restriction.fiscal_authority', 'am', 'የግብር ሰነዱ ግንኙነቱ ሲመለስ ይወጣል። ሽያጮ ተጠናቅቁል።፤ ደረሰኞም ታትሞታል።'),
 (:t_habesha::uuid, 'restriction.fiscal_authority', 'ar', 'ستصدر الوثيقة الضريبية عند عودة الاتصال. البيع مكتمل والإيصال قد طُبع.'),
 (:t_habesha::uuid, 'restriction.external_delivery', 'en', 'This notice will be sent when the connection returns.'),
 (:t_habesha::uuid, 'restriction.external_delivery', 'am', 'ይህ መልእክት ግንኙነቱ ሲመለስ ይላካል።'),
 (:t_habesha::uuid, 'restriction.external_delivery', 'ar', 'سيُرسل هذا الإشعار عند عودة الاتصال.'),
 (:t_habesha::uuid, 'restriction.cloud_read', 'en', 'Reports are read from the cloud and are unavailable while the outlet is offline. Service is unaffected.'),
 (:t_habesha::uuid, 'restriction.cloud_read', 'am', 'ሪፖርቶች ከደመናው ስለሚነበቡ መሻጫው ከመስመር ውጭ ሲሆን አይገኙም። አገልግሎቱ ግን አልተቅረጠም።'),
 (:t_habesha::uuid, 'restriction.cloud_read', 'ar', 'تُقرأ التقارير من السحابة ولا تتوفر أثناء انقطاع الاتصال. الخدمة غير متأثرة.'),
 (:t_habesha::uuid, 'restriction.remote_configuration', 'en', 'Configuration is published from the cloud and cannot be changed here while the outlet is offline.'),
 (:t_habesha::uuid, 'restriction.remote_configuration', 'am', 'ማዋቀሪያው ከደመናው ስለሚታተም መሻጫው ከመስመር ውጭ በሆነበት ጊዜ እዚህ ሊቀየር አይችልም።'),
 (:t_habesha::uuid, 'restriction.remote_configuration', 'ar', 'يُنشر الإعداد من السحابة ولا يمكن تغييره هنا أثناء انقطاع الاتصال.'),
 (:t_habesha::uuid, 'sync_state.saved_locally', 'en', 'Saved here'),
 (:t_habesha::uuid, 'sync_state.saved_locally', 'am', 'እዚህ ተቀምጧል'),
 (:t_habesha::uuid, 'sync_state.saved_locally', 'ar', 'محفوظ هنا'),
 (:t_habesha::uuid, 'sync_state.queued', 'en', 'Waiting to be sent'),
 (:t_habesha::uuid, 'sync_state.queued', 'am', 'ለመላክ በመጠባበቅ ላይ'),
 (:t_habesha::uuid, 'sync_state.queued', 'ar', 'في انتظار الإرسال'),
 (:t_habesha::uuid, 'sync_state.synchronized', 'en', 'Sent and confirmed'),
 (:t_habesha::uuid, 'sync_state.synchronized', 'am', 'ተልኮ ተረጋግጧል'),
 (:t_habesha::uuid, 'sync_state.synchronized', 'ar', 'أُرسل وتم تأكيده'),
 (:t_habesha::uuid, 'sync_state.conflict', 'en', 'Needs a decision'),
 (:t_habesha::uuid, 'sync_state.conflict', 'am', 'ውሳኔ ይፈልጋል'),
 (:t_habesha::uuid, 'sync_state.conflict', 'ar', 'يحتاج إلى قرار'),
 (:t_habesha::uuid, 'sync_state.blocked', 'en', 'Stopped — tell a manager'),
 (:t_habesha::uuid, 'sync_state.blocked', 'am', 'ቀሞ።። — ለስራ አስኪያጅ ይንገሩ'),
 (:t_habesha::uuid, 'sync_state.blocked', 'ar', 'متوقف — أبلغ المدير');

SELECT set_config('app.tenant_id', :t_nile, false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 (:t_nile::uuid, 'restriction.external_payment_authority', 'en', 'Card payments cannot be authorised while the outlet is offline. Take cash, or use the card terminal and record the result.'),
 (:t_nile::uuid, 'restriction.external_payment_authority', 'am', 'መሻጫው ከመስመር ውጭ በሆነበት ጊዜ የካርድ ክፍያ ማረጋገጥ አይቻል። ጥሬ ገንዘብ ይቀበሉ፣ ወይም የካርድ ተርሚናሉን ተጠቅመው ውጤቱን ይመዝግቡ።'),
 (:t_nile::uuid, 'restriction.external_payment_authority', 'ar', 'لا يمكن اعتماد الدفع بالبطاقة أثناء انقطاع الاتصال. اقبل النقد، أو استخدم جهاز البطاقات وسجّل النتيجة.'),
 (:t_nile::uuid, 'restriction.fiscal_authority', 'en', 'The fiscal document will be issued when the connection returns. The sale is complete and the receipt has printed.'),
 (:t_nile::uuid, 'restriction.fiscal_authority', 'am', 'የግብር ሰነዱ ግንኙነቱ ሲመለስ ይወጣል። ሽያጮ ተጠናቅቁል።፤ ደረሰኞም ታትሞታል።'),
 (:t_nile::uuid, 'restriction.fiscal_authority', 'ar', 'ستصدر الوثيقة الضريبية عند عودة الاتصال. البيع مكتمل والإيصال قد طُبع.'),
 (:t_nile::uuid, 'restriction.external_delivery', 'en', 'This notice will be sent when the connection returns.'),
 (:t_nile::uuid, 'restriction.external_delivery', 'am', 'ይህ መልእክት ግንኙነቱ ሲመለስ ይላካል።'),
 (:t_nile::uuid, 'restriction.external_delivery', 'ar', 'سيُرسل هذا الإشعار عند عودة الاتصال.'),
 (:t_nile::uuid, 'restriction.cloud_read', 'en', 'Reports are read from the cloud and are unavailable while the outlet is offline. Service is unaffected.'),
 (:t_nile::uuid, 'restriction.cloud_read', 'am', 'ሪፖርቶች ከደመናው ስለሚነበቡ መሻጫው ከመስመር ውጭ ሲሆን አይገኙም። አገልግሎቱ ግን አልተቅረጠም።'),
 (:t_nile::uuid, 'restriction.cloud_read', 'ar', 'تُقرأ التقارير من السحابة ولا تتوفر أثناء انقطاع الاتصال. الخدمة غير متأثرة.'),
 (:t_nile::uuid, 'restriction.remote_configuration', 'en', 'Configuration is published from the cloud and cannot be changed here while the outlet is offline.'),
 (:t_nile::uuid, 'restriction.remote_configuration', 'am', 'ማዋቀሪያው ከደመናው ስለሚታተም መሻጫው ከመስመር ውጭ በሆነበት ጊዜ እዚህ ሊቀየር አይችልም።'),
 (:t_nile::uuid, 'restriction.remote_configuration', 'ar', 'يُنشر الإعداد من السحابة ولا يمكن تغييره هنا أثناء انقطاع الاتصال.'),
 (:t_nile::uuid, 'sync_state.saved_locally', 'en', 'Saved here'),
 (:t_nile::uuid, 'sync_state.saved_locally', 'am', 'እዚህ ተቀምጧል'),
 (:t_nile::uuid, 'sync_state.saved_locally', 'ar', 'محفوظ هنا'),
 (:t_nile::uuid, 'sync_state.queued', 'en', 'Waiting to be sent'),
 (:t_nile::uuid, 'sync_state.queued', 'am', 'ለመላክ በመጠባበቅ ላይ'),
 (:t_nile::uuid, 'sync_state.queued', 'ar', 'في انتظار الإرسال'),
 (:t_nile::uuid, 'sync_state.synchronized', 'en', 'Sent and confirmed'),
 (:t_nile::uuid, 'sync_state.synchronized', 'am', 'ተልኮ ተረጋግጧል'),
 (:t_nile::uuid, 'sync_state.synchronized', 'ar', 'أُرسل وتم تأكيده'),
 (:t_nile::uuid, 'sync_state.conflict', 'en', 'Needs a decision'),
 (:t_nile::uuid, 'sync_state.conflict', 'am', 'ውሳኔ ይፈልጋል'),
 (:t_nile::uuid, 'sync_state.conflict', 'ar', 'يحتاج إلى قرار'),
 (:t_nile::uuid, 'sync_state.blocked', 'en', 'Stopped — tell a manager'),
 (:t_nile::uuid, 'sync_state.blocked', 'am', 'ቀሞ።። — ለስራ አስኪያጅ ይንገሩ'),
 (:t_nile::uuid, 'sync_state.blocked', 'ar', 'متوقف — أبلغ المدير');

SELECT set_config('app.tenant_id', '', false);
