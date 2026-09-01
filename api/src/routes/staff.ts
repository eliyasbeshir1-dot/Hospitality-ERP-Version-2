/**
 * The staff surface's API: terminals, role home, the table view, operational search,
 * waiter-entered ordering, manager override and handover.
 *
 * THE ORDERING ENDPOINTS ARE THE POINT OF THIS FILE, AND THEY ARE THE THINNEST IN IT.
 *
 * FR-POS-003A says a waiter-entered order obeys the identical menu, modifier, price,
 * safety and authorization rules as a QR order, and rejects "two implementations that
 * agree today". So nothing below decides anything. There is no price arithmetic, no
 * availability branch, no allergen resolution and no authorization test written here.
 * Every one of those lives in a database function that M3-A, M2-A and M2-B already
 * built, and the guest route calls the same ones:
 *
 *   a priced cart line   service.add_cart_line()
 *   a preview            ordering.preview_cart()
 *   a submission         ordering.submit_order()   with origin 'waiter_entered'
 *   an amendment         ordering.amend_order_line()
 *   safety               resolved inside those, from safety.effective_allergens()
 *
 * The ONLY thing this file does that the guest route does not is pass a different
 * ordering.order_origin and a different actor. That is the channel dimension M3-A built
 * the aggregate with, and it is the whole of the difference.
 *
 * tests/m3d proves that structurally rather than taking this comment's word for it: it
 * enumerates the rule functions from the catalog, asserts each has exactly one
 * implementation, and asserts the set of them this file names is a subset of the set the
 * guest route names. A pricing rule added at M4 and re-implemented here fails that check
 * without anybody remembering to extend a list.
 *
 * These are staff routes. Every one authenticates a staff session through the same
 * db.withSession() M1-D built, and resolves the acting user FROM the session rather than
 * from the request body — a user id a caller can supply is a user id a caller can
 * choose.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface StaffDependencies {
  db: Database;
  logger: StructuredLogger;
}

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

function idempotencyKey(request: FastifyRequest): string | null {
  const raw = request.headers['idempotency-key'];
  const key = Array.isArray(raw) ? raw[0] : raw;
  return typeof key === 'string' && key.trim().length > 0 ? key.trim() : null;
}

/** The signature a database refusal carries, so a route can answer with the reason. */
function refusal(error: unknown): string | null {
  const message = error instanceof Error ? error.message : '';
  const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
  return matched && matched[1] ? matched[1] : null;
}

export function registerStaffRoutes(app: FastifyInstance, deps: StaffDependencies): void {
  async function asStaff<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string, userId: string,
           sessionId: string) => Promise<T>,
  ): Promise<T | { error: string }> {
    const token = staffToken(request);
    if (!token) {
      reply.code(401);
      return { error: 'authentication required' };
    }
    try {
      return await deps.db.withSession(token, async (client, context) => {
        const { rows } = await client.query(
          'SELECT user_account_id FROM identity.session WHERE id = $1::uuid',
          [context.sessionId],
        );
        if (rows.length === 0 || !rows[0].user_account_id) {
          reply.code(401);
          return { error: 'authentication required' } as T & { error: string };
        }
        return work(client, context.tenantId, context.outletId ?? '',
                    rows[0].user_account_id as string, context.sessionId as string);
      });
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        deps.logger.warn('staff authentication refused', {
          correlationId: request.id, event: 'staff.refused', errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  // -------------------------------------------------------------------------
  // Role home and the table view (FR-POS-002, FR-POS-004)
  // -------------------------------------------------------------------------

  /** FR-POS-002. Queues and next actions, overdue first — never a browsable list. */
  app.get('/s/v1/home', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { rows } = await client.query(
        `SELECT queue, subject_kind, subject_id, headline, next_action,
                waiting_since, elapsed_seconds, overdue
           FROM pos.role_home($1::uuid, $2::uuid, $3::uuid)`,
        [tenantId, outletId, userId],
      );
      return { queues: rows };
    }),
  );

  /** FR-POS-004. Occupancy with everything a waiter needs to decide where to go next. */
  app.get('/s/v1/tables', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      const { rows } = await client.query(
        `SELECT table_session_id, table_node_id, table_reference, opened_at, guests,
                assigned_waiter_id, open_requests, overdue_requests, open_orders,
                order_progress, unpaid_balance_minor, needs_attention, attention_reason
           FROM pos.table_view($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      // unpaid_balance_minor comes back NULL from the read model and is passed through
      // as null. A zero here would be a figure a waiter could act on, and billing is M4.
      return { tables: rows };
    }),
  );

  /** FR-UX-015. How much friction each action carries. The surface reads this; it never decides it. */
  app.get('/s/v1/confirmation-requirements', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId) => {
      const { rows } = await client.query(
        `SELECT action_code, consequence::text AS consequence, requires_reason
           FROM pos.confirmation_requirement
          WHERE tenant_id = $1::uuid ORDER BY action_code`,
        [tenantId],
      );
      return { requirements: rows };
    }),
  );

  // -------------------------------------------------------------------------
  // Fast entry and operational search (FR-POS-005, FR-POS-010A)
  // -------------------------------------------------------------------------

  app.get<{ Querystring: { q?: string; categoryId?: string; locale?: string } }>(
    '/s/v1/search',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT item_id, item_code, display_name, matched_field,
                    amount_minor::text AS amount_minor, currency_code,
                    availability::text AS availability, preparation_minutes
               FROM pos.staff_search($1::uuid, $2::uuid, $3::uuid, $4, $5::uuid, $6::menu.customer_locale)`,
            [tenantId, outletId, userId, request.query.q ?? null,
             request.query.categoryId ?? null, request.query.locale ?? 'en'],
          );
          return { results: rows };
        } catch (error) {
          const signature = refusal(error);
          if (signature === 'STAFF_SEARCH_CROSSES_SCOPE') {
            reply.code(403);
            return { error: 'not permitted', reason: signature };
          }
          throw error;
        }
      }),
  );

  app.get('/s/v1/fast-picks', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { rows } = await client.query(
        `SELECT f.item_id, f.position, i.canonical_name AS display_name, i.item_code
           FROM pos.fast_pick f
           JOIN menu.sellable_item i ON i.id = f.item_id
          WHERE f.tenant_id = $1::uuid AND f.outlet_id = $2::uuid
            AND (f.user_account_id IS NULL OR f.user_account_id = $3::uuid)
          ORDER BY f.position`,
        [tenantId, outletId, userId],
      );
      return { picks: rows };
    }),
  );

  // -------------------------------------------------------------------------
  // Waiter-entered ordering (FR-POS-003A) — the thin part
  // -------------------------------------------------------------------------

  /** The table's shared basket. A waiter fills the TABLE's, never a guest's personal one. */
  app.post<{ Body: { tableSessionId: string } }>(
    '/s/v1/carts',
    {
      schema: {
        body: {
          type: 'object', required: ['tableSessionId'],
          properties: { tableSessionId: { type: 'string', format: 'uuid' } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        const { rows } = await client.query(
          `WITH existing AS (
             SELECT id FROM service.cart
              WHERE tenant_id = $1::uuid AND table_session_id = $3::uuid
                AND kind = 'shared' AND state = 'open'
           ), created AS (
             INSERT INTO service.cart (tenant_id, outlet_id, table_session_id, kind)
             SELECT $1::uuid, $2::uuid, $3::uuid, 'shared'
              WHERE NOT EXISTS (SELECT 1 FROM existing)
             RETURNING id
           )
           SELECT id FROM existing UNION ALL SELECT id FROM created`,
          [tenantId, outletId, request.body.tableSessionId],
        );
        return { cartId: rows[0].id as string };
      }),
  );

  /** The same writer the guest route calls. No price is computed here. */
  app.post<{ Body: { cartId: string; itemId: string; variantId: string; quantity?: number } }>(
    '/s/v1/cart/lines',
    {
      schema: {
        body: {
          type: 'object', required: ['cartId', 'itemId', 'variantId'],
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
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT service.add_cart_line($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                          $5::uuid, $6::integer, NULL::uuid) AS id`,
            [tenantId, outletId, request.body.cartId, request.body.itemId,
             request.body.variantId, request.body.quantity ?? 1],
          );
          return { id: rows[0].id as string };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(422);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  /** FR-ORD-002. The same server-calculated preview the guest surface receives. */
  app.post<{ Body: { cartId: string; locale?: string } }>(
    '/s/v1/orders/preview',
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
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT ordering.preview_cart($1::uuid, $2::uuid, $3::uuid,
                                          $4::menu.customer_locale) AS preview`,
            [tenantId, outletId, request.body.cartId, request.body.locale ?? 'en'],
          );
          return { preview: rows[0]?.preview ?? null };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(422);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  /**
   * FR-POS-003A. The submission, through ordering.submit_order() — the same function the
   * guest route calls, with origin 'waiter_entered' and the acting user resolved from
   * the session. Everything that makes an order legal happens inside it: revalidation
   * against availability, hours and channel; re-pricing; the commercial and language
   * snapshots; the allergy declarations; the ledger. None of it is repeated here.
   */
  app.post<{
    Body: {
      cartId: string; expectedTotalMinor: number; pricingDigest: string;
      locale?: string; allergyDeclarations?: unknown[]; notes?: unknown[];
      repeatIntent?: boolean;
    };
  }>(
    '/s/v1/orders',
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
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
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
                      'waiter_entered'::ordering.order_origin,
                      $8::uuid, NULL::uuid, $9::boolean,
                      $10::jsonb, $11::jsonb) AS id`,
            [tenantId, outletId, request.body.cartId, key, request.body.pricingDigest,
             request.body.expectedTotalMinor, request.body.locale ?? 'en', userId,
             request.body.repeatIntent ?? false,
             JSON.stringify(request.body.allergyDeclarations ?? []),
             JSON.stringify(request.body.notes ?? [])],
          );
          return { orderId: rows[0].id as string };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            // The reason travels back verbatim. A staff surface that said only "refused"
            // would send a waiter to find a manager for a problem they could have fixed.
            reply.code(409);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  /**
   * FR-ORD-010 with FR-POS-006. An amendment after acceptance is a governed action, so
   * it names the override that authorized it. The override itself was recorded by
   * pos.approve_override() on a separate request, from the manager's own session; this
   * endpoint only checks that one exists, is for this order, and has not been used to
   * authorize something else.
   */
  app.post<{
    Body: { orderId: string; orderLineId: string; newQuantity: number; overrideId: string };
  }>(
    '/s/v1/orders/amend',
    {
      schema: {
        body: {
          type: 'object',
          required: ['orderId', 'orderLineId', 'newQuantity', 'overrideId'],
          properties: {
            orderId: { type: 'string', format: 'uuid' },
            orderLineId: { type: 'string', format: 'uuid' },
            newQuantity: { type: 'integer', minimum: 0, maximum: 50 },
            overrideId: { type: 'string', format: 'uuid' },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        const { rows: approvals } = await client.query(
          `SELECT id FROM pos.override_approval
            WHERE tenant_id = $1::uuid AND id = $2::uuid
              AND action_code = 'order.amend'
              AND subject_kind = 'order' AND subject_id = $3::uuid
              AND actor_user_id = $4::uuid`,
          [tenantId, request.body.overrideId, request.body.orderId, userId],
        );
        if (approvals.length === 0) {
          reply.code(403);
          return { error: 'not permitted', reason: 'OVERRIDE_WITHOUT_STEP_UP' };
        }
        try {
          await client.query(
            `SELECT ordering.amend_order_line($1::uuid, $2::uuid, $3::uuid, $4::integer,
                                              $5::uuid, NULL::uuid)`,
            [tenantId, request.body.orderId, request.body.orderLineId,
             request.body.newQuantity, userId],
          );
          return { amended: true, overrideId: request.body.overrideId };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(409);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  // -------------------------------------------------------------------------
  // Manager override (FR-POS-006)
  // -------------------------------------------------------------------------

  /**
   * The approving session is named, never the approving PERSON. Who the approver is gets
   * derived inside pos.approve_override() from that session, so there is no field here
   * by which a caller could claim somebody else authorized this.
   */
  app.post<{
    Body: {
      actionCode: string; approverSessionId: string; reasonCodeId: string;
      subjectKind: string; subjectId: string; reasonText?: string;
    };
  }>(
    '/s/v1/overrides',
    {
      schema: {
        body: {
          type: 'object',
          required: ['actionCode', 'approverSessionId', 'reasonCodeId', 'subjectKind', 'subjectId'],
          properties: {
            actionCode: { type: 'string', maxLength: 64 },
            approverSessionId: { type: 'string', format: 'uuid' },
            reasonCodeId: { type: 'string', format: 'uuid' },
            subjectKind: { type: 'string', maxLength: 32 },
            subjectId: { type: 'string', format: 'uuid' },
            reasonText: { type: 'string', maxLength: 500 },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT pos.approve_override($1::uuid, $2::uuid, $3, $4::uuid, $5::uuid,
                                         $6, $7::uuid, $8) AS id`,
            [tenantId, outletId, request.body.actionCode, request.body.approverSessionId,
             request.body.reasonCodeId, request.body.subjectKind, request.body.subjectId,
             request.body.reasonText ?? null],
          );
          return { overrideId: rows[0].id as string };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(403);
            return { error: 'not permitted', reason: signature };
          }
          throw error;
        }
      }),
  );

  // -------------------------------------------------------------------------
  // Handover (FR-POS-007)
  // -------------------------------------------------------------------------

  app.get('/s/v1/handovers', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { rows } = await client.query(
        `SELECT h.id, h.from_user_id, h.to_user_id, h.state::text AS state, h.proposed_at,
                (SELECT count(*) FROM pos.handover_item i
                  WHERE i.handover_id = h.id AND i.item_kind = 'table_session') AS tables,
                (SELECT count(*) FROM pos.handover_item i
                  WHERE i.handover_id = h.id AND i.item_kind = 'service_request') AS requests
           FROM pos.handover h
          WHERE h.tenant_id = $1::uuid AND h.outlet_id = $2::uuid
            AND (h.to_user_id = $3::uuid OR h.from_user_id = $3::uuid)
          ORDER BY h.proposed_at DESC`,
        [tenantId, outletId, userId],
      );
      return { handovers: rows };
    }),
  );

  app.post<{ Body: { toUserId: string; note?: string } }>(
    '/s/v1/handovers',
    {
      schema: {
        body: {
          type: 'object', required: ['toUserId'],
          properties: {
            toUserId: { type: 'string', format: 'uuid' },
            note: { type: 'string', maxLength: 500 },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT pos.propose_handover($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                         $3::uuid, $5) AS id`,
            [tenantId, outletId, userId, request.body.toUserId, request.body.note ?? null],
          );
          return { handoverId: rows[0].id as string };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(409);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  app.post<{ Params: { handoverId: string } }>(
    '/s/v1/handovers/:handoverId/acknowledge',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            'SELECT pos.acknowledge_handover($1::uuid, $2::uuid, $3::uuid) AS moved',
            [tenantId, request.params.handoverId, userId],
          );
          return { moved: Number(rows[0].moved) };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(403);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  // -------------------------------------------------------------------------
  // Terminals (FR-POS-001)
  // -------------------------------------------------------------------------

  app.get('/s/v1/terminals', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      const { rows } = await client.query(
        `SELECT t.device_id, t.profile::text AS profile, t.registered_at, t.revoked_at,
                d.registration_code
           FROM pos.terminal t
           JOIN org.device_registration d ON d.device_id = t.device_id
          WHERE t.tenant_id = $1::uuid AND t.outlet_id = $2::uuid
          ORDER BY d.registration_code`,
        [tenantId, outletId],
      );
      return { terminals: rows };
    }),
  );

  app.post<{ Body: { deviceId: string; profile: string } }>(
    '/s/v1/terminals',
    {
      schema: {
        body: {
          type: 'object', required: ['deviceId', 'profile'],
          properties: {
            deviceId: { type: 'string', format: 'uuid' },
            profile: { type: 'string', enum: ['point_of_sale', 'waiter_handheld', 'kitchen_display'] },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT pos.register_terminal($1::uuid, $2::uuid, $3::uuid,
                                          $4::pos.terminal_profile, $5::uuid) AS id`,
            [tenantId, outletId, request.body.deviceId, request.body.profile, userId],
          );
          return { deviceId: rows[0].id as string };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(422);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );

  /**
   * Revoking is destructive and graded 'deliberate', so it states a reason. The count of
   * sessions it ended comes back, because "revoked" with nothing ended would mean the
   * terminal is still taking orders.
   */
  app.post<{ Params: { deviceId: string }; Body: { reasonCodeId: string } }>(
    '/s/v1/terminals/:deviceId/revoke',
    {
      schema: {
        body: {
          type: 'object', required: ['reasonCodeId'],
          properties: { reasonCodeId: { type: 'string', format: 'uuid' } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            'SELECT pos.revoke_terminal($1::uuid, $2::uuid, $3::uuid, $4::uuid) AS ended',
            [tenantId, request.params.deviceId, userId, request.body.reasonCodeId],
          );
          return { sessionsEnded: Number(rows[0].ended) };
        } catch (error) {
          const signature = refusal(error);
          if (signature) {
            reply.code(422);
            return { error: 'refused', reason: signature };
          }
          throw error;
        }
      }),
  );
}
