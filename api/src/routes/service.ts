/**
 * Service requests and notifications, on both surfaces.
 *
 * The guest half runs in a GUEST context and the staff half in a staff session, exactly
 * as M2-C and M3-B split theirs. Two properties are load-bearing:
 *
 * NOTHING HERE DECIDES WHAT A CUSTOMER MAY SEE. The status route returns whatever
 * service.customer_status() returns and drops nothing and adds nothing — the staff name
 * is present or absent because the outlet's policy said so, one layer down, and a route
 * that filtered it here would be a second opinion about a safety-adjacent rule. Same
 * arrangement as M3-B's station route, which computes no salience of its own.
 *
 * EVERY WRITE TAKES AN IDEMPOTENCY KEY, and the deliberate-repeat flag is separate from
 * it. They answer different questions: the key says "this is the same command arriving
 * twice", the flag says "this is a second ask". Conflating them is how a guest who
 * genuinely needs water twice gets told they already asked.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface ServiceDependencies {
  db: Database;
  logger: StructuredLogger;
  asGuest: <T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string, guestId: string) => Promise<T>,
  ) => Promise<T | { error: string }>;
}

function idempotencyKey(request: FastifyRequest): string | null {
  const raw = request.headers['idempotency-key'];
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed.length <= 200 ? trimmed : null;
}

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
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

export function registerServiceRoutes(app: FastifyInstance, deps: ServiceDependencies): void {
  const { asGuest } = deps;

  /**
   * Staff, with the USER resolved from the session rather than taken from the caller.
   *
   * A notification centre keyed on a user id the caller supplied would let anyone read
   * anyone's notifications with a valid token of their own — the same shape as accepting
   * an audience parameter from a note reader, which M3-A refused.
   */
  async function asStaff<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string, userId: string) => Promise<T>,
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
        if (rows.length === 0) {
          reply.code(401);
          return { error: 'authentication required' } as T & { error: string };
        }
        return work(client, context.tenantId, context.outletId ?? '',
                    rows[0].user_account_id as string);
      });
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        deps.logger.warn('service authentication refused', {
          correlationId: request.id, event: 'service.refused', errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  // -------------------------------------------------------------------------
  // The guest half
  // -------------------------------------------------------------------------

  /** FR-SRV-001. What this outlet can be asked for, in the session's language. */
  app.get('/c/v1/service/types', async (request, reply) =>
    asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
      const tableSessionId = await seatedAt(client, guestId);
      if (tableSessionId === null) {
        reply.code(409);
        return { error: 'not seated', reason: 'NO_OPEN_OCCUPANCY' };
      }
      const { rows } = await client.query(
        `SELECT rt.id, rt.code,
                coalesce(
                  (SELECT tr.translated_text FROM menu.translation tr
                    WHERE tr.tenant_id = rt.tenant_id
                      AND tr.entity = 'service_request_type'
                      AND tr.entity_id = rt.id AND tr.field_name = 'label'
                      AND tr.locale = coalesce(ts.customer_locale, 'en')
                      AND tr.state = 'approved'),
                  rt.canonical_name) AS label
           FROM service.request_type rt
           JOIN service.table_session ts ON ts.id = $1::uuid
          WHERE rt.tenant_id = $2::uuid AND rt.outlet_id = $3::uuid
            AND rt.status = 'active'
          ORDER BY rt.code`,
        [tableSessionId, tenantId, outletId],
      );
      return { tableSessionId, types: rows };
    }),
  );

  /** FR-SRV-001 and FR-SRV-006. Raise one, or collapse into the one already open. */
  app.post<{ Body: { requestTypeId?: string; note?: string; deliberate?: boolean } }>(
    '/c/v1/service/requests',
    async (request, reply) =>
      asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
        const key = idempotencyKey(request);
        if (!key) {
          reply.code(400);
          return { error: 'Idempotency-Key required' };
        }
        const body = request.body ?? {};
        if (typeof body.requestTypeId !== 'string') {
          reply.code(400);
          return { error: 'requestTypeId required' };
        }
        const tableSessionId = await seatedAt(client, guestId);
        if (tableSessionId === null) {
          reply.code(409);
          return { error: 'not seated', reason: 'NO_OPEN_OCCUPANCY' };
        }

        const before = await client.query(
          'SELECT count(*)::int AS n FROM service.service_request WHERE table_session_id = $1::uuid',
          [tableSessionId],
        );
        const { rows } = await client.query(
          `SELECT service.raise_request($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::text,
                                        $6::uuid, NULL, NULL, $7::text, $8::boolean) AS id`,
          [tenantId, outletId, tableSessionId, body.requestTypeId, key, guestId,
           typeof body.note === 'string' && body.note.trim() !== '' ? body.note : null,
           body.deliberate === true],
        );
        const after = await client.query(
          'SELECT count(*)::int AS n FROM service.service_request WHERE table_session_id = $1::uuid',
          [tableSessionId],
        );
        // Told plainly, because the customer surface has to say something different when
        // a tap collapsed than when it raised: "you have already asked" is not an error
        // and must not look like one.
        return {
          serviceRequestId: rows[0].id as string,
          collapsed: (after.rows[0].n as number) === (before.rows[0].n as number),
        };
      }),
  );

  /** FR-SRV-003, FR-SRV-009, FR-I18N-008. */
  app.get('/c/v1/service/status', async (request, reply) =>
    asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
      const tableSessionId = await seatedAt(client, guestId);
      if (tableSessionId === null) {
        reply.code(409);
        return { error: 'not seated', reason: 'NO_OPEN_OCCUPANCY' };
      }
      const { rows } = await client.query(
        `SELECT service_request_id, request_label, status_code, status_text,
                raised_at, repeat_ordinal, handled_by
           FROM service.customer_status($1::uuid, $2::uuid, $3::uuid)`,
        [tenantId, tableSessionId, guestId],
      );
      return { tableSessionId, requests: rows };
    }),
  );

  /** FR-NOT-012's customer half and FR-I18N-001B. */
  app.get('/c/v1/service/timeline', async (request, reply) =>
    asGuest(request, reply, async (client, tenantId, outletId, guestId) => {
      const tableSessionId = await seatedAt(client, guestId);
      if (tableSessionId === null) {
        reply.code(409);
        return { error: 'not seated', reason: 'NO_OPEN_OCCUPANCY' };
      }
      const { rows } = await client.query(
        `SELECT occurred_at, source, summary, locale::text AS locale
           FROM notify.customer_timeline($1::uuid, $2::uuid, $3::uuid)`,
        [tenantId, tableSessionId, guestId],
      );
      return { tableSessionId, entries: rows };
    }),
  );

  // -------------------------------------------------------------------------
  // The staff half — DATA ONLY. The screen is M3-D's.
  // -------------------------------------------------------------------------

  /** FR-NOT-012's staff half, in English (FR-I18N-007). */
  app.get('/s/v1/notifications', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { rows } = await client.query(
        `SELECT notice_id, event_id, event_class::text AS event_class, severity,
                subject_kind::text AS subject_kind, subject_id, body, state::text AS state,
                emitted_at, sent_at, read_at
           FROM notify.staff_notification_center($1::uuid, $2::uuid, $3::uuid)`,
        [tenantId, outletId, userId],
      );
      return { notifications: rows };
    }),
  );

  /** FR-SRV-002/003. The requests this person is accountable for. */
  app.get('/s/v1/service/queue', async (request, reply) =>
    asStaff(request, reply, async (client, tenantId, outletId, userId) => {
      const { rows } = await client.query(
        `SELECT sr.id, rt.code AS request_type_code, rt.canonical_name,
                sr.state::text AS state, sr.raised_at, sr.sla_due_at,
                sr.repeat_ordinal, sr.note,
                (now() > sr.sla_due_at) AS overdue
           FROM service.service_request sr
           JOIN service.request_type rt ON rt.id = sr.request_type_id
          WHERE sr.tenant_id = $1::uuid AND sr.outlet_id = $2::uuid
            AND sr.assigned_user_id = $3::uuid
            AND sr.state NOT IN ('completed', 'cancelled', 'expired', 'unresolved')
          ORDER BY sr.sla_due_at`,
        [tenantId, outletId, userId],
      );
      return { requests: rows };
    }),
  );
}
