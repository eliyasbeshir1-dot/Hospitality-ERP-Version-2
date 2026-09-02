/**
 * Drives the CUSTOMER surface to the bill, in a real browser, and prints what it
 * MEASURED as JSON.
 *
 * Decides nothing, exactly as M2-C's, M3-B's, M3-C's and M3-D's probes decide nothing. It
 * renders, reads the DOM and the boxes the layout engine actually produced, and hands the
 * numbers to verify_m4a.py where the assertions live.
 *
 * TWO MEASUREMENTS ARE THE POINT OF THIS FILE.
 *
 * FR-BIL-007 puts the optional Tip box after or beside the bill summary and never inside
 * it. "Inside" has two meanings and both are measured: DOM containment, which a developer
 * controls, and the rectangle the browser drew, which a stylesheet can undo without
 * touching the markup. A tip box positioned on top of the summary is inside it as far as
 * a guest is concerned, whatever the document says.
 *
 * NC-M4-001 is the other. No tip is selected by default, so every suggestion is read back
 * with its aria-pressed, its checked state if it has one, and its class list — because a
 * preselection can be expressed as any of the three and asserting on only the first would
 * be an assertion that a plausible defect walks past.
 */
import { chromium } from 'playwright';

const [, , baseUrl, payloadJson] = process.argv;
const payload = JSON.parse(payloadJson);

const out = { locales: {}, errors: [], probeFailed: null };

async function measure(page) {
  return page.evaluate(() => {
    const rect = (node) => {
      if (!node) return null;
      const r = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        top: r.top, left: r.left, right: r.right, bottom: r.bottom,
        width: r.width, height: r.height,
        visible: r.width > 0 && r.height > 0 && style.visibility !== 'hidden'
                 && style.display !== 'none',
      };
    };

    const summary = document.getElementById('bill-summary');
    const section = document.getElementById('bill-section');
    const tipBox = document.getElementById('tip-box');

    const lines = [...document.querySelectorAll('#bill-lines tr.bill-line')].map((n) => ({
      kind: n.dataset.kind ?? null,
      label: (n.querySelector('.bill-label')?.textContent || '').trim(),
      amount: (n.querySelector('.bill-amount')?.textContent || '').trim(),
    }));

    const options = [...document.querySelectorAll('.tip-option')].map((n) => ({
      text: (n.textContent || '').trim(),
      ariaPressed: n.getAttribute('aria-pressed'),
      // A <button> has no checked property; an <input type="radio"> masquerading as a
      // suggestion would. Read both rather than assuming which element was used.
      checked: n.checked === true || n.getAttribute('checked') !== null,
      classes: [...n.classList],
      defaultAttribute: n.getAttribute('data-default') ?? n.getAttribute('data-selected'),
      amountMinor: n.dataset ? (n.dataset.amountMinor ?? null) : null,
      percentage: n.dataset ? (n.dataset.percentage ?? null) : null,
      box: rect(n),
    }));

    return {
      dir: document.documentElement.getAttribute('dir'),
      lang: document.documentElement.getAttribute('lang'),
      billHeading: (document.getElementById('bill-heading')?.textContent || '').trim(),
      tipHeading: (document.getElementById('tip-heading')?.textContent || '').trim(),
      tipHint: (document.getElementById('tip-hint')?.textContent || '').trim(),
      totalLabel: (document.getElementById('bill-total-label')?.textContent || '').trim(),
      total: (document.getElementById('bill-total')?.textContent || '').trim(),
      calculationVersion: summary?.dataset?.calculationVersion ?? null,
      lines,
      options,
      // CONTAINMENT, both directions, from the browser's own answer rather than from a
      // selector this file composed.
      tipInsideSummary: !!(summary && tipBox && summary.contains(tipBox)),
      tipInsideSection: !!(section && tipBox && section.contains(tipBox)),
      summaryBox: rect(summary),
      sectionBox: rect(section),
      tipBox: rect(tipBox),
      // Every word the two blocks say, so a suite can prove no untranslated string is
      // sitting beside a translated one.
      billWords: (section?.textContent || '').trim(),
      tipWords: (tipBox?.textContent || '').trim(),
    };
  });
}

try {
  const browser = await chromium.launch();
  // ONE CASE PER LANGUAGE, each its own table and its own bill. A bill is translated by
  // the locale it was ISSUED in rather than by the locale the reader has chosen, so
  // reading one bill three ways would show the same English three times and prove
  // nothing — which is exactly what the first version of this did.
  for (const { locale, code } of payload.cases) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, locale,
    });
    const page = await context.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });

    await page.goto(
      `${baseUrl}/?t=${payload.tenant}&o=${payload.outlet}&c=${encodeURIComponent(code)}`,
      { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.surface === 'object');
    await page.evaluate(() => window.surface.ready());
    await page.evaluate((l) => window.surface.chooseLocale(l), locale);
    // The bill is loaded last in the surface's own start(), and chooseLocale() redraws
    // rather than refetches, so this asks for it explicitly after the language is set.
    await page.evaluate(() => window.surface.loadBill());
    await page.waitForFunction(
      () => document.querySelectorAll('#bill-lines tr.bill-line').length > 0,
      null, { timeout: 20000 });

    out.locales[locale] = await measure(page);

    // TAPPING one suggestion, in one language only, because FR-BIL-015 is about a payer
    // CHOOSING and a measurement of the untouched page cannot show that choosing works.
    if (payload.tap && locale === payload.tap) {
      const first = page.locator('.tip-option').first();
      if (await first.count() > 0) {
        await first.click();
        await page.waitForFunction(
          () => !document.getElementById('tip-outcome')?.hidden, null, { timeout: 15000 });
        out.afterTap = await measure(page);
        out.afterTap.outcome =
          await page.evaluate(() =>
            (document.getElementById('tip-outcome')?.textContent || '').trim());
      }
    }
    await context.close();
  }
  await browser.close();
} catch (error) {
  // A probe that could not run says so. A caller comparing counts must not be able to
  // read "the browser never started" as "nothing was preselected".
  out.probeFailed = String(error).slice(0, 600);
}

process.stdout.write(JSON.stringify(out));
