/**
 * Drives the customer surface in a real browser and prints what it MEASURED, as JSON.
 *
 * This file decides nothing. It renders, interacts, reads computed styles, bounding
 * boxes, the accessibility tree and axe-core's findings, and hands the numbers to
 * verify_m2c.py, which is where the assertions live. Keeping the judgement out of the
 * probe is the same rule the SQL suites follow: a probe that decides what counts as a
 * pass can be quietly adjusted until everything passes.
 *
 * Every field in the output comes from Chromium's own layout — getComputedStyle,
 * getBoundingClientRect, the rendered accessibility tree — not from the HTML the server
 * sent. That distinction is the whole point of this slice: a `dir="rtl"` attribute in the
 * markup says what was asked for, and only the browser can say what happened.
 */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const AXE_SOURCE = readFileSync(require.resolve('axe-core'), 'utf8');

const [, , baseUrl, tenantId, outletId, code, cpuThrottle, downloadKbps, latencyMs, mode]
  = process.argv;

// 'full' measures everything and is what the suite's evidence comes from. 'quick' is for
// the negative controls, which call this three times each: it renders the same page the
// same way and skips the passes no control reads — axe, the keyboard walks and the zoom
// — so a control costs seconds rather than a minute. Nothing a control asserts on is
// measured differently in the two modes.
const QUICK = mode === 'quick';

/**
 * A mid-range Android phone on Ethiopian mobile data, emulated through the DevTools
 * protocol. Emulated, not a handset: stated plainly here and in the report, because a
 * throttled desktop is a reasonable proxy for a slow phone and is not the same thing.
 */
const DEVICE = {
  name: 'mid-range Android phone, emulated',
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  cpuThrottlingRate: Number(cpuThrottle ?? 4),
  downloadKbps: Number(downloadKbps ?? 1600),
  latencyMs: Number(latencyMs ?? 300),
};

const out = { device: DEVICE, locales: {}, states: {}, axe: {}, journeys: {}, errors: [] };

function entryUrl() {
  return `${baseUrl}/?t=${tenantId}&o=${outletId}&c=${code}`;
}

/** Wait until the menu has rendered at least one item, or give up saying so. */
async function waitForMenu(page) {
  try {
    await page.waitForFunction(() => document.querySelectorAll('.item').length > 0,
      null, { timeout: 15000 });
    return true;
  } catch {
    return false;
  }
}

async function measureLocale(page, locale) {
  await page.evaluate((wanted) => window.surface.chooseLocale(wanted), locale);
  await waitForMenu(page);

  return page.evaluate((wanted) => {
    const root = document.documentElement;
    const computed = getComputedStyle(root);

    // ---- What the browser actually laid out, not what the markup asked for ----
    const measurement = {
      lang: root.lang,
      dirAttribute: root.dir,
      computedDirection: computed.direction,
      title: document.title,
    };

    // ---- Clipping: an element whose content is wider or taller than its box ----
    // scrollWidth against clientWidth is the browser's own answer to "did this fit",
    // computed after layout with the real Amharic and Arabic strings in place.
    const clipped = [];
    for (const node of document.querySelectorAll(
      '.item-name, .allergen-text, .locale, .status-text, .cart-line, .empty, h1, h2')) {
      const overflowsX = node.scrollWidth - node.clientWidth > 1;
      const overflowsY = node.scrollHeight - node.clientHeight > 1;
      if (overflowsX || overflowsY) {
        clipped.push({
          selector: node.className || node.tagName,
          text: (node.textContent || '').slice(0, 60),
          scrollWidth: node.scrollWidth, clientWidth: node.clientWidth,
          scrollHeight: node.scrollHeight, clientHeight: node.clientHeight,
        });
      }
    }
    measurement.clipped = clipped;

    // ---- Does anything overflow the viewport horizontally? ----
    measurement.documentScrollWidth = document.documentElement.scrollWidth;
    measurement.viewportWidth = document.documentElement.clientWidth;

    // ---- Allergens: is any icon drawn without words beside it? ----
    // Read from the rendered DOM, so a glyph inserted by CSS content or by a later
    // script is still counted.
    const allergens = [];
    for (const row of document.querySelectorAll('.allergen')) {
      const glyph = row.querySelector('.allergen-glyph');
      const text = row.querySelector('.allergen-text');
      const textContent = (text?.textContent || '').trim();
      const glyphBox = glyph ? glyph.getBoundingClientRect() : null;
      const textBox = text ? text.getBoundingClientRect() : null;
      allergens.push({
        kitchenCode: row.dataset.kitchenCode || null,
        hasGlyphElement: Boolean(glyph),
        glyphVisible: Boolean(glyphBox && glyphBox.width > 0 && glyphBox.height > 0),
        textLength: textContent.length,
        textVisible: Boolean(textBox && textBox.width > 0 && textBox.height > 0),
        text: textContent.slice(0, 80),
      });
    }
    measurement.allergens = allergens;

    // ---- Prices: rendered reading order of the run ----
    // In an RTL paragraph the bidirectional algorithm can put the currency code on the
    // other side of the digits. Reading the first and last glyph positions from their
    // client rects is the only way to know which way round it actually came out.
    const prices = [];
    for (const price of document.querySelectorAll('.item-price')) {
      const range = document.createRange();
      const node = price.firstChild;
      const text = price.textContent || '';
      let firstX = null; let lastX = null;
      if (node && text.length > 0) {
        range.setStart(node, 0); range.setEnd(node, 1);
        firstX = range.getBoundingClientRect().left;
        range.setStart(node, text.length - 1); range.setEnd(node, text.length);
        lastX = range.getBoundingClientRect().left;
      }
      prices.push({
        text,
        computedDirection: getComputedStyle(price).direction,
        unicodeBidi: getComputedStyle(price).unicodeBidi,
        firstGlyphX: firstX, lastGlyphX: lastX,
        readsLeftToRight: firstX !== null && lastX !== null ? lastX > firstX : null,
      });
    }
    measurement.prices = prices;

    // ---- Which side is the layout on? ----
    // Two elements that logical properties should mirror. Their measured x positions are
    // the evidence that dir="rtl" reached layout rather than only the attribute.
    const skip = document.querySelector('.skip-link');
    const firstLocale = document.querySelector('.locale');
    measurement.skipLinkLeft = skip ? skip.getBoundingClientRect().left : null;
    measurement.localeLeft = firstLocale ? firstLocale.getBoundingClientRect().left : null;
    measurement.bodyWidth = document.body.getBoundingClientRect().width;

    // ---- Completeness: any surface string still showing English? ----
    measurement.missingStrings = window.surface.missingStrings(wanted);
    const chrome = [];
    for (const node of document.querySelectorAll('[data-i18n]')) {
      chrome.push({ key: node.dataset.i18n, text: (node.textContent || '').trim() });
    }
    measurement.chrome = chrome;

    measurement.itemCount = document.querySelectorAll('.item').length;
    measurement.itemNames = [...document.querySelectorAll('.item-name')]
      .map((n) => (n.textContent || '').trim());
    return measurement;
  }, locale);
}

/** Colour is not the only difference: read each state as rendered. */
async function measureStates(page) {
  return page.evaluate(() => {
    const seen = {};
    for (const state of window.surface.states) {
      window.surface.renderAs(state);
      const glyph = document.getElementById('status-glyph');
      const text = document.getElementById('status-text');
      const time = document.getElementById('status-time');
      const style = getComputedStyle(document.getElementById('status'));
      seen[state] = {
        glyph: (glyph.textContent || '').trim(),
        text: (text.textContent || '').trim(),
        time: (time.textContent || '').trim(),
        dateTime: time.getAttribute('datetime'),
        colour: style.color,
        backgroundColor: style.backgroundColor,
        // Measured, so an empty span that occupies no space is not counted as visible.
        glyphVisible: glyph.getBoundingClientRect().width > 0,
        textVisible: text.getBoundingClientRect().width > 0,
      };
    }
    return seen;
  });
}

/** Walk every declared transition and record which the surface accepted. */
async function measureTransitions(page) {
  return page.evaluate(() => {
    const results = [];
    const transitions = window.surface.transitions;
    for (const from of Object.keys(transitions)) {
      for (const to of transitions[from]) {
        // renderAs() to get INTO the starting state, setState() to test the edge.
        // Positioning with setState() would itself have to be a legal transition, so the
        // walk could only reach the states already reachable — which is the thing under
        // test, not a way to set it up.
        window.surface.renderAs(from);
        let accepted = true; let error = null;
        try { window.surface.setState(to); } catch (e) { accepted = false; error = String(e.message || e); }
        results.push({ from, to, declared: true, accepted, error });
      }
      // One edge that is NOT declared, so the table is shown to refuse something rather
      // than to permit everything.
      const undeclared = window.surface.states.find(
        (s) => s !== from && !transitions[from].includes(s));
      if (undeclared) {
        window.surface.renderAs(from);
        let refused = false; let message = null;
        try { window.surface.setState(undeclared); } catch (e) { refused = true; message = String(e.message || e); }
        results.push({ from, to: undeclared, declared: false, refused, error: message });
      }
    }
    return results;
  });
}

/** Keyboard order, read from the browser's own focus behaviour. */
async function measureKeyboard(page) {
  // Blur whatever holds focus and scroll to the top before walking. Without this the
  // walk starts wherever the last click left focus, and the first thing it reports is
  // the button that was clicked rather than the first thing in the tab order — which
  // reads exactly like a missing skip link.
  // Anchor sequential focus navigation at the top of the document before walking.
  //
  // document.body.focus() alone does nothing — body is not focusable — so after an
  // earlier click Chromium resumes tabbing from that button, and the walk reported the
  // add buttons as the first things in the tab order. Giving body tabindex="-1" and
  // focusing it makes it the anchor, so the next Tab genuinely goes to the first
  // focusable element in the document.
  await page.evaluate(() => {
    const active = document.activeElement;
    if (active instanceof HTMLElement) active.blur();
    document.body.tabIndex = -1;
    document.body.focus();
    window.scrollTo(0, 0);
  });
  const order = [];
  for (let i = 0; i < 12; i += 1) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const box = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        tag: el.tagName.toLowerCase(),
        className: el.className || null,
        text: (el.textContent || '').trim().slice(0, 40),
        label: el.getAttribute('aria-label'),
        x: box.left, y: box.top, width: box.width, height: box.height,
        outlineWidth: style.outlineWidth, outlineStyle: style.outlineStyle,
      };
    });
    if (info) order.push(info);
  }
  return order;
}

let browser;

async function main() {
  browser = await chromium.launch({ args: ['--no-sandbox'] });
  const context = await browser.newContext({
    viewport: DEVICE.viewport,
    deviceScaleFactor: DEVICE.deviceScaleFactor,
    isMobile: DEVICE.isMobile,
    hasTouch: DEVICE.hasTouch,
    locale: 'en-GB',
  });
  const page = await context.newPage();
  page.on('pageerror', (error) => out.errors.push(String(error)));
  page.on('console', (message) => {
    if (message.type() === 'error') out.errors.push(message.text());
  });

  // ---- Throttled first load, for the performance budget ----
  const session = await context.newCDPSession(page);
  await session.send('Network.enable');
  await session.send('Network.emulateNetworkConditions', {
    offline: false,
    latency: DEVICE.latencyMs,
    downloadThroughput: (DEVICE.downloadKbps * 1024) / 8,
    uploadThroughput: (DEVICE.downloadKbps * 1024) / 16,
  });
  await session.send('Emulation.setCPUThrottlingRate', { rate: DEVICE.cpuThrottlingRate });

  const startedAt = Date.now();
  await page.goto(entryUrl(), { waitUntil: 'domcontentloaded' });
  const menuArrived = await waitForMenu(page);
  const loadedAt = Date.now();

  out.performance = {
    throttled: true,
    menuArrived,
    firstContentfulPaintMs: await page.evaluate(() => {
      const entry = performance.getEntriesByName('first-contentful-paint')[0];
      return entry ? Math.round(entry.startTime) : null;
    }),
    domContentLoadedMs: await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      return nav ? Math.round(nav.domContentLoadedEventEnd) : null;
    }),
    menuVisibleMs: loadedAt - startedAt,
    transferredBytes: await page.evaluate(() => performance.getEntriesByType('resource')
      .reduce((sum, r) => sum + (r.transferSize || 0), 0)),
    requestCount: await page.evaluate(() => performance.getEntriesByType('resource').length),
  };

  // Interaction budget is measured unthrottled on the network but with the CPU still
  // throttled: tapping "add" is local work, and leaving the network throttle on would
  // measure the request rather than the response of the interface.
  await session.send('Network.emulateNetworkConditions', {
    offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1,
  });

  // ---- Per-locale render measurements ----
  for (const locale of (QUICK ? ['en', 'ar'] : ['en', 'am', 'ar'])) {
    out.locales[locale] = await measureLocale(page, locale);
  }

  // ---- The cart survives a language change ----
  await page.evaluate((wanted) => window.surface.chooseLocale(wanted), 'en');
  await waitForMenu(page);
  const addButton = page.locator('.add').first();
  const interactionStart = Date.now();
  await addButton.click();
  await page.waitForFunction(() => document.querySelectorAll('.cart-line').length > 0,
    null, { timeout: 10000 }).catch(() => undefined);
  out.performance.interactionMs = Date.now() - interactionStart;

  const before = await page.evaluate(() => window.surface.cart().map((l) => ({
    key: l.key, itemCode: l.itemCode, amountMinor: l.amountMinor,
  })));
  await page.evaluate(() => window.surface.chooseLocale('ar'));
  await waitForMenu(page);
  const after = await page.evaluate(() => window.surface.cart().map((l) => ({
    key: l.key, itemCode: l.itemCode, amountMinor: l.amountMinor,
  })));
  const renderedAfter = await page.evaluate(() =>
    [...document.querySelectorAll('.cart-line')].map((n) => ({
      key: n.dataset.key,
      price: (n.querySelector('.cart-line-price')?.textContent || '').trim(),
    })));
  out.journeys.cartAcrossLocale = { before, after, renderedAfter };

  // Everything up to here rendered without the probe interfering. Recorded before the
  // retry journey starts, because that journey aborts a request on purpose and its own
  // instrument must not be reported as a defect in the surface.
  out.errorsBeforeRetry = [...out.errors];

  // ---- Retry: the same key, or a second commitment ----
  //
  // The first attempt is made to fail at the network, which is what actually happens on
  // mobile data, and then the guest presses "try again". Both requests are intercepted so
  // the Idempotency-Key each one carried can be compared. A retry that mints a fresh key
  // is a second commitment however well-behaved the server is.
  const keysSeen = [];
  let failFirst = true;
  await page.route('**/c/v1/cart/lines', async (route) => {
    keysSeen.push(route.request().headers()['idempotency-key'] ?? null);
    if (failFirst) { failFirst = false; await route.abort('connectionfailed'); return; }
    await route.continue();
  });

  await page.evaluate(() => window.surface.chooseLocale('en'));
  await waitForMenu(page);
  await page.locator('.add').first().click();
  await page.waitForFunction(
    () => [...document.querySelectorAll('.cart-line')].some((n) => n.dataset.state === 'failed'),
    null, { timeout: 15000 }).catch(() => undefined);

  const retryVisible = await page.locator('#retry').isVisible().catch(() => false);
  if (retryVisible) {
    await page.locator('#retry').click();
    await page.waitForFunction(
      () => [...document.querySelectorAll('.cart-line')]
        .some((n) => n.dataset.state === 'synchronized'),
      null, { timeout: 15000 }).catch(() => undefined);
  }
  await page.unroute('**/c/v1/cart/lines');

  out.journeys.retry = {
    keysSeen,
    sameKeyOnRetry: keysSeen.length >= 2 && keysSeen[0] !== null
      && keysSeen.every((k) => k === keysSeen[0]),
    retryOffered: retryVisible,
    lineStates: await page.evaluate(() =>
      [...document.querySelectorAll('.cart-line')].map((n) => n.dataset.state)),
    cartKeys: await page.evaluate(() => window.surface.cart().map((l) => l.key)),
  };

  // ---- The seven states, and every declared transition ----
  out.states.rendered = await measureStates(page);
  out.states.transitions = await measureTransitions(page);

  if (QUICK) {
    process.stdout.write(JSON.stringify(out, null, 2));
    return;
  }

  // ---- Keyboard, in Arabic so the order is measured in the mirrored layout ----
  await page.evaluate(() => window.surface.chooseLocale('ar'));
  await waitForMenu(page);
  out.journeys.keyboardArabic = await measureKeyboard(page);
  await page.evaluate(() => window.surface.chooseLocale('en'));
  await waitForMenu(page);
  out.journeys.keyboardEnglish = await measureKeyboard(page);

  // ---- axe-core, in each locale ----
  for (const locale of ['en', 'am', 'ar']) {
    await page.evaluate((wanted) => window.surface.chooseLocale(wanted), locale);
    await waitForMenu(page);
    await page.evaluate(AXE_SOURCE);
    out.axe[locale] = await page.evaluate(async () => {
      const run = await window.axe.run(document, {
        resultTypes: ['violations'],
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
      });
      return {
        violations: run.violations.map((v) => ({
          id: v.id, impact: v.impact, help: v.help,
          nodes: v.nodes.length,
          target: v.nodes[0]?.target?.join(' ') ?? null,
        })),
        passes: run.passes ? run.passes.length : null,
      };
    });
  }

  // ---- Zoom to 200%, which WCAG asks for, measured for overflow ----
  await page.setViewportSize({ width: 195, height: 422 });
  await page.evaluate(() => window.surface.chooseLocale('am'));
  await waitForMenu(page);
  out.journeys.zoomed = await page.evaluate(() => ({
    documentScrollWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    clipped: [...document.querySelectorAll('.item-name, .allergen-text, .locale')]
      .filter((n) => n.scrollWidth - n.clientWidth > 1)
      .map((n) => (n.textContent || '').slice(0, 40)),
  }));

  process.stdout.write(JSON.stringify(out, null, 2));
}

main()
  .catch((error) => {
    out.probeFailed = String((error && error.stack) || error);
    process.stdout.write(JSON.stringify(out, null, 2));
    process.exitCode = 1;
  })
  // Always, on both paths. A probe that leaves Chromium running turns a diagnosable
  // failure into a timeout, which is what happened the first time this threw.
  .finally(async () => { if (browser) await browser.close().catch(() => undefined); });
