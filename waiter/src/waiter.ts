/**
 * The waiter surface.
 *
 * Vanilla TypeScript, no runtime dependency, and shaped by one idea: A WAITER IS
 * CARRYING SOMETHING. Everything below assumes a person moving between tables with one
 * hand free, glancing at a screen for a second at a time — not somebody sitting down to
 * read it. So the screen answers one question, "what should I do next", and every other
 * view is subordinate to that.
 *
 * FOUR properties are load-bearing, and the suite measures each of them in a browser
 * rather than reading this file.
 *
 * 1. THE NEXT REQUIRED ACTION IS THE BIGGEST THING ON THE ROW (FR-UX-004). Not first,
 *    not coloured — measurably larger, so it survives being glanced at.
 *
 * 2. THE ORDER OF THE LIST IS THE PRIORITY (FR-POS-002). It comes from pos.role_home(),
 *    which sorts overdue first and oldest first within that. This file does not re-sort:
 *    a screen that re-orders the queue it was given is a second opinion about what
 *    matters, and the two will disagree.
 *
 * 3. FRICTION IS GRADED BY CONSEQUENCE AND THE GRADE COMES FROM THE SERVER
 *    (FR-UX-015). pos.confirmation_requirement decides whether an action needs a
 *    confirmation and whether it needs a reason. Nothing here decides that, and there is
 *    no branch by which a deliberate action could be confirmed like a routine one — the
 *    grade is looked up, and an action with no grade is treated as deliberate rather
 *    than waved through, because an unknown consequence is not a small one.
 *
 * 4. NOTHING IS CARRIED BY COLOUR ALONE. Inherited from M3-B. An overdue row differs in
 *    words and weight; the stylesheet's colour is reinforcement.
 *
 * Accessibility mode (FR-UX-008) is a class on the document element, so every rule that
 * responds to it lives beside the rule it modifies and neither can be forgotten.
 */

export type Consequence = 'routine' | 'elevated' | 'deliberate';

export interface ConfirmationRequirement {
  action_code: string;
  consequence: Consequence;
  requires_reason: boolean;
}

export interface HomeRow {
  queue: string;
  subject_kind: string;
  subject_id: string;
  headline: string;
  next_action: string;
  waiting_since: string;
  elapsed_seconds: number;
  overdue: boolean;
}

export interface TableRow {
  table_session_id: string;
  table_reference: string;
  guests: number;
  assigned_waiter_id: string | null;
  open_requests: number;
  overdue_requests: number;
  open_orders: number;
  order_progress: string | null;
  unpaid_balance_minor: string | null;
  needs_attention: boolean;
  attention_reason: string | null;
}

/**
 * An order placed and not yet admitted to the kitchen (FR-ORD-004, FR-ORD-007A).
 *
 * Only exists where the outlet's ordering policy says a channel is `staff_confirmed`. On
 * a floor whose guest_qr acceptance is `automatic` this list is always empty and the
 * section is not drawn at all — which is the demonstration floor's case after seeds/0009,
 * and is why the empty state here is silence rather than "nothing waiting".
 */
export interface PendingOrderRow {
  order_id: string;
  order_number: string;
  table_reference: string | null;
  origin: string;
  waiting_seconds: number;
  lines: number;
  total_amount_minor: string;
  currency_code: string;
}

/**
 * A table with nobody at it (FR-TAB-003).
 *
 * pos.table_view() returns one row per OPEN occupancy, so free tables are correctly absent
 * from TableRow above. This is the complement, from pos.seatable_tables(), and it is what
 * the waiter seats from.
 */
export interface SeatableRow {
  table_node_id: string;
  table_reference: string;
  display_name: string | null;
  seat_count: number | null;
}

export interface NotificationRow {
  notice_id: string;
  event_id: string;
  severity: string;
  body: string;
  state: string;
  emitted_at: string;
}

export interface SearchRow {
  item_id: string;
  item_code: string;
  display_name: string;
  amount_minor: string;
  currency_code: string;
  availability: string;
}

/**
 * The action a queue row offers, mapped to the action code the server grades. A row's
 * next_action is a verb for a person; the grade is registered against the action code
 * the system knows. Keeping the mapping here, in one object, means a new verb without a
 * grade is a missing key rather than a silently routine confirmation.
 */
const ACTION_CODES: Record<string, string> = {
  acknowledge: 'service_request.acknowledge',
  start: 'service_request.acknowledge',
  complete: 'service_request.complete',
  review: 'order.view',
  'check on the table': 'order.view',
};

const state: {
  requirements: Map<string, ConfirmationRequirement>;
  home: HomeRow[];
  tables: TableRow[];
  seatable: SeatableRow[];
  pendingOrders: PendingOrderRow[];
  notifications: NotificationRow[];
  results: SearchRow[];
  pending: { actionCode: string; label: string; run: (reason: string | null) => void } | null;
} = {
  requirements: new Map(),
  home: [],
  tables: [],
  seatable: [],
  pendingOrders: [],
  notifications: [],
  results: [],
  pending: null,
};

function $(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element: ${id}`);
  return node;
}

/** Optional by id. Used only where an element genuinely may not be on the page. */
function maybe(id: string): HTMLElement | null { return document.getElementById(id); }

function notice(message: string | null): void {
  const bar = maybe('notice');
  if (!bar) return;
  if (message === null) { bar.hidden = true; bar.textContent = ''; return; }
  bar.textContent = message;
  bar.hidden = false;
}

function minutes(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/**
 * The grade for an action code. An UNREGISTERED action is deliberate, not routine.
 *
 * This is the fail-closed direction, and it is the whole reason the default is written
 * down rather than left to a `?? 'routine'`. A new destructive action that nobody
 * remembered to grade would otherwise be confirmed with a single tap.
 */
export function gradeFor(actionCode: string): ConfirmationRequirement {
  const found = state.requirements.get(actionCode);
  if (found) return found;
  return { action_code: actionCode, consequence: 'deliberate', requires_reason: true };
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderHome(): void {
  const main = $('next');
  main.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Next';
  main.appendChild(heading);

  if (state.home.length === 0) {
    const calm = document.createElement('p');
    calm.className = 'meta';
    calm.textContent = 'Nothing waiting.';
    main.appendChild(calm);
    return;
  }

  const list = document.createElement('ul');
  // NOT sorted here. pos.role_home() returned these in priority order and re-sorting
  // would be a second opinion about what matters most.
  for (const row of state.home) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.overdue = String(row.overdue);
    item.dataset.queue = row.queue;
    item.dataset.subjectId = row.subject_id;

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = row.headline;
    const elapsed = document.createElement('span');
    elapsed.className = 'elapsed';
    // Elapsed time in WORDS beside the row, because FR-UX-004 asks for elapsed time and
    // a timestamp is not elapsed time to somebody holding two plates.
    elapsed.textContent = ` · waiting ${minutes(row.elapsed_seconds)}`;
    text.append(headline, elapsed);

    const actionCode = ACTION_CODES[row.next_action] ?? row.next_action;
    const grade = gradeFor(actionCode);
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'primary';
    button.dataset.consequence = grade.consequence;
    button.dataset.action = actionCode;
    button.textContent = row.next_action;
    button.addEventListener('click', () => {
      askThenRun(actionCode, row.next_action, () => undefined);
    });

    item.append(text, button);
    list.appendChild(item);
  }
  main.appendChild(list);
}

/**
 * Orders placed and not yet admitted to the kitchen (FR-ORD-004).
 *
 * ABOVE THE TABLES, AND THAT IS THE ONLY JUDGEMENT HERE. FR-POS-002 says the order of the
 * screen is the priority. A guest who has ordered and is waiting for somebody to press a
 * button outranks a table that merely exists — the food has not started, and every second
 * is on the guest's meal rather than on the kitchen's.
 *
 * DRAWN ONLY WHEN THERE IS SOMETHING IN IT. Where the outlet accepts guest_qr orders
 * automatically this list is permanently empty, and a permanent "Nothing waiting" heading
 * is a heading a waiter learns to stop reading. Silence is the correct empty state for a
 * section that exists only under one policy.
 */
function renderPendingOrders(): void {
  const section = maybe('pending-orders');
  if (!section) return;
  section.replaceChildren();
  section.hidden = state.pendingOrders.length === 0;
  if (state.pendingOrders.length === 0) return;

  const heading = document.createElement('h2');
  heading.textContent = 'Waiting to be confirmed';
  section.appendChild(heading);

  const list = document.createElement('ul');
  list.id = 'pending-order-list';
  // NOT re-sorted. pos.pending_orders() returns oldest first, which is the order they
  // should be dealt with, and a second opinion here would disagree with the server's.
  for (const row of state.pendingOrders) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.orderId = row.order_id;
    item.dataset.orderNumber = row.order_number;
    // Long waits read as overdue in words and weight, using the same signal the queue
    // rows use rather than a second vocabulary. Five minutes is not a configured SLA and
    // is not presented as one — it is the point past which this screen says so out loud.
    item.dataset.overdue = String(row.waiting_seconds >= 300);

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = row.table_reference
      ? `Table ${row.table_reference} — ${row.lines} item${row.lines === 1 ? '' : 's'}`
      : `${row.order_number} — ${row.lines} item${row.lines === 1 ? '' : 's'}`;

    const meta = document.createElement('span');
    meta.className = 'elapsed';
    // Elapsed time in WORDS, as everywhere else on this screen. The order number travels
    // too: it is what a waiter reads back to a guest who asks.
    meta.textContent = ` · waiting ${minutes(row.waiting_seconds)} · ${row.order_number}`;
    text.append(headline, meta);

    const grade = gradeFor('order.accept');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'primary';
    button.dataset.consequence = grade.consequence;
    button.dataset.action = 'order.accept';
    button.dataset.orderId = row.order_id;
    button.textContent = 'Confirm';
    button.addEventListener('click', () => {
      askThenRun('order.accept',
                 `Confirm ${row.table_reference ? `table ${row.table_reference}` : row.order_number}`,
                 () => { void acceptOrder(row.order_id, row.table_reference ?? row.order_number); });
    });

    item.append(text, button);
    list.appendChild(item);
  }
  section.appendChild(list);
}

function renderTables(): void {
  const section = $('tables');
  section.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Tables';
  section.appendChild(heading);

  const list = document.createElement('ul');
  // Named, because the free tables are a second list in this same section and a
  // measurement that could not tell them apart would count a seated table twice.
  list.id = 'occupied-tables';
  for (const row of state.tables) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.overdue = String(row.needs_attention);
    item.dataset.table = row.table_reference;

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = `Table ${row.table_reference}`;
    const meta = document.createElement('span');
    meta.className = 'meta';

    // Every fact in words. An unpaid balance the server did not send is NOT drawn as a
    // zero: FR-POS-004 names the figure and M4 owns it, and "nothing outstanding" and
    // "we cannot tell you yet" are different sentences.
    const parts = [
      `${row.guests} seated`,
      `${row.open_requests} open request${row.open_requests === 1 ? '' : 's'}`,
      `${row.open_orders} order${row.open_orders === 1 ? '' : 's'}`,
    ];
    if (row.order_progress) parts.push(row.order_progress);
    if (row.assigned_waiter_id === null) parts.push('no waiter assigned');
    if (row.unpaid_balance_minor !== null) parts.push(`balance ${row.unpaid_balance_minor}`);
    if (row.attention_reason) parts.push(row.attention_reason);
    meta.textContent = ` · ${parts.join(' · ')}`;
    text.append(headline, meta);

    item.appendChild(text);
    list.appendChild(item);
  }
  section.appendChild(list);
  renderSeatable(section);
}

/**
 * Seating a table (FR-TAB-003), below the occupied ones.
 *
 * BELOW, not above, and that is the only judgement in this function. FR-POS-002 says the
 * order of the screen is the priority, and a table that needs something outranks a table
 * that has nobody at it. Seating is the thing a waiter does when nothing is waiting.
 *
 * The list is empty when every table is busy, and then nothing is drawn at all — not an
 * empty heading over a blank space, which reads as a screen that failed to load.
 */
function renderSeatable(section: HTMLElement): void {
  if (state.seatable.length === 0) return;

  const heading = document.createElement('h2');
  heading.textContent = 'Seat a table';
  section.appendChild(heading);

  const list = document.createElement('ul');
  list.id = 'seatable-tables';
  for (const row of state.seatable) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.seatable = row.table_reference;

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = `Table ${row.table_reference}`;
    const meta = document.createElement('span');
    meta.className = 'meta';
    // Seats in WORDS where the table declares them, and nothing at all where it does not.
    // service.table_profile.seat_count is nullable and "0 seats" would be a number this
    // screen invented for a table that simply has not said.
    meta.textContent = row.seat_count === null ? ' · free'
      : ` · free · ${row.seat_count} seat${row.seat_count === 1 ? '' : 's'}`;
    text.append(headline, meta);

    // Graded like every other action on this screen, through the one path that grades
    // them. Seating is not a destructive act, so the database will almost certainly call
    // it routine and it will run on one tap — but the grade is LOOKED UP, never assumed,
    // and an action nobody has graded is treated as deliberate rather than waved through.
    const grade = gradeFor('table.seat');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'primary';
    button.dataset.consequence = grade.consequence;
    button.dataset.action = 'table.seat';
    button.dataset.tableNode = row.table_node_id;
    button.textContent = 'Seat';
    button.addEventListener('click', () => {
      askThenRun('table.seat', `Seat table ${row.table_reference}`,
                 () => { void seatTable(row.table_node_id, row.table_reference); });
    });

    item.append(text, button);
    list.appendChild(item);
  }
  section.appendChild(list);
}

/** FR-NOT-012's staff half: the notification centre, in English, over M3-C's data. */
function renderNotifications(): void {
  const section = $('notifications');
  section.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Notifications';
  section.appendChild(heading);

  if (state.notifications.length === 0) {
    const none = document.createElement('p');
    none.className = 'meta';
    none.textContent = 'Nothing new.';
    section.appendChild(none);
    return;
  }

  const list = document.createElement('ul');
  for (const row of state.notifications) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.notice = row.notice_id;
    item.dataset.severity = row.severity;
    item.dataset.read = String(row.state === 'read');

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = row.body;
    const meta = document.createElement('span');
    meta.className = 'meta';
    // Severity as a WORD. A red dot is a severity nobody can read aloud.
    meta.textContent = ` · ${row.severity}${row.state === 'read' ? ' · read' : ' · unread'}`;
    text.append(headline, meta);

    item.appendChild(text);
    list.appendChild(item);
  }
  section.appendChild(list);
}

function renderSearch(): void {
  const list = $('search-results');
  list.replaceChildren();
  for (const row of state.results) {
    const item = document.createElement('li');
    item.className = 'row';
    item.dataset.itemCode = row.item_code;

    const text = document.createElement('div');
    const headline = document.createElement('span');
    headline.className = 'headline';
    headline.textContent = row.display_name;
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = ` · ${row.item_code} · ${row.availability}`;
    text.append(headline, meta);

    const add = document.createElement('button');
    add.type = 'button';
    add.dataset.consequence = gradeFor('order.line.add').consequence;
    add.dataset.action = 'order.line.add';
    add.textContent = 'Add';

    item.append(text, add);
    list.appendChild(item);
  }
}

// ---------------------------------------------------------------------------
// Confirmation, graded by consequence (FR-UX-015)
// ---------------------------------------------------------------------------

/**
 * The one path by which anything is confirmed.
 *
 * A routine action runs immediately. Anything else opens the panel, and a DELIBERATE one
 * additionally shows a reason field and will not proceed while it is empty. There is no
 * second path and no argument that skips this, so an action cannot be confirmed with
 * less friction than its grade by being called from somewhere else.
 */
export function askThenRun(
  actionCode: string, label: string, run: (reason: string | null) => void,
): void {
  const grade = gradeFor(actionCode);
  if (grade.consequence === 'routine') {
    run(null);
    return;
  }

  const panel = $('confirm-panel');
  const reasonLabel = $('confirm-reason-label');
  const reason = $('confirm-reason') as HTMLInputElement;
  const yes = $('confirm-yes') as HTMLButtonElement;

  panel.dataset.consequence = grade.consequence;
  panel.dataset.action = actionCode;
  panel.hidden = false;
  $('confirm-question').textContent =
    grade.consequence === 'deliberate'
      ? `${label} — this cannot be undone. Say why.`
      : `${label}?`;

  reason.value = '';
  reason.hidden = !grade.requires_reason;
  reasonLabel.hidden = !grade.requires_reason;
  yes.textContent = label;
  yes.dataset.consequence = grade.consequence;

  state.pending = { actionCode, label, run };
}

function confirmYes(): void {
  const pending = state.pending;
  if (!pending) return;
  const grade = gradeFor(pending.actionCode);
  const reason = ($('confirm-reason') as HTMLInputElement).value.trim();

  // A deliberate action with no reason does not proceed. This is the surface half of
  // the CHECK on pos.confirmation_requirement, and the database refuses it too — two
  // independent locks, so neither can hide a defect in the other.
  if (grade.requires_reason && reason.length === 0) {
    $('confirm-question').textContent = `${pending.label} — a reason is required.`;
    return;
  }
  closeConfirm();
  pending.run(reason.length > 0 ? reason : null);
}

function closeConfirm(): void {
  const panel = $('confirm-panel');
  panel.hidden = true;
  delete panel.dataset.action;
  state.pending = null;
}

// ---------------------------------------------------------------------------
// Accessibility mode (FR-UX-008)
// ---------------------------------------------------------------------------

export function setAccessibilityMode(on: boolean): void {
  document.documentElement.classList.toggle('accessible', on);
  const button = $('accessibility') as HTMLButtonElement;
  button.setAttribute('aria-pressed', String(on));
}

// ---------------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------------

export function render(payload: {
  requirements?: ConfirmationRequirement[];
  home?: HomeRow[];
  tables?: TableRow[];
  seatable?: SeatableRow[];
  pendingOrders?: PendingOrderRow[];
  notifications?: NotificationRow[];
  results?: SearchRow[];
}): void {
  if (payload.requirements) {
    state.requirements = new Map(payload.requirements.map((r) => [r.action_code, r]));
  }
  if (payload.home) state.home = payload.home;
  if (payload.tables) state.tables = payload.tables;
  if (payload.seatable) state.seatable = payload.seatable;
  if (payload.pendingOrders) state.pendingOrders = payload.pendingOrders;
  if (payload.notifications) state.notifications = payload.notifications;
  if (payload.results) state.results = payload.results;

  renderHome();
  renderPendingOrders();
  renderTables();
  renderNotifications();
  renderSearch();
}

function start(): void {
  $('accessibility').addEventListener('click', () => {
    const on = $('accessibility').getAttribute('aria-pressed') === 'true';
    setAccessibilityMode(!on);
  });
  $('confirm-yes').addEventListener('click', confirmYes);
  $('confirm-no').addEventListener('click', closeConfirm);
}

/* ===========================================================================
 * THE NETWORK LAYER (OP-B)
 * ===========================================================================
 *
 * Before OP-B this file had no fetch in it. It rendered a floor somebody handed it and
 * waited: M3-D measured the surface by calling render() with a payload the suite wrote,
 * which proves the rendering and proves nothing about whether a waiter can reach it.
 *
 * render() is untouched and stays pure — it takes a payload and draws it, exactly as that
 * suite calls it. Everything below fetches a payload and hands it to render(), so the
 * drawing has one implementation whether the data came from a probe or from the service.
 *
 * NOTHING IS FETCHED WITHOUT A SESSION, for the same reason as the station board: M3-D
 * opens this page with no service behind it, and a poll that overwrote what it drew would
 * break a measurement that has nothing to do with this gate.
 */

interface WaiterSession { token: string; }

const WAITER_SESSION_KEY = 'waiter.session';
let waiterSession: WaiterSession | null = null;
let waiterPoller: number | null = null;

async function waiterApi(method: string, path: string, body?: unknown): Promise<{
  status: number; data: Record<string, unknown>;
}> {
  // THE CONTENT TYPE IS CLAIMED ONLY WHEN THERE IS CONTENT.
  //
  // This used to send `content-type: application/json` on every request including the
  // ones with no body, and Fastify answers that 400: a request that declares a JSON body
  // and carries none is malformed, and it is right to refuse it. It went unnoticed for as
  // long as every write this surface made carried a payload. Seating does not — the table
  // is named in the path and there is nothing else to say — so it was the first bodyless
  // POST here, and it was refused before it reached the route.
  const response = await fetch(path, {
    method,
    headers: {
      ...(body === undefined ? {} : { 'content-type': 'application/json' }),
      ...(waiterSession ? { authorization: `Bearer ${waiterSession.token}` } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await response.text();
  let data: Record<string, unknown> = {};
  try { data = text ? JSON.parse(text) as Record<string, unknown> : {}; } catch { /* not json */ }
  return { status: response.status, data };
}

/**
 * One pass over the floor.
 *
 * Four reads, then ONE render. Rendering after each would show a floor that is partly
 * this second's and partly last second's, which on a screen whose job is "what needs me
 * next" is worse than being a moment late.
 */
export async function refresh(): Promise<void> {
  if (!waiterSession) return;
  const [home, tables, seatable, pending, notifications, needs] = await Promise.all([
    waiterApi('GET', '/s/v1/home'),
    waiterApi('GET', '/s/v1/tables'),
    waiterApi('GET', '/s/v1/tables/seatable'),
    waiterApi('GET', '/s/v1/orders/pending'),
    waiterApi('GET', '/s/v1/notifications'),
    waiterApi('GET', '/s/v1/confirmation-requirements'),
  ]);
  if (home.status === 401 || tables.status === 401) { waiterSignOut(); return; }

  render({
    requirements: (needs.data.requirements ?? []) as ConfirmationRequirement[],
    // GET /s/v1/home answers { queues: [...] } — pos.role_home()'s rows, one per queue.
    home: (home.data.queues ?? []) as HomeRow[],
    tables: (tables.data.tables ?? []) as TableRow[],
    // The occupied list and the free list come from two functions over the same
    // occupancies, in one pass, so the screen cannot draw a table as both.
    seatable: (seatable.data.tables ?? []) as SeatableRow[],
    // The orders nobody has admitted yet. Empty on a floor that accepts automatically,
    // which is the demonstration floor after seeds/0009 — the section then draws nothing.
    pendingOrders: (pending.data.orders ?? []) as PendingOrderRow[],
    notifications: (notifications.data.notifications ?? []) as NotificationRow[],
  });
}

/**
 * Admitting an order to the kitchen (FR-ORD-004, F-OPD-1).
 *
 * The step that had no caller. POST /s/v1/orders/:orderId/accept has existed since OP-A
 * and works; no surface called it, and no screen listed an order awaiting acceptance — so
 * under `staff_confirmed` a guest's order was invisible everywhere and could not be
 * admitted by anybody. The station board shows TICKETS, and an unaccepted order has none.
 *
 * The floor is redrawn from the SERVICE afterwards rather than the row being removed
 * locally. Accepting releases the order to its stations and creates the tickets, which
 * changes the tables, the queue and this list at once; a screen that hid one row would be
 * telling the truth about the row and lying about everything around it.
 */
export async function acceptOrder(orderId: string, reference: string): Promise<boolean> {
  if (!waiterSession) return false;
  const answer = await waiterApi('POST', `/s/v1/orders/${orderId}/accept`, {});
  if (answer.status === 200) {
    notice(`${reference} is confirmed and with the kitchen.`);
    await refresh();
    return true;
  }
  // A refusal by name, not "failed". ORDER_NOT_SUBMITTED is the ordinary race — somebody
  // else confirmed it between this screen's last poll and this tap — and the repair is to
  // redraw, after which the row is gone because the order has left the list.
  notice(`${reference} could not be confirmed: ${String(answer.data.reason ?? answer.status)}`);
  await refresh();
  return false;
}

/**
 * Seating a table (FR-TAB-003, F-OPB-9).
 *
 * Nothing in the delivered code path could open a table occupancy before OP-C: every
 * INSERT INTO service.table_session was in a test file. This is one half of closing that —
 * the other is the guest seating themselves by scanning — and both call the same
 * service.open_table_session() with a different opening source.
 *
 * The screen is redrawn from the SERVICE afterwards rather than moved optimistically. A
 * seated table has an occupancy number, an accountable waiter and a place in two lists,
 * and a surface that decided any of that for itself would be inventing the floor rather
 * than reading it.
 */
export async function seatTable(tableNodeId: string, reference: string): Promise<boolean> {
  if (!waiterSession) return false;
  const answer = await waiterApi('POST', `/s/v1/tables/${tableNodeId}/seat`);
  if (answer.status === 200) {
    notice(`Table ${reference} is seated. It is yours.`);
    await refresh();
    return true;
  }
  // 409 is OCCUPANCY_ALREADY_OPEN: somebody seated it between this screen's last poll and
  // this tap. That is the ordinary race on a busy floor, not a fault, and the repair is to
  // redraw — after which the table is in the occupied list where it belongs.
  if (answer.status === 409) {
    notice(`Table ${reference} was seated by somebody else.`);
    await refresh();
    return false;
  }
  notice(`Table ${reference} could not be seated: ${String(answer.data.reason ?? answer.status)}`);
  return false;
}

export async function search(term: string): Promise<void> {
  if (!waiterSession) return;
  const answer = await waiterApi('GET', `/s/v1/search?q=${encodeURIComponent(term)}`);
  render({ results: (answer.data.results ?? []) as SearchRow[] });
}

function waiterSignOut(): void {
  waiterSession = null;
  sessionStorage.removeItem(WAITER_SESSION_KEY);
  if (waiterPoller !== null) { clearInterval(waiterPoller); waiterPoller = null; }
  renderSignIn();
}

function waiterStart(): void {
  const panel = maybe('sign-in-panel');
  if (panel) { panel.replaceChildren(); panel.hidden = true; }
  void refresh();
  if (waiterPoller === null) {
    waiterPoller = window.setInterval(() => { void refresh(); }, 5000);
  }
}

/**
 * The way in (F-OPB-12).
 *
 * OP-B added this surface's network layer and no way to reach it. station.ts and
 * cashier.ts each rendered a form; this file exported signIn() and rendered nothing, so a
 * waiter opening the page saw a blank screen and the only way in was the browser console.
 * The capability existed and the door did not, which is the same defect as a route with no
 * caller, one layer further out — and it is the defect this whole gate exists to close.
 */
export function renderSignIn(): void {
  const panel = maybe('sign-in-panel');
  if (!panel) return;
  panel.hidden = false;
  panel.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Sign in';
  panel.appendChild(heading);

  const form = document.createElement('form');
  form.id = 'sign-in';

  function field(name: string, label: string, type: string): HTMLInputElement {
    const row = document.createElement('label');
    row.className = 'field';
    row.textContent = label;
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

  const submit = document.createElement('button');
  submit.type = 'submit';
  submit.className = 'primary';
  submit.textContent = 'Sign in';
  form.appendChild(submit);

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      notice(null);
      const ok = await signIn(tenantId.value, outletId.value,
                              channelValue.value, secret.value);
      // Refused, not "failed". A wrong password and an unreachable service are different
      // situations and the route already tells them apart; what a waiter needs to know
      // here is that they are not in, which is the same either way.
      if (!ok) notice('Sign in refused.');
    })();
  });

  panel.appendChild(form);
}

export async function signIn(tenantId: string, outletId: string,
                             channelValue: string, secret: string): Promise<boolean> {
  const answer = await waiterApi('POST', '/v1/auth/login', {
    tenantId, outletId, channel: 'email', channelValue, kind: 'password', secret,
  });
  if (answer.status !== 200 || !answer.data.token) return false;
  waiterSession = { token: String(answer.data.token) };
  sessionStorage.setItem(WAITER_SESSION_KEY, JSON.stringify(waiterSession));
  waiterStart();
  return true;
}

declare global {
  interface Window {
    waiterSurface: {
      render: typeof render;
      askThenRun: typeof askThenRun;
      gradeFor: typeof gradeFor;
      setAccessibilityMode: typeof setAccessibilityMode;
      signIn: typeof signIn;
      renderSignIn: typeof renderSignIn;
      seatTable: typeof seatTable;
      acceptOrder: typeof acceptOrder;
      refresh: typeof refresh;
      search: typeof search;
    };
  }
}

window.waiterSurface = { render, askThenRun, gradeFor, setAccessibilityMode,
                         signIn, renderSignIn, seatTable, acceptOrder, refresh, search };

try {
  const raw = sessionStorage.getItem(WAITER_SESSION_KEY);
  waiterSession = raw ? JSON.parse(raw) as WaiterSession : null;
} catch { waiterSession = null; }
if (waiterSession) waiterStart();
else if (maybe('sign-in-panel')) renderSignIn();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
