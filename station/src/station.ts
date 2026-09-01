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

declare global {
  interface Window {
    stationSurface: {
      renderAll: typeof renderAll;
      renderAllergy: typeof renderAllergy;
      BUCKETS: readonly Bucket[];
    };
  }
}

window.stationSurface = { renderAll, renderAllergy, BUCKETS };
