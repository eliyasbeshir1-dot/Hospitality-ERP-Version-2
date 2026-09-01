/**
 * Drives the WAITER surface in a real browser and prints what it MEASURED, as JSON.
 *
 * Decides nothing, exactly as M2-C's and M3-B's probes decide nothing. It renders, reads
 * computed styles and bounding boxes, and hands the numbers to verify_m3d.py where the
 * assertions live. A probe that decided what counted as a pass could be adjusted until
 * everything passed, which is the separation this file exists to keep.
 *
 * It renders the surface THREE times:
 *
 *   normal      — as a waiter sees it
 *   accessible  — with FR-UX-008's mode on, so "larger targets and text" is a measured
 *                 difference rather than a claim about a stylesheet
 *   flattened   — with every colour in the document reduced to one ink, inherited from
 *                 M3-B. If an overdue table is distinguishable only by colour, this is
 *                 where that stops being visible.
 *
 * It also drives the CONFIRMATION path for one routine action and one deliberate action,
 * because FR-UX-015's grading is a claim about what a person has to DO, and the only way
 * to measure that is to do it.
 */
import { chromium } from 'playwright';

const [, , baseUrl, payloadJson] = process.argv;
const payload = JSON.parse(payloadJson);

const out = { normal: null, accessible: null, flattened: null, confirm: null, errors: [] };

const FLATTEN_CSS = `
  *, *::before, *::after {
    color: #000000 !important;
    background-color: #ffffff !important;
    border-color: #000000 !important;
    outline-color: #000000 !important;
    text-decoration-color: #000000 !important;
    fill: #000000 !important;
    stroke: #000000 !important;
  }
`;

async function measure(page) {
  return page.evaluate(() => {
    const box = (node) => {
      const r = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      return {
        text: (node.textContent || '').trim(),
        width: r.width,
        height: r.height,
        fontSize: parseFloat(style.fontSize),
        fontWeight: style.fontWeight,
        borderTopWidth: parseFloat(style.borderTopWidth),
        visible: r.width > 0 && r.height > 0 && style.visibility !== 'hidden'
                 && style.display !== 'none',
        consequence: node.dataset ? (node.dataset.consequence ?? null) : null,
      };
    };

    const rows = [...document.querySelectorAll('#next li.row')].map((n) => ({
      overdue: n.dataset.overdue === 'true',
      queue: n.dataset.queue ?? null,
      subjectId: n.dataset.subjectId ?? null,
      headline: (n.querySelector('.headline')?.textContent || '').trim(),
      elapsed: (n.querySelector('.elapsed')?.textContent || '').trim(),
      action: n.querySelector('button') ? box(n.querySelector('button')) : null,
      words: (n.textContent || '').trim(),
    }));

    const tables = [...document.querySelectorAll('#tables li.row')].map((n) => ({
      table: n.dataset.table ?? null,
      attention: n.dataset.overdue === 'true',
      words: (n.textContent || '').trim(),
    }));

    const notifications = [...document.querySelectorAll('#notifications li.row')].map((n) => ({
      noticeId: n.dataset.notice ?? null,
      severity: n.dataset.severity ?? null,
      read: n.dataset.read === 'true',
      words: (n.textContent || '').trim(),
    }));

    const results = [...document.querySelectorAll('#search-results li.row')].map((n) => ({
      itemCode: n.dataset.itemCode ?? null,
      words: (n.textContent || '').trim(),
      add: n.querySelector('button') ? box(n.querySelector('button')) : null,
    }));

    const controls = [...document.querySelectorAll('button, input')].map(box);

    return {
      rows,
      tables,
      notifications,
      results,
      controls,
      documentText: (document.body.textContent || '').trim(),
      accessible: document.documentElement.classList.contains('accessible'),
      bodyFontSize: parseFloat(getComputedStyle(document.body).fontSize),
    };
  });
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 480, height: 900 },
  deviceScaleFactor: 2,
});
const page = await context.newPage();

page.on('pageerror', (error) => out.errors.push(String(error)));
page.on('console', (message) => {
  if (message.type() === 'error') out.errors.push(message.text());
});

try {
  await page.goto(`${baseUrl}/waiter`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.waiterSurface === 'object');

  await page.evaluate((data) => window.waiterSurface.render(data), payload);
  out.normal = await measure(page);

  out.confirm = await page.evaluate(() => {
    const result = { routine: null, deliberate: null };
    const panel = document.getElementById('confirm-panel');
    const reason = document.getElementById('confirm-reason');
    const question = document.getElementById('confirm-question');

    let ran = false;
    window.waiterSurface.askThenRun('order.line.add', 'Add', () => { ran = true; });
    result.routine = { ranWithoutConfirming: ran, panelShown: !panel.hidden };

    ran = false;
    window.waiterSurface.askThenRun('allergy.declare', 'Declare an allergy', () => { ran = true; });
    const before = {
      ranImmediately: ran,
      panelShown: !panel.hidden,
      reasonShown: !reason.hidden,
      consequence: panel.dataset.consequence ?? null,
      questionWords: (question.textContent || '').trim(),
    };

    document.getElementById('confirm-yes').click();
    const emptyRefused = { ran, stillOpen: !panel.hidden,
                           questionWords: (question.textContent || '').trim() };

    reason.value = 'guest declared a nut allergy';
    document.getElementById('confirm-yes').click();
    const withReason = { ran, closed: panel.hidden };

    result.deliberate = { before, emptyRefused, withReason };
    return result;
  });

  await page.evaluate(() => window.waiterSurface.setAccessibilityMode(true));
  out.accessible = await measure(page);
  await page.evaluate(() => window.waiterSurface.setAccessibilityMode(false));

  await context.route('**/app/waiter.css', async (route) => {
    const response = await route.fetch();
    route.fulfill({ response, body: (await response.text()) + FLATTEN_CSS });
  });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.waiterSurface === 'object');
  await page.evaluate((data) => window.waiterSurface.render(data), payload);
  out.flattened = await measure(page);
} catch (error) {
  out.errors.push(String(error));
}

await browser.close();
process.stdout.write(JSON.stringify(out));
