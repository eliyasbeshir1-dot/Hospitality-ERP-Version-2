// The OP-D surfaces, measured in a real browser.
//
// Three scenes, and none of them is handed data. The menu card, the sentence a guest is
// shown after ordering, and the list a waiter admits an order from are all fetched by the
// surfaces themselves — which is the whole point, because every defect this gate closes
// was a screen that could not reach something the service already did.
import { chromium } from 'playwright';

const [baseUrl, scene, argsJson] = process.argv.slice(2);
const args = JSON.parse(argsJson);
const out = { scene, steps: {}, errors: [] };

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 430, height: 940 } });
  const page = await context.newPage();
  page.on('pageerror', (e) => out.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });

  const guestLink = `${baseUrl}/?t=${args.tenant}&o=${args.outlet}&c=${args.code}`;

  // ------------------------------------------------------------------------ menu
  //
  // FR-MNU-004 on the rendered card. The seed has carried a description, the ingredients
  // and a preparation time since 0003 and the menu function returned none of them, so
  // this measures the whole chain — seed, function, route, surface — by looking at what a
  // guest can actually read.
  if (scene === 'menu') {
    await page.goto(guestLink, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => document.querySelectorAll('#items li').length > 0
            || (document.getElementById('status-text') || {}).textContent === 'Cannot send',
      null, { timeout: 30000 });

    out.steps.card = await page.evaluate(() => {
      const cards = [...document.querySelectorAll('#items li')];
      const has = (li, sel) => {
        const node = li.querySelector(sel);
        return Boolean(node && (node.textContent || '').trim().length > 0);
      };
      return {
        items: cards.length,
        withDescription: cards.filter((li) => has(li, '.item-description')).length,
        withIngredients: cards.filter((li) => has(li, '.item-ingredients')).length,
        withPrep: cards.filter((li) => has(li, '.item-prep')).length,
        first: cards[0] ? (cards[0].textContent || '').replace(/\s+/g, ' ').trim() : null,
      };
    });
  }

  // ------------------------------------------------------------------------ order
  //
  // What a guest is TOLD, under a policy where the order waits. The scene is run with the
  // outlet set to staff_confirmed by the suite, so "with the kitchen" would be false.
  if (scene === 'order') {
    await page.goto(guestLink, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => document.querySelectorAll('#items li').length > 0, null, { timeout: 30000 });
    await page.click('#items li:nth-child(1) .add');
    await page.waitForFunction(
      () => [...document.querySelectorAll('.cart-line-state')]
              .some((s) => (s.textContent || '').includes('Sent')),
      null, { timeout: 20000 });
    await page.click('#place-order');
    await page.waitForFunction(
      () => !(document.getElementById('order-outcome') || {}).hidden,
      null, { timeout: 25000 }).catch(() => undefined);

    out.steps.placed = await page.evaluate(() => {
      const node = document.getElementById('order-outcome');
      return {
        message: node ? (node.textContent || '').trim() : null,
        // The state the ROUTE reported, kept on the element. The sentence and the state
        // are measured together, because "is the wording right" is only answerable
        // against what actually happened to the order.
        state: node ? (node.dataset.orderState || null) : null,
        orderId: node ? (node.dataset.orderId || null) : null,
      };
    });
  }

  // ------------------------------------------------------------------------ floor
  //
  // The waiter floor: an order waiting, above the tables, with a control that admits it.
  // Signed in through the form on the page — nothing hands this session in.
  if (scene === 'floor') {
    await page.goto(`${baseUrl}/waiter`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.waiterSurface === 'object');
    await page.fill('#sign-in-tenantId', args.tenant);
    await page.fill('#sign-in-outletId', args.outlet);
    await page.fill('#sign-in-channelValue', args.email);
    await page.fill('#sign-in-secret', args.secret);
    await page.click('#sign-in button[type="submit"]');

    await page.waitForFunction(
      () => document.querySelectorAll('#pending-order-list li').length > 0,
      null, { timeout: 30000 }).catch(() => undefined);

    const read = () => page.evaluate(() => {
      const section = document.getElementById('pending-orders');
      const tables = document.getElementById('tables');
      const rows = [...document.querySelectorAll('#pending-order-list li')];
      const button = rows[0] ? rows[0].querySelector('button') : null;
      return {
        rows: rows.length,
        hidden: section ? section.hidden : null,
        // DOCUMENT_POSITION_FOLLOWING: the tables come after the waiting orders, which is
        // FR-POS-002's priority order rather than a layout preference.
        aboveTables: section && tables
          ? (section.compareDocumentPosition(tables) & 4) > 0 : null,
        consequence: button ? button.dataset.consequence : null,
        label: button ? (button.textContent || '').trim() : null,
        first: rows[0] ? (rows[0].textContent || '').replace(/\s+/g, ' ').trim() : null,
        notice: (document.getElementById('notice') || {}).textContent || '',
      };
    });

    out.steps.before = await read();

    if (out.steps.before.rows > 0) {
      // Pressed, not called. The finding was that no control existed; proving one exists
      // by driving it from the console would repeat the defect one layer up.
      await page.click('#pending-order-list li:first-child button');
      // `order.accept` is graded elevated, so the confirmation panel opens and has to be
      // answered — which is itself the grade doing its job and is measured by the fact
      // that the list does not shrink until it is answered.
      await page.waitForTimeout(400);
      const panelOpen = await page.evaluate(
        () => !(document.getElementById('confirm-panel') || {}).hidden);
      if (panelOpen) await page.click('#confirm-yes');
      await page.waitForFunction(
        (before) => document.querySelectorAll('#pending-order-list li').length < before,
        out.steps.before.rows, { timeout: 25000 }).catch(() => undefined);
      out.steps.after = { ...(await read()), panelOpened: panelOpen };
    }
  }
} catch (error) {
  out.errors.push(String(error));
}

await browser.close();
process.stdout.write(JSON.stringify(out));
