/**
 * Walks ONE golden journey in a real browser and reports what happened at each STEP.
 *
 * FR-TST-005A asks for browser/device automation against real persistence — the journey
 * a person walks, not an API sequence. So this drives the actual documents the actual
 * surfaces serve: the customer PWA for a guest, the waiter surface for staff, two
 * browser CONTEXTS when a journey has two devices at one table.
 *
 * It decides nothing. Every step returns what it observed and verify_journeys.py holds
 * the assertions, exactly as M2-C, M3-B, M3-C and M3-D separate them. A probe that
 * decided what counted as a pass could be adjusted until everything passed.
 *
 * The step list is the contract with the suite: each entry carries its name, whether it
 * completed, and what it saw. A journey that fails must name the JOURNEY and the STEP —
 * "GJ-03A failed at 'view the Arabic timeline'" is actionable, "journeys: 4/5" is not —
 * so a step that throws records the failure and everything after it is reported as not
 * reached rather than silently skipped.
 */
import { chromium } from 'playwright';

const [, , baseUrl, journey, argsJson] = process.argv;
const args = JSON.parse(argsJson);

const steps = [];
let aborted = false;

async function step(name, work) {
  if (aborted) {
    steps.push({ name, reached: false, ok: false, detail: 'not reached' });
    return null;
  }
  try {
    const detail = await work();
    steps.push({ name, reached: true, ok: true, detail: detail ?? null });
    return detail;
  } catch (error) {
    steps.push({ name, reached: true, ok: false, detail: String(error).slice(0, 400) });
    aborted = true;
    return null;
  }
}

const browser = await chromium.launch();

/** One guest device: its own browser context, as a phone is its own device. */
async function guestDevice(locale) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, locale,
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  return { context, page, errors };
}

async function enterAsGuest(device, code, locale) {
  // The entry URL carries the tenant, the outlet AND the code, exactly as a printed
  // placard does — this is the shape M2-C's surface parses, and a URL with only the
  // code lands on a page that never establishes a session.
  await device.page.goto(
    `${baseUrl}/?t=${args.tenant}&o=${args.outlet}&c=${encodeURIComponent(code)}`,
    { waitUntil: 'domcontentloaded' });
  await device.page.waitForFunction(() => typeof window.surface === 'object');
  // The surface's own load, awaited rather than raced: the service panel and the menu
  // both arrive on it, and a journey that tapped before it finished would be measuring
  // how fast a fetch answered.
  await device.page.evaluate(() => window.surface.ready());
  await device.page.evaluate((l) => window.surface.chooseLocale(l), locale);
  await device.page.waitForFunction(
    () => document.querySelectorAll('.item').length > 0, null, { timeout: 20000 });
  return device.page.evaluate(() => document.querySelectorAll('.item').length);
}

async function addFirstItem(page) {
  await page.locator('.add').first().click();
  await page.waitForFunction(
    () => document.querySelectorAll('.cart-line').length > 0, null, { timeout: 15000 });
  return page.evaluate(() => window.surface.cart().length);
}

async function placeOrder(page) {
  await page.locator('#place-order').click({ timeout: 15000 });
  await page.waitForFunction(
    () => !document.getElementById('order-outcome').hidden, null, { timeout: 20000 });
  return page.evaluate(() => {
    const node = document.getElementById('order-outcome');
    return { words: (node.textContent || '').trim(),
             orderId: node.dataset.orderId ?? null,
             reason: node.dataset.reason ?? null };
  });
}

const out = { journey, steps, errors: [] };

try {
  if (journey === 'GJ-01A' || journey === 'GJ-02' || journey === 'GJ-03A') {
    const locale = journey === 'GJ-02' ? 'am' : journey === 'GJ-03A' ? 'ar' : 'en';
    const device = await guestDevice(locale);

    await step('scan the QR and become a guest', async () => {
      const items = await enterAsGuest(device, args.code, locale);
      if (!items) throw new Error('no menu items rendered');
      return { items };
    });

    await step('read the menu in the chosen language', async () =>
      device.page.evaluate((l) => ({
        missing: window.surface.missingStrings(l),
        documentLocale: document.documentElement.lang,
        direction: getComputedStyle(document.documentElement).direction,
        firstItem: (document.querySelector('.item-name')
                    || document.querySelector('.item'))?.textContent?.trim() ?? '',
      }), locale));

    if (journey === 'GJ-02') {
      await step('read the allergen text in Amharic', async () =>
        device.page.evaluate(() => ({
          rows: [...document.querySelectorAll('.allergen')].map(
            (n) => (n.textContent || '').trim()).slice(0, 6),
        })));
    }

    if (journey === 'GJ-03A') {
      await step('search the menu by its Latin SKU', async () => {
        const codes = await device.page.evaluate(() =>
          [...document.querySelectorAll('.item')].map(
            (n) => n.getAttribute('data-item-code')
                   ?? n.querySelector('[data-item-code]')?.getAttribute('data-item-code')
          ).filter(Boolean));
        return { codesVisible: codes.slice(0, 5) };
      });
      await step('read ETB prices left to right inside the Arabic page', async () =>
        device.page.evaluate(() => {
          const price = document.querySelector('.item-price, .cart-line-price');
          if (!price) return { prices: [] };
          const range = document.createRange();
          range.selectNodeContents(price);
          const rects = [...range.getClientRects()];
          return {
            text: (price.textContent || '').trim(),
            direction: getComputedStyle(price).direction,
            firstX: rects.length ? rects[0].left : null,
            lastX: rects.length ? rects[rects.length - 1].right : null,
          };
        }));
    }

    await step('choose a dish', async () => ({ lines: await addFirstItem(device.page) }));
    await step('place the order', async () => placeOrder(device.page));

    if (journey === 'GJ-02') {
      // The brief's GJ-02 calls the waiter between the first order and the second, and
      // it is the only leg on this journey that produces a customer NOTICE — order
      // status is a timeline, a service acknowledgement is a message. Both have to be
      // in Amharic and they travel by different machinery, so the journey walks both.
      await step('call the waiter', async () => {
        const button = device.page.locator('.service-ask').first();
        await button.click({ timeout: 15000 });
        await device.page.waitForTimeout(300);
        return device.page.evaluate(() => ({
          statuses: [...document.querySelectorAll('#service-status li')].map(
            (n) => (n.textContent || '').trim()),
        }));
      });
    }

    await step('watch the status change as the kitchen works', async () => {
      // Driven from the database by the suite between polls; the surface is asked what
      // it DISPLAYS, which is the half a person experiences.
      await device.page.waitForTimeout(200);
      return device.page.evaluate(() => ({
        statusWords: (document.getElementById('status-text')?.textContent || '').trim(),
        outcome: (document.getElementById('order-outcome')?.textContent || '').trim(),
      }));
    });

    out.errors = device.errors;
  }

  if (journey === 'GJ-04') {
    const one = await guestDevice('en');
    const two = await guestDevice('en');

    await step('two devices scan the same table', async () => {
      const a = await enterAsGuest(one, args.code, 'en');
      const b = await enterAsGuest(two, args.codeTwo ?? args.code, 'en');
      return { deviceOneItems: a, deviceTwoItems: b };
    });

    await step('each device keeps its own basket', async () => {
      const a = await addFirstItem(one.page);
      const b = await addFirstItem(two.page);
      const keys = {
        one: await one.page.evaluate(() => window.surface.cart().map((l) => l.key)),
        two: await two.page.evaluate(() => window.surface.cart().map((l) => l.key)),
      };
      return { linesOne: a, linesTwo: b, keys };
    });

    await step('each device places its own order', async () => ({
      one: await placeOrder(one.page),
      two: await placeOrder(two.page),
    }));

    await step('one device calls the waiter', async () => {
      const button = one.page.locator('.service-ask').first();
      await button.click({ timeout: 15000 });
      await one.page.waitForTimeout(300);
      return one.page.evaluate(() => ({
        statuses: [...document.querySelectorAll('#service-status li')].map(
          (n) => (n.textContent || '').trim()),
      }));
    });

    await step('a later add-on goes on the same table', async () => ({
      lines: await addFirstItem(one.page),
    }));

    out.errors = [...one.errors, ...two.errors];
  }

  if (journey === 'GJ-05') {
    const context = await browser.newContext({ viewport: { width: 480, height: 900 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    await step('the waiter opens the floor', async () => {
      await page.goto(`${baseUrl}/waiter`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => typeof window.waiterSurface === 'object');
      await page.evaluate((data) => window.waiterSurface.render(data), args.payload);
      return page.evaluate(() => ({
        queues: document.querySelectorAll('#next li.row').length,
        tables: document.querySelectorAll('#tables li.row').length,
      }));
    });

    await step('the next required action is the biggest thing on the row', async () =>
      page.evaluate(() => {
        const row = document.querySelector('#next li.row');
        if (!row) return { rows: 0 };
        const button = row.querySelector('button');
        const others = [...document.querySelectorAll('button')].filter((b) => b !== button);
        return {
          rows: document.querySelectorAll('#next li.row').length,
          actionFont: parseFloat(getComputedStyle(button).fontSize),
          otherFonts: others.map((b) => parseFloat(getComputedStyle(b).fontSize)),
        };
      }));

    await step('an allergy is emphasised without relying on colour', async () =>
      page.evaluate(() => ({
        rows: [...document.querySelectorAll('#next li.row, #tables li.row')].map(
          (n) => (n.textContent || '').trim()).filter((t) => /allerg/i.test(t)),
        documentText: (document.body.textContent || '').slice(0, 4000),
      })));

    await step('amending needs a deliberate confirmation with a reason', async () =>
      page.evaluate(() => {
        let ran = false;
        window.waiterSurface.askThenRun('order.amend', 'Amend', () => { ran = true; });
        const panel = document.getElementById('confirm-panel');
        const reason = document.getElementById('confirm-reason');
        const before = { ranImmediately: ran, panelShown: !panel.hidden,
                         reasonShown: !reason.hidden };
        document.getElementById('confirm-yes').click();
        const empty = { ran };
        reason.value = 'guest asked for one fewer';
        document.getElementById('confirm-yes').click();
        return { before, empty, after: { ran } };
      }));

    out.errors = errors;
  }
} catch (error) {
  out.errors.push(String(error));
}

await browser.close();
process.stdout.write(JSON.stringify(out));
