/**
 * The continuity banner — one implementation, four surfaces.
 *
 * FR-EDG-009 requires the connectivity state to be shown to customers AND staff. That is
 * four screens with four different audiences, and the obvious way to build it is four
 * copies of the same twenty lines. This repository has spent four gates finding what
 * happens next: the copies drift, one of them stops being updated, and the one that stops
 * is discovered by somebody standing at a till during an outage.
 *
 * So it is one module, served once, imported by all four documents. It installs itself:
 * a surface adds a script tag and gets the banner, with nothing to remember and nothing
 * to keep in step.
 *
 * WHAT IT SHOWS AND WHAT IT REFUSES TO SHOW.
 *
 *   - the state and its wording come from the node, which reads them from the database.
 *     No English lives in this file. A banner with its English here and its Amharic in a
 *     table would be two places to change one sentence.
 *   - when the node cannot be reached AT ALL, it says so as "unknown" rather than
 *     assuming the worst or the best. A surface loaded from the node that cannot then
 *     reach the node is a real state, and it is not the same as an outage — the outlet
 *     may be fine and this tablet may be the thing that is off the wifi.
 *   - it never blocks. FR-EDG-009 says "without blocking ordinary local service", so the
 *     banner is a strip of text and never a modal, never a disabled button, never a
 *     spinner over the screen. If this file ever grows one, it has broken the requirement
 *     it exists to satisfy.
 *
 * FR-POS-008's five states are a separate, staff-only call, because a guest has no
 * business knowing how many operations are queued and no token to ask with.
 */

export type Connectivity = 'cloud_connected' | 'local_continuity' | 'reconciling' | 'unknown';

export interface BannerState {
  connectivity: Connectivity;
  wording: string | null;
  pausedReason: string | null;
  openConflicts: number;
  blocksService: boolean;
}

const POLL_MS = 5000;
const MOUNT_ID = 'continuity-banner';

/** The locale the surrounding document is already in, so the banner matches its page. */
function documentLocale(): string {
  const declared = document.documentElement.getAttribute('lang');
  return declared === 'am' || declared === 'ar' ? declared : 'en';
}

export async function readBanner(fetcher: typeof fetch = fetch): Promise<BannerState> {
  try {
    const response = await fetcher(`/n/v1/connectivity?locale=${documentLocale()}`, {
      headers: { accept: 'application/json' },
    });
    if (!response.ok) {
      // A node that answers with an error is reachable and unwell, which is not the same
      // as unreachable — but from here they are indistinguishable, and saying "unknown"
      // is the only claim this code can support.
      return { connectivity: 'unknown', wording: null, pausedReason: null,
               openConflicts: 0, blocksService: false };
    }
    const body = await response.json() as Partial<BannerState>;
    return {
      connectivity: (body.connectivity ?? 'unknown') as Connectivity,
      wording: body.wording ?? null,
      pausedReason: body.pausedReason ?? null,
      openConflicts: body.openConflicts ?? 0,
      blocksService: body.blocksService ?? false,
    };
  } catch {
    return { connectivity: 'unknown', wording: null, pausedReason: null,
             openConflicts: 0, blocksService: false };
  }
}

export function render(mount: HTMLElement, state: BannerState): void {
  mount.dataset.connectivity = state.connectivity;

  // CONNECTED IS THE QUIET CASE. A banner that is always visible is a banner nobody
  // reads, and the state staff need to notice is the one that is not normal.
  if (state.connectivity === 'cloud_connected' && state.openConflicts === 0) {
    mount.hidden = true;
    mount.textContent = '';
    return;
  }

  mount.hidden = false;
  mount.textContent = '';

  const line = document.createElement('span');
  line.className = 'continuity-line';
  // An unworded state is reported as unworded rather than rendered blank. A blank strip
  // is indistinguishable from a working outlet.
  line.textContent = state.wording
    ?? (state.connectivity === 'unknown'
        ? 'The outlet node cannot be reached from this screen'
        : `connectivity: ${state.connectivity}`);
  mount.append(line);

  if (state.pausedReason) {
    const why = document.createElement('span');
    why.className = 'continuity-detail';
    why.textContent = state.pausedReason;
    mount.append(why);
  }

  // ARIA-LIVE POLITE, NEVER ASSERTIVE. This is information, not an alarm: an assertive
  // region interrupts a screen reader mid-sentence, and interrupting a waiter reading an
  // allergy line to tell them the wifi is down would be a defect with a worse outcome
  // than the outage.
  mount.setAttribute('role', 'status');
  mount.setAttribute('aria-live', 'polite');
}

export function mountPoint(): HTMLElement {
  const existing = document.getElementById(MOUNT_ID);
  if (existing) return existing;
  // A surface that forgot the element still gets the banner. The alternative — do nothing
  // when the mount is missing — is a silent failure of the requirement, discovered by
  // nobody, on the screen that needed it most.
  const created = document.createElement('div');
  created.id = MOUNT_ID;
  created.hidden = true;
  document.body.prepend(created);
  return created;
}

export function start(intervalMs: number = POLL_MS): { stop(): void } {
  const mount = mountPoint();
  let stopped = false;

  const tick = async (): Promise<void> => {
    if (stopped) return;
    render(mount, await readBanner());
  };

  void tick();
  const timer = window.setInterval(() => { void tick(); }, intervalMs);
  return {
    stop() { stopped = true; window.clearInterval(timer); },
  };
}

// SELF-INSTALLING, because the requirement is about every surface and an opt-in would be
// a thing to forget on the fifth one. A surface that wants to control it can import
// start() and call it itself; nothing here prevents that, and nothing requires it.
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { start(); });
  } else {
    start();
  }
}
