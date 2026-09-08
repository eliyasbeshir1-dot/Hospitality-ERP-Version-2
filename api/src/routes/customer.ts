/**
 * The customer surface's API: QR entry, menu read, locale snapshot, cart, allergy input.
 *
 * Read-only where it can be, and idempotent where it cannot. There is no order
 * submission, no check, no payment and no kitchen route here — those are M3 and M4, and
 * they are not stubbed, not registered and not reserved.
 *
 * Two properties are load-bearing and are worth stating where a reader will find them.
 *
 * The menu route never returns an allergen icon on its own. It cannot: the shape it
 * serves is produced by safety.selection_safety(), which returns the icon and the written
 * warning in one row or refuses outright, and this route drops the icon rather than the
 * warning if it is ever handed one without the other. M2-B enforced that by privilege one
 * layer down; the surface has to not undo it.
 *
 * Every write takes an Idempotency-Key. A retry finishes the first attempt instead of
 * starting a second one, which at M2-C means a duplicate cart line and at M4 would mean a
 * duplicate charge.
 */
import { createHash } from 'node:crypto';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import type { Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface CustomerDependencies {
  db: Database;
  logger: StructuredLogger;
}

const LOCALES = ['en', 'am', 'ar'] as const;
type Locale = (typeof LOCALES)[number];

function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/** `tenantId.outletId.secret`, the same shape M1-D's staff tokens use. */
function guestCredential(request: FastifyRequest): [string, string, string] | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('guest ')) return null;
  const parts = header.slice(6).trim().split('.');
  if (parts.length !== 3) return null;
  if (parts.some((part) => part.length === 0)) return null;
  return parts as [string, string, string];
}

function idempotencyKey(request: FastifyRequest): string | null {
  const raw = request.headers['idempotency-key'];
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= 200 ? trimmed : null;
}

/**
 * Run inside an authenticated GUEST context, or answer 401.
 *
 * A guest context carries no app.session_id and no auth_strength, so nothing that
 * requires staff authentication can run under it even by accident.
 *
 * Exported as a factory because M3-C's service routes need the identical context and a
 * second copy of it would be a second chance to get the digest scope wrong — which is
 * the one detail in it that matters.
 */
export function guestContext(deps: CustomerDependencies) {
  return async function asGuest<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string, guestId: string) => Promise<T>,
  ): Promise<T | { error: string }> {
    const credential = guestCredential(request);
    if (!credential) {
      reply.code(401);
      return { error: 'authentication required' };
    }
    const [tenantId, outletId, secret] = credential;
    // The digest covers the SECRET only, which is what service.mint_guest_session()
    // hashed. The tenant and outlet in front of it are a plain claim, not part of the
    // credential, and service.establish_guest_context() checks them against the row it
    // found rather than trusting them — so a forged prefix finds nothing, and a correct
    // prefix proves nothing on its own.
    const digest = createHash('sha256').update(secret).digest('hex');

    return deps.db.withoutContext(async (client) => {
      try {
        await client.query('BEGIN');
        const { rows } = await client.query(
          'SELECT service.establish_guest_context($1::uuid, $2::uuid, decode($3, $4)) AS guest_id',
          [tenantId, outletId, digest, 'hex'],
        );
        const result = await work(client, tenantId, outletId, rows[0].guest_id);
        await client.query('COMMIT');
        return result;
      } catch (error) {
        await client.query('ROLLBACK').catch(() => undefined);
        const message = error instanceof Error ? error.message : '';
        if (message.includes('GUEST_SESSION_NOT_LIVE')) {
          reply.code(401);
          deps.logger.warn('guest authentication refused', {
            correlationId: request.id, event: 'guest.refused', errorClass: 'GUEST_SESSION_NOT_LIVE',
          });
          return { error: 'authentication required' };
        }
        throw error;
      }
    });
  };
}

export function registerCustomerRoutes(app: FastifyInstance, deps: CustomerDependencies): void {
  const asGuest = guestContext(deps);

  // -------------------------------------------------------------------------
  // Entry: a code becomes a session
  // -------------------------------------------------------------------------

  app.post<{ Params: { tenantId: string; outletId: string }; Body: { code?: string } }>(
    '/c/v1/:tenantId/:outletId/session',
    {
      schema: {
        params: {
          type: 'object',
          required: ['tenantId', 'outletId'],
          properties: {
            tenantId: { type: 'string', format: 'uuid' },
            outletId: { type: 'string', format: 'uuid' },
          },
        },
        body: {
          type: 'object',
          required: ['code'],
          properties: { code: { type: 'string', minLength: 16, maxLength: 128 } },
        },
      },
    },
    async (request, reply) => {
      const { tenantId, outletId } = request.params;
      return deps.db.withoutContext(async (client) => {
        try {
          await client.query('BEGIN');
          const { rows } = await client.query(
            'SELECT * FROM service.open_guest_session($1::uuid, $2::uuid, $3)',
            [tenantId, outletId, request.body.code],
          );
          await client.query('COMMIT');
          const row = rows[0];
          return {
            guestToken: `${tenantId}.${outletId}.${row.guest_token}`,
            scanId: row.scan_id,
            tableSessionId: row.table_session_id,
            tableName: row.table_display_name,
            // No locale is guessed here. The surface offers the three explicitly and
            // records what the customer picks; a value chosen for them would be a
            // default that reads like a choice.
            locales: LOCALES,
          };
        } catch (error) {
          await client.query('ROLLBACK').catch(() => undefined);
          reply.code(401);
          return { error: 'this code is not valid here' };
        }
      });
    },
  );

  app.post<{ Body: { scanId: string; verification?: string; evidence?: string } }>(
    '/c/v1/join',
    {
      schema: {
        body: {
          type: 'object',
          required: ['scanId'],
          properties: {
            scanId: { type: 'string', format: 'uuid' },
            verification: { type: 'string', maxLength: 64 },
            evidence: { type: 'string', maxLength: 500 },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId) => {
        try {
          const { rows } = await client.query(
            'SELECT service.join_table_session($1::uuid, $2::uuid, $3::service.verification_method, $4) AS id',
            [tenantId, request.body.scanId, request.body.verification ?? null,
             request.body.evidence ?? null],
          );
          return { tableSessionId: rows[0].id };
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          if (message.includes('STALE_QR_VERIFICATION_REQUIRED')) {
            reply.code(409);
            // The surface has to be able to tell this apart from a plain failure, because
            // it is the one refusal a guest can actually resolve.
            return { error: 'verification required', reason: 'STALE_QR_VERIFICATION_REQUIRED' };
          }
          // AND EVERY OTHER NAMED REFUSAL, which this route used to answer 500 to.
          //
          // NO_OPEN_OCCUPANCY was the one a person actually met: the first guest to scan
          // the demonstration floor was told the server had broken, when the service was
          // correctly reporting that the table had no session to join. That is the fifth
          // instance in this repository of a named business rule answered as a server
          // fault — F-OPB-4b counted four in documents.ts — and it is the same shape every
          // time: a map of the refusals somebody remembered, beside a set of refusals
          // somebody else adds to.
          //
          // Derived rather than listed here, so a refusal added to
          // service.join_table_session() tomorrow does not become a 500 by being new.
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          if (!matched) throw error;
          reply.code(409);
          return { error: 'refused', reason: matched[1] };
        }
      }),
  );

  /**
   * Being seated: the route the guest surface calls after a scan (FR-TAB-003).
   *
   * `/c/v1/join` above joins an occupancy that already exists, and until OP-C nothing in
   * this repository created one — every INSERT INTO service.table_session was in a test.
   * So a guest who scanned an unoccupied table got a session, a scan, and then
   * NO_OPEN_OCCUPANCY from the cart, which is what the first person to open the
   * demonstration floor met.
   *
   * THE BRANCH IS NOT HERE. service.seat_guest_from_scan() decides whether this scan
   * opens an occupancy or joins one, because a surface that decided would be a second
   * opinion about whether a table is busy and the two would disagree the moment a party
   * sits down between the scan and the tap. This route passes the verification arguments
   * through unread and reports what came back.
   */
  app.post<{ Body: { scanId: string; verification?: string; evidence?: string } }>(
    '/c/v1/seat',
    {
      schema: {
        body: {
          type: 'object',
          required: ['scanId'],
          properties: {
            scanId: { type: 'string', format: 'uuid' },
            verification: { type: 'string', maxLength: 64 },
            evidence: { type: 'string', maxLength: 500 },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId) => {
        try {
          const { rows } = await client.query(
            `SELECT table_session_id, opened
               FROM service.seat_guest_from_scan($1::uuid, $2::uuid,
                                                $3::service.verification_method, $4)`,
            [tenantId, request.body.scanId, request.body.verification ?? null,
             request.body.evidence ?? null],
          );
          return { tableSessionId: rows[0].table_session_id, opened: rows[0].opened };
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          if (message.includes('STALE_QR_VERIFICATION_REQUIRED')) {
            reply.code(409);
            // Named, not flattened into a generic failure, for the same reason as on the
            // join route: it is the one refusal a guest can actually resolve, and after
            // OP-C the surface resolves it by presenting the code again rather than by
            // finding a member of staff.
            return { error: 'verification required', reason: 'STALE_QR_VERIFICATION_REQUIRED' };
          }
          // Every other refusal this path raises is named by the database, and a named
          // domain refusal is not a server fault. Reporting one as a 500 is the defect
          // the guest route already carried once, at M3-D, and four times in documents.ts.
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          if (!matched) throw error;
          reply.code(409);
          return { error: 'refused', reason: matched[1] };
        }
      }),
  );

  // -------------------------------------------------------------------------
  // The locale snapshot (FR-I18N-005)
  // -------------------------------------------------------------------------

  app.put<{ Body: { tableSessionId: string; locale: string } }>(
    '/c/v1/locale',
    {
      schema: {
        body: {
          type: 'object',
          required: ['tableSessionId', 'locale'],
          properties: {
            tableSessionId: { type: 'string', format: 'uuid' },
            locale: { type: 'string', enum: [...LOCALES] },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId) => {
        await client.query('SELECT service.record_locale_choice($1::uuid, $2::uuid, $3::menu.customer_locale)',
          [tenantId, request.body.tableSessionId, request.body.locale]);
        return { locale: request.body.locale, recorded: true };
      }),
  );

  // -------------------------------------------------------------------------
  // The menu, in one locale, complete or not at all
  // -------------------------------------------------------------------------

  app.get<{ Querystring: { locale?: string; snapshotId?: string } }>(
    '/c/v1/menu',
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId) => {
        const locale = isLocale(request.query.locale) ? request.query.locale : 'en';
        const snapshot = request.query.snapshotId ?? null;

        const { rows: snapshots } = await client.query(
          snapshot
            ? `SELECT id FROM menu.publication_snapshot WHERE id = $2::uuid AND tenant_id = $1::uuid`
            : `SELECT id FROM menu.publication_snapshot WHERE tenant_id = $1::uuid
                 ORDER BY published_at DESC LIMIT 1`,
          snapshot ? [tenantId, snapshot] : [tenantId],
        );
        if (snapshots.length === 0) {
          // An instructive empty state, not an error and not a fabricated menu
          // (FR-UX-014).
          return { locale, snapshotId: null, items: [], empty: 'NO_PUBLISHED_MENU' };
        }
        const snapshotId = snapshots[0].id;

        const { rows } = await client.query(
          `SELECT g.item_code, g.canonical_name, g.display_name, g.currency_code,
                  g.amount_minor::text AS amount_minor,
                  g.allergen_kitchen_code, g.declaration_class::text AS declaration_class,
                  g.written_warning, g.icon_key,
                  -- FR-MNU-004. Present in the seed since 0003 and returned by nothing
                  -- until OP-D, so a guest read a name and a price and decided on that.
                  g.short_description, g.long_description,
                  g.customer_visible_ingredients, g.preparation_minutes,
                  l.item_id, l.variant_id
             FROM menu.published_menu_for_guest($1::uuid, $2::uuid, $3::menu.customer_locale) g
             JOIN menu.publication_snapshot_line l
               ON l.snapshot_id = $2::uuid AND l.item_code = g.item_code
              AND l.amount_minor::text = g.amount_minor::text`,
          [tenantId, snapshotId, locale],
        );

        const byItem = new Map<string, {
          itemCode: string; itemId: string; variantId: string; name: string;
          currencyCode: string; amountMinor: string;
          shortDescription: string | null; longDescription: string | null;
          ingredients: string | null; preparationMinutes: number | null;
          allergens: { kitchenCode: string; declarationClass: string; writtenWarning: string;
                       iconKey: string | null }[];
        }>();

        for (const row of rows) {
          const key = `${row.item_code}|${row.amount_minor}`;
          if (!byItem.has(key)) {
            byItem.set(key, {
              itemCode: row.item_code,
              itemId: row.item_id,
              variantId: row.variant_id,
              name: row.display_name,
              currencyCode: row.currency_code,
              amountMinor: row.amount_minor,
              // Null travels as null. A dish with no description gets no description on
              // the screen; substituting the name, or an empty string the surface would
              // render as a blank line, would be this route inventing prose nobody wrote.
              shortDescription: row.short_description ?? null,
              longDescription: row.long_description ?? null,
              ingredients: row.customer_visible_ingredients ?? null,
              preparationMinutes: row.preparation_minutes ?? null,
              allergens: [],
            });
          }
          if (!row.allergen_kitchen_code) continue;

          // The M2-B handoff, honoured here rather than assumed. If a warning ever
          // arrives empty the ICON is dropped, never the words: a guest who sees nothing
          // asks, and a guest who sees a wheat symbol with no text has been told
          // something they cannot read.
          const warning = typeof row.written_warning === 'string' ? row.written_warning.trim() : '';
          byItem.get(key)!.allergens.push({
            kitchenCode: row.allergen_kitchen_code,
            declarationClass: row.declaration_class,
            writtenWarning: warning,
            iconKey: warning.length > 0 ? row.icon_key : null,
          });
        }

        return {
          locale,
          snapshotId,
          // Canonical values, localized by the surface (FR-I18N-005): minor units and an
          // ISO currency code travel, never a formatted string.
          items: [...byItem.values()],
        };
      }),
  );

  /**
   * The guest's own basket in the current occupancy, created on first ask.
   *
   * Find-or-create rather than a separate creation step: a basket is not a thing a
   * customer decides to have, it is where what they choose goes, and an extra round trip
   * before the first tap is a round trip on mobile data.
   */
  app.get('/c/v1/cart', async (request, reply) =>
    asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
      const { rows: sessions } = await client.query(
        `SELECT p.table_session_id AS id, s.customer_locale::text AS customer_locale
           FROM service.session_participant p
           JOIN service.table_session s ON s.id = p.table_session_id
          WHERE p.guest_session_id = $1::uuid AND s.state = 'open'
          ORDER BY p.joined_at DESC LIMIT 1`,
        [guestId],
      );
      if (sessions.length === 0) {
        reply.code(409);
        return { error: 'not seated', reason: 'NO_OPEN_OCCUPANCY' };
      }
      const tableSessionId = sessions[0].id as string;

      const { rows } = await client.query(
        // "Open" is not the same as "usable". service.cart_state has no 'submitted'
        // label on purpose — submission is a fact about an ORDER that references the
        // cart, and service.refuse_change_to_submitted_cart() reads exactly that. This
        // CTE did not, so a guest who had ordered was handed the same frozen basket
        // forever and every later line was refused. GJ-02's second order and GJ-04's
        // later add-on both walked into it; no slice check did, because none of them
        // asks for a basket twice with a submission in between. The condition here is
        // the trigger's own, so the route and the trigger cannot come to disagree about
        // what "already ordered" means.
        `WITH existing AS (
           SELECT c.id FROM service.cart c
            WHERE c.table_session_id = $3::uuid AND c.owner_guest_session_id = $4::uuid
              AND c.state = 'open'
              AND NOT EXISTS (SELECT 1 FROM ordering.customer_order o
                               WHERE o.tenant_id = c.tenant_id AND o.cart_id = c.id
                                 AND o.state <> 'rejected')
         ), created AS (
           INSERT INTO service.cart
             (tenant_id, outlet_id, table_session_id, kind, owner_guest_session_id)
           SELECT $1::uuid, $2::uuid, $3::uuid, 'personal', $4::uuid
            WHERE NOT EXISTS (SELECT 1 FROM existing)
           RETURNING id
         )
         SELECT id FROM existing UNION ALL SELECT id FROM created`,
        [tenantId, outletId, tableSessionId, guestId],
      );
      return {
        cartId: rows[0].id as string,
        tableSessionId,
        customerLocale: sessions[0].customer_locale ?? null,
      };
    }),
  );

  // -------------------------------------------------------------------------
  // Writes, each of which a browser may retry
  // -------------------------------------------------------------------------

  async function idempotent<T extends { id: string }>(
    request: FastifyRequest, reply: FastifyReply, client: PoolClient,
    tenantId: string, outletId: string, scope: string,
    perform: () => Promise<T>,
  ): Promise<{ id: string; replayed: boolean } | { error: string; reason: string }> {
    const key = idempotencyKey(request);
    if (!key) {
      reply.code(400);
      return { error: 'Idempotency-Key is required', reason: 'IDEMPOTENCY_KEY_ABSENT' };
    }
    const body = JSON.stringify(request.body ?? {});
    let claim;
    try {
      const { rows } = await client.query(
        'SELECT * FROM service.claim_idempotency($1::uuid, $2::uuid, $3, $4, $5)',
        [tenantId, outletId, scope, key, body],
      );
      claim = rows[0];
    } catch (error) {
      const message = error instanceof Error ? error.message : '';
      if (message.includes('IDEMPOTENCY_KEY_REUSED')) {
        reply.code(409);
        return { error: 'this key was used for a different request', reason: 'IDEMPOTENCY_KEY_REUSED' };
      }
      throw error;
    }

    if (claim.is_replay) {
      // The first attempt already did the work. Answering with its result is what makes
      // a retry safe; doing the work again is what makes it a duplicate.
      return { id: claim.result_id, replayed: true };
    }
    const created = await perform();
    await client.query('SELECT service.record_idempotent_result($1::uuid, $2, $3, $4::uuid)',
      [tenantId, scope, key, created.id]);
    return { id: created.id, replayed: false };
  }

  app.post<{ Body: { cartId: string; itemId: string; variantId: string; quantity?: number } }>(
    '/c/v1/cart/lines',
    {
      schema: {
        body: {
          type: 'object',
          required: ['cartId', 'itemId', 'variantId'],
          properties: {
            cartId: { type: 'string', format: 'uuid' },
            itemId: { type: 'string', format: 'uuid' },
            variantId: { type: 'string', format: 'uuid' },
            quantity: { type: 'integer', minimum: 1, maximum: 50 },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
        try {
          return await idempotent(
            request, reply, client, tenantId, outletId, 'cart_line', async () => {
              // Through service.add_cart_line(), not an INSERT that prices the line
              // here. This route used to call menu.effective_price() inline; the staff
              // route added at M3-D would then have been a second call site for the same
              // rule, and FR-POS-003A rejects two implementations that agree today. One
              // writer, two callers, and neither of them names a pricing function.
              const { rows } = await client.query(
                `SELECT service.add_cart_line($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                              $5::uuid, $6::integer, $7::uuid) AS id`,
                [tenantId, outletId, request.body.cartId, request.body.itemId,
                 request.body.variantId, request.body.quantity ?? 1, guestId],
              );
              return { id: rows[0].id as string };
            });
        } catch (error) {
          // A named domain refusal is not a server fault, and until M3-D this route
          // reported one as a 500. GJ-04 walked into it: a guest who orders and then
          // adds a later round hits CART_ALREADY_SUBMITTED, which is the basket
          // correctly refusing to change what somebody agreed to — and the guest was
          // shown a broken server instead of a reason. No slice check saw it, because
          // none of them adds a line to a cart it has already submitted.
          //
          // Outside idempotent() rather than inside: a refusal is not a RESULT, and
          // recording one against the idempotency key would answer the guest's retry
          // with the refusal instead of letting them try again.
          const message = error instanceof Error ? error.message : '';
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          if (!matched) throw error;
          reply.code(409);
          return { error: 'refused', reason: matched[1] };
        }
      }),
  );

  /**
   * Taking a line back out of the basket (FR-ORD-002).
   *
   * There was no way to until OP-C. service.add_cart_line() has existed since M3-D and
   * nothing ever removed one — no function, no route, no control on the guest surface.
   * Every golden journey adds items and places the order; none has ever changed its mind,
   * which is how an absence this plain survived three gates of browser measurement.
   *
   * NOT idempotent-keyed, and the asymmetry with the POST above is deliberate. A repeated
   * add is a second line and a duplicate charge, which is what the key exists to prevent.
   * A repeated remove of a line that is already gone is CART_LINE_UNKNOWN and has removed
   * nothing twice, so a retry needs no ledger to be safe.
   */
  app.delete<{ Params: { lineId: string }; Querystring: { cartId?: string } }>(
    '/c/v1/cart/lines/:lineId',
    {
      schema: {
        params: {
          type: 'object',
          required: ['lineId'],
          properties: { lineId: { type: 'string', format: 'uuid' } },
        },
        querystring: {
          type: 'object',
          properties: { cartId: { type: 'string', format: 'uuid' } },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId) => {
        try {
          const { rows } = await client.query(
            'SELECT service.remove_cart_line($1::uuid, $2::uuid, $3::uuid) AS cart_id',
            [tenantId, request.params.lineId, request.query.cartId ?? null],
          );
          return { removed: request.params.lineId, cartId: rows[0].cart_id };
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          // CART_LINE_UNKNOWN is a 404 and CART_ALREADY_SUBMITTED is a 409, and the
          // difference matters to the surface: the first means the line is already gone
          // and the basket should simply be redrawn without it, the second means the
          // basket is frozen and redrawing would hide a refusal the guest needs to see.
          if (message.includes('CART_LINE_UNKNOWN')) {
            reply.code(404);
            return { error: 'refused', reason: 'CART_LINE_UNKNOWN' };
          }
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          if (!matched) throw error;
          reply.code(409);
          return { error: 'refused', reason: matched[1] };
        }
      }),
  );

  /**
   * FR-ORD-002. The server-calculated preview a guest is shown before committing.
   *
   * Added at M3-D, and the reason is worth recording. M3-A built ordering.preview_cart()
   * and ordering.submit_order() and proved both against the database; no HTTP route ever
   * called them, because M3-A had no surface and M3-C's surface stopped at the basket.
   * That was invisible until the golden journeys tried to walk "browse, choose, submit"
   * as a guest actually does it and found there was nothing to submit THROUGH. A
   * requirement can be met in SQL and unreachable by the person it is written for.
   *
   * It calls exactly what the staff route calls. That is not a coincidence to be
   * maintained by hand: tests/m3d asserts the two sets of rule functions against each
   * other, and asserts from the catalog that no second implementation of any of them can
   * exist.
   */
  app.post<{ Body: { cartId: string; locale?: string } }>(
    '/c/v1/orders/preview',
    {
      schema: {
        body: {
          type: 'object', required: ['cartId'],
          properties: {
            cartId: { type: 'string', format: 'uuid' },
            locale: { type: 'string' },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT ordering.preview_cart($1::uuid, $2::uuid, $3::uuid,
                                          $4::menu.customer_locale) AS preview`,
            [tenantId, outletId, request.body.cartId, request.body.locale ?? 'en'],
          );
          return { preview: rows[0]?.preview ?? null };
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          reply.code(422);
          return { error: 'refused', reason: matched && matched[1] ? matched[1] : 'REFUSED' };
        }
      }),
  );

  /** FR-ORD-001A. The guest half of the one submission path, with origin 'guest_qr'. */
  app.post<{
    Body: {
      cartId: string; expectedTotalMinor: number; pricingDigest: string;
      locale?: string; allergyDeclarations?: unknown[]; notes?: unknown[];
      repeatIntent?: boolean;
    };
  }>(
    '/c/v1/orders',
    {
      schema: {
        body: {
          type: 'object',
          required: ['cartId', 'expectedTotalMinor', 'pricingDigest'],
          properties: {
            cartId: { type: 'string', format: 'uuid' },
            expectedTotalMinor: { type: 'integer' },
            pricingDigest: { type: 'string' },
            locale: { type: 'string' },
            allergyDeclarations: { type: 'array' },
            notes: { type: 'array' },
            repeatIntent: { type: 'boolean' },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
        const key = idempotencyKey(request);
        if (!key) {
          reply.code(400);
          return { error: 'Idempotency-Key is required', reason: 'IDEMPOTENCY_KEY_ABSENT' };
        }
        try {
          const { rows } = await client.query(
            `SELECT ordering.submit_order(
                      $1::uuid, $2::uuid, $3::uuid, $4, decode($5, 'hex'), $6::bigint,
                      $7::menu.customer_locale, gen_random_uuid(), gen_random_uuid(),
                      'guest_qr'::ordering.order_origin,
                      NULL::uuid, $8::uuid, $9::boolean,
                      $10::jsonb, $11::jsonb) AS id`,
            [tenantId, outletId, request.body.cartId, key, request.body.pricingDigest,
             request.body.expectedTotalMinor, request.body.locale ?? 'en', guestId,
             request.body.repeatIntent ?? false,
             JSON.stringify(request.body.allergyDeclarations ?? []),
             JSON.stringify(request.body.notes ?? [])],
          );
          // THE STATE TRAVELS BACK, AND THE SURFACE NEEDS IT TO TELL THE TRUTH.
          //
          // This used to answer with an id alone, so the guest surface had no way to know
          // what had become of the order and said "Your order is with the kitchen" in
          // every case. Under FR-ORD-007A's `staff_confirmed` that sentence is false: the
          // order is in 'submitted', no kitchen has seen it, and it waits for a person.
          // The surface cannot be truthful about an outcome it was not told.
          //
          // Read back rather than inferred from the policy. ordering.submit_order() may
          // accept automatically, may leave the order submitted, and at FR-ORD-007B may
          // hold it pending a verified payment; asking the row what happened is one
          // answer, and a surface that recomputed the policy would be a second.
          const placed = await client.query(
            `SELECT state::text AS state, accepted_at IS NOT NULL AS accepted
               FROM ordering.customer_order
              WHERE tenant_id = $1::uuid AND id = $2::uuid`,
            [tenantId, rows[0].id],
          );
          return {
            orderId: rows[0].id as string,
            state: placed.rows[0]?.state ?? null,
            accepted: placed.rows[0]?.accepted ?? false,
          };
        } catch (error) {
          const message = error instanceof Error ? error.message : '';
          const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
          reply.code(409);
          return { error: 'refused', reason: matched && matched[1] ? matched[1] : 'REFUSED' };
        }
      }),
  );

  app.post<{ Body: { tableSessionId: string; allergenId?: string; note?: string } }>(
    '/c/v1/allergy-concerns',
    {
      schema: {
        body: {
          type: 'object',
          required: ['tableSessionId'],
          properties: {
            tableSessionId: { type: 'string', format: 'uuid' },
            allergenId: { type: 'string', format: 'uuid' },
            note: { type: 'string', maxLength: 500 },
          },
        },
      },
    },
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId, outletId, guestId) =>
        idempotent(request, reply, client, tenantId, outletId, 'allergy_concern', async () => {
          const { rows } = await client.query(
            `INSERT INTO safety.allergy_concern
               (tenant_id, outlet_id, table_session_id, raised_by, guest_session_id,
                allergen_id, note, acknowledgement_wording_id, acknowledgement_text)
             SELECT $1::uuid, $2::uuid, $3::uuid, 'guest', $4::uuid, $5::uuid, $6,
                    w.id, w.wording
               FROM safety.approved_wording w
              WHERE w.tenant_id = $1::uuid AND w.purpose = 'allergy_acknowledgement'
                AND w.locale = 'en'
             RETURNING id`,
            [tenantId, outletId, request.body.tableSessionId, guestId,
             request.body.allergenId ?? null, request.body.note ?? null],
          );
          return { id: rows[0].id as string };
        })),
  );
}
