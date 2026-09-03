/**
 * Payment capture, verification, reversal and the cash drawer.
 *
 * NOTHING HERE DECIDES WHETHER MONEY ARRIVED. Every refusal this file can produce is
 * raised by a constraint or a function that migrations 0023 to 0025 wrote: a simulated
 * adapter cannot reach a live outcome because the two are different types; an allocation
 * whose payment is simulated, declined or resting on an unverified proof is refused by
 * payments.assert_allocation_is_earned(); change is arithmetic in the database. A route
 * that made any of those decisions would be a second implementation of them, and it would
 * be the one an operator actually meets.
 *
 * THE SIMULATOR IS REACHABLE AND SAYS SO. /s/v1/payments/simulate exists because
 * FR-PAY-015 says the direct provider APIs remain simulated until contracted, and a fence
 * with nothing behind it is not a fence — NC-M4-003 has to attempt the forbidden write
 * through a real path rather than against a table. The route answers with
 * `simulated: true` and a result typed payments.simulated_outcome, which no live column
 * accepts. It cannot be pointed at a live adapter: the function refuses.
 *
 * NO CARD DATA HAS A PARAMETER. A terminal result takes a scheme, a four-digit tail and
 * an approval code, because that is what is printed on a merchant slip. There is no field
 * for a primary account number, and payments.refuse_card_data() walks every string on
 * every row in this schema in case a later column forgets.
 *
 * WHO VERIFIED IS NOT A PARAMETER EITHER. payments.verify_proof() and
 * cash.transition_shift() read the person from the live session in context, so there is
 * no argument by which a caller could attest on somebody else's behalf. That is M3-D's
 * reasoning about override approvers, and it is what makes NC-M4-004 a property of the
 * schema rather than a rule somebody follows.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface PaymentDependencies {
  db: Database;
  logger: StructuredLogger;
}

const UUID = { type: 'string', format: 'uuid' } as const;

/** The six providers the database knows. Mirrored so a body can be rejected before it
 *  reaches a cast that would fail with a less useful message; payments.provider remains
 *  the authority and tests/m4b asserts this list equals it. */
const PROVIDERS = [
  'cash', 'external_terminal', 'telebirr_proof', 'cbe_birr_proof',
  'telebirr_direct', 'cbe_birr_direct',
] as const;

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

function refusal(error: unknown): string | null {
  const message = error instanceof Error ? error.message : '';
  const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
  return matched && matched[1] ? matched[1] : null;
}

/**
 * How a database refusal becomes a status code.
 *
 * Every entry is a signature some constraint or function raises. The 402 is deliberate
 * and is the only one of its kind in this system: an unverified or simulated claim is not
 * a malformed request and not a permission problem — it is a statement that the money is
 * not there.
 */
const STATUS: Record<string, number> = {
  UNVERIFIED_OR_SIMULATED_PAYMENT_CLAIM: 402,
  CARD_DATA_RETAINED: 422,
  SELF_APPROVAL_ACCEPTED: 403,
  REOPENED_SHIFT_NOT_RESOLVED: 409,
  FINALIZED_SHIFT_MUTATED: 409,
  UNKNOWN_SCHEMA_ACCEPTED: 409,
  VERIFICATION_WITHOUT_ATTRIBUTOR: 422,
  PAYMENT_TENDER_INSUFFICIENT: 422,
  PAYMENT_TENDER_NOT_EXACT: 422,
  PAYMENT_TENDER_NOT_FULLY_ALLOCATED: 409,
  PAYMENT_INTENT_EXPIRED: 409,
  PAYMENT_INTENT_NOT_FOUND: 404,
  PAYMENT_METHOD_NOT_PERMITTED: 409,
  PAYMENT_ADAPTER_NOT_REGISTERED: 404,
  PAYMENT_ADAPTER_INACTIVE: 409,
  PAYMENT_CONFIGURATION_ABSENT: 412,
  PAYMENT_CONFIGURATION_EMPTY: 422,
  PAYMENT_NOT_FOUND: 404,
  PROOF_NOT_FOUND: 404,
  PROOF_ALREADY_RESOLVED: 409,
  ALLOCATION_NOT_FOUND: 404,
  TERMINAL_RESULT_NOT_FOUND: 404,
  REVERSAL_EXCEEDS_ALLOCATION: 409,
  BILL_NOT_FOUND: 404,
  BILL_NOT_PAYABLE: 409,
  CASH_SHIFT_NOT_FOUND: 404,
  CASH_SHIFT_TRANSITION_INVALID: 409,
  CASH_MOVEMENT_WRONG_PROVIDER: 422,
  CASH_TALLY_NOT_THE_COUNT: 409,
  CASH_TALLY_CURRENCY_MISMATCH: 422,
  CUSTODY_AMOUNT_DISAGREES: 409,
  CUSTODY_MOVEMENT_WRONG_KIND: 422,
  SESSION_NOT_LIVE: 401,
  OVERRIDE_NOT_FOUND: 404,
};

export function registerPaymentRoutes(app: FastifyInstance, deps: PaymentDependencies): void {
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
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  /**
   * Answer with the reason the database gave.
   *
   * IT DOES NOT RETHROW, and that is deliberate. M1-D's withSession() wraps a request in
   * a transaction and converts anything thrown inside it into a refused session, so a
   * rethrow here becomes "401 authentication required" — for a permission error, for a
   * constraint nobody mapped, and for a genuine bug alike. Three defects in this slice
   * presented as authentication failures before that was noticed, and each cost a
   * bisection to find. An unmapped refusal is a 500 that NAMES the signature it could not
   * place, which is diagnosable; a 401 for a card-data violation is not.
   */
  function answer(reply: FastifyReply, error: unknown):
      { error: string; reason: string; sqlstate?: string } {
    const reason = refusal(error);
    if (reason && STATUS[reason] !== undefined) {
      reply.code(STATUS[reason] as number);
      return { error: 'refused', reason };
    }
    reply.code(500);
    // The SQLSTATE, and NOT the message. A code is five characters of ASCII that cannot
    // contain a card number or anything else FR-SEC-007 keeps out of logs, and it is
    // enough to find the constraint or the RAISE that produced it. Logging the message
    // would put whatever the caller sent into the log, which is the thing this slice
    // spends a trigger preventing.
    const sqlstate = (error as { code?: string })?.code ?? 'unknown';
    deps.logger.error('unmapped database refusal', {
      event: 'payment.unmapped', errorClass: reason ?? 'UNKNOWN', sqlstate,
    });
    return { error: 'refused', reason: reason ?? 'UNMAPPED_REFUSAL', sqlstate };
  }

  // -------------------------------------------------------------------------
  // Intent (FR-PAY-001, FR-PAY-012)
  // -------------------------------------------------------------------------

  app.post('/s/v1/payments/intents', {
    schema: {
      body: {
        type: 'object',
        required: ['billId', 'billAmountMinor'],
        additionalProperties: false,
        properties: {
          billId: UUID,
          billShareId: UUID,
          billAmountMinor: { type: 'integer', minimum: 0 },
          tipAmountMinor: { type: 'integer', minimum: 0 },
          tipId: UUID,
          permittedProviders: {
            type: 'array', items: { type: 'string', enum: PROVIDERS as unknown as string[] },
          },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const body = request.body as {
        billId: string; billShareId?: string; billAmountMinor: number;
        tipAmountMinor?: number; tipId?: string; permittedProviders?: string[];
      };
      // FR-PAY-012's key comes from the HEADER, not the body. A retry is the same request
      // sent again; a body that carried its own key would let two different requests
      // claim to be one retry of each other.
      const key = idempotencyKey(request);
      if (!key) {
        reply.code(400);
        return { error: 'Idempotency-Key required', reason: 'IDEMPOTENCY_KEY_ABSENT' };
      }
      try {
        const { rows } = await client.query(
          `SELECT payments.create_intent($1::uuid, $2::uuid, $3::uuid, $4::text,
                                         $5::bigint, $6::uuid, $7::bigint, $8::uuid,
                                         $9::uuid, $10::payments.provider[]) AS id`,
          [tenantId, outletId, body.billId, key, body.billAmountMinor, userId,
           body.tipAmountMinor ?? 0, body.tipId ?? null, body.billShareId ?? null,
           body.permittedProviders ?? null],
        );
        reply.code(201);
        return { intentId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  // -------------------------------------------------------------------------
  // The three live methods (FR-PAY-002, FR-PAY-003, FR-PAY-014)
  // -------------------------------------------------------------------------

  app.post('/s/v1/payments/:intentId/cash', {
    schema: {
      params: { type: 'object', required: ['intentId'], properties: { intentId: UUID } },
      body: {
        type: 'object', required: ['tenderedMinor'], additionalProperties: false,
        // NOTE WHAT IS ABSENT: a change field. FR-PAY-002 wants change RECORDED, and the
        // surface sends what the guest handed over. A change amount computed in a browser
        // is a number nobody can reconcile against a drawer.
        properties: { tenderedMinor: { type: 'integer', minimum: 1 } },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { intentId } = request.params as { intentId: string };
      const { tenderedMinor } = request.body as { tenderedMinor: number };
      try {
        const { rows } = await client.query(
          `SELECT payments.record_cash_payment($1::uuid, $2::uuid, $3::uuid, $4::bigint,
                                               $5::uuid) AS id`,
          [tenantId, outletId, intentId, tenderedMinor, userId],
        );
        reply.code(201);
        return { paymentId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/terminal-results', {
    schema: {
      body: {
        type: 'object',
        required: ['terminalReference', 'scheme', 'currencyCode', 'amountMinor', 'outcome'],
        additionalProperties: false,
        properties: {
          terminalReference: { type: 'string', minLength: 1, maxLength: 64 },
          scheme: { type: 'string', minLength: 1, maxLength: 32 },
          currencyCode: { type: 'string', minLength: 3, maxLength: 3 },
          amountMinor: { type: 'integer', minimum: 1 },
          outcome: { type: 'string', enum: ['approved', 'declined'] },
          // Four digits, and the schema says so as well as the CHECK. Two locks, and the
          // one here gives an operator a message rather than a constraint name.
          maskedTail: { type: 'string', pattern: '^[0-9]{4}$' },
          approvalCode: { type: 'string', pattern: '^[A-Za-z0-9]{1,12}$' },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const b = request.body as {
        terminalReference: string; scheme: string; currencyCode: string;
        amountMinor: number; outcome: string; maskedTail?: string; approvalCode?: string;
      };
      try {
        const { rows } = await client.query(
          `SELECT payments.record_terminal_result($1::uuid, $2::uuid, $3::text, $4::text,
                    $5::char(3), $6::bigint, $7::payments.live_outcome, $8::uuid,
                    $9::text, $10::text) AS id`,
          [tenantId, outletId, b.terminalReference, b.scheme, b.currencyCode,
           b.amountMinor, b.outcome, userId, b.maskedTail ?? null,
           b.approvalCode ?? null],
        );
        reply.code(201);
        return { terminalResultId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/payments/:intentId/terminal', {
    schema: {
      params: { type: 'object', required: ['intentId'], properties: { intentId: UUID } },
      body: {
        type: 'object', required: ['terminalResultId', 'tenderedMinor'],
        additionalProperties: false,
        properties: { terminalResultId: UUID, tenderedMinor: { type: 'integer', minimum: 1 } },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { intentId } = request.params as { intentId: string };
      const b = request.body as { terminalResultId: string; tenderedMinor: number };
      try {
        const { rows } = await client.query(
          `SELECT payments.record_terminal_payment($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                                   $5::bigint, $6::uuid) AS id`,
          [tenantId, outletId, intentId, b.terminalResultId, b.tenderedMinor, userId],
        );
        reply.code(201);
        return { paymentId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/proofs', {
    schema: {
      body: {
        type: 'object',
        required: ['provider', 'currencyCode', 'amountMinor', 'providerReference'],
        additionalProperties: false,
        properties: {
          provider: { type: 'string', enum: ['telebirr_proof', 'cbe_birr_proof'] },
          currencyCode: { type: 'string', minLength: 3, maxLength: 3 },
          amountMinor: { type: 'integer', minimum: 1 },
          providerReference: { type: 'string', minLength: 1, maxLength: 128 },
          maskedIdentifier: { type: 'string', maxLength: 64 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      const b = request.body as {
        provider: string; currencyCode: string; amountMinor: number;
        providerReference: string; maskedIdentifier?: string;
      };
      try {
        const { rows } = await client.query(
          `SELECT payments.raise_proof($1::uuid, $2::uuid, $3::payments.provider,
                                       $4::char(3), $5::bigint, $6::text, $7::text) AS id`,
          [tenantId, outletId, b.provider, b.currencyCode, b.amountMinor,
           b.providerReference, b.maskedIdentifier ?? null],
        );
        // 201 and PENDING. FR-PAY-014 leaves unverified proof pending rather than paid,
        // and the answer says so rather than leaving a caller to assume.
        reply.code(201);
        return { proofId: rows[0].id as string, state: 'pending' };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/proofs/:proofId/verify', {
    schema: {
      params: { type: 'object', required: ['proofId'], properties: { proofId: UUID } },
      body: {
        type: 'object', required: ['whatYouSaw'], additionalProperties: false,
        // The only field. WHO verified is not here and cannot be: payments.verify_proof()
        // reads it from the live session, so an attestation is always attributable to the
        // person whose credentials were used rather than to whoever a body names.
        properties: { whatYouSaw: { type: 'string', minLength: 1, maxLength: 500 } },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId) => {
      const { proofId } = request.params as { proofId: string };
      const { whatYouSaw } = request.body as { whatYouSaw: string };
      try {
        await client.query('SELECT payments.verify_proof($1::uuid, $2::uuid, $3::text)',
                           [tenantId, proofId, whatYouSaw]);
        return { proofId, state: 'verified' };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/payments/:intentId/proof', {
    schema: {
      params: { type: 'object', required: ['intentId'], properties: { intentId: UUID } },
      body: {
        type: 'object', required: ['proofId', 'tenderedMinor'], additionalProperties: false,
        properties: { proofId: UUID, tenderedMinor: { type: 'integer', minimum: 1 } },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { intentId } = request.params as { intentId: string };
      const b = request.body as { proofId: string; tenderedMinor: number };
      try {
        const { rows } = await client.query(
          `SELECT payments.record_proof_payment($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                                                $5::bigint, $6::uuid) AS id`,
          [tenantId, outletId, intentId, b.proofId, b.tenderedMinor, userId],
        );
        reply.code(201);
        return { paymentId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  // -------------------------------------------------------------------------
  // The simulated path, labelled as what it is (FR-PAY-015)
  // -------------------------------------------------------------------------

  app.post('/s/v1/payments/simulate', {
    schema: {
      body: {
        type: 'object', required: ['provider', 'currencyCode', 'amountMinor'],
        additionalProperties: false,
        properties: {
          provider: { type: 'string', enum: ['telebirr_direct', 'cbe_birr_direct'] },
          currencyCode: { type: 'string', minLength: 3, maxLength: 3 },
          amountMinor: { type: 'integer', minimum: 1 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const b = request.body as { provider: string; currencyCode: string; amountMinor: number };
      try {
        const { rows } = await client.query(
          `SELECT payments.invoke_direct_provider($1::uuid, $2::uuid,
                    $3::payments.provider, $4::char(3), $5::bigint, $6::uuid)::text
                  AS result`,
          [tenantId, outletId, b.provider, b.currencyCode, b.amountMinor, userId],
        );
        // `simulated: true` is in the answer and is not derivable from the result, which
        // reads 'approved' exactly as a live one would. A caller that ignored this field
        // would still be unable to settle anything: the write refuses.
        return { simulated: true, result: rows[0].result as string,
                 note: 'not contracted; this settles nothing (FR-PAY-015)' };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  // -------------------------------------------------------------------------
  // Allocations and reversal (FR-PAY-017, FR-PAY-009)
  // -------------------------------------------------------------------------

  app.get('/s/v1/payments/:paymentId/allocations', {
    schema: {
      params: { type: 'object', required: ['paymentId'], properties: { paymentId: UUID } },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId) => {
      const { paymentId } = request.params as { paymentId: string };
      // Every figure is read out of the column it was stored in. Nothing here consults a
      // bill, so a bill reissued after capture does not change what a guest handed over.
      const { rows } = await client.query(
        `SELECT allocation_id, target, bill_id, tip_id, currency_code,
                amount_minor::text AS amount_minor,
                reversed_minor::text AS reversed_minor,
                net_minor::text AS net_minor
           FROM payments.allocation_view($1::uuid, $2::uuid)`,
        [tenantId, paymentId],
      );
      return { paymentId, allocations: rows };
    }),
  );

  app.post('/s/v1/allocations/:allocationId/reversal', {
    schema: {
      params: { type: 'object', required: ['allocationId'], properties: { allocationId: UUID } },
      body: {
        type: 'object', required: ['kind', 'amountMinor', 'reasonCodeId', 'reasonText'],
        additionalProperties: false,
        properties: {
          kind: { type: 'string', enum: ['refund', 'reversal', 'correction'] },
          amountMinor: { type: 'integer', minimum: 1 },
          reasonCodeId: UUID,
          reasonText: { type: 'string', minLength: 1, maxLength: 500 },
          overrideId: UUID,
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { allocationId } = request.params as { allocationId: string };
      const b = request.body as {
        kind: string; amountMinor: number; reasonCodeId: string; reasonText: string;
        overrideId?: string;
      };
      try {
        const { rows } = await client.query(
          `SELECT payments.reverse_allocation($1::uuid, $2::uuid, $3::uuid,
                    $4::payments.reversal_kind, $5::bigint, $6::uuid, $7::text, $8::uuid,
                    $9::uuid) AS id`,
          [tenantId, outletId, allocationId, b.kind, b.amountMinor, b.reasonCodeId,
           b.reasonText, userId, b.overrideId ?? null],
        );
        reply.code(201);
        return { reversalId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.get('/s/v1/payments/reconciliation', {
    schema: {
      querystring: {
        type: 'object', required: ['from', 'to'],
        properties: { from: { type: 'string' }, to: { type: 'string' } },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      const q = request.query as { from: string; to: string };
      // billAllocationMinor and tipAllocationMinor are separate fields and no field sums
      // them. FR-PAY-013 forbids merging tips into sales revenue, and the merge would
      // happen here if it happened anywhere.
      const { rows } = await client.query(
        `SELECT provider, payment_count::text AS payment_count,
                tendered_minor::text AS tendered_minor,
                change_minor::text AS change_minor,
                bill_allocation_minor::text AS bill_allocation_minor,
                tip_allocation_minor::text AS tip_allocation_minor,
                reversed_minor::text AS reversed_minor,
                provider_references::text AS provider_references
           FROM payments.reconciliation($1::uuid, $2::uuid, $3::timestamptz,
                                        $4::timestamptz)`,
        [tenantId, outletId, q.from, q.to],
      );
      return { from: q.from, to: q.to, providers: rows };
    }),
  );

  app.get('/s/v1/payments/adapters', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      // FR-INT-011. Only the payment adapters, because only they exist. Node
      // connectivity, synchronization lag and printer status are absent rather than
      // reported healthy, and the closure register names M4-C and M5a.
      const { rows } = await client.query(
        `SELECT provider, mode, active, healthy, detail
           FROM integration.payment_adapter_health($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      const unhealthy = rows.filter((r) => r.healthy === false);
      if (unhealthy.length > 0) reply.code(503);
      return { adapters: rows, ready: unhealthy.length === 0 };
    }),
  );

  // -------------------------------------------------------------------------
  // The drawer (FR-CSH-001 … FR-CSH-004, FR-CSH-007, FR-CSH-008)
  // -------------------------------------------------------------------------

  app.post('/s/v1/cash/shifts', {
    schema: {
      body: {
        type: 'object',
        required: ['terminalDeviceId', 'currencyCode', 'openingFloatMinor'],
        additionalProperties: false,
        properties: {
          terminalDeviceId: UUID,
          currencyCode: { type: 'string', minLength: 3, maxLength: 3 },
          openingFloatMinor: { type: 'integer', minimum: 0 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const b = request.body as {
        terminalDeviceId: string; currencyCode: string; openingFloatMinor: number;
      };
      try {
        const { rows } = await client.query(
          `SELECT cash.open_shift($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::char(3),
                                  $6::bigint) AS id`,
          [tenantId, outletId, b.terminalDeviceId, userId, b.currencyCode,
           b.openingFloatMinor],
        );
        reply.code(201);
        return { shiftId: rows[0].id as string, state: 'open' };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/cash/shifts/:shiftId/count', {
    schema: {
      params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
      body: {
        type: 'object', required: ['phase', 'tally'], additionalProperties: false,
        properties: {
          phase: { type: 'string', enum: ['opening', 'closing', 'recount'] },
          // The tally, and NOT a counted total. FR-CSH-003's counted figure is the sum of
          // the denominations, derived in cash.record_count(). A count whose total and
          // breakdown are two independent inputs is a count in which one can be adjusted
          // to make the evening balance.
          tally: {
            type: 'array', minItems: 1,
            items: {
              type: 'object', required: ['denominationMinor', 'pieceCount'],
              additionalProperties: false,
              properties: {
                denominationMinor: { type: 'integer', minimum: 1 },
                pieceCount: { type: 'integer', minimum: 0 },
              },
            },
          },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { shiftId } = request.params as { shiftId: string };
      const b = request.body as {
        phase: string; tally: { denominationMinor: number; pieceCount: number }[];
      };
      const tally = b.tally.map((t) => ({
        denomination_minor: t.denominationMinor, piece_count: t.pieceCount,
      }));
      try {
        const { rows } = await client.query(
          `SELECT cash.record_count($1::uuid, $2::uuid, $3::uuid, $4::cash.count_phase,
                                    $5::jsonb, $6::uuid) AS id`,
          [tenantId, outletId, shiftId, b.phase, JSON.stringify(tally), userId],
        );
        const detail = await client.query(
          `SELECT expected_minor::text AS expected_minor,
                  counted_minor::text AS counted_minor,
                  over_short_minor::text AS over_short_minor
             FROM cash.drawer_count WHERE tenant_id = $1::uuid AND id = $2::uuid`,
          [tenantId, rows[0].id],
        );
        reply.code(201);
        return { countId: rows[0].id as string, ...(detail.rows[0] ?? {}) };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/cash/shifts/:shiftId/transition', {
    schema: {
      params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
      body: {
        type: 'object', required: ['toState'], additionalProperties: false,
        properties: {
          // 'finalized' is reachable and 'resolved' is reachable; there is no edge
          // between 'reopened' and 'finalized', which is NC-M4-006 and is enforced in
          // cash.transition_shift() rather than by this list.
          toState: {
            type: 'string',
            enum: ['submitted', 'verified', 'finalized', 'reopened', 'resolved', 'open'],
          },
          overrideId: UUID,
          reasonCodeId: UUID,
          reasonText: { type: 'string', maxLength: 500 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { shiftId } = request.params as { shiftId: string };
      const b = request.body as {
        toState: string; overrideId?: string; reasonCodeId?: string; reasonText?: string;
      };
      try {
        // NOTE WHAT IS NOT SENT: who verified. cash.transition_shift() reads the verifier
        // from the live session, so a manager approving from the cashier's terminal
        // resolves to the cashier and the CHECK refuses. NC-M4-004.
        await client.query(
          `SELECT cash.transition_shift($1::uuid, $2::uuid, $3::cash.shift_state,
                                        $4::uuid, $5::uuid, $6::uuid, $7::text)`,
          [tenantId, shiftId, b.toState, userId, b.overrideId ?? null,
           b.reasonCodeId ?? null, b.reasonText ?? null],
        );
        return { shiftId, state: b.toState };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.post('/s/v1/cash/shifts/:shiftId/custody', {
    schema: {
      params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
      body: {
        type: 'object',
        required: ['destination', 'sealedBagReference', 'amountMinor', 'acceptedByUserId'],
        additionalProperties: false,
        properties: {
          destination: { type: 'string', enum: ['safe', 'bank'] },
          sealedBagReference: { type: 'string', minLength: 1, maxLength: 64 },
          amountMinor: { type: 'integer', minimum: 1 },
          acceptedByUserId: UUID,
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { shiftId } = request.params as { shiftId: string };
      const b = request.body as {
        destination: string; sealedBagReference: string; amountMinor: number;
        acceptedByUserId: string;
      };
      try {
        // The drop and the bag are one transaction. A bag recorded without the movement
        // that emptied the drawer would make the count right and the safe wrong.
        const movement = await client.query(
          `INSERT INTO cash.movement
              (tenant_id, outlet_id, shift_id, kind, currency_code, amount_minor,
               actor_user_id)
           SELECT $1::uuid, $2::uuid, $3::uuid, 'drop', s.currency_code,
                  -$4::bigint, $5::uuid
             FROM cash.shift s WHERE s.tenant_id = $1::uuid AND s.id = $3::uuid
           RETURNING id, currency_code`,
          [tenantId, outletId, shiftId, b.amountMinor, userId],
        );
        if (movement.rows.length === 0) {
          reply.code(404);
          return { error: 'refused', reason: 'CASH_SHIFT_NOT_FOUND' };
        }
        const { rows } = await client.query(
          `INSERT INTO cash.custody_transfer
              (tenant_id, outlet_id, shift_id, movement_id, destination,
               sealed_bag_reference, currency_code, amount_minor,
               released_by_user_id, accepted_by_user_id)
           VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                   $5::cash.custody_destination, $6::text, $7::char(3), $8::bigint,
                   $9::uuid, $10::uuid)
           RETURNING id`,
          [tenantId, outletId, shiftId, movement.rows[0].id, b.destination,
           b.sealedBagReference, movement.rows[0].currency_code, b.amountMinor,
           userId, b.acceptedByUserId],
        );
        reply.code(201);
        return { custodyId: rows[0].id as string, movementId: movement.rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }),
  );

  app.get('/s/v1/cash/shifts/:shiftId/reconciliation', {
    schema: {
      params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId) => {
      const { shiftId } = request.params as { shiftId: string };
      const { rows } = await client.query(
        `SELECT shift_id, state,
                opening_float_minor::text AS opening_float_minor,
                sales_receipt_minor::text AS sales_receipt_minor,
                refund_minor::text AS refund_minor,
                payout_minor::text AS payout_minor,
                drop_minor::text AS drop_minor,
                float_adjustment_minor::text AS float_adjustment_minor,
                transfer_minor::text AS transfer_minor,
                expected_minor::text AS expected_minor,
                counted_minor::text AS counted_minor,
                over_short_minor::text AS over_short_minor,
                tip_allocation_minor::text AS tip_allocation_minor
           FROM cash.shift_reconciliation($1::uuid, $2::uuid)`,
        [tenantId, shiftId],
      );
      if (rows.length === 0) {
        reply.code(404);
        return { error: 'refused', reason: 'CASH_SHIFT_NOT_FOUND' };
      }
      return rows[0];
    }),
  );

  app.get('/s/v1/cash/exceptions', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId) => {
      const { rows } = await client.query(
        `SELECT kind, shift_id, detail, amount_minor::text AS amount_minor, since
           FROM cash.exception_report($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      return { exceptions: rows };
    }),
  );
}
