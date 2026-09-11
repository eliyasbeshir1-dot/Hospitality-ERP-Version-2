/**
 * The station surface.
 *
 * Vanilla TypeScript, no runtime dependency, and deliberately small: it exists so that
 * FR-FUL-003, FR-FUL-008 and FR-SAF-004 — all claims about what a station SEES — can be
 * measured in a real browser rather than asserted from a payload. The full staff
 * experience is M3-D.
 *
 * The rule that shapes every function below: NOTHING IS CONVEYED BY COLOUR. Each fact a
 * station acts on is rendered as words, and where it needs emphasis it also gets weight,
 * size and a glyph. Nothing in this file sets a colour at all — the stylesheet carries
 * one ink and one paper, and the surface is measured again with those flattened.
 */

export type Bucket =
  | 'new' | 'acknowledged' | 'held' | 'preparing' | 'ready' | 'completed' | 'exception';

/** FR-FUL-003's seven display buckets, in the order a station reads them. */
export const BUCKETS: readonly Bucket[] = [
  'new', 'acknowledged', 'held', 'preparing', 'ready', 'completed', 'exception',
] as const;

export interface QueueTicket {
  ticket_id: string;
  order_number: string;
  bucket: Bucket;
  state: string;
  priority: string;
  priority_reason: string | null;
  priority_by: string | null;
  elapsed_seconds: number;
  sla_due_at: string | null;
  sla_breached: boolean | null;
  units: number;
  ready_units: number;
  allergy_count: number;
  allergy_acknowledged: boolean;
}

export interface AllergyEmphasis {
  kitchen_code: string;
  written_warning: string;
  acknowledgement_text: string | null;
  emphasis_rank: number;
  emphasis_glyph: string;
}

export interface TicketDetail {
  ticket: { id: string; state: string; priority: string; order_number: string;
            allergy_acknowledged: boolean };
  lines: { id: string; quantity: number; ready_quantity: number;
           item_code: string; canonical_name: string }[];
  allergies: AllergyEmphasis[];
  notes: { kind: string; body: string }[];
}

export interface ExpoView {
  tickets: { ticket_id: string; station_kind: string; state: string; units: number;
             ready_units: number; allergy_declarations: number;
             allergy_acknowledged: boolean }[];
  blocking: { reason: string; ticket_id: string | null; detail: string }[];
  fulfillmentState: string | null;
}

function element(tag: string, className?: string, text?: string): HTMLElement {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * The allergy block.
 *
 * The order of the statements here is the guarantee, and it is the same one M2-C made on
 * the customer surface: THE WORDS ARE APPENDED FIRST, and the glyph element is not
 * constructed at all unless there is a written warning to sit beside. There is no
 * ordering of these lines — and no later edit to them — that produces a mark on a
 * kitchen screen with nothing to read.
 */
export function renderAllergy(emphasis: AllergyEmphasis, acknowledged: boolean): HTMLElement {
  const block = element('p', 'allergy');
  block.setAttribute('role', 'alert');

  if (!emphasis.written_warning || emphasis.written_warning.trim() === '') {
    // Refused outright rather than rendered as a code on its own. A kitchen code with no
    // sentence behind it is the shape of the defect M2-B closed by privilege.
    block.textContent = 'ALLERGY DECLARED — WARNING TEXT UNAVAILABLE, ASK THE FLOOR';
    return block;
  }

  block.appendChild(document.createTextNode(
    `ALLERGY ${emphasis.kitchen_code} — ${emphasis.written_warning}`));

  const glyph = element('span', 'allergy-glyph', emphasis.emphasis_glyph);
  glyph.setAttribute('aria-hidden', 'true');
  block.insertBefore(glyph, block.firstChild);

  if (emphasis.acknowledgement_text) {
    block.appendChild(element('span', 'allergy-ack',
      `Told to the guest: ${emphasis.acknowledgement_text}`));
  }
  if (!acknowledged) block.classList.add('allergy-unacknowledged');
  return block;
}

/** One row of the queue. Every fact is a word; nothing is a colour or a position. */
export function renderQueueTicket(ticket: QueueTicket): HTMLElement {
  const card = element('article', 'ticket');
  card.setAttribute('data-ticket', ticket.ticket_id);
  card.setAttribute('data-bucket', ticket.bucket);

  const head = element('div', 'ticket-head');
  head.appendChild(element('span', 'bucket', ticket.bucket));
  head.appendChild(element('span', 'order-number', `Order ${ticket.order_number}`));

  const elapsed = element('span', ticket.sla_breached ? 'elapsed breached' : 'elapsed',
    `${Math.floor(ticket.elapsed_seconds / 60)}m ${ticket.elapsed_seconds % 60}s`);
  head.appendChild(elapsed);

  // FR-FUL-007: the level AND who applied it AND why, together. A priority rendered
  // without its attribution is the thing the requirement exists to prevent.
  if (ticket.priority !== 'ordinary') {
    head.appendChild(element('span', 'priority', ticket.priority.toUpperCase()));
    head.appendChild(element('span', 'priority-attribution',
      ticket.priority_by
        ? `set by ${ticket.priority_by}${ticket.priority_reason ? ` (${ticket.priority_reason})` : ''}`
        : 'set by nobody on record'));
  }
  card.appendChild(head);

  if (ticket.allergy_count > 0) {
    const flag = element('p', 'allergy',
      `${ticket.allergy_count} ALLERGY DECLARATION${ticket.allergy_count > 1 ? 'S' : ''}`);
    flag.setAttribute('role', 'alert');
    if (!ticket.allergy_acknowledged) flag.classList.add('allergy-unacknowledged');
    card.appendChild(flag);
  }

  card.appendChild(element('p', 'progress',
    `${ticket.ready_units} of ${ticket.units} unit(s) ready`));
  return card;
}

export function renderQueue(root: HTMLElement, tickets: QueueTicket[]): void {
  root.textContent = '';
  if (tickets.length === 0) {
    root.appendChild(element('p', 'empty', 'No tickets at this station.'));
    return;
  }
  for (const bucket of BUCKETS) {
    const inBucket = tickets.filter((t) => t.bucket === bucket);
    if (inBucket.length === 0) continue;
    const group = element('section', 'bucket-group');
    group.setAttribute('data-bucket-group', bucket);
    group.appendChild(element('h2', 'bucket', `${bucket} (${inBucket.length})`));
    for (const ticket of inBucket) group.appendChild(renderQueueTicket(ticket));
    root.appendChild(group);
  }
}

/** The ticket a station opens before it starts. Allergies first, always. */
export function renderTicket(root: HTMLElement, detail: TicketDetail): void {
  root.textContent = '';
  const card = element('article', 'ticket');
  card.setAttribute('data-ticket-detail', detail.ticket.id);

  // FIRST, before the lines. A station reading top to bottom meets the allergy before it
  // meets the dish, which is the whole of "prominently" in FR-SAF-004.
  for (const allergy of detail.allergies) {
    card.appendChild(renderAllergy(allergy, detail.ticket.allergy_acknowledged));
  }

  const head = element('div', 'ticket-head');
  head.appendChild(element('span', 'bucket', detail.ticket.state));
  head.appendChild(element('span', 'order-number', `Order ${detail.ticket.order_number}`));
  card.appendChild(head);

  for (const line of detail.lines) {
    const row = element('div', 'line');
    row.appendChild(element('span', 'line-quantity', `${line.quantity}`));
    row.appendChild(element('span', 'line-name', line.canonical_name));
    row.appendChild(element('span', 'progress',
      `${line.ready_quantity}/${line.quantity} ready`));
    card.appendChild(row);
  }
  for (const note of detail.notes) {
    card.appendChild(element('p', 'note', note.body));
  }
  root.appendChild(card);
}

/** FR-FUL-009. What is ready, and in words why service is blocked. */
export function renderExpo(root: HTMLElement, view: ExpoView): void {
  root.textContent = '';
  root.appendChild(element('h2', 'bucket',
    `Expo — ${view.fulfillmentState ?? 'not released'}`));

  for (const ticket of view.tickets) {
    const card = element('article', 'ticket');
    card.setAttribute('data-expo-ticket', ticket.ticket_id);
    card.appendChild(element('span', 'bucket',
      `${ticket.station_kind}: ${ticket.state}`));
    card.appendChild(element('span', 'progress',
      ` ${ticket.ready_units} of ${ticket.units} ready`));
    if (ticket.allergy_declarations > 0) {
      const flag = element('p', 'allergy',
        `${ticket.allergy_declarations} ALLERGY DECLARATION${ticket.allergy_declarations > 1 ? 'S' : ''}`);
      flag.setAttribute('role', 'alert');
      if (!ticket.allergy_acknowledged) flag.classList.add('allergy-unacknowledged');
      card.appendChild(flag);
    }
    root.appendChild(card);
  }

  // A refusal that says why. "Not yet" without a reason is what makes an expo screen an
  // obstacle rather than a tool, and this renders the same reasons the database gives
  // release_to_service() — not a second opinion about readiness.
  for (const block of view.blocking) {
    root.appendChild(element('p', 'block', `${block.reason} — ${block.detail}`));
  }
  if (view.blocking.length === 0 && view.tickets.length > 0) {
    root.appendChild(element('p', 'ready-to-serve', 'Complete set — ready to serve.'));
  }
}

/** Draw without fetching, for measurement. The probe supplies the data. */
export function renderAll(payload: {
  queue?: QueueTicket[]; detail?: TicketDetail; expo?: ExpoView;
}): void {
  const queue = document.getElementById('queue');
  const detail = document.getElementById('detail');
  const expo = document.getElementById('expo');
  if (queue && payload.queue) renderQueue(queue, payload.queue);
  if (detail && payload.detail) renderTicket(detail, payload.detail);
  if (expo && payload.expo) renderExpo(expo, payload.expo);
}

/* ===========================================================================
 * THE NETWORK LAYER (OP-B)
 * ===========================================================================
 *
 * Everything above renders. Until OP-B nothing above was ever CALLED by anything but a
 * test handing it a payload: this file contained no fetch, so OP-A's thirteen kitchen
 * routes existed and no cook could reach one. A screen that can only be driven by its own
 * test suite is the same defect as a route with no caller, one layer out.
 *
 * TWO RULES SHAPE WHAT FOLLOWS.
 *
 * First, NOTHING HERE DECIDES WHAT IS LEGAL. The buttons on a ticket are drawn from the
 * `transitions` the service returns, which it reads from fulfillment.transition — the same
 * ordered pairs the database enforces. This file contains no state table, no list of
 * allowed moves, and no opinion about what a cook may do next. If the machine changes,
 * this screen changes with it without being edited.
 *
 * Second, THE RENDER FUNCTIONS STAY PURE. M3-B measures this surface by calling
 * window.stationSurface.renderAll(payload) in a browser with no service behind it, and
 * that must keep working exactly as it did. So nothing below runs on import except
 * attaching the surface object and looking for a saved session; with no session the screen
 * shows a sign-in panel and issues no requests at all, which is the state M3-B measures in.
 */

interface Session { token: string; stationId: string; base: string; }

const SESSION_KEY = 'station.session';
let session: Session | null = null;
let poller: number | null = null;

function saved(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) as Session : null;
  } catch { return null; }
}

async function api(method: string, path: string, body?: unknown): Promise<{
  status: number; data: Record<string, unknown>;
}> {
  const response = await fetch(path, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(session ? { authorization: `Bearer ${session.token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  let data: Record<string, unknown> = {};
  try { data = text ? JSON.parse(text) as Record<string, unknown> : {}; } catch { /* not json */ }
  return { status: response.status, data };
}

/** A refusal is shown, never swallowed. A cook who taps and sees nothing taps again. */
function report(message: string): void {
  const bar = document.getElementById('notice') ?? element('p', 'notice');
  bar.id = 'notice';
  bar.setAttribute('role', 'status');
  bar.textContent = message;
  document.body.insertBefore(bar, document.body.firstChild);
}

/**
 * One action button.
 *
 * Large by default because FR-UX-002 asks for a target a cook can hit at arm's length
 * with wet hands, and because the alternative — a dense list of small controls — is the
 * shape that makes people tap the wrong ticket.
 */
function actionButton(label: string, run: () => Promise<void>): HTMLElement {
  const button = element('button', 'action', label);
  button.setAttribute('type', 'button');
  button.addEventListener('click', () => {
    button.setAttribute('disabled', 'disabled');
    void run().finally(() => button.removeAttribute('disabled'));
  });
  return button;
}

async function act(method: string, path: string, body: unknown, what: string): Promise<void> {
  const answer = await api(method, path, body);
  if (answer.status >= 400) {
    // The database's own words. A screen that translates a refusal into "something went
    // wrong" has thrown away the only part a cook can act on.
    report(`${what}: ${String(answer.data.reason ?? answer.data.error ?? answer.status)}`);
    return;
  }
  report(`${what}: done`);
  await refresh();
}

export async function openTicket(ticketId: string): Promise<void> {
  if (!session) return;
  const answer = await api('GET', `/s/v1/tickets/${ticketId}`);
  if (answer.status >= 400) { report(`ticket: ${answer.status}`); return; }

  const detail = answer.data as unknown as TicketDetail & {
    transitions: { to_state: string; reason: string }[];
  };
  const root = document.getElementById('detail');
  if (!root) return;
  renderTicket(root, detail);

  const actions = element('div', 'actions');

  // THE ALLERGY ACKNOWLEDGEMENT COMES FIRST, and only while there is one to make. It is
  // the one action whose absence is a safety matter rather than an inconvenience.
  if (detail.allergies.length > 0 && !detail.ticket.allergy_acknowledged) {
    actions.appendChild(actionButton('Acknowledge allergy', () =>
      act('POST', `/s/v1/tickets/${ticketId}/allergy-acknowledgement`, {},
          'allergy acknowledgement')));
  }

  // DRAWN FROM THE CATALOG, NOT FROM A TABLE IN THIS FILE. Each button is one row of
  // fulfillment.transition for this ticket's current state, and its label is the reason
  // the database records for that pair — so the button says what the move means in the
  // machine's own words rather than in this surface's.
  for (const move of detail.transitions ?? []) {
    actions.appendChild(actionButton(`${move.to_state} — ${move.reason}`, () =>
      act('POST', `/s/v1/tickets/${ticketId}/transitions`,
          { toState: move.to_state }, move.to_state)));
  }

  for (const line of detail.lines) {
    if (line.ready_quantity < line.quantity) {
      actions.appendChild(actionButton(
        `+1 ready — ${line.canonical_name}`, () =>
        act('POST', `/s/v1/tickets/${ticketId}/unit-progress`,
            { ticketLineId: line.id, readyQuantity: line.ready_quantity + 1 },
            'unit progress')));
    }
  }

  actions.appendChild(actionButton('Recall', () =>
    act('POST', `/s/v1/tickets/${ticketId}/recall`,
        { reason: 'recalled from the station board' }, 'recall')));
  actions.appendChild(actionButton('Waste', () =>
    act('POST', `/s/v1/tickets/${ticketId}/waste`,
        { reason: 'wasted at the station' }, 'waste')));
  actions.appendChild(actionButton('Priority — rush', () =>
    act('POST', `/s/v1/tickets/${ticketId}/priority`,
        { priority: 'rush', reason: 'set from the station board' }, 'priority')));

  root.appendChild(actions);
}

export async function refresh(): Promise<void> {
  if (!session) return;
  const queue = await api('GET', `/s/v1/stations/${session.stationId}/queue`);
  if (queue.status === 401) { signOut(); return; }
  const root = document.getElementById('queue');
  if (!root) return;

  const tickets = (queue.data.tickets ?? []) as QueueTicket[];
  renderQueue(root, tickets);

  // Opening a ticket is how a cook starts work, so the whole card is the target rather
  // than a separate control on it.
  for (const card of Array.from(root.querySelectorAll('[data-ticket]'))) {
    const id = card.getAttribute('data-ticket');
    if (id) card.addEventListener('click', () => { void openTicket(id); });
  }
}

function signOut(): void {
  session = null;
  sessionStorage.removeItem(SESSION_KEY);
  if (poller !== null) { clearInterval(poller); poller = null; }
  renderSignIn();
}

function renderSignIn(): void {
  const root = document.getElementById('queue');
  if (!root) return;
  root.textContent = '';
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
  const stationId = field('stationId', 'Station', 'text');
  const channelValue = field('channelValue', 'Email', 'text');
  const secret = field('secret', 'Password', 'password');

  const submit = element('button', 'action', 'Sign in');
  submit.setAttribute('type', 'submit');
  form.appendChild(submit);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      const ok = await signIn(tenantId.value, outletId.value, stationId.value,
                              channelValue.value, secret.value);
      if (!ok) report('sign in: refused');
    })();
  });
  root.appendChild(form);
}

function start(): void {
  void refresh();
  // Polling, not a socket. M5a owns the outlet node and anything that pushes; a board that
  // re-reads its own queue is the honest amount of machinery for what this gate delivers.
  if (poller === null) poller = window.setInterval(() => { void refresh(); }, 5000);
}

export async function signIn(tenantId: string, outletId: string, stationId: string,
                             channelValue: string, secret: string): Promise<boolean> {
  const answer = await api('POST', '/v1/auth/login', {
    tenantId, outletId, channel: 'email', channelValue, kind: 'password', secret,
  });
  if (answer.status !== 200 || !answer.data.token) return false;
  session = { token: String(answer.data.token), stationId, base: '' };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  start();
  return true;
}

export async function loadExpo(orderId: string): Promise<void> {
  if (!session) return;
  const answer = await api('GET', `/s/v1/orders/${orderId}/expo`);
  const root = document.getElementById('expo');
  if (!root || answer.status >= 400) return;
  renderExpo(root, answer.data as unknown as ExpoView);

  const release = actionButton('Release to service', () =>
    act('POST', `/s/v1/orders/${orderId}/release-to-service`, {}, 'release to service'));
  root.appendChild(release);
}

declare global {
  interface Window {
    stationSurface: {
      renderAll: typeof renderAll;
      renderAllergy: typeof renderAllergy;
      BUCKETS: readonly Bucket[];
      signIn: typeof signIn;
      refresh: typeof refresh;
      openTicket: typeof openTicket;
      loadExpo: typeof loadExpo;
    };
  }
}

window.stationSurface = { renderAll, renderAllergy, BUCKETS, signIn, refresh,
                          openTicket, loadExpo };

// NOTHING IS FETCHED WITHOUT A SESSION. This is what keeps M3-B's measurement honest: it
// opens this page with no service to talk to, calls renderAll() with its own payload, and
// measures the result. With no saved session there is no poll to overwrite what it drew.
session = saved();
if (session) start();
else if (document.getElementById('queue')) renderSignIn();
