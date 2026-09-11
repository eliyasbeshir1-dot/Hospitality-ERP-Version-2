/**
 * The till.
 *
 * WHY THIS FILE EXISTS. Every route it calls was delivered at M4-A and M4-B and proved
 * through the service. None of them had a screen. The M4 executing review's P0-2 was that
 * there is no cashier browser journey, and the reason there was none is that there was no
 * till: a person could not open a bill, split it, take money or hand over a receipt,
 * however thoroughly the database could.
 *
 * So this is a surface over routes that already exist. It computes no money. Every figure
 * it shows was calculated by the database and is rendered as it arrived; the one piece of
 * arithmetic here is subtracting to display change, and even that is shown beside the
 * change the service returned rather than instead of it.
 *
 * THREE RULES SHAPE IT, and each has a control behind it:
 *
 *   1. THE TIP IS NEVER INSIDE THE BILL. Two sibling sections in index.html, and this file
 *      never appends a tip element to the bill's subtree. FR-BIL-014.
 *   2. NOTHING IS PRESELECTED. The tip options arrive with no notion of a preferred one
 *      and leave this file the same way: no checked input, no pressed button, no default.
 *      A till that suggests is a till that has decided for the guest. FR-BIL-015.
 *   3. FRICTION IS GRADED BY THE DATABASE, NOT BY THIS FILE. What needs confirming, and
 *      what needs a reason, comes from GET /s/v1/confirmation-requirements. There is no
 *      list of destructive actions in this file to drift from the one in pos.
 *      confirmation_requirement. FR-UX-008.
 *
 * And a fourth that is not a rendering rule: A MANAGER APPROVES ON THEIR OWN SESSION. The
 * override panel signs the manager in separately and sends THEIR session id. It never
 * takes a manager's password into the cashier's session, because M3-D made credential
 * sharing fail as a property of the schema and a screen offering a way around that would
 * be worse than the schema being loose. FR-POS-006.
 */

type Json = Record<string, unknown>;

interface Session { token: string; sessionId: string; }

interface BillLine {
  stage: string; kind: string; label: string;
  currency_code: string; amount_minor: string;
}

interface BillSummary {
  id: string; bill_number: string; state: string; currency_code: string;
  bill_total_minor: string; disposed_minor: string; outstanding_minor: string;
  calculation_version: string; locale: string;
}

interface TipOption {
  display_order: number; percentage: string;
  currency_code: string; amount_minor: string;
}

interface Requirement {
  action_code: string; consequence: string; requires_reason: boolean;
}

const SESSION_KEY = 'cashier.session';

let session: Session | null = null;
let requirements: Requirement[] = [];
let bill: BillSummary | null = null;
let intentId: string | null = null;

function element(tag: string, className?: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function $(id: string): HTMLElement | null { return document.getElementById(id); }

function report(message: string): void {
  const bar = $('notice');
  if (!bar) return;
  bar.textContent = message;
  bar.removeAttribute('hidden');
}

/**
 * An idempotency key with NO LONG RUN OF DIGITS IN IT.
 *
 * The first version was `till-${Date.now()}-...`, and the database refused it:
 * CARD_DATA_RETAINED, "was given a value shaped like a primary account number". A
 * millisecond timestamp is thirteen digits, and thirteen to nineteen digits is what a PAN
 * looks like. M4-B scans every textual column for that shape, and it caught a key this
 * till invented.
 *
 * The rule is right and the key was wrong, so the key changed. Base-36 only, which cannot
 * produce a run of digits long enough to be mistaken for a card, and still unique enough
 * for what an idempotency key is for.
 */
function newIdempotencyKey(): string {
  const part = () => Math.random().toString(36).slice(2, 10);
  return `till-${part()}-${part()}`;
}

async function api(method: string, path: string, body?: unknown,
                   idempotencyKey?: string): Promise<{
  status: number; data: Json;
}> {
  const response = await fetch(path, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(session ? { authorization: `Bearer ${session.token}` } : {}),
      ...(idempotencyKey ? { 'idempotency-key': idempotencyKey } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  let data: Json = {};
  try { data = text ? JSON.parse(text) as Json : {}; } catch { /* not json */ }
  return { status: response.status, data };
}

function refusal(answer: { status: number; data: Json }): string {
  return String(answer.data.reason ?? answer.data.error ?? answer.status);
}

/**
 * Money, formatted in the BILL'S locale.
 *
 * Not the cashier's, and not the browser's. A bill issued in Amharic is an Amharic
 * document; a manager reading it at the till does not turn it into an English one. The
 * same rule M4-C applied to a reprinted receipt.
 */
function money(minor: string, currency: string, locale: string): string {
  const amount = Number(minor) / 100;
  try {
    return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function button(label: string, className: string, run: () => Promise<void>): HTMLElement {
  const node = element('button', className, label);
  node.setAttribute('type', 'button');
  node.addEventListener('click', () => {
    node.setAttribute('disabled', 'disabled');
    void run().finally(() => node.removeAttribute('disabled'));
  });
  return node;
}

/* ---------------------------------------------------------------------------
 * Confirmation friction, graded by the database
 * ------------------------------------------------------------------------- */

export function requirementFor(actionCode: string): Requirement {
  const found = requirements.find((r) => r.action_code === actionCode);
  // An action the catalogue does not know is treated as the MOST deliberate thing, not the
  // least. A till that silently treats an unknown action as routine is one migration away
  // from performing a refund with no confirmation at all.
  return found ?? { action_code: actionCode, consequence: 'deliberate', requires_reason: true };
}

/**
 * Ask, then run — with the friction the database says this action deserves.
 *
 * Routine actions run immediately. Anything above that shows a panel that states the
 * consequence in words, and where a reason is required the action does not proceed until
 * one is typed. The grading is never computed here.
 */
export function askThenRun(actionCode: string, label: string,
                           run: (reason: string) => void): void {
  const need = requirementFor(actionCode);
  if (need.consequence === 'routine') { run(''); return; }

  const panel = element('div', 'confirm');
  panel.id = 'confirm-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', `Confirm ${label}`);
  panel.appendChild(element('p', 'confirm-what',
    `${label} — ${need.consequence}. This is recorded against you.`));

  const reason = document.createElement('input');
  reason.id = 'confirm-reason';
  reason.type = 'text';
  reason.placeholder = 'Reason';
  reason.hidden = !need.requires_reason;
  panel.appendChild(reason);

  const yes = element('button', 'action confirm-yes', `Yes — ${label}`);
  yes.id = 'confirm-yes';
  yes.setAttribute('type', 'button');
  yes.addEventListener('click', () => {
    if (need.requires_reason && reason.value.trim() === '') {
      report(`${label}: a reason is required`);
      return;
    }
    panel.remove();
    run(reason.value.trim());
  });
  panel.appendChild(yes);

  const no = element('button', 'action confirm-no', 'No');
  no.setAttribute('type', 'button');
  no.addEventListener('click', () => panel.remove());
  panel.appendChild(no);

  (($('payment') ?? document.body)).appendChild(panel);
}

/* ---------------------------------------------------------------------------
 * The floor, the bill, the tip
 * ------------------------------------------------------------------------- */

export async function loadFloor(): Promise<void> {
  if (!session) return;
  const answer = await api('GET', '/s/v1/tables');
  const root = $('floor');
  if (!root) return;
  root.textContent = '';
  if (answer.status >= 400) { report(`tables: ${refusal(answer)}`); return; }

  const tables = (answer.data.tables ?? []) as Json[];
  if (tables.length === 0) {
    root.appendChild(element('p', 'empty', 'No open tables.'));
    return;
  }
  const list = element('ul', 'tables');
  for (const table of tables) {
    const row = element('li', 'row');
    row.setAttribute('data-table-session', String(table.table_session_id));
    row.appendChild(element('span', 'table-reference', String(table.table_reference)));
    row.appendChild(element('span', 'guests', `${String(table.guests ?? '?')} guest(s)`));
    row.appendChild(button('Open the bill', 'action', () =>
      openTable(String(table.table_session_id))));
    list.appendChild(row);
  }
  root.appendChild(list);
}

/** A table's check becomes a bill, or an existing bill is reopened. */
export async function openTable(tableSessionId: string): Promise<void> {
  const checks = await api('GET', `/s/v1/checks?tableSessionId=${tableSessionId}`);
  if (checks.status >= 400) { report(`checks: ${refusal(checks)}`); return; }
  const rows = (checks.data.checks ?? []) as Json[];
  const first = rows[0];
  if (!first) { report('this table has no check yet'); return; }

  const existing = first.bill_id ? String(first.bill_id) : null;
  if (existing) { await showBill(existing); return; }

  const issued = await api('POST', '/s/v1/bills', { checkId: String(first.check_id) });
  if (issued.status >= 400) { report(`bill: ${refusal(issued)}`); return; }
  await showBill(String(issued.data.billId));
}

/**
 * What the bill and tip boxes say before a bill is loaded (F-OPB-11).
 *
 * They said nothing. #bill and #tip-box are sections with a border and no heading, so a
 * cashier who had signed in and had no bill open saw two empty rectangles and nothing
 * telling them what they were or what to do next. Visible on first sight to somebody who
 * had not read the code, and invisible to every check in tests/opb — which measures both
 * boxes with a bill already in them, because that is the state the rules are about.
 *
 * The heading is the same heading the loaded state uses, so the box does not RENAME itself
 * when a bill arrives; only its contents change. A box whose title appears at the moment it
 * fills is a box that was unlabelled exactly when the label was needed.
 */
function labelEmptyBoxes(): void {
  const boxes: [string, string, string][] = [
    ['bill', 'Bill', 'No bill is open. Choose a table above to open one.'],
    ['tip-box', 'Tip — separate from the bill',
     'A tip is offered once a bill is open and split.'],
  ];
  for (const [id, heading, guidance] of boxes) {
    const root = $(id);
    if (!root) continue;
    root.textContent = '';
    root.appendChild(element('h2', `${id}-heading`, heading));
    root.appendChild(element('p', 'empty', guidance));
  }
}

export async function showBill(billId: string): Promise<void> {
  const answer = await api('GET', `/s/v1/bills/${billId}`);
  if (answer.status >= 400) { report(`bill: ${refusal(answer)}`); return; }

  bill = answer.data.bill as unknown as BillSummary;
  const lines = (answer.data.lines ?? []) as unknown as BillLine[];
  const root = $('bill');
  if (!root || !bill) return;

  root.textContent = '';
  // The box's own heading, the same words it carries when empty, OUTSIDE the summary. The
  // bill number below it is the document's identity, not the box's name, and the two were
  // conflated while the box had no name of its own.
  root.appendChild(element('h2', 'bill-heading', 'Bill'));

  const summary = element('section', 'bill-summary');
  summary.id = 'bill-summary';
  summary.setAttribute('data-bill', bill.id);
  summary.setAttribute('lang', bill.locale);
  summary.appendChild(element('h3', 'bill-number', bill.bill_number));

  for (const line of lines) {
    const row = element('div', `bill-line stage-${line.stage}`);
    row.appendChild(element('span', 'bill-label', line.label));
    row.appendChild(element('span', 'bill-amount',
      money(line.amount_minor, line.currency_code, bill.locale)));
    summary.appendChild(row);
  }

  const total = element('div', 'bill-line bill-total');
  total.id = 'bill-total';
  total.appendChild(element('span', 'bill-label', 'Total'));
  total.appendChild(element('span', 'bill-amount',
    money(bill.bill_total_minor, bill.currency_code, bill.locale)));
  summary.appendChild(total);

  const outstanding = element('div', 'bill-line bill-outstanding');
  outstanding.appendChild(element('span', 'bill-label', 'Outstanding'));
  outstanding.appendChild(element('span', 'bill-amount',
    money(bill.outstanding_minor, bill.currency_code, bill.locale)));
  summary.appendChild(outstanding);

  root.appendChild(summary);
  root.appendChild(splitControls(bill.id));

  await loadTipOptions(bill.id);
  renderPayment();
}

/** FR-BIL-003's modes, each one request. No amount is computed here. */
function splitControls(billId: string): HTMLElement {
  const box = element('div', 'splits');
  const modes: [string, string][] = [
    ['equal_share', 'Split equally'],
    ['by_item', 'Split by item'],
    ['by_participant', 'Split by participant'],
    ['custom_amount', 'Split by custom amount'],
  ];
  for (const [mode, label] of modes) {
    box.appendChild(button(label, 'action split', async () => {
      const body: Json = { mode };
      if (mode === 'equal_share') {
        const payers = Number(window.prompt('How many payers?', '2') ?? '0');
        if (!payers) return;
        body.payers = payers;
      }
      if (mode === 'custom_amount') {
        const amounts = (window.prompt('Amounts in minor units, comma separated', '') ?? '')
          .split(',').map((n) => Number(n.trim())).filter((n) => Number.isFinite(n) && n > 0);
        if (amounts.length === 0) return;
        body.amountsMinor = amounts;
      }
      const answer = await api('POST', `/s/v1/bills/${billId}/split`, body);
      if (answer.status >= 400) { report(`split: ${refusal(answer)}`); return; }
      report(`split into ${String(answer.data.shares)} share(s)`);
      await showBill(billId);
    }));
  }
  return box;
}

/**
 * The tip box.
 *
 * Rendered into #tip-box, which is a SIBLING of #bill. Nothing in this function touches
 * the bill's subtree, and no option is marked as chosen — there is no "selected" in what
 * the service returns and none is invented here.
 */
export async function loadTipOptions(billId: string): Promise<void> {
  const root = $('tip-box');
  if (!root) return;
  root.textContent = '';
  // The heading FIRST and unconditionally, so the box is named in all three of its states
  // — no bill, a bill with no tip on offer, and a bill with options. It used to appear
  // only in the third, which meant the box was anonymous in exactly the two states where
  // a cashier would be wondering what it was.
  root.appendChild(element('h2', 'tip-heading', 'Tip — separate from the bill'));

  const answer = await api('GET', `/s/v1/bills/${billId}/tip-options`);
  if (answer.status >= 400) return;
  const options = (answer.data.options ?? []) as unknown as TipOption[];
  const shareId = answer.data.shareId ? String(answer.data.shareId) : null;
  if (!shareId || options.length === 0) {
    root.appendChild(element('p', 'empty', 'No tip is offered for this bill.'));
    return;
  }

  const list = element('div', 'tip-options');
  list.id = 'tip-options';
  for (const option of options) {
    const node = element('button', 'action tip-option',
      `${option.percentage}% — ${money(option.amount_minor, option.currency_code,
                                       bill?.locale ?? 'en')}`);
    node.setAttribute('type', 'button');
    node.setAttribute('data-tip-percentage', option.percentage);
    // Deliberately no aria-pressed, no .selected, no checked. A tip nobody has chosen has
    // no chosen state to render, and rendering one would be the till deciding.
    list.appendChild(node);
  }
  root.appendChild(list);
  root.appendChild(element('p', 'tip-note',
    'A tip is optional and is not part of what the guest owes.'));
}

/* ---------------------------------------------------------------------------
 * Payment
 * ------------------------------------------------------------------------- */

function renderPayment(): void {
  const root = $('payment');
  if (!root || !bill) return;
  root.textContent = '';
  const current = bill;

  root.appendChild(button('Take cash', 'action pay-cash', async () => {
    const tendered = Number(window.prompt('Cash tendered, in minor units',
                                          current.outstanding_minor) ?? '0');
    if (!tendered) return;
    await takeCash(current, tendered);
  }));

  root.appendChild(button('Card on the terminal', 'action pay-terminal', async () => {
    await takeTerminal(current);
  }));

  for (const provider of ['telebirr_proof', 'cbe_birr_proof'] as const) {
    root.appendChild(button(`${provider === 'telebirr_proof' ? 'Telebirr' : 'CBE Birr'} proof`,
                            'action pay-proof', async () => {
      await takeProof(current, provider);
    }));
  }

  root.appendChild(button('Refund', 'action pay-refund', async () => {
    askThenRun('payment.refund', 'Refund', (reason) => {
      report(`refund requires a manager: ${reason || 'no reason given'}`);
      renderOverride('payment.refund', current.id, reason);
    });
  }));
}

async function intentFor(current: BillSummary): Promise<string | null> {
  if (intentId) return intentId;
  // An intent is money about to move, so the route requires an Idempotency-Key: a till
  // that double-submits because somebody tapped twice must not open two intents.
  const answer = await api('POST', '/s/v1/payments/intents', {
    billId: current.id, billAmountMinor: Number(current.outstanding_minor),
  }, newIdempotencyKey());
  if (answer.status >= 400) { report(`intent: ${refusal(answer)}`); return null; }
  intentId = String(answer.data.intentId ?? answer.data.id ?? '');
  return intentId || null;
}

async function takeCash(current: BillSummary, tenderedMinor: number): Promise<void> {
  const intent = await intentFor(current);
  if (!intent) return;
  const answer = await api('POST', `/s/v1/payments/${intent}/cash`, { tenderedMinor });
  if (answer.status >= 400) { report(`cash: ${refusal(answer)}`); return; }

  // CHANGE IS NOT IN THIS ANSWER, AND THAT IS DELIBERATE UPSTREAM. The cash route takes
  // what the guest handed over and records the change itself; it returns a paymentId and
  // no change field, because "a change amount computed in a browser is a number nobody
  // can reconcile against a drawer". The recorded figure surfaces in the drawer's
  // reconciliation, which is where a shift is counted.
  //
  // So the number below is labelled as what it is: this screen's own subtraction, shown
  // to help a cashier count coins into a hand, and never presented as the record.
  const owed = Number(current.outstanding_minor);
  const change = Math.max(0, tenderedMinor - owed);
  report(`cash taken (payment ${String(answer.data.paymentId).slice(0, 8)}…). `
       + `Count out ${money(String(change), current.currency_code, current.locale)} `
       + `— this till's arithmetic; the recorded change is in the drawer reconciliation.`);
  await showBill(current.id);
}

async function takeTerminal(current: BillSummary): Promise<void> {
  const intent = await intentFor(current);
  if (!intent) return;
  const reference = window.prompt('Terminal reference') ?? '';
  if (!reference) return;
  const recorded = await api('POST', '/s/v1/terminal-results', {
    terminalReference: reference, scheme: 'card',
    currencyCode: current.currency_code,
    amountMinor: Number(current.outstanding_minor), outcome: 'approved',
  });
  if (recorded.status >= 400) { report(`terminal: ${refusal(recorded)}`); return; }
  const answer = await api('POST', `/s/v1/payments/${intent}/terminal`, {
    terminalResultId: String(recorded.data.terminalResultId ?? recorded.data.id),
    tenderedMinor: Number(current.outstanding_minor),
  });
  if (answer.status >= 400) { report(`terminal: ${refusal(answer)}`); return; }
  report('card recorded from the terminal');
  await showBill(current.id);
}

async function takeProof(current: BillSummary, provider: string): Promise<void> {
  const intent = await intentFor(current);
  if (!intent) return;
  const reference = window.prompt(`${provider} reference`) ?? '';
  if (!reference) return;

  const proof = await api('POST', '/s/v1/proofs', {
    provider, currencyCode: current.currency_code,
    amountMinor: Number(current.outstanding_minor), providerReference: reference,
  });
  if (proof.status >= 400) { report(`proof: ${refusal(proof)}`); return; }
  const proofId = String(proof.data.proofId ?? proof.data.id);

  // VERIFIED BY A PERSON WHO SAYS WHAT THEY SAW. FR-PAY-006 asks for an attestation, not a
  // checkbox, so the words go to the service and are recorded against this session.
  const saw = window.prompt('What did you see on the payer’s screen?') ?? '';
  if (!saw) return;
  const verified = await api('POST', `/s/v1/proofs/${proofId}/verify`, { whatYouSaw: saw });
  if (verified.status >= 400) { report(`verify: ${refusal(verified)}`); return; }

  const answer = await api('POST', `/s/v1/payments/${intent}/proof`, {
    proofId, tenderedMinor: Number(current.outstanding_minor),
  });
  if (answer.status >= 400) { report(`proof payment: ${refusal(answer)}`); return; }
  report(`${provider} accepted`);
  await showBill(current.id);
}

/* ---------------------------------------------------------------------------
 * Manager override — on the manager's own session
 * ------------------------------------------------------------------------- */

export function renderOverride(actionCode: string, subjectId: string,
                               reason: string): void {
  const root = $('payment');
  if (!root) return;
  const panel = element('form', 'override');
  panel.id = 'override-panel';
  panel.appendChild(element('p', 'override-what',
    `${actionCode} needs a manager. The manager signs in here, on their own session.`));

  const email = document.createElement('input');
  email.id = 'override-email';
  email.type = 'text';
  email.placeholder = 'Manager email';
  const secret = document.createElement('input');
  secret.id = 'override-secret';
  secret.type = 'password';
  secret.placeholder = 'Manager password';
  panel.appendChild(email);
  panel.appendChild(secret);

  const approve = element('button', 'action override-approve', 'Approve');
  approve.id = 'override-approve';
  approve.setAttribute('type', 'submit');
  panel.appendChild(approve);

  panel.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      // A SECOND SESSION, NOT A SECOND PASSWORD ON THIS ONE. The manager authenticates and
      // the override carries THEIR session id. Nothing here puts the manager's credential
      // into the cashier's session, and the cashier's own session id would be refused by
      // pos.approve_override() as a self-approval.
      const answer = await api('POST', '/v1/auth/login', {
        tenantId: sessionStorage.getItem('cashier.tenant'),
        outletId: sessionStorage.getItem('cashier.outlet'),
        channel: 'email', channelValue: email.value,
        kind: 'password', secret: secret.value,
      });
      if (answer.status !== 200 || !answer.data.sessionId) {
        report(`override: the manager could not sign in (${refusal(answer)})`);
        return;
      }
      const approved = await api('POST', '/s/v1/overrides', {
        actionCode, approverSessionId: String(answer.data.sessionId),
        reasonCodeId: sessionStorage.getItem('cashier.reasonCode'),
        subjectKind: 'bill', subjectId, reasonText: reason,
      });
      report(approved.status >= 400
        ? `override refused: ${refusal(approved)}`
        : 'override approved by the manager');
      panel.remove();
    })();
  });
  root.appendChild(panel);
}

/* ---------------------------------------------------------------------------
 * The receipt
 * ------------------------------------------------------------------------- */

export async function issueReceipt(billId: string,
                                   paymentMethod = 'cash'): Promise<void> {
  // The method is carried as words rather than a code, because a receipt says how the
  // guest paid in the language a guest and a cashier both use.
  const answer = await api('POST', '/s/v1/receipts', { billId, paymentMethod });
  const root = $('receipt');
  if (!root) return;
  if (answer.status >= 400) { report(`receipt: ${refusal(answer)}`); return; }
  const receiptId = String(answer.data.receiptId ?? answer.data.id);
  const got = await api('GET', `/s/v1/receipts/${receiptId}`);
  root.textContent = '';
  root.setAttribute('data-receipt', receiptId);
  root.appendChild(element('h2', 'receipt-heading', 'Receipt'));
  root.appendChild(element('pre', 'receipt-body',
    JSON.stringify(got.data, null, 2).slice(0, 4000)));
  report('receipt issued');
}

/* ---------------------------------------------------------------------------
 * Sign in
 * ------------------------------------------------------------------------- */

export async function signIn(tenantId: string, outletId: string,
                             channelValue: string, secret: string): Promise<boolean> {
  const answer = await api('POST', '/v1/auth/login', {
    tenantId, outletId, channel: 'email', channelValue, kind: 'password', secret,
  });
  if (answer.status !== 200 || !answer.data.token) return false;
  session = { token: String(answer.data.token),
              sessionId: String(answer.data.sessionId ?? '') };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  sessionStorage.setItem('cashier.tenant', tenantId);
  sessionStorage.setItem('cashier.outlet', outletId);
  await afterSignIn();
  return true;
}

async function afterSignIn(): Promise<void> {
  // Signed in with no bill open is the state a cashier is in most of the day, and it is
  // the state the two boxes were blank in.
  labelEmptyBoxes();
  const answer = await api('GET', '/s/v1/confirmation-requirements');
  requirements = (answer.data.requirements ?? []) as unknown as Requirement[];
  await loadFloor();
}

function renderSignIn(): void {
  const root = $('floor');
  if (!root) return;
  root.textContent = '';
  labelEmptyBoxes();
  const form = element('form', 'sign-in');
  form.id = 'sign-in';

  function field(name: string, label: string, type: string): HTMLInputElement {
    const row = element('label', 'field', label);
    const input = document.createElement('input');
    input.type = type;
    input.name = name;
    input.id = `sign-in-${name}`;
    row.appendChild(input);
    form.appendChild(row);
    return input;
  }

  const tenantId = field('tenantId', 'Tenant', 'text');
  const outletId = field('outletId', 'Outlet', 'text');
  const channelValue = field('channelValue', 'Email', 'text');
  const secret = field('secret', 'Password', 'password');

  const submit = element('button', 'action', 'Sign in');
  submit.setAttribute('type', 'submit');
  form.appendChild(submit);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      const ok = await signIn(tenantId.value, outletId.value,
                              channelValue.value, secret.value);
      if (!ok) report('sign in: refused');
    })();
  });
  root.appendChild(form);
}

declare global {
  interface Window {
    cashierSurface: {
      signIn: typeof signIn;
      loadFloor: typeof loadFloor;
      openTable: typeof openTable;
      showBill: typeof showBill;
      loadTipOptions: typeof loadTipOptions;
      issueReceipt: typeof issueReceipt;
      askThenRun: typeof askThenRun;
      requirementFor: typeof requirementFor;
      renderOverride: typeof renderOverride;
    };
  }
}

window.cashierSurface = { signIn, loadFloor, openTable, showBill, loadTipOptions,
                          issueReceipt, askThenRun, requirementFor, renderOverride };

// Nothing is fetched without a session, for the same reason as the station board: the
// surface must be openable and measurable with no service behind it.
try {
  const raw = sessionStorage.getItem(SESSION_KEY);
  session = raw ? JSON.parse(raw) as Session : null;
} catch { session = null; }
if (session) void afterSignIn();
else if ($('floor')) renderSignIn();
