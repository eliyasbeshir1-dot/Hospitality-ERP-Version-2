-- 0014_the_room_can_be_told.provision.sql — the three connectivity phrases
--
-- 0047 gives edge.plain_language a third namespace and edge.connectivity_banner() a
-- reason to read it. This writes the nine rows — three states, three locales — for each
-- tenant that has any wording at all.
--
-- IT IS A SEPARATE SEED BECAUSE 0012 IS APPLIED. Seeds are checksum-locked: a seed that
-- has run has run, and editing it is refused on every database that ran it. The rows
-- could not have gone in 0012 anyway, because the CHECK that admits them did not exist
-- until 0047.
--
-- edge.say() RAISES on a missing phrase, so a banner with no wording is a screen that
-- stops rather than a screen that lies. That is only useful if the set is complete, which
-- is why all nine go in together rather than English first and the rest later.

\set ON_ERROR_STOP on

\set t_habesha  '''33333333-3333-3333-3333-333333333333'''
\set t_nile     '''44444444-4444-4444-4444-444444444444'''

SELECT set_config('app.tenant_id', :t_habesha, false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 (:t_habesha::uuid, 'connectivity.cloud_connected', 'en', 'Connected'),
 (:t_habesha::uuid, 'connectivity.cloud_connected', 'am', 'ተገናኝቷል'),
 (:t_habesha::uuid, 'connectivity.cloud_connected', 'ar', 'متّصل'),
 (:t_habesha::uuid, 'connectivity.local_continuity', 'en', 'Working offline — service continues'),
 (:t_habesha::uuid, 'connectivity.local_continuity', 'am', 'ክመስመር ውጭ በስራ ላይ — አገልግሎቱ ይቀጥላል'),
 (:t_habesha::uuid, 'connectivity.local_continuity', 'ar', 'يعمل دون اتصال — الخدمة مستمرة'),
 (:t_habesha::uuid, 'connectivity.reconciling', 'en', 'Catching up — something needs a decision'),
 (:t_habesha::uuid, 'connectivity.reconciling', 'am', 'በመያካት ላይ — ውሳኔ የሚፈልግ ነገር አለ'),
 (:t_habesha::uuid, 'connectivity.reconciling', 'ar', 'جارٍ اللحاق — هناك ما يحتاج إلى قرار');

SELECT set_config('app.tenant_id', :t_nile, false);

INSERT INTO edge.plain_language (tenant_id, phrase_code, locale, text) VALUES
 (:t_nile::uuid, 'connectivity.cloud_connected', 'en', 'Connected'),
 (:t_nile::uuid, 'connectivity.cloud_connected', 'am', 'ተገናኝቷል'),
 (:t_nile::uuid, 'connectivity.cloud_connected', 'ar', 'متّصل'),
 (:t_nile::uuid, 'connectivity.local_continuity', 'en', 'Working offline — service continues'),
 (:t_nile::uuid, 'connectivity.local_continuity', 'am', 'ክመስመር ውጭ በስራ ላይ — አገልግሎቱ ይቀጥላል'),
 (:t_nile::uuid, 'connectivity.local_continuity', 'ar', 'يعمل دون اتصال — الخدمة مستمرة'),
 (:t_nile::uuid, 'connectivity.reconciling', 'en', 'Catching up — something needs a decision'),
 (:t_nile::uuid, 'connectivity.reconciling', 'am', 'በመያካት ላይ — ውሳኔ የሚፈልግ ነገር አለ'),
 (:t_nile::uuid, 'connectivity.reconciling', 'ar', 'جارٍ اللحاق — هناك ما يحتاج إلى قرار');

SELECT set_config('app.tenant_id', '', false);
