/**
 * Drives the CUSTOMER surface's service panel in a real browser and prints what it
 * MEASURED, as JSON.
 *
 * Decides nothing, exactly as M2-C's and M3-B's probes decide nothing. It renders, reads
 * computed styles and text, and hands the numbers to verify_m3c.py where the assertions
 * live.
 *
 * The payload comes from the REAL API — the suite fetches it over HTTP with a real guest
 * credential and passes it in — so what is rendered is what a guest's device would have
 * received, not a shape this file invented.
 */
import { chromium } from 'playwright';

const [, , baseUrl, tenantId, outletId, code, payloadJson, locale] = process.argv;
const payload = JSON.parse(payloadJson);

const out = { rendered: null, errors: [] };

async function measure(page) {
  return page.evaluate(() => {
    const visible = (el) => {
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return box.width > 0 && box.height > 0
        && style.visibility !== 'hidden' && style.display !== 'none'
        && Number(style.opacity) > 0;
    };
    const describe = (el) => ({
      text: (el.textContent || '').trim(),
      fontWeight: Number(getComputedStyle(el).fontWeight),
      color: getComputedStyle(el).color,
      visible: visible(el),
    });

    const root = document.documentElement;
    return {
      dir: root.getAttribute('dir'),
      lang: root.getAttribute('lang'),
      // The ask buttons and the ask-again buttons are different affordances and are
      // counted separately: selecting every button in the list made a type with an open
      // request look like two types.
      types: Array.from(document.querySelectorAll('#service-types .service-ask'))
        .map((el) => ({ ...describe(el),
                        requestType: el.getAttribute('data-request-type') })),
      askAgain: Array.from(document.querySelectorAll('#service-types .ask-again'))
        .map((el) => ({ ...describe(el),
                        requestType: el.getAttribute('data-request-type') })),
      statuses: Array.from(document.querySelectorAll('#service-status li'))
        .map((el) => ({ ...describe(el),
                        status: el.getAttribute('data-status'),
                        label: (el.querySelector('.request-label')?.textContent || '').trim(),
                        word: (el.querySelector('.status-word')?.textContent || '').trim(),
                        repeat: (el.querySelector('.repeat')?.textContent || '').trim(),
                        handledBy: (el.querySelector('.handled-by')?.textContent || '').trim() })),
      timeline: Array.from(document.querySelectorAll('#service-timeline li'))
        .map((el) => ({ ...describe(el), source: el.getAttribute('data-source') })),
      collapsedNote: (() => {
        const el = document.getElementById('service-collapsed');
        return el && !el.hidden ? describe(el) : null;
      })(),
      headings: Array.from(
        document.querySelectorAll('#service-heading, #service-status-heading, #service-timeline-heading'))
        .map(describe),
      // Everything a guest can read in the service panel, as one string. The language
      // assertions are made against this rather than against a list of selectors, so a
      // string added to the panel later is covered without anybody remembering to add it.
      panelText: (() => {
        const panel = document.querySelector('.service');
        return panel ? (panel.textContent || '').replace(/\s+/g, ' ').trim() : '';
      })(),
      documentText: (document.body.textContent || '').replace(/\s+/g, ' ').trim(),
    };
  });
}

let browser;
try {
  browser = await chromium.launch({ args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 420, height: 900 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));

  await page.goto(`${baseUrl}/?t=${tenantId}&o=${outletId}&c=${code}`,
                  { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(window.surface));
  // Wait for the surface's OWN load before drawing into it. M3-D wired the service panel
  // to fetch its own data, which it never did at M3-C, so a payload drawn before that
  // load finished was overwritten by it a moment later — and the measurement then read
  // an empty panel and reported it as a missing status word.
  await page.evaluate(() => window.surface.ready());
  if (locale) {
    await page.evaluate(async (l) => { await window.surface.chooseLocale(l); }, locale);
  }
  await page.evaluate((data) => window.surface.renderService(data), payload);
  await page.waitForTimeout(60);
  out.rendered = await measure(page);
  await page.close();
  await context.close();
} catch (error) {
  out.errors.push(String(error));
} finally {
  if (browser) await browser.close();
  process.stdout.write(JSON.stringify(out, null, 2));
}
