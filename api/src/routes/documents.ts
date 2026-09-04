/**
 * Receipts, the printer that prints them, and the preview that comes before both.
 *
 * NOTHING HERE COMPOSES A DOCUMENT. docs.compose_document() is the only function in this
 * build that turns lines into a print document, and both the receipt path and the preview
 * path call it — which is what makes FR-UX-018's "the physical output matches the
 * preview" a property rather than a claim about two implementations that agree today.
 * A route that laid out its own lines would be the second implementation, and it would be
 * the one an operator actually meets.
 *
 * NOTHING HERE DECIDES WHETHER A RECEIPT IS FAITHFUL EITHER. Every figure
 * docs.issue_receipt() writes is checked against its own source by 0027's deferred
 * triggers: a bill total carrying the tip raises TIP_MERGED_ON_RECEIPT, a non-English
 * receipt carrying English source text raises RECEIPT_INCOMPLETE_IN_LOCALE, and a second
 * original print raises RECEIPT_ALREADY_PRINTED. This file maps those signatures onto
 * status codes and does not repeat one of the checks.
 *
 * THE LOCALE IS NOT A PARAMETER ANYWHERE IN THIS FILE. M4-A ruled that a bill translates
 * by its own locale rather than the reader's, and a receipt inherits that. There is no
 * query string, header or body field by which a manager reprinting a customer's receipt
 * could change what language it is in — docs.issue_receipt() takes no locale at all.
 *
 * THE BYTES ARE THE AGENT'S. This service records that a print happened and what its
 * digest was; print/agent.py is what writes to a device, because a web service holding a
 * character device open is the shape M5a's outlet node exists to replace. What is proved
 * at M4 is the path from composition to encoded bytes, and the record of where they went.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface DocumentDependencies {
  db: Database;
  logger: StructuredLogger;
}

const UUID = { type: 'string', format: 'uuid' } as const;
const DIGEST = { type: 'string', pattern: '^[0-9a-f]{64}$' } as const;

/**
 * WHICH LOCALES EXIST IS NOT STATED HERE. menu.customer_locale is an enum in the
 * database and a list in this file would be a second copy of it — M1-D's rule and, more
 * to the point, the drift this repository refuses everywhere else. An unknown locale
 * fails the cast and comes back as a named refusal.
 */
const LOCALE = { type: 'string', minLength: 2, maxLength: 8 } as const;

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

function refusal(error: unknown): string | null {
  const message = error instanceof Error ? error.message : '';
  const matched = /\b([A-Z][A-Z_]{4,})\b/.exec(message);
  return matched && matched[1] ? matched[1] : null;
}

const STATUS: Record<string, number> = {
  BILL_NOT_FOUND: 404,
  BILL_NOT_SETTLED: 409,
  PAYMENT_METHOD_ABSENT: 422,
  RECEIPT_NOT_FOUND: 404,
  RECEIPT_ALREADY_PRINTED: 409,
  RECEIPT_INCOMPLETE_IN_LOCALE: 422,
  RECEIPT_FIGURE_UNFAITHFUL: 409,
  TIP_MERGED_ON_RECEIPT: 409,
  PRINTER_NEVER_TESTED: 409,
  PRINTER_IDENTITY_IMMUTABLE: 409,
  SINK_MISMATCH: 422,
  DOCUMENT_HAS_NO_LINES: 422,
  SPECIMEN_CARRIES_A_RECEIPT_NUMBER: 422,
  RECEIPT_NUMBER_ABSENT: 422,
  DOCUMENT_NUMBER_SERIES_ABSENT: 412,
  SESSION_NOT_LIVE: 401,
};

export function registerDocumentRoutes(
    app: FastifyInstance, deps: DocumentDependencies): void {
  async function asStaff<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string,
           userId: string) => Promise<T>,
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
                    rows[0].user_account_id as string);
      });
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  /** The reason the database gave, with the status it maps to. */
  function answer(reply: FastifyReply, error: unknown):
      { error: string; reason: string; sqlstate?: string } {
    const reason = refusal(error);
    if (reason && STATUS[reason] !== undefined) {
      reply.code(STATUS[reason] as number);
      return { error: 'refused', reason };
    }
    reply.code(500);
    const sqlstate = (error as { code?: string })?.code ?? 'unknown';
    deps.logger.error('unmapped database refusal', {
      event: 'document.unmapped', errorClass: reason ?? 'UNKNOWN', sqlstate,
    });
    return { error: 'refused', reason: reason ?? 'UNMAPPED_REFUSAL', sqlstate };
  }

  // -------------------------------------------------------------------------
  // The printer, registered and tested (FR-CFG-001D)
  // -------------------------------------------------------------------------

  app.post<{
    Body: {
      displayName: string; connection: string;
      devicePath?: string; hostAndPort?: string;
    };
  }>('/s/v1/printers', {
    schema: {
      body: {
        type: 'object', required: ['displayName', 'connection'],
        additionalProperties: false,
        properties: {
          displayName: { type: 'string', minLength: 1, maxLength: 120 },
          // SHAPE, NOT MEMBERSHIP: docs.connection_kind is the list, and an unknown value
          // fails the cast rather than a schema written twice.
          connection: { type: 'string', minLength: 1, maxLength: 40 },
          devicePath: { type: 'string', minLength: 1, maxLength: 400 },
          hostAndPort: { type: 'string', minLength: 1, maxLength: 200 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      try {
        const { rows } = await client.query(
          `SELECT docs.register_printer($1::uuid, $2::uuid, $3, $4::docs.connection_kind,
                                        $5, $6, $7::uuid) AS id`,
          [tenantId, outletId, request.body.displayName, request.body.connection,
           request.body.devicePath ?? null, request.body.hostAndPort ?? null, userId]);
        return { printerId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }));

  /**
   * FR-CFG-001D's other half, and the half a setup screen usually skips. The OUTCOME is
   * docs.print_outcome, which a preview printer cannot produce a value of — 0027's
   * printer_test_needs_a_device trigger refuses the row — so a file that received bytes
   * cannot be recorded as a printer that works.
   */
  app.post<{
    Params: { printerId: string };
    Body: { outcome: string; bytesSha256: string; byteCount: number; detail?: string };
  }>('/s/v1/printers/:printerId/test', {
    schema: {
      params: { type: 'object', required: ['printerId'],
                properties: { printerId: UUID } },
      body: {
        type: 'object', required: ['outcome', 'bytesSha256', 'byteCount'],
        additionalProperties: false,
        properties: {
          outcome: { type: 'string', minLength: 1, maxLength: 20 },
          bytesSha256: DIGEST,
          byteCount: { type: 'integer', minimum: 1 },
          detail: { type: 'string', maxLength: 2000 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      try {
        const { rows } = await client.query(
          `SELECT docs.record_printer_test($1::uuid, $2::uuid, $3::uuid,
                    $4::docs.print_outcome, $5::char(64), $6::integer, $7, $8::uuid) AS id`,
          [tenantId, outletId, request.params.printerId, request.body.outcome,
           request.body.bytesSha256, request.body.byteCount,
           request.body.detail ?? null, userId]);
        return { printerTestId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }));

  app.get('/s/v1/printers', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId) => {
      const { rows } = await client.query(
        `SELECT p.id, p.display_name, p.connection, p.sink, p.command_set, p.status,
                docs.printer_has_passed_a_test($1::uuid, p.id) AS tested
           FROM docs.printer p WHERE p.status = 'active' ORDER BY p.display_name`,
        [tenantId]);
      return { printers: rows };
    }));

  // -------------------------------------------------------------------------
  // The preview, before publication (FR-UX-018)
  // -------------------------------------------------------------------------

  /**
   * A SPECIMEN, AND IT SAYS SO ON ITS FACE. docs.compose_document() refuses to give a
   * preview a receipt number and puts the specimen marking in the document itself, so a
   * renderer that ignored a flag would produce a document with a line missing rather than
   * one indistinguishable from a receipt.
   */
  app.get<{ Querystring: { locale?: string; currency?: string } }>(
    '/s/v1/documents/preview', {
      schema: {
        querystring: {
          type: 'object',
          properties: { locale: LOCALE, currency: { type: 'string', minLength: 3, maxLength: 3 } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT docs.preview_document($1::uuid, $2::uuid,
                      $3::menu.customer_locale, $4::char(3)) AS document`,
            [tenantId, outletId, request.query.locale ?? 'en',
             request.query.currency ?? 'ETB']);
          return { document: rows[0].document };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  // -------------------------------------------------------------------------
  // The receipt (FR-BIL-010, FR-BIL-016, FR-BIL-017, FR-I18N-001C)
  // -------------------------------------------------------------------------

  app.post<{ Body: { billId: string; paymentMethod: string } }>(
    '/s/v1/receipts', {
      schema: {
        body: {
          type: 'object', required: ['billId', 'paymentMethod'],
          additionalProperties: false,
          properties: {
            billId: UUID,
            // FR-BIL-017: the method ACTUALLY used. Free text of bounded length rather
            // than an enum, because the method is what the cashier and the customer both
            // saw happen — "cash", "Telebirr", "card terminal" — and constraining it to a
            // list here would be a third copy of a vocabulary that lives in
            // payments.provider and on a merchant slip.
            paymentMethod: { type: 'string', minLength: 1, maxLength: 80 },
          },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT docs.issue_receipt($1::uuid, $2::uuid, $3::uuid, $4, $5::uuid) AS id`,
            [tenantId, outletId, request.body.billId, request.body.paymentMethod, userId]);
          return { receiptId: rows[0].id as string };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  app.get<{ Params: { receiptId: string } }>(
    '/s/v1/receipts/:receiptId', {
      schema: {
        params: { type: 'object', required: ['receiptId'],
                  properties: { receiptId: UUID } },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        try {
          const { rows } = await client.query(
            `SELECT r.receipt_number, r.revision, r.locale, r.currency_code,
                    r.bill_total_minor, r.tip_total_minor, r.paid_total_minor,
                    r.payment_method, r.generated_at,
                    (SELECT jsonb_agg(jsonb_build_object(
                              'kind', l.kind, 'label', l.label,
                              'amountMinor', l.amount_minor,
                              'currencyCode', l.currency_code)
                            ORDER BY l.display_order)
                       FROM docs.receipt_line l
                      WHERE l.tenant_id = r.tenant_id AND l.receipt_id = r.id) AS lines,
                    docs.receipt_document($1::uuid, r.id) AS document
               FROM docs.receipt r WHERE r.tenant_id = $1::uuid AND r.id = $2::uuid`,
            [tenantId, request.params.receiptId]);
          if (rows.length === 0) {
            reply.code(404);
            return { error: 'refused', reason: 'RECEIPT_NOT_FOUND' };
          }
          return { receipt: rows[0] };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  /**
   * FR-BIL-011. A REPRINT and a REISSUE are different things and this route is the first.
   * A reprint is a second copy of a document the customer already has, so it is marked,
   * carries an operator and a reason, and is refused without both. A reissue is a new
   * revision with its own number, and it goes through POST /s/v1/receipts/:id/revisions.
   */
  app.post<{
    Params: { receiptId: string };
    Body: {
      printerId: string; outcome: string; bytesSha256: string; byteCount: number;
      isReprint?: boolean; reasonCodeId?: string; reasonText?: string; detail?: string;
    };
  }>('/s/v1/receipts/:receiptId/prints', {
    schema: {
      params: { type: 'object', required: ['receiptId'],
                properties: { receiptId: UUID } },
      body: {
        type: 'object', required: ['printerId', 'outcome', 'bytesSha256', 'byteCount'],
        additionalProperties: false,
        properties: {
          printerId: UUID,
          outcome: { type: 'string', minLength: 1, maxLength: 20 },
          bytesSha256: DIGEST,
          byteCount: { type: 'integer', minimum: 1 },
          isReprint: { type: 'boolean' },
          reasonCodeId: UUID,
          reasonText: { type: 'string', maxLength: 2000 },
          detail: { type: 'string', maxLength: 2000 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      try {
        const { rows } = await client.query(
          `SELECT docs.record_receipt_print($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                    $5::docs.print_outcome, $6::char(64), $7::integer, $8::uuid,
                    $9::boolean, $10::uuid, $11, $12) AS id`,
          [tenantId, outletId, request.params.receiptId, request.body.printerId,
           request.body.outcome, request.body.bytesSha256, request.body.byteCount,
           userId, request.body.isReprint ?? false, request.body.reasonCodeId ?? null,
           request.body.reasonText ?? null, request.body.detail ?? null]);
        return { printAttemptId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }));

  /** FR-UX-018. A preview render of a real receipt, to a file sink. */
  app.post<{
    Params: { receiptId: string };
    Body: { printerId: string; outcome: string; bytesSha256: string; byteCount: number };
  }>('/s/v1/receipts/:receiptId/renders', {
    schema: {
      params: { type: 'object', required: ['receiptId'],
                properties: { receiptId: UUID } },
      body: {
        type: 'object', required: ['printerId', 'outcome', 'bytesSha256', 'byteCount'],
        additionalProperties: false,
        properties: {
          printerId: UUID,
          outcome: { type: 'string', minLength: 1, maxLength: 20 },
          bytesSha256: DIGEST,
          byteCount: { type: 'integer', minimum: 1 },
        },
      },
    },
  }, async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      try {
        const { rows } = await client.query(
          `SELECT docs.record_receipt_render($1::uuid, $2::uuid,
                    'receipt'::docs.document_kind, $3::uuid, $4::uuid,
                    $5::docs.render_outcome, $6::char(64), $7::integer, $8::uuid) AS id`,
          [tenantId, outletId, request.params.receiptId, request.body.printerId,
           request.body.outcome, request.body.bytesSha256, request.body.byteCount,
           userId]);
        return { renderAttemptId: rows[0].id as string };
      } catch (error) {
        return answer(reply, error);
      }
    }));

  app.post<{ Params: { receiptId: string } }>(
    '/s/v1/receipts/:receiptId/revisions', {
      schema: {
        params: { type: 'object', required: ['receiptId'],
                  properties: { receiptId: UUID } },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT docs.reissue_receipt($1::uuid, $2::uuid, $3::uuid, $4::uuid) AS id`,
            [tenantId, outletId, request.params.receiptId, userId]);
          return { receiptId: rows[0].id as string };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  // -------------------------------------------------------------------------
  // The fiscal port (FR-BIL-012)
  // -------------------------------------------------------------------------

  /**
   * RECONCILIATION COUNTS BY STATE AND NEVER TOTALS. The question a reconciliation
   * answers is which documents are stuck; a single number hides the requested ones that
   * never went anywhere.
   */
  app.get<{ Querystring: { from?: string; to?: string } }>(
    '/s/v1/fiscal/reconciliation', {
      schema: {
        querystring: {
          type: 'object',
          properties: { from: { type: 'string' }, to: { type: 'string' } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        try {
          const { rows } = await client.query(
            `SELECT * FROM fiscal.reconciliation($1::uuid, $2::uuid,
                       coalesce($3::timestamptz, now() - interval '1 day'),
                       coalesce($4::timestamptz, now()))`,
            [tenantId, outletId, request.query.from ?? null, request.query.to ?? null]);
          return { reconciliation: rows };
        } catch (error) {
          return answer(reply, error);
        }
      }));
}
