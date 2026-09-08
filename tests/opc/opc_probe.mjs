// The OP-C surfaces, measured in a real browser.
//
// Three scenes, and every one of them REACHES rather than renders. OP-B's probe supplied
// a payload where the question was what a screen draws; the questions here are all of the
// other kind — can a guest be seated by scanning, can they take something back out, can a
// waiter get in, can a waiter seat a table — and none of them can be answered by handing
// a surface some data and looking at it.
//
// So the only thing this file supplies is a QR link and a set of credentials. The
// occupancy, the basket, the totals, the floor and the free-table list are all fetched by
// the surfaces themselves, and every number below is read back out of the page.
import { chromium } from 'playwright';

const [baseUrl, scene, argsJson] = process.argv.slice(2);
const args = JSON.parse(argsJson);
const out = { scene, steps: {}, errors: [] };

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1400, height: 950 } });
  const page = await context.newPage();
  page.on('pageerror', (e) => out.errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });

  // ------------------------------------------------------------------------ basket
  //
  // A guest arrives at an unoccupied table by the link the placard encodes, is seated,
  // adds a dish, and takes it back out.
  //
  // THE SEATING IS THE FIRST MEASUREMENT AND IT IS NOT ASSERTED ANYWHERE. Before OP-C the
  // page reached exactly this point and stopped: /c/v1/join answered NO_OPEN_OCCUPANCY at
  // an empty table because nothing in the delivered code path had ever opened one. If the
  // basket below fills, the guest was seated, because a basket cannot exist without an
  // occupancy to hold it.
  if (scene === 'basket') {
    await page.goto(`${baseUrl}/?t=${args.tenant}&o=${args.outlet}&c=${args.code}`,
                    { waitUntil: 'domcontentloaded' });

    // The menu arriving IS the seating: /c/v1/menu is fetched after beSeated() resolves,
    // and the surface goes to its blocked state instead if it does not.
    await page.waitForFunction(
      () => document.querySelectorAll('#items li').length > 0
            || (document.getElementById('status-text') || {}).textContent === 'Cannot send',
      null, { timeout: 30000 });

    out.steps.seated = await page.evaluate(() => ({
      items: document.querySelectorAll('#items li').length,
      status: (document.getElementById('status-text') || {}).textContent || '',
      basketEmptyShown: !(document.getElementById('cart-empty') || {}).hidden,
    }));
    if (out.steps.seated.items === 0) {
      process.stdout.write(JSON.stringify(out));
      await browser.close();
      process.exit(0);
    }

    // TWO DIFFERENT DISHES where the menu has two, so removing one leaves something
    // behind and the two lines are distinguishable from each other. A basket that empties
    // completely cannot tell "the line went" from "the list stopped rendering", and two
    // lines of the SAME dish cannot tell "each control names its line" from "every
    // control says the same thing".
    const second = await page.$('#items li:nth-child(2) .add');
    await page.click('#items li:nth-child(1) .add');
    await page.waitForFunction(
      () => document.querySelectorAll('#cart-lines li').length === 1, null,
      { timeout: 20000 });
    if (second) await second.click(); else await page.click('#items li:nth-child(1) .add');
    await page.waitForFunction(
      () => [...document.querySelectorAll('.cart-line-state')]
              .filter((s) => (s.textContent || '').includes('Sent')).length === 2,
      null, { timeout: 20000 });

    out.steps.beforeRemoval = await page.evaluate(() => {
      const lines = [...document.querySelectorAll('#cart-lines li')];
      const buttons = [...document.querySelectorAll('.cart-line-remove')];
      const first = buttons[0];
      const box = first ? first.getBoundingClientRect() : null;
      return {
        lines: lines.length,
        // One control per line, on every line. A remove offered on some of them would
        // make the guest work out which, which is worse than none.
        removeControls: buttons.length,
        // The accessible name has to say WHICH line. Controls that all read "Remove" are
        // one control repeated to somebody who cannot see the list — so the test is not
        // that the names DIFFER (two of the same dish legitimately read alike) but that
        // each one names the dish on its own row.
        labels: buttons.map((b) => b.getAttribute('aria-label') || ''),
        labelsNameTheirLine: lines.filter((li) => {
          const button = li.querySelector('.cart-line-remove');
          const dish = (li.querySelector('span') || {}).textContent || '';
          const label = button ? (button.getAttribute('aria-label') || '') : '';
          return dish.length > 0 && label.includes(dish);
        }).length,
        // FR-UX-011's thumb target, measured rather than asserted.
        smallestTarget: box ? Math.min(box.width, box.height) : 0,
        total: (document.getElementById('cart-total') || {}).textContent || '',
      };
    });

    // Removed by TAPPING IT, not by calling a function. The whole finding was that no
    // control existed; proving one exists by driving it from the console would repeat
    // the defect one layer up.
    await page.click('#cart-lines li:nth-child(1) .cart-line-remove');
    await page.waitForFunction(
      () => document.querySelectorAll('#cart-lines li').length === 1, null,
      { timeout: 20000 }).catch(() => undefined);

    out.steps.afterRemoval = await page.evaluate(() => ({
      lines: document.querySelectorAll('#cart-lines li').length,
      total: (document.getElementById('cart-total') || {}).textContent || '',
      outcome: (document.getElementById('order-outcome') || {}).textContent || '',
    }));
  }

  // ------------------------------------------------------------------------ till
  //
  // What a cashier sees having signed in with no bill open, which is the state they are
  // in for most of a shift and the state both boxes were blank in.
  if (scene === 'till') {
    if (args.token) {
      await page.addInitScript((a) => {
        sessionStorage.setItem('cashier.session',
          JSON.stringify({ token: a.token, sessionId: a.sessionId || '' }));
      }, args);
    }
    await page.goto(`${baseUrl}/cashier`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.cashierSurface === 'object');
    await page.waitForFunction(
      () => (document.getElementById('bill') || {}).textContent !== '', null,
      { timeout: 20000 }).catch(() => undefined);

    out.steps.boxes = await page.evaluate(() => {
      const read = (id) => {
        const box = document.getElementById(id);
        if (!box) return null;
        const heading = box.querySelector('h2');
        return {
          // A section with a border and nothing in it is the defect. Both halves are
          // measured: whether it says anything at all, and whether what it says is a
          // NAME rather than a stray line of content.
          text: (box.textContent || '').trim(),
          headingText: heading ? (heading.textContent || '').trim() : '',
          hasHeading: Boolean(heading),
          rendered: box.getBoundingClientRect().height > 0,
        };
      };
      return { bill: read('bill'), tip: read('tip-box') };
    });
  }

  // ------------------------------------------------------------------------ waiter
  //
  // A waiter gets in through a form on the page, and seats a table from the floor.
  //
  // Signing in through the SCREEN is half the point: OP-B gave this surface a network
  // layer and no door, so the only way in was the browser console. Nothing below hands
  // the page a session.
  if (scene === 'waiter') {
    await page.goto(`${baseUrl}/waiter`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.waiterSurface === 'object');

    out.steps.beforeSignIn = await page.evaluate(() => {
      const form = document.getElementById('sign-in');
      const fields = form ? [...form.querySelectorAll('input')] : [];
      const submit = form ? form.querySelector('button[type="submit"]') : null;
      const box = submit ? submit.getBoundingClientRect() : null;
      return {
        formPresent: Boolean(form),
        fields: fields.map((f) => f.id),
        // A form whose inputs are 2px tall is a form nobody can fill in on a phone.
        smallestField: fields.length
          ? Math.min(...fields.map((f) => f.getBoundingClientRect().height)) : 0,
        submitTarget: box ? Math.min(box.width, box.height) : 0,
        // Nothing may be fetched before there is a session.
        staffRequests: performance.getEntriesByType('resource')
          .filter((r) => r.name.includes('/s/v1/')).length,
      };
    });

    if (out.steps.beforeSignIn.formPresent) {
      await page.fill('#sign-in-tenantId', args.tenant);
      await page.fill('#sign-in-outletId', args.outlet);
      await page.fill('#sign-in-channelValue', args.email);
      await page.fill('#sign-in-secret', args.secret);
      await page.click('#sign-in button[type="submit"]');

      // The floor arriving is what proves the form reached the service. Waited for by
      // CONTENT rather than by a timer: a fixed pause turns a slow floor into a failure
      // and a broken one into a pass.
      await page.waitForFunction(
        () => document.querySelectorAll('#tables li').length > 0
              || document.querySelectorAll('#seatable-tables li').length > 0,
        null, { timeout: 30000 }).catch(() => undefined);

      out.steps.afterSignIn = await page.evaluate(() => ({
        formStillShown: !(document.getElementById('sign-in-panel') || {}).hidden,
        occupied: document.querySelectorAll('#occupied-tables li').length,
        seatable: document.querySelectorAll('#seatable-tables li').length,
        notice: (document.getElementById('notice') || {}).textContent || '',
        staffRequests: performance.getEntriesByType('resource')
          .filter((r) => r.name.includes('/s/v1/')).length,
      }));

      // Seating, by pressing the button a waiter presses.
      const seat = await page.$('#seatable-tables li:first-child button');
      if (seat) {
        out.steps.seatTarget = await page.evaluate((node) => {
          const box = node.getBoundingClientRect();
          return { smallest: Math.min(box.width, box.height),
                   reference: (node.closest('li') || {}).dataset.seatable || '',
                   label: (node.textContent || '').trim() };
        }, seat);
        await seat.click();
        await page.waitForFunction(
          (before) => document.querySelectorAll('#seatable-tables li').length < before,
          out.steps.afterSignIn.seatable, { timeout: 20000 }).catch(() => undefined);

        out.steps.afterSeating = await page.evaluate(() => ({
          seatable: document.querySelectorAll('#seatable-tables li').length,
          notice: (document.getElementById('notice') || {}).textContent || '',
          // The seated table must now be drawn among the occupied ones, and the floor
          // must be able to say who is accountable for it.
          tableRows: [...document.querySelectorAll('#occupied-tables li.row')]
            .map((li) => (li.textContent || '').trim()).slice(0, 12),
        }));
      }
    }
  }
} catch (error) {
  out.errors.push(String(error));
}

await browser.close();
process.stdout.write(JSON.stringify(out));
