/**
 * Checks, bills, splits and tips, on both surfaces.
 *
 * NOTHING HERE CALCULATES MONEY. Every figure a guest is shown or a cashier acts on comes
 * out of a database function that migration 0019 wrote and tests/m4a proves: the subtotal
 * from the order's own snapshot, the discount and tax from approved configuration, the
 * service charge from FR-CFG-001C's setting, the split from money.allocate(). A total
 * computed in TypeScript would be a second implementation of the one thing in this system
 * that must have exactly one, and it would be the implementation a guest actually sees.
 *
 * THE BILL SUMMARY AND THE TIP BOX ARE TWO ENDPOINTS.
 *
 * FR-BIL-007 puts the optional Tip box after or beside the bill summary and never inside
 * it. That is a rule about a rendered page, so it cannot be enforced here — but it can be
 * made hard to break. /c/v1/bill answers with the components and the total and carries no
 * tip at all; /c/v1/bill/tip-options answers with what one payer may tap. A surface that
 * drew a tip inside the summary would have to fetch it separately and put it there
 * deliberately, and tests/m4a measures the rendered page in a real browser to prove none
 * does.
 *
 * THERE IS NO DEFAULT TIP AND NO FIELD IN WHICH TO EXPRESS ONE. The options route returns
 * a display order and an amount per suggestion. It returns no "selected", because
 * billing.tip_suggestion has no column for one (NC-M4-001).
 *
 * No payment is taken anywhere in this file. Settling a balance at this gate is an
 * authorized disposition, and the tender is M4-B's.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface BillingDependencies {
  db: Database;
  logger: StructuredLogger;
  asGuest: <T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string, guestId: string) => Promise<T>,
  ) => Promise<T | { error: string }>;
}

const UUID = { type: 'string', format: 'uuid' } as const;

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

function idempotencyKey(request: FastifyRequest): string | null {
  const raw = request.headers['idempotency-key'];
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= 200 ? trimmed : null;
}

/** The signature a database refusal carries, so a route can answer with the reason. */
function refusal(error: unknown): string | null {
  const message = error instanceof Error ? error.message : '';
  const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
  return matched && matched[1] ? matched[1] : null;
}

/** The open occupancy this guest is sitting in, or null. */
async function seatedAt(client: PoolClient, guestId: string): Promise<string | null> {
  const { rows } = await client.query(
    `SELECT p.table_session_id AS id
       FROM service.session_participant p
       JOIN service.table_session s ON s.id = p.table_session_id
      WHERE p.guest_session_id = $1::uuid AND p.left_at IS NULL AND s.state = 'open'
      ORDER BY p.joined_at DESC LIMIT 1`,
    [guestId],
  );
  return rows.length > 0 ? (rows[0].id as string) : null;
}

export function registerBillingRoutes(app: FastifyInstance, deps: BillingDependencies): void {
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
        deps.logger.warn('authentication refused', {
          correlationId: request.id, event: 'auth.refused', errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  /** The most recent live bill on the guest's own table, or null. */
  async function liveBill(client: PoolClient, tableSessionId: string): Promise<string | null> {
    const { rows } = await client.query(
      `SELECT b.id
         FROM billing.bill b
         JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
        WHERE c.table_session_id = $1::uuid
          AND b.state IN ('issued', 'finalized', 'reissued')
        ORDER BY b.issued_at DESC LIMIT 1`,
      [tableSessionId],
    );
    return rows.length > 0 ? (rows[0].id as string) : null;
  }

  // -------------------------------------------------------------------------
  // What a guest reads (FR-BIL-007)
  // -------------------------------------------------------------------------

  /**
   * The translated bill summary. Components in the order they were computed, the total,
   * and the calculation version the whole thing was computed under.
   *
   * It carries NO TIP FIELD. Not "tip: 0" and not "tip: null" — no field, because a field
   * is a place a surface would put a number and a bill balance is not where a tip goes.
   */
  app.get('/c/v1/bill', async (request, reply) =>
    deps.asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
      const table = await seatedAt(client, guestId);
      if (!table) {
        reply.code(409);
        return { error: 'not seated', reason: 'GUEST_NOT_SEATED' };
      }
      const bill = await liveBill(client, table);
      if (!bill) return { bill: null, lines: [] };

      const summary = await client.query(
        `SELECT bill_number, state::text AS state, currency_code,
                bill_total_minor::text AS bill_total_minor,
                disposed_minor::text AS disposed_minor,
                outstanding_minor::text AS outstanding_minor,
                calculation_version, locale::text AS locale
           FROM billing.bill_summary($1::uuid, $2::uuid)`,
        [tenantId, bill],
      );
      const lines = await client.query(
        `SELECT stage, kind::text AS kind, label, currency_code,
                amount_minor::text AS amount_minor
           FROM billing.bill_preview_lines($1::uuid, $2::uuid)`,
        [tenantId, bill],
      );
      return { bill: { id: bill, ...(summary.rows[0] ?? {}) }, lines: lines.rows };
    }),
  );

  /**
   * The tip box, for ONE payer's share (FR-BIL-013, FR-BIL-015).
   *
   * A separate request from the summary, deliberately. There is no "selected" in the
   * answer and no way for the configuration to say which suggestion is preferred; a
   * surface that preselects one is inventing a fact, and NC-M4-001 measures the rendered
   * page for exactly that.
   */
  app.get<{ Querystring: { shareId?: string } }>(
    '/c/v1/bill/tip-options',
    async (request, reply) =>
      deps.asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
        const table = await seatedAt(client, guestId);
        if (!table) {
          reply.code(409);
          return { error: 'not seated', reason: 'GUEST_NOT_SEATED' };
        }
        const bill = await liveBill(client, table);
        if (!bill) return { shareId: null, options: [] };

        // The share this guest is paying. Named explicitly when the party has split, and
        // otherwise the single share the bill has. A guest with no share has nothing to
        // tip ON, which is different from having no tip.
        const share = request.query.shareId
          ? request.query.shareId
          : (await client.query(
              `SELECT id FROM billing.bill_share
                WHERE bill_id = $1::uuid ORDER BY share_number LIMIT 1`, [bill],
            )).rows[0]?.id ?? null;
        if (!share) return { shareId: null, options: [] };

        const { rows } = await client.query(
          `SELECT display_order, percentage::text AS percentage, currency_code,
                  amount_minor::text AS amount_minor
             FROM billing.tip_options($1::uuid, $2::uuid)`,
          [tenantId, share],
        );
        return { shareId: share, options: rows };
      }),
  );

  /**
   * One payer chooses their own tip (FR-BIL-015).
   *
   * It writes billing.tip and touches nothing else. There is no path from here to
   * billing.check_allocation, billing.bill_component or billing.bill, so choosing a tip
   * cannot reallocate a bill line — which is the requirement, made structural.
   */
  app.post<{ Body: { shareId: string; amountMinor: number; percentage?: number } }>(
    '/c/v1/bill/tip',
    {
      schema: {
        body: {
          type: 'object', required: ['shareId', 'amountMinor'],
          properties: {
            shareId: UUID,
            amountMinor: { type: 'integer', minimum: 1 },
            percentage: { type: 'number' },
          },
        },
      },
    },
    async (request, reply) =>
      deps.asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
        if (!idempotencyKey(request)) {
          reply.code(400);
          return { error: 'Idempotency-Key is required', reason: 'IDEMPOTENCY_KEY_ABSENT' };
        }
        const table = await seatedAt(client, guestId);
        if (!table) {
          reply.code(409);
          return { error: 'not seated', reason: 'GUEST_NOT_SEATED' };
        }
        try {
          const { rows } = await client.query(
            `INSERT INTO billing.tip
                 (tenant_id, outlet_id, bill_share_id, currency_code, amount_minor,
                  chosen_from_percentage)
             SELECT $1::uuid, $2::uuid, s.id, s.currency_code, $4::bigint, $5::numeric
               FROM billing.bill_share s
               JOIN billing.bill b ON b.tenant_id = s.tenant_id AND b.id = s.bill_id
               JOIN billing.check c ON c.tenant_id = b.tenant_id AND c.id = b.check_id
              WHERE s.id = $3::uuid AND c.table_session_id = $6::uuid
             RETURNING id`,
            [tenantId, outletId, request.body.shareId, request.body.amountMinor,
             request.body.percentage ?? null, table],
          );
          if (rows.length === 0) {
            reply.code(404);
            return { error: 'no such share on this table', reason: 'BILL_SHARE_NOT_FOUND' };
          }
          return { tipId: rows[0].id as string };
        } catch (error) {
          // A payer who taps twice has already chosen. billing.tip is unique on the
          // share, and a unique violation carries no signature of its own — PostgreSQL's
          // message names the CONSTRAINT — so it is mapped here rather than falling
          // through to a 500. A guest meeting an internal error because they tapped
          // twice is the defect this catch exists to prevent.
          const message = error instanceof Error ? error.message : '';
          if (message.includes('tip_one_per_share')) {
            reply.code(409);
            return { error: 'refused', reason: 'TIP_ALREADY_CHOSEN' };
          }
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
  // What staff do (FR-BIL-001 through FR-BIL-009)
  // -------------------------------------------------------------------------

  app.get<{ Querystring: { tableSessionId?: string } }>(
    '/s/v1/checks',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        if (!request.query.tableSessionId) {
          reply.code(400);
          return { error: 'tableSessionId is required', reason: 'TABLE_SESSION_ABSENT' };
        }
        const { rows } = await client.query(
          `SELECT check_id, check_number, state::text AS state, allocated_lines,
                  allocated_units, currency_code, allocated_minor::text AS allocated_minor,
                  bill_id, bill_state::text AS bill_state,
                  outstanding_minor::text AS outstanding_minor
             FROM billing.check_view($1::uuid, $2::uuid, $3::uuid)`,
          [tenantId, outletId, request.query.tableSessionId],
        );
        return { checks: rows };
      }),
  );

  app.post<{ Body: { tableSessionId: string } }>(
    '/s/v1/checks',
    {
      schema: {
        body: {
          type: 'object', required: ['tableSessionId'],
          properties: { tableSessionId: UUID },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.open_check($1::uuid, $2::uuid, $3::uuid, $4::uuid) AS id`,
            [tenantId, outletId, request.body.tableSessionId, userId],
          );
          return { checkId: rows[0].id as string };
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

  /** FR-BIL-002. Whole or partial. The double-billing guard is a trigger, not a check here. */
  app.post<{ Params: { checkId: string };
             Body: { orderLineId: string; quantity?: number } }>(
    '/s/v1/checks/:checkId/allocations',
    {
      schema: {
        body: {
          type: 'object', required: ['orderLineId'],
          properties: { orderLineId: UUID, quantity: { type: 'integer', minimum: 1 } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.allocate_to_check($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                              $5::integer) AS id`,
            [tenantId, outletId, request.params.checkId, request.body.orderLineId,
             request.body.quantity ?? null],
          );
          return { allocationId: rows[0].id as string };
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

  app.post<{ Body: { targetCheckId: string; sourceCheckId: string } }>(
    '/s/v1/checks/merge',
    {
      schema: {
        body: {
          type: 'object', required: ['targetCheckId', 'sourceCheckId'],
          properties: { targetCheckId: UUID, sourceCheckId: UUID },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.merge_checks($1::uuid, $2::uuid, $3::uuid, $4::uuid) AS moved`,
            [tenantId, outletId, request.body.targetCheckId, request.body.sourceCheckId],
          );
          return { movedAllocations: Number(rows[0].moved) };
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

  app.post<{ Params: { checkId: string }; Body: { orderLineIds: string[] } }>(
    '/s/v1/checks/:checkId/split',
    {
      schema: {
        body: {
          type: 'object', required: ['orderLineIds'],
          properties: { orderLineIds: { type: 'array', items: UUID, minItems: 1 } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.split_check($1::uuid, $2::uuid, $3::uuid, $4::uuid[],
                                        $5::uuid) AS id`,
            [tenantId, outletId, request.params.checkId, request.body.orderLineIds, userId],
          );
          return { checkId: rows[0].id as string };
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

  /** FR-BIL-005, FR-BIL-006. The calculation, and the version it was calculated under. */
  app.post<{ Body: { checkId: string; locale?: string } }>(
    '/s/v1/bills',
    {
      schema: {
        body: {
          type: 'object', required: ['checkId'],
          properties: { checkId: UUID, locale: { type: 'string' } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.issue_bill($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                       $5::menu.customer_locale) AS id`,
            [tenantId, outletId, request.body.checkId, userId, request.body.locale ?? 'en'],
          );
          return { billId: rows[0].id as string };
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

  /**
   * FR-BIL-003's five modes, each dispatched to the function that implements it.
   *
   * The dispatch is a switch over the mode and nothing else: no amount is computed here,
   * and the shares-sum-to-the-total trigger refuses any result that does not add up
   * whichever branch produced it.
   */
  app.post<{ Params: { billId: string };
             Body: { mode: string; payers?: number; amountsMinor?: number[];
                     assignments?: string[][] } }>(
    '/s/v1/bills/:billId/split',
    {
      schema: {
        body: {
          type: 'object', required: ['mode'],
          properties: {
            mode: { type: 'string',
                    enum: ['by_item', 'by_participant', 'equal_share', 'custom_amount',
                           'separate_orders'] },
            payers: { type: 'integer', minimum: 1 },
            amountsMinor: { type: 'array', items: { type: 'integer' } },
            assignments: { type: 'array', items: { type: 'array', items: UUID } },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        const bill = request.params.billId;
        const body = request.body;
        try {
          let sql: string;
          let params: unknown[];
          switch (body.mode) {
            case 'equal_share':
              if (!body.payers) {
                reply.code(400);
                return { error: 'payers is required', reason: 'SPLIT_PAYERS_ABSENT' };
              }
              sql = 'SELECT billing.split_equally($1::uuid, $2::uuid, $3::integer) AS shares';
              params = [tenantId, bill, body.payers];
              break;
            case 'by_participant':
              sql = 'SELECT billing.split_by_participant($1::uuid, $2::uuid) AS shares';
              params = [tenantId, bill];
              break;
            case 'separate_orders':
              sql = 'SELECT billing.split_by_separate_orders($1::uuid, $2::uuid) AS shares';
              params = [tenantId, bill];
              break;
            case 'by_item':
              if (!body.assignments) {
                reply.code(400);
                return { error: 'assignments are required', reason: 'SPLIT_ASSIGNMENT_ABSENT' };
              }
              sql = 'SELECT billing.split_by_item($1::uuid, $2::uuid, $3::jsonb) AS shares';
              params = [tenantId, bill, JSON.stringify(body.assignments)];
              break;
            case 'custom_amount':
              if (!body.amountsMinor) {
                reply.code(400);
                return { error: 'amountsMinor are required', reason: 'SPLIT_AMOUNTS_ABSENT' };
              }
              sql = 'SELECT billing.split_by_custom_amount($1::uuid, $2::uuid, $3::bigint[]) AS shares';
              params = [tenantId, bill, body.amountsMinor];
              break;
            default:
              reply.code(400);
              return { error: 'unknown split mode', reason: 'SPLIT_MODE_UNKNOWN' };
          }
          const { rows } = await client.query(sql, params);
          return { shares: Number(rows[0].shares) };
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

  /** FR-BIL-008's authorized disposition — the only route to a settled balance at M4-A. */
  app.post<{ Params: { billId: string };
             Body: { kind: string; amountMinor: number; overrideId: string;
                     reasonCodeId: string; reasonText: string;
                     transferredToCheckId?: string } }>(
    '/s/v1/bills/:billId/dispositions',
    {
      schema: {
        body: {
          type: 'object',
          required: ['kind', 'amountMinor', 'overrideId', 'reasonCodeId', 'reasonText'],
          properties: {
            kind: { type: 'string', enum: ['comped', 'written_off', 'transferred'] },
            amountMinor: { type: 'integer', minimum: 1 },
            overrideId: UUID,
            reasonCodeId: UUID,
            reasonText: { type: 'string', minLength: 1 },
            transferredToCheckId: UUID,
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT billing.record_disposition($1::uuid, $2::uuid, $3::uuid,
                        $4::billing.disposition_kind, $5::bigint, $6::uuid, $7::uuid,
                        $8, $9::uuid, $10::uuid) AS id`,
            [tenantId, outletId, request.params.billId, request.body.kind,
             request.body.amountMinor, request.body.overrideId, request.body.reasonCodeId,
             request.body.reasonText, userId, request.body.transferredToCheckId ?? null],
          );
          return { dispositionId: rows[0].id as string };
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

  /** FR-BIL-008. Settled, or authorized. A tip is neither. */
  app.post<{ Params: { billId: string } }>(
    '/s/v1/bills/:billId/finalize',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          await client.query(
            `SELECT billing.finalize_bill($1::uuid, $2::uuid, $3::uuid, $4::uuid)`,
            [tenantId, outletId, request.params.billId, userId],
          );
          return { finalized: true };
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

  /** FR-BIL-009. Void or reissue. There is no delete route, and no grant behind one. */
  app.post<{ Params: { billId: string };
             Body: { action: string; overrideId: string; reasonCodeId: string;
                     reasonText: string } }>(
    '/s/v1/bills/:billId/corrections',
    {
      schema: {
        body: {
          type: 'object',
          required: ['action', 'overrideId', 'reasonCodeId', 'reasonText'],
          properties: {
            action: { type: 'string', enum: ['void', 'reissue'] },
            overrideId: UUID,
            reasonCodeId: UUID,
            reasonText: { type: 'string', minLength: 1 },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          if (request.body.action === 'void') {
            await client.query(
              `SELECT billing.void_bill($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid,
                                        $6, $7::uuid)`,
              [tenantId, outletId, request.params.billId, request.body.overrideId,
               request.body.reasonCodeId, request.body.reasonText, userId],
            );
            return { voided: true };
          }
          const { rows } = await client.query(
            `SELECT billing.reissue_bill($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid,
                                         $6, $7::uuid) AS id`,
            [tenantId, outletId, request.params.billId, request.body.overrideId,
             request.body.reasonCodeId, request.body.reasonText, userId],
          );
          return { billId: rows[0].id as string };
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
}
