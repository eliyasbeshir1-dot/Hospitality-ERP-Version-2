/**
 * Drives the STATION surface in a real browser and prints what it MEASURED, as JSON.
 *
 * Decides nothing, exactly as M2-C's probe decides nothing. It renders, reads computed
 * styles and bounding boxes, and hands the numbers to verify_m3b.py where the assertions
 * live. A probe that decided what counted as a pass could be adjusted until everything
 * passed, which is the failure this separation exists to prevent.
 *
 * The one thing this probe does that M2-C's did not: it renders the surface TWICE — once
 * normally and once with every colour in the document flattened to a single value. The
 * second render is the decisive measurement for FR-FUL-008. If an allergy is emphasised
 * by colour, the flattened render is where that stops being visible; if it is emphasised
 * by weight, size, a glyph and words, the flattened render is indistinguishable from the
 * first in every respect that matters.
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';

// THE PAYLOAD ARRIVES AS A FILE, NOT AS AN ARGUMENT.
//
// It used to be one `json.dumps(payload)` on the command line, and the payload carries
// the station's WHOLE ticket queue — so its size is a function of how much the database
// has accumulated, not of anything this probe or that surface does. Under the reordered
// sweep the suites run against a database an earlier full run had already filled (178
// tickets, 154 of them queued, when this was measured), the argument crossed Windows'
// 32767-character command-line limit, and python died with
// `FileNotFoundError: [WinError 206] The filename or extension is too long` before the
// suite printed any verdict at all. Linux's ~2MB ARG_MAX hid it, and the reorder sweep
// only runs on Linux, so the one platform that fails is the one never asked the question.
//
// A file has no such ceiling and no platform difference.
const [, , baseUrl, payloadPath] = process.argv;
const payload = JSON.parse(readFileSync(payloadPath, 'utf8'));

const out = { normal: null, flattened: null, errors: [] };

/**
 * Flatten every colour in the document to one value.
 *
 * Text, background, border, outline, fill and stroke all become the same ink — a page
 * where colour carries NO information at all. That is the strongest form of the "not
 * colour alone" test: not a simulation of one kind of colour blindness, but the removal
 * of colour as a channel entirely.
 *
 * Appended to the surface's OWN stylesheet by intercepting the response, rather than
 * injected with addStyleTag. The first attempt injected it and Chromium refused: the
 * station document is served with style-src 'self', so an inline stylesheet is blocked.
 * That refusal is the CSP working, and routing the real stylesheet is both the way round
 * it and the more honest test — what the browser applies is the page's own CSS, from the
 * page's own origin, with the colours taken out.
 */
const FLATTEN_CSS = `
  *, *::before, *::after {
    color: #000000 !important;
    background-color: #ffffff !important;
    background-image: none !important;
    border-color: #000000 !important;
    outline-color: #000000 !important;
    text-decoration-color: #000000 !important;
    fill: #000000 !important;
    stroke: #000000 !important;
  }
`;

/** Everything the suite asserts on, read out of the browser's own layout. */
async function measure(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return box.width > 0 && box.height > 0
        && style.visibility !== 'hidden' && style.display !== 'none'
        && Number(style.opacity) > 0;
    };
    const describe = (el) => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return {
        text: (el.textContent || '').trim(),
        fontWeight: Number(style.fontWeight),
        fontSizePx: parseFloat(style.fontSize),
        textTransform: style.textTransform,
        borderTopWidthPx: parseFloat(style.borderTopWidth),
        color: style.color,
        backgroundColor: style.backgroundColor,
        top: box.top,
        width: box.width,
        height: box.height,
        visible: visible(el),
      };
    };

    const allergies = Array.from(document.querySelectorAll('.allergy')).map(describe);
    // The comparison text: an ordinary ticket line in the same card. Prominence is
    // measured RELATIVELY against this, never against an absolute threshold a later
    // style change could satisfy without meaning anything.
    const ordinary = Array.from(document.querySelectorAll('.line-name, .progress, .bucket'))
      .map(describe);

    const glyphs = Array.from(document.querySelectorAll('.allergy-glyph')).map(describe);
    const buckets = Array.from(document.querySelectorAll('[data-bucket-group]'))
      .map((el) => el.getAttribute('data-bucket-group'));
    const blocks = Array.from(document.querySelectorAll('.block')).map(describe);
    const priorities = Array.from(document.querySelectorAll('.priority')).map(describe);
    const attributions = Array.from(document.querySelectorAll('.priority-attribution'))
      .map(describe);
    const readyToServe = Array.from(document.querySelectorAll('.ready-to-serve'))
      .map(describe);

    // Where the allergy sits relative to the first dish on the same ticket. FR-SAF-004
    // says "prominently", and a warning below the food is not prominent.
    const detail = document.querySelector('[data-ticket-detail]');
    let allergyAboveLines = null;
    if (detail) {
      const firstAllergy = detail.querySelector('.allergy');
      const firstLine = detail.querySelector('.line');
      if (firstAllergy && firstLine) {
        allergyAboveLines =
          firstAllergy.getBoundingClientRect().top < firstLine.getBoundingClientRect().top;
      }
    }

    return {
      allergies, ordinary, glyphs, buckets, blocks, priorities, attributions,
      readyToServe, allergyAboveLines,
      documentText: (document.body.textContent || '').replace(/\s+/g, ' ').trim(),
      distinctColours: Array.from(new Set(
        Array.from(document.querySelectorAll('*')).map((el) => getComputedStyle(el).color))),
    };
  });
}

async function renderOnce(context, flatten) {
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));
  if (flatten) {
    await page.route('**/app/station.css', async (route) => {
      const response = await route.fetch();
      route.fulfill({
        response,
        body: (await response.text()) + FLATTEN_CSS,
        headers: { ...response.headers(), 'content-type': 'text/css; charset=utf-8' },
      });
    });
  }
  await page.goto(`${baseUrl}/station`, { waitUntil: 'domcontentloaded' });
  // The surface is drawn from data the probe supplies rather than fetched, so a
  // measurement is never waiting on a network round trip it did not intend to measure.
  await page.waitForFunction(() => Boolean(window.stationSurface));
  await page.evaluate((data) => window.stationSurface.renderAll(data), payload);
  await page.waitForTimeout(60);
  const measured = await measure(page);
  await page.close();
  return measured;
}

let browser;
try {
  browser = await chromium.launch({ args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  out.normal = await renderOnce(context, false);
  out.flattened = await renderOnce(context, true);
  await context.close();
} catch (error) {
  out.errors.push(String(error));
} finally {
  if (browser) await browser.close();
  process.stdout.write(JSON.stringify(out, null, 2));
}
