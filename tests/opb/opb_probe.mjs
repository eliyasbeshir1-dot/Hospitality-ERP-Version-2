// The OP-B surfaces, measured in a real browser.
//
// One probe, several scenes, because a browser launch is the expensive part and the eight
// controls each need one. Every scene returns raw measurements — numbers and strings out
// of the page's own layout and DOM — and decides nothing. The suite decides.
//
// WHAT THE PROBE SUPPLIES AND WHAT IT DOES NOT. It supplies a sign-in and, where a scene
// is about rendering rather than about reaching, a payload to render. It never supplies a
// bill, a queue, a total or a tip: those the surface fetches for itself, which is the
// whole point of the slice.
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
  if (args.prompts) {
    await page.addInitScript((answers) => {
      let i = 0;
      window.prompt = () => answers[Math.min(i++, answers.length - 1)];
    }, args.prompts);
  }

  // ---------------------------------------------------------------------- allergy
  // The allergy block, rendered from a known emphasis and measured. The DATA is supplied
  // here on purpose: this scene is about what the surface DRAWS, which is the same thing
  // M3-B measures and the thing NC-OPB-001 and NC-OPB-002 plant a defect in. Whether a
  // real ticket can carry an allergy is a different question, answered elsewhere.
  if (scene === 'allergy') {
    await page.goto(`${baseUrl}/station`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.stationSurface === 'object');

    out.steps.rendered = await page.evaluate((emphasis) => {
      const detail = document.getElementById('detail');
      detail.textContent = '';
      detail.appendChild(window.stationSurface.renderAllergy(emphasis, false));
      const block = detail.querySelector('.allergy');
      const style = getComputedStyle(block);
      const glyph = block.querySelector('.allergy-glyph');
      const around = getComputedStyle(document.body);
      return {
        text: (block.textContent || '').trim(),
        carriesTheWarning: (block.textContent || '').includes(emphasis.written_warning),
        // The non-colour signals, each measured rather than asserted. If every one of
        // these matches the surrounding text, the only thing left telling a cook this is
        // a warning is its colour.
        weight: style.fontWeight,
        size: parseFloat(style.fontSize),
        border: style.borderTopWidth,
        // A glyph element with nothing in it is not a signal. The question is whether a
        // cook sees a mark, not whether a span exists.
        glyphPresent: Boolean(glyph && (glyph.textContent || '').trim()),
        bodyWeight: around.fontWeight,
        bodySize: parseFloat(around.fontSize),
        role: block.getAttribute('role'),
      };
    }, args.emphasis);
  }

  // ---------------------------------------------------------------------- till
  if (scene === 'till') {
    // A SESSION HANDED IN, WHEN ONE IS OFFERED, BECAUSE THE LOCKOUT IS REAL.
    //
    // Three of the eight controls drive this scene, and each runs it three times —
    // baseline, red, green. Nine sign-ins inside a minute is nine more than FR-AUTH-007's
    // limiter allows, and the suite met it as an HTTP 429 that looked like the tip box
    // failing to render. The limiter is not disabled or reconfigured; the scene simply
    // stops asking for a tenth session it does not need. Signing in through the screen is
    // proved once, in its own scene, where it is the thing being measured.
    if (args.token) {
      await page.addInitScript((a) => {
        sessionStorage.setItem('cashier.session',
          JSON.stringify({ token: a.token, sessionId: a.sessionId || '' }));
        sessionStorage.setItem('cashier.tenant', a.tenant);
        sessionStorage.setItem('cashier.outlet', a.outlet);
      }, args);
    }
    await page.goto(`${baseUrl}/cashier`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.cashierSurface === 'object');
    out.steps.beforeSignIn = await page.evaluate(() => ({
      staffRequests: performance.getEntriesByType('resource')
        .filter((r) => r.name.includes('/s/v1/')).length,
    }));
    out.steps.signedIn = args.token
      ? { ok: true, from: 'a session handed to the page' }
      : await page.evaluate(async (a) =>
          ({ ok: await window.cashierSurface.signIn(a.tenant, a.outlet, a.email, a.secret) }),
          args);

    await page.evaluate((id) => window.cashierSurface.showBill(id), args.bill);
    await page.waitForFunction(
      () => document.querySelectorAll('#bill .bill-line').length > 0, null,
      { timeout: 20000 });

    out.steps.bill = await page.evaluate(() => ({
      billNumber: (document.querySelector('.bill-number') || {}).textContent || '',
      lines: document.querySelectorAll('#bill .bill-line').length,
      total: (document.querySelector('#bill-total .bill-amount') || {}).textContent || '',
      lang: (document.getElementById('bill-summary') || {}).getAttribute('lang') || '',
    }));

    // FR-BIL-014 and FR-BIL-015, both read out of the rendered page.
    out.steps.tip = await page.evaluate(() => {
      const bill = document.getElementById('bill');
      const summary = document.getElementById('bill-summary');
      const options = [...document.querySelectorAll('.tip-option')];
      return {
        options: options.length,
        insideTheBill: options.filter((t) => bill && bill.contains(t)).length,
        insideTheSummary: options.filter((t) => summary && summary.contains(t)).length,
        preselected: options.filter((t) =>
          t.getAttribute('aria-pressed') === 'true' || t.classList.contains('selected')
          || t.hasAttribute('checked') || t.hasAttribute('data-selected')
          || t.getAttribute('data-chosen') === 'true').length,
        tipWordInsideSummary: /tip/i.test((summary || {}).textContent || ''),
      };
    });

    // FR-UX-008, driven rather than described: the panel must appear, must refuse an
    // empty reason, and must proceed once one is given.
    out.steps.friction = await page.evaluate(() => {
      let ran = null;
      window.cashierSurface.askThenRun('payment.refund', 'Refund', (r) => { ran = r; });
      const panel = document.getElementById('confirm-panel');
      const reason = document.getElementById('confirm-reason');
      const shown = { ranImmediately: ran !== null, panelShown: Boolean(panel),
                      reasonShown: reason ? !reason.hidden : false };
      if (!panel) return { shown, withoutReason: { ran }, after: { ran } };

      // EACH CLICK GUARDED, because the interesting case is the one where the panel is
      // GONE after the first click — that is exactly what a missing reason check does.
      // An unguarded second click throws on a null element, the whole step is lost, and
      // the control reports "the gate still passed" when the gate was never reached.
      const clickYes = () => {
        const yes = document.getElementById('confirm-yes');
        if (yes) yes.click();
        return Boolean(yes);
      };
      clickYes();
      const withoutReason = { ran, panelSurvived: Boolean(document.getElementById('confirm-panel')) };
      if (reason) reason.value = 'the guest returned the dish';
      clickYes();
      return { shown, withoutReason, after: { ran },
               grading: window.cashierSurface.requirementFor('payment.refund') };
    });
  }

  // ---------------------------------------------------------------------- board
  if (scene === 'board') {
    await page.goto(`${baseUrl}/station`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.stationSurface === 'object');
    out.steps.beforeSignIn = await page.evaluate(() => ({
      signInShown: Boolean(document.getElementById('sign-in')),
      staffRequests: performance.getEntriesByType('resource')
        .filter((r) => r.name.includes('/s/v1/')).length,
    }));
    out.steps.signedIn = await page.evaluate(async (a) => ({
      ok: await window.stationSurface.signIn(a.tenant, a.outlet, a.station, a.email, a.secret),
    }), args);

    await page.waitForFunction(
      (id) => document.querySelector(`#queue [data-ticket="${id}"]`) !== null,
      args.ticket, { timeout: 20000 });
    await page.click(`#queue [data-ticket="${args.ticket}"]`);
    await page.waitForFunction(
      () => document.querySelectorAll('#detail .action').length > 0, null,
      { timeout: 20000 });

    out.steps.actions = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll('#detail .action')];
      return {
        labels: buttons.map((b) => b.textContent),
        smallestTarget: Math.min(...buttons.map((b) => {
          const r = b.getBoundingClientRect();
          return Math.min(r.height, r.width);
        })),
      };
    });

    const move = (out.steps.actions.labels || []).find((l) => /^acknowledged|^preparing/.test(l));
    if (move) {
      await page.click(`#detail .action:has-text("${move.split(' — ')[0]}")`);
      await page.waitForTimeout(1800);
    }
    out.steps.moved = await page.evaluate(() => ({
      notice: (document.getElementById('notice') || {}).textContent || '',
    }));
  }

  // ---------------------------------------------------------------------- waiter
  if (scene === 'waiter') {
    await page.goto(`${baseUrl}/waiter`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.waiterSurface === 'object');
    out.steps.beforeSignIn = await page.evaluate(() => ({
      staffRequests: performance.getEntriesByType('resource')
        .filter((r) => r.name.includes('/s/v1/')).length,
    }));
    out.steps.signedIn = await page.evaluate(async (a) =>
      ({ ok: await window.waiterSurface.signIn(a.tenant, a.outlet, a.email, a.secret) }),
      args);
    await page.waitForTimeout(2500);
    out.steps.floor = await page.evaluate(() => ({
      tableRows: document.querySelectorAll('#tables li.row').length,
      showsUnpaidBalance: /balance/i.test(
        (document.getElementById('tables') || {}).textContent || ''),
      staffRequests: performance.getEntriesByType('resource')
        .filter((r) => r.name.includes('/s/v1/')).length,
    }));
  }
} catch (error) {
  out.errors.push(String(error));
}

await browser.close();
process.stdout.write(JSON.stringify(out));
