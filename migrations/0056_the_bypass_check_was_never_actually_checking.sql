-- 0056: the bypass check was never actually checking
--
-- 0054 added edge.assert_resolution_guidance_is_safe(), which reads FR-EDG-028's four
-- phrases in all three locales and refuses any that tells somebody to click through a
-- certificate warning. It was written like this:
--
--     IF v_text ~* '(proceed anyway|continue anyway|advanced|accept the risk'
--                || '|ignore the warning|not secure|unsafe|bypass)' THEN
--
-- and the very first call raised `invalid regular expression: parentheses () not
-- balanced`. THE CONCATENATION NEVER HAPPENED. In PostgreSQL `~*` and `||` are both in the
-- "any other operator" precedence class, so they associate left to right and that line
-- parses as
--
--     (v_text ~* '(proceed anyway|continue anyway|advanced|accept the risk') || '...'
--
-- — the pattern is the first half alone, with an opening parenthesis and no closing one.
--
-- IT FAILED LOUDLY, WHICH IS THE ONLY REASON THIS IS A SMALL NOTE. Either branch of the
-- mistake raises: an unbalanced pattern is a regex error, and a balanced one would have
-- made the IF argument a text value instead of a boolean. Nothing silently passed and no
-- wording was ever wrongly approved.
--
-- WHAT IT DOES SAY IS THAT THE FUNCTION HAD NEVER BEEN RUN. 0054 applied cleanly, because
-- applying a function only parses its body — PL/pgSQL resolves expressions at execution.
-- A migration that defines something nothing calls is a migration whose claim is untested,
-- and the gap between "applied" and "exercised" is exactly the width of this bug. The M5b
-- suite calls it, which is what closes the gap rather than this fix.
--
-- The parentheses go round the whole concatenation. The pattern is unchanged.

CREATE OR REPLACE FUNCTION edge.assert_resolution_guidance_is_safe(p_tenant_id uuid)
RETURNS integer
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'edge', 'menu', 'public'
AS $$
DECLARE
    v_required text[] := ARRAY['resolution.no_local_certificate',
                               'resolution.cached_answer_wait',
                               'resolution.encrypted_dns_blocks_local',
                               'resolution.join_outlet_wifi'];
    -- HELD AS A VALUE RATHER THAN BUILT INSIDE THE IF. That is the actual repair: the
    -- pattern is now one literal that a reader can see the shape of, and there is no
    -- operator precedence involved in producing it.
    v_bypass_words text :=
        '(proceed anyway|continue anyway|accept the risk|ignore the warning'
        '|not secure|unsafe|bypass|advanced)';
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
            IF v_text ~* v_bypass_words THEN
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

-- AND A PROOF THAT IT NOW CATCHES SOMETHING, run here rather than promised. A function
-- whose refusal has never fired is a function with the same problem 0054's had.
DO $$
DECLARE v_ok boolean;
BEGIN
    SELECT 'Tap Advanced, then Proceed anyway to continue' ~*
           '(proceed anyway|continue anyway|accept the risk|ignore the warning'
           '|not secure|unsafe|bypass|advanced)'
      INTO v_ok;
    IF NOT v_ok THEN
        RAISE EXCEPTION
            'BYPASS_PATTERN_MATCHES_NOTHING: the pattern does not match the sentence it '
            'exists to refuse, so the check would pass anything'
            USING ERRCODE = 'HS500';
    END IF;

    SELECT 'Connect to our Wi-Fi to order from your phone.' ~*
           '(proceed anyway|continue anyway|accept the risk|ignore the warning'
           '|not secure|unsafe|bypass|advanced)'
      INTO v_ok;
    IF v_ok THEN
        RAISE EXCEPTION
            'BYPASS_PATTERN_MATCHES_EVERYTHING: the pattern refuses an ordinary '
            'instruction, so no wording could ever be admitted'
            USING ERRCODE = 'HS500';
    END IF;
END;
$$;
