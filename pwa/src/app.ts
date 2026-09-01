/**
 * The customer surface.
 *
 * Vanilla TypeScript compiled to a browser ES module. No framework, no runtime
 * dependency: the bundle a phone on Ethiopian mobile data downloads is this file and one
 * stylesheet, which is the cheapest way to hold a performance budget and the smallest
 * supply chain to trust on an untrusted device.
 *
 * Three things here are load-bearing and are commented where they happen rather than
 * described here: an allergen is never drawn as an icon alone; a state is never conveyed
 * by colour alone; and a retry carries the key its first attempt carried.
 */

// ---------------------------------------------------------------------------
// Locales
// ---------------------------------------------------------------------------

export type Locale = 'en' | 'am' | 'ar';
const LOCALES: readonly Locale[] = ['en', 'am', 'ar'];

/**
 * Every string the surface itself says, in all three languages.
 *
 * Completeness is the requirement, not presence (FR-I18N-001A): a screen that renders
 * half in Amharic and half in English is the failure mode. The shape below makes a
 * missing string a compile error rather than a silent fall back to English, and
 * `missingStrings()` lets the suite prove at run time that no key resolves to a
 * different language than the one asked for.
 */
type StringKey =
  | 'title' | 'menuHeading' | 'cartHeading' | 'cartEmpty' | 'retry' | 'skipToMenu'
  | 'add' | 'allergenHeading' | 'noMenu' | 'localeHint' | 'total' | 'warningUnavailable'
  | 'contains' | 'may_contain' | 'cross_contact'
  | 'loading' | 'saved_locally' | 'queued' | 'synchronized' | 'stale' | 'failed' | 'blocked'
  // M3-C. Service requests, their statuses and the table's timeline.
  | 'serviceHeading' | 'statusHeading' | 'timelineHeading' | 'serviceEmpty'
  | 'askAgain' | 'alreadyAsked' | 'askedTimes'
  | 'received' | 'being_handled' | 'completed' | 'withdrawn' | 'closed';

const STRINGS: Record<Locale, Record<StringKey, string>> = {
  en: {
    title: 'Menu', menuHeading: 'Today', cartHeading: 'Your basket',
    cartEmpty: 'Nothing chosen yet. Add a dish to start.', retry: 'Try again',
    skipToMenu: 'Skip to the menu', add: 'Add', allergenHeading: 'Allergen information',
    noMenu: 'No menu has been published for this table yet. Please ask a member of staff.',
    localeHint: 'Your device suggests this language. Choose the one you want.',
    total: 'Total', warningUnavailable: 'Allergen information is not available in this language. Please ask a member of staff.',
    contains: 'Contains', may_contain: 'May contain', cross_contact: 'Prepared near',
    loading: 'Loading', saved_locally: 'Saved on this device', queued: 'Waiting to send',
    synchronized: 'Sent', stale: 'Out of date', failed: 'Did not send', blocked: 'Cannot send',
    serviceHeading: 'Ask for something', statusHeading: 'Your requests',
    timelineHeading: 'What has happened',
    serviceEmpty: 'You have not asked for anything yet.',
    askAgain: 'Ask again', alreadyAsked: 'You have already asked for this. It is on its way.',
    askedTimes: 'asked', received: 'Received', being_handled: 'Being handled',
    completed: 'Done', withdrawn: 'Withdrawn', closed: 'Closed',
  },
  am: {
    title: 'ዝርዝር', menuHeading: 'ዛሬ', cartHeading: 'ቅርጫትዎ',
    cartEmpty: 'እስካሁን ምንም አልተመረጠም። ለመጀመር ምግብ ይጨምሩ።', retry: 'እንደገና ይሞክሩ',
    skipToMenu: 'ወደ ዝርዝሩ ይሂዱ', add: 'ጨምር', allergenHeading: 'የአለርጂ መረጃ',
    noMenu: 'ለዚህ ጠረጴዛ እስካሁን ዝርዝር አልታተመም። እባክዎ ሠራተኛ ይጠይቁ።',
    localeHint: 'መሣሪያዎ ይህን ቋንቋ ይጠቁማል። የሚፈልጉትን ይምረጡ።',
    total: 'ጠቅላላ', warningUnavailable: 'የአለርጂ መረጃ በዚህ ቋንቋ አይገኝም። እባክዎ ሠራተኛ ይጠይቁ።',
    contains: 'ይዟል', may_contain: 'ሊይዝ ይችላል', cross_contact: 'በአጠገቡ የተዘጋጀ',
    loading: 'በመጫን ላይ', saved_locally: 'በዚህ መሣሪያ ተቀምጧል', queued: 'ለመላክ በመጠባበቅ ላይ',
    synchronized: 'ተልኳል', stale: 'ጊዜው ያለፈበት', failed: 'አልተላከም', blocked: 'መላክ አይቻልም',
    serviceHeading: 'እርዳታ ይጠይቁ', statusHeading: 'ጥያቄዎችዎ',
    timelineHeading: 'የሆነው ነገር',
    serviceEmpty: 'እስካሁን ምንም አልጠየቁም።',
    askAgain: 'እንደገና ይጠይቁ', alreadyAsked: 'ይህን አስቀድመው ጠይቀዋል። በመንገድ ላይ ነው።',
    askedTimes: 'ተጠይቋል', received: 'ደርሷል', being_handled: 'እየተስተናገደ ነው',
    completed: 'ተጠናቋል', withdrawn: 'ተሰርዟል', closed: 'ተዘግቷል',
  },
  ar: {
    title: 'قائمة الطعام', menuHeading: 'اليوم', cartHeading: 'سلتك',
    cartEmpty: 'لم يتم اختيار شيء بعد. أضف طبقًا للبدء.', retry: 'حاول مرة أخرى',
    skipToMenu: 'انتقل إلى القائمة', add: 'أضف', allergenHeading: 'معلومات الحساسية',
    noMenu: 'لم تُنشر قائمة لهذه الطاولة بعد. يرجى سؤال أحد الموظفين.',
    localeHint: 'يقترح جهازك هذه اللغة. اختر اللغة التي تريدها.',
    total: 'الإجمالي', warningUnavailable: 'معلومات الحساسية غير متوفرة بهذه اللغة. يرجى سؤال أحد الموظفين.',
    contains: 'يحتوي على', may_contain: 'قد يحتوي على', cross_contact: 'حُضّر بالقرب من',
    loading: 'جارٍ التحميل', saved_locally: 'محفوظ على هذا الجهاز', queued: 'في انتظار الإرسال',
    synchronized: 'تم الإرسال', stale: 'قديم', failed: 'لم يتم الإرسال', blocked: 'تعذر الإرسال',
    serviceHeading: 'اطلب شيئًا', statusHeading: 'طلباتك',
    timelineHeading: 'ما الذي حدث',
    serviceEmpty: 'لم تطلب أي شيء بعد.',
    askAgain: 'اطلب مرة أخرى', alreadyAsked: 'لقد طلبت هذا بالفعل. إنه في الطريق.',
    askedTimes: 'طُلب', received: 'تم الاستلام', being_handled: 'قيد المعالجة',
    completed: 'تم', withdrawn: 'تم السحب', closed: 'مغلق',
  },
};

/** Which keys, if any, are absent or identical to English in a non-English locale. */
export function missingStrings(locale: Locale): string[] {
  const table = STRINGS[locale];
  const english = STRINGS.en;
  return (Object.keys(english) as StringKey[]).filter((key) => {
    const value = table[key];
    if (typeof value !== 'string' || value.trim() === '') return true;
    // An untranslated string in a non-Latin locale reads as English on the screen, which
    // is the partial render this requirement is about. Identical text is the signal.
    return locale !== 'en' && value === english[key];
  });
}

// ---------------------------------------------------------------------------
// The seven states (FR-UX-006, FR-UX-007)
// ---------------------------------------------------------------------------

/**
 * Seven, distinguishable, with no two meaning the same thing.
 *
 * "Saved on this device" and "waiting to send" are different promises: the first says the
 * work will survive the browser closing, the second says it will leave. "Out of date" and
 * "did not send" are different too: one is stale data successfully received, the other is
 * data that never arrived. Collapsing any pair loses something the guest needs.
 *
 * Each carries a glyph as well as a word, so the set survives greyscale (FR-UX-005).
 */
export type SurfaceState =
  | 'loading' | 'saved_locally' | 'queued' | 'synchronized' | 'stale' | 'failed' | 'blocked';

export const STATES: readonly SurfaceState[] = [
  'loading', 'saved_locally', 'queued', 'synchronized', 'stale', 'failed', 'blocked',
];

const GLYPH: Record<SurfaceState, string> = {
  loading: '◐', saved_locally: '▣', queued: '◔', synchronized: '✓',
  stale: '◷', failed: '✕', blocked: '⊘',
};

/** Which states a state may move to. Written down so the suite can walk every edge. */
export const TRANSITIONS: Record<SurfaceState, readonly SurfaceState[]> = {
  loading: ['synchronized', 'failed', 'blocked', 'stale'],
  saved_locally: ['queued', 'blocked'],
  queued: ['synchronized', 'failed', 'blocked'],
  synchronized: ['loading', 'stale', 'saved_locally'],
  stale: ['loading', 'synchronized'],
  failed: ['queued', 'loading', 'blocked'],
  blocked: ['loading'],
};

// ---------------------------------------------------------------------------
// Formatting: canonical values stored, localized values displayed (FR-I18N-005)
// ---------------------------------------------------------------------------

/**
 * Minor units and an ISO code go in; a localized string comes out. The canonical value is
 * never overwritten by its formatting — the cart holds `amountMinor` as an integer and
 * this runs at render time, so switching language reformats and never re-prices.
 */
export function formatMoney(amountMinor: number, currency: string, locale: Locale): string {
  const major = amountMinor / 100;
  // 'latn' explicitly: Arabic locales default to Arabic-Indic digits in some engines, and
  // a price a guest cannot match against the printed menu helps nobody. The currency and
  // the number stay one unbroken run, isolated by the stylesheet.
  return new Intl.NumberFormat(`${locale}-u-nu-latn`, {
    style: 'currency', currency, currencyDisplay: 'code',
  }).format(major);
}

export function formatTime(at: Date, locale: Locale): string {
  return new Intl.DateTimeFormat(`${locale}-u-nu-latn`, {
    hour: '2-digit', minute: '2-digit',
  }).format(at);
}

// ---------------------------------------------------------------------------
// Shape of what the API returns
// ---------------------------------------------------------------------------

interface Allergen {
  kitchenCode: string;
  declarationClass: 'contains' | 'may_contain' | 'cross_contact';
  writtenWarning: string;
  iconKey: string | null;
}

interface Item {
  itemCode: string;
  itemId: string;
  variantId: string;
  name: string;
  currencyCode: string;
  amountMinor: string;
  allergens: Allergen[];
}

interface CartLine {
  key: string;
  itemCode: string;
  itemId: string;
  variantId: string;
  name: string;
  currencyCode: string;
  amountMinor: number;
  state: SurfaceState;
}

// ---------------------------------------------------------------------------
// Application state
// ---------------------------------------------------------------------------

interface AppState {
  locale: Locale;
  state: SurfaceState;
  changedAt: Date;
  items: Item[];
  cart: CartLine[];
  emptyReason: string | null;
}

const app: AppState = {
  locale: 'en',
  state: 'loading',
  changedAt: new Date(),
  items: [],
  cart: [],
  emptyReason: null,
};

function $(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element: ${id}`);
  return node;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

/** One string in the session's language. Never a key, never English by default. */
function t(key: StringKey): string {
  return STRINGS[app.locale][key];
}

function setState(next: SurfaceState): void {
  const allowed = TRANSITIONS[app.state];
  if (app.state !== next && !allowed.includes(next)) {
    // A transition nobody declared is a bug in the caller, and drawing it anyway would
    // show the guest a state the surface does not actually mean.
    throw new Error(`UNDECLARED_TRANSITION: ${app.state} -> ${next}`);
  }
  app.state = next;
  app.changedAt = new Date();
  renderStatus();
}

function renderStatus(): void {
  const strings = STRINGS[app.locale];
  // Three independent carriers: a glyph, a word, and a time. Colour is applied by the
  // stylesheet and carries nothing that is not already here (FR-UX-005).
  $('status-glyph').textContent = GLYPH[app.state];
  $('status-text').textContent = strings[app.state];
  const time = $('status-time') as HTMLTimeElement;
  time.textContent = formatTime(app.changedAt, app.locale);
  time.dateTime = app.changedAt.toISOString();
  $('status').setAttribute('data-state', app.state);
}

function renderChrome(): void {
  const strings = STRINGS[app.locale];
  document.documentElement.lang = app.locale;
  document.documentElement.dir = app.locale === 'ar' ? 'rtl' : 'ltr';
  document.title = strings.title;

  for (const node of Array.from(document.querySelectorAll<HTMLElement>('[data-i18n]'))) {
    const key = node.dataset.i18n as StringKey | undefined;
    if (key && key in strings) node.textContent = strings[key];
  }
  for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>('.locale'))) {
    button.setAttribute('aria-pressed', String(button.dataset.locale === app.locale));
  }
}

function renderMenu(): void {
  const strings = STRINGS[app.locale];
  const list = $('items');
  list.textContent = '';

  const empty = $('menu-empty');
  if (app.items.length === 0) {
    // An instructive empty state that says what to do next, and no fabricated dish, no
    // placeholder price and no sample figure of any kind (FR-UX-014).
    empty.textContent = app.emptyReason ? strings.noMenu : strings.noMenu;
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  for (const item of app.items) {
    const li = document.createElement('li');
    li.className = 'item';
    li.dataset.itemCode = item.itemCode;

    const head = document.createElement('div');
    head.className = 'item-head';

    const name = document.createElement('span');
    name.className = 'item-name';
    name.textContent = item.name;

    const price = document.createElement('span');
    price.className = 'item-price';
    // dir on the element as well as in the stylesheet: the attribute is what the
    // bidirectional algorithm reads, and a stylesheet that failed to load must not be
    // able to reorder a price.
    price.dir = 'ltr';
    price.textContent = formatMoney(Number(item.amountMinor), item.currencyCode, app.locale);

    head.append(name, price);
    li.append(head);

    if (item.allergens.length > 0) {
      const allergens = document.createElement('ul');
      allergens.className = 'allergens';
      allergens.setAttribute('aria-label', strings.allergenHeading);

      for (const allergen of item.allergens) {
        const row = document.createElement('li');
        row.className = 'allergen';
        row.dataset.kitchenCode = allergen.kitchenCode;

        const warning = (allergen.writtenWarning ?? '').trim();

        // ===== M2-B's handoff, discharged here =====
        //
        // M2-B proved by privilege that no icon can be OBTAINED without its written
        // warning. This is the other half: a surface that received both and drew only
        // the icon would defeat that one layer up.
        //
        // The words are appended first and unconditionally. The glyph is appended only
        // when there are words for it to sit beside, so there is no ordering of these
        // statements, and no future edit to them, that produces an icon on its own —
        // the icon element is not created in the branch where the text is missing.
        const text = document.createElement('span');
        text.className = 'allergen-text';
        text.textContent = warning.length > 0
          ? `${strings[allergen.declarationClass]}: ${warning}`
          : strings.warningUnavailable;
        row.append(text);

        if (warning.length > 0 && allergen.iconKey) {
          const glyph = document.createElement('span');
          glyph.className = 'allergen-glyph';
          glyph.dataset.iconKey = allergen.iconKey;
          // Decorative: the sentence beside it already carries the meaning, so a screen
          // reader is not made to announce a shape.
          glyph.setAttribute('aria-hidden', 'true');
          glyph.textContent = '▲';
          row.insertBefore(glyph, text);
        }
        allergens.append(row);
      }
      li.append(allergens);
    }

    const add = document.createElement('button');
    add.type = 'button';
    add.className = 'add';
    add.textContent = strings.add;
    add.dataset.itemCode = item.itemCode;
    add.setAttribute('aria-label', `${strings.add}: ${item.name}`);
    add.addEventListener('click', () => addToCart(item));
    li.append(add);

    list.append(li);
  }
}

function renderCart(): void {
  const strings = STRINGS[app.locale];
  const list = $('cart-lines');
  list.textContent = '';
  $('cart-empty').hidden = app.cart.length > 0;

  let total = 0;
  let currency = 'ETB';
  for (const line of app.cart) {
    total += line.amountMinor;
    currency = line.currencyCode;

    const li = document.createElement('li');
    li.className = 'cart-line';
    li.dataset.key = line.key;
    li.dataset.state = line.state;

    const name = document.createElement('span');
    name.textContent = line.name;

    const price = document.createElement('span');
    price.className = 'cart-line-price';
    price.dir = 'ltr';
    price.textContent = formatMoney(line.amountMinor, line.currencyCode, app.locale);

    const state = document.createElement('span');
    state.className = 'cart-line-state';
    state.textContent = `${GLYPH[line.state]} ${strings[line.state]}`;

    li.append(name, price, state);
    list.append(li);
  }

  const totalNode = $('cart-total');
  totalNode.hidden = app.cart.length === 0;
  totalNode.textContent = `${strings.total} ${formatMoney(total, currency, app.locale)}`;
}

function render(): void {
  renderChrome();
  renderStatus();
  renderMenu();
  renderCart();
}

// ---------------------------------------------------------------------------
// Talking to the API
// ---------------------------------------------------------------------------

interface Credentials { guestToken: string; tableSessionId: string; }
let credentials: Credentials | null = null;

/**
 * A write that a retry may repeat safely.
 *
 * The key is generated once, when the guest first asks for the thing, and it is kept with
 * the pending work. Pressing "try again" sends the SAME key, so the server finishes the
 * first attempt instead of starting a second one. Generating a fresh key on retry is the
 * defect this exists to prevent — it is a duplicate cart line today and a duplicate charge
 * at M4 (FR-UX-007).
 */
interface Pending { key: string; url: string; body: unknown; lineKey: string; }
let pending: Pending | null = null;

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

async function send(work: Pending): Promise<Response> {
  return fetch(work.url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'idempotency-key': work.key,
      authorization: `Guest ${credentials?.guestToken ?? ''}`,
    },
    body: JSON.stringify(work.body),
  });
}

function addToCart(item: Item): void {
  const line: CartLine = {
    key: newIdempotencyKey(),
    itemCode: item.itemCode,
    itemId: item.itemId,
    variantId: item.variantId,
    name: item.name,
    currencyCode: item.currencyCode,
    amountMinor: Number(item.amountMinor),
    // Held on the device before anything leaves it, so a guest who loses signal mid-tap
    // still has their choice (FR-UX-007).
    state: 'saved_locally',
  };
  app.cart.push(line);
  persist();
  renderCart();
  void commit(line);
}

async function commit(line: CartLine): Promise<void> {
  const work: Pending = {
    key: line.key,
    url: '/c/v1/cart/lines',
    body: { cartId: CART_ID, itemId: line.itemId, variantId: line.variantId },
    lineKey: line.key,
  };
  pending = work;
  line.state = 'queued';
  renderCart();

  try {
    const response = await send(work);
    if (response.ok) {
      line.state = 'synchronized';
      pending = null;
      $('retry').hidden = true;
    } else if (response.status === 401 || response.status === 409) {
      // Refused for a reason retrying will not change.
      line.state = 'blocked';
      $('retry').hidden = true;
    } else {
      line.state = 'failed';
      $('retry').hidden = false;
    }
  } catch {
    line.state = 'failed';
    $('retry').hidden = false;
  }
  persist();
  renderCart();
}

async function retry(): Promise<void> {
  if (!pending) return;
  const line = app.cart.find((candidate) => candidate.key === pending!.lineKey);
  if (!line) return;
  line.state = 'queued';
  renderCart();
  // Deliberately the same `pending` object, carrying the same key.
  const work = pending;
  try {
    const response = await send(work);
    line.state = response.ok ? 'synchronized' : 'failed';
    if (response.ok) { pending = null; $('retry').hidden = true; }
  } catch {
    line.state = 'failed';
  }
  persist();
  renderCart();
}

// The basket this guest's choices go into, resolved once the guest is seated.
let CART_ID = '';

async function loadMenu(): Promise<void> {
  if (app.state !== 'loading') setState('loading');
  try {
    const response = await fetch(`/c/v1/menu?locale=${app.locale}`, {
      headers: { authorization: `Guest ${credentials?.guestToken ?? ''}` },
    });
    if (!response.ok) { setState('failed'); return; }
    const payload = await response.json() as { items: Item[]; empty?: string };
    app.items = payload.items ?? [];
    app.emptyReason = payload.empty ?? null;
    setState('synchronized');
  } catch {
    // Nothing arrived. What is on screen, if anything, is now old — and saying so is
    // different from saying the request failed, which is why both states exist.
    setState(app.items.length > 0 ? 'stale' : 'failed');
  }
  renderMenu();
}

// ---------------------------------------------------------------------------
// Locale switching
// ---------------------------------------------------------------------------

/**
 * Switching language re-renders. It does not reload the cart, reset it, or re-price it.
 *
 * The cart is application state holding canonical values; the language is a rendering
 * concern. Keeping them separate is what makes "switching must not lose the cart"
 * (FR-I18N-004) a property of the design rather than something to remember.
 */
async function chooseLocale(locale: Locale): Promise<void> {
  app.locale = locale;
  try { localStorage.setItem('locale', locale); } catch { /* private mode */ }

  render();

  // The snapshot on the table session, for M3's order communications and M4's receipts
  // (FR-I18N-005). Fire and forget: the surface has already switched, and a customer
  // waiting on a round trip to read their own language is the wrong trade.
  if (credentials) {
    void fetch('/c/v1/locale', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', authorization: `Guest ${credentials.guestToken}` },
      body: JSON.stringify({ tableSessionId: credentials.tableSessionId, locale }),
    }).catch(() => undefined);
  }
  await loadMenu();
}

function persist(): void {
  try {
    localStorage.setItem('cart', JSON.stringify(app.cart));
  } catch { /* private mode: the cart lives for this page only, which is still a cart */ }
}

function restore(): void {
  try {
    const raw = localStorage.getItem('cart');
    if (raw) app.cart = JSON.parse(raw) as CartLine[];
  } catch { /* unreadable storage is an empty cart, never a crash */ }
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

function suggestedLocale(): Locale | null {
  for (const tag of navigator.languages ?? []) {
    const base = tag.split('-')[0] as Locale;
    if (LOCALES.includes(base)) return base;
  }
  return null;
}

async function start(): Promise<void> {
  restore();

  // The browser's preference is shown as a suggestion and applied to nothing. A customer
  // handed a language by their device has no way to know another was available, which is
  // why FR-I18N-001A asks for the three to be offered explicitly.
  const suggestion = suggestedLocale();
  if (suggestion && suggestion !== 'en') {
    const hint = $('locale-hint');
    hint.textContent = STRINGS[suggestion].localeHint;
    hint.hidden = false;
  }

  for (const button of Array.from(document.querySelectorAll<HTMLButtonElement>('.locale'))) {
    button.addEventListener('click', () => {
      void chooseLocale(button.dataset.locale as Locale);
    });
  }
  $('retry').addEventListener('click', () => { void retry(); });

  render();

  // What the QR encodes: the tenant and outlet in the path, which are not secrets, and
  // the opaque code, which is. The code never enters the surface's own state — it is
  // exchanged once for a guest token and then forgotten.
  const params = new URLSearchParams(location.search);
  const tenant = params.get('t');
  const outlet = params.get('o');
  const code = params.get('c');
  if (!tenant || !outlet || !code) {
    setState('blocked');
    return;
  }

  try {
    const opened = await fetch(`/c/v1/${tenant}/${outlet}/session`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    if (!opened.ok) { setState('blocked'); return; }
    const session = await opened.json() as { guestToken: string; scanId: string; tableSessionId: string };
    credentials = { guestToken: session.guestToken, tableSessionId: session.tableSessionId };

    const joined = await fetch('/c/v1/join', {
      method: 'POST',
      headers: { 'content-type': 'application/json', authorization: `Guest ${session.guestToken}` },
      body: JSON.stringify({ scanId: session.scanId }),
    });
    if (!joined.ok) {
      // A stale code needs a member of staff, which is a different thing from a broken
      // one and is why "cannot send" and "did not send" are separate states.
      setState('blocked');
      return;
    }
    const seated = await joined.json() as { tableSessionId: string };
    credentials.tableSessionId = seated.tableSessionId;

    const cart = await fetch('/c/v1/cart', {
      headers: { authorization: `Guest ${session.guestToken}` },
    });
    if (cart.ok) {
      const info = await cart.json() as { cartId: string; customerLocale: Locale | null };
      CART_ID = info.cartId;
      // A locale already snapshotted on this occupancy is a choice somebody made, so it
      // is honoured rather than asked for again.
      if (info.customerLocale) { app.locale = info.customerLocale; render(); }
    }
  } catch {
    setState('blocked');
    return;
  }

  await loadMenu();
}


// ===========================================================================
// M3-C. Service requests: asking, what came of it, and the table's timeline
// ===========================================================================
// Every fact here is a WORD, in the session's language, and none of it is a colour or a
// position. Two things are load-bearing and both are about what is NOT here:
//
//   * no staff name is ever constructed. The status row renders handledBy only when the
//     server sent one, and the server sends one only where the outlet configured
//     disclosure (FR-SRV-009). The surface has no branch that could add a name the
//     server withheld, which is the same arrangement M3-B used for allergy salience.
//
//   * no status text is invented. status_text is what the server rendered from the
//     approved template in the session's language; when it is absent the surface falls
//     back to its own translated word for the status CODE, never to English.

export interface ServiceType { id: string; code: string; label: string; }

export interface ServiceStatusRow {
  service_request_id: string;
  request_label: string;
  status_code: 'received' | 'being_handled' | 'completed' | 'withdrawn' | 'closed';
  status_text: string | null;
  raised_at: string;
  repeat_ordinal: number;
  handled_by: string | null;
}

export interface TimelineEntry {
  occurred_at: string; source: string; summary: string | null; locale: string;
}

function renderServiceTypes(types: ServiceType[], alreadyOpen: Set<string>): void {
  const root = document.getElementById('service-types');
  if (!root) return;
  root.textContent = '';
  for (const type of types) {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'service-ask';
    button.setAttribute('data-request-type', type.id);
    // The label the SERVER resolved from the approved translation, not a key looked up
    // here: a request type an outlet invented has no entry in this file's string table
    // and must still render in the guest's language.
    button.textContent = type.label;
    li.appendChild(button);

    // FR-SRV-006 on the surface. A second tap on something already open is offered as a
    // DELIBERATE repeat, in words, rather than silently becoming one or silently being
    // swallowed. The guest decides which of the two it is.
    if (alreadyOpen.has(type.id)) {
      const again = document.createElement('button');
      again.type = 'button';
      again.className = 'ask-again';
      again.setAttribute('data-request-type', type.id);
      again.setAttribute('data-deliberate', 'true');
      again.textContent = t('askAgain');
      li.appendChild(again);
    }
    root.appendChild(li);
  }
}

function renderServiceStatus(rows: ServiceStatusRow[]): void {
  const root = document.getElementById('service-status');
  const empty = document.getElementById('service-empty');
  if (!root) return;
  root.textContent = '';
  if (empty) empty.hidden = rows.length > 0;

  for (const row of rows) {
    const li = document.createElement('li');
    li.setAttribute('data-request', row.service_request_id);
    li.setAttribute('data-status', row.status_code);

    const label = document.createElement('span');
    label.className = 'request-label';
    label.textContent = row.request_label;
    li.appendChild(label);

    // The status as a WORD. The server's rendered sentence where there is one, this
    // surface's translated word for the code where there is not — never the code itself,
    // which is English and is not for reading.
    const word = document.createElement('span');
    word.className = 'status-word';
    word.textContent = row.status_text ?? t(row.status_code);
    li.appendChild(word);

    if (row.repeat_ordinal > 1) {
      const repeat = document.createElement('span');
      repeat.className = 'repeat';
      repeat.textContent = `${t('askedTimes')} ${row.repeat_ordinal}×`;
      li.appendChild(repeat);
    }

    // Only what the server sent. There is no else-branch that supplies a name.
    if (row.handled_by) {
      const who = document.createElement('span');
      who.className = 'handled-by';
      who.textContent = row.handled_by;
      li.appendChild(who);
    }
    root.appendChild(li);
  }
}

function renderTimeline(entries: TimelineEntry[]): void {
  const root = document.getElementById('service-timeline');
  if (!root) return;
  root.textContent = '';
  for (const entry of entries) {
    if (!entry.summary) continue;
    const li = document.createElement('li');
    li.setAttribute('data-source', entry.source);
    li.setAttribute('data-locale', entry.locale);
    li.textContent = entry.summary;
    root.appendChild(li);
  }
}

/** Told plainly when a tap collapsed, because that is not an error. */
function renderCollapsed(collapsed: boolean): void {
  const node = document.getElementById('service-collapsed');
  if (!node) return;
  node.textContent = collapsed ? t('alreadyAsked') : '';
  node.hidden = !collapsed;
}

export function renderService(payload: {
  types?: ServiceType[]; status?: ServiceStatusRow[]; timeline?: TimelineEntry[];
  collapsed?: boolean;
}): void {
  const status = payload.status ?? [];
  const open = new Set(
    status.filter((r) => r.status_code === 'received' || r.status_code === 'being_handled')
          .map((r) => r.service_request_id));
  // Keyed by TYPE for the ask-again affordance, which needs the type rather than the
  // request: a guest asks again for water, not for request 8f3c.
  const openTypes = new Set<string>();
  for (const type of payload.types ?? []) {
    if (status.some((r) => r.request_label && open.size > 0
                           && (r.status_code === 'received' || r.status_code === 'being_handled')
                           && r.request_label === type.label)) {
      openTypes.add(type.id);
    }
  }
  renderServiceTypes(payload.types ?? [], openTypes);
  renderServiceStatus(status);
  renderTimeline(payload.timeline ?? []);
  renderCollapsed(payload.collapsed === true);
}

// Exposed so the verification suite can drive transitions and read the tables it is
// asserting about, rather than reimplementing them and testing its own copy.
declare global {
  interface Window {
    surface: {
      setState(next: SurfaceState): void;
      renderAs(state: SurfaceState): void;
      states: readonly SurfaceState[];
      transitions: Record<SurfaceState, readonly SurfaceState[]>;
      missingStrings(locale: Locale): string[];
      chooseLocale(locale: Locale): Promise<void>;
      cart(): CartLine[];
      renderService: typeof renderService;
      pendingKey(): string | null;
      formatMoney: typeof formatMoney;
    };
  }
}

window.surface = {
  setState,
  // Draws a state without walking to it. The seven have to be MEASURED as rendered —
  // glyph, word, time, computed colour — and no sequence of legal transitions visits all
  // seven, so a measurement pass that used setState() would be testing the transition
  // table rather than the rendering. The guard is proved separately, by walking every
  // declared edge and one undeclared one.
  renderAs(state: SurfaceState) {
    app.state = state;
    app.changedAt = new Date();
    renderStatus();
  },
  states: STATES,
  transitions: TRANSITIONS,
  missingStrings,
  chooseLocale,
  cart: () => app.cart,
  renderService,
  pendingKey: () => pending?.key ?? null,
  formatMoney,
};

void start();
