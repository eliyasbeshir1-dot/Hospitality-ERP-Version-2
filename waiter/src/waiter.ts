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
  notifications: NotificationRow[];
  results: SearchRow[];
  pending: { actionCode: string; label: string; run: (reason: string | null) => void } | null;
} = {
  requirements: new Map(),
  home: [],
  tables: [],
  notifications: [],
  results: [],
  pending: null,
};

function $(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element: ${id}`);
  return node;
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

function renderTables(): void {
  const section = $('tables');
  section.replaceChildren();

  const heading = document.createElement('h2');
  heading.textContent = 'Tables';
  section.appendChild(heading);

  const list = document.createElement('ul');
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
  notifications?: NotificationRow[];
  results?: SearchRow[];
}): void {
  if (payload.requirements) {
    state.requirements = new Map(payload.requirements.map((r) => [r.action_code, r]));
  }
  if (payload.home) state.home = payload.home;
  if (payload.tables) state.tables = payload.tables;
  if (payload.notifications) state.notifications = payload.notifications;
  if (payload.results) state.results = payload.results;

  renderHome();
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

declare global {
  interface Window {
    waiterSurface: {
      render: typeof render;
      askThenRun: typeof askThenRun;
      gradeFor: typeof gradeFor;
      setAccessibilityMode: typeof setAccessibilityMode;
    };
  }
}

window.waiterSurface = { render, askThenRun, gradeFor, setAccessibilityMode };

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
