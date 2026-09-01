/**
 * The station surface's API: the queue a kitchen reads, one ticket, and expo.
 *
 * Deliberately small. FR-FUL-003, FR-FUL-008 and FR-SAF-004 are claims about what a
 * STATION SEES, and a claim about a screen can only be proved by rendering one — M2-C
 * found a defect no SQL suite could see, and this is the same class of claim with higher
 * stakes. So there is a surface, and it exists to make the safety claim falsifiable.
 * The full staff experience is M3-D and this must not pre-shape it: there is no floor
 * plan, no shift view, no navigation and no setting.
 *
 * Two properties are load-bearing.
 *
 * The allergy emphasis is not decided here. It comes from
 * fulfillment.ticket_allergy_emphasis(), which returns the kitchen code, the written
 * warning and a rank in one row — so a screen cannot invent a salience of its own, and
 * cannot receive a rank with no words to render beside it.
 *
 * These are staff routes. They authenticate a staff session through the same
 * db.withSession() M1-D built, so a guest credential reaches none of them: a guest
 * context carries no app.session_id, and every read below is scoped by it.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface StationDependencies {
  db: Database;
  logger: StructuredLogger;
}

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

export function registerStationRoutes(app: FastifyInstance, deps: StationDependencies): void {
  async function asStaff<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, tenantId: string, outletId: string) => Promise<T>,
  ): Promise<T | { error: string }> {
    const token = staffToken(request);
    if (!token) {
      reply.code(401);
      return { error: 'authentication required' };
    }
    try {
      return await deps.db.withSession(token, async (client, context) =>
        work(client, context.tenantId, context.outletId ?? ''),
      );
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        deps.logger.warn('station authentication refused', {
          correlationId: request.id, event: 'station.refused', errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  /** FR-FUL-003. The queue, in the seven display buckets over the eleven states. */
  app.get<{ Params: { stationId: string } }>(
    '/s/v1/stations/:stationId/queue',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        const { rows } = await client.query(
          `SELECT ticket_id, order_number, bucket, state::text AS state,
                  priority::text AS priority, priority_reason, priority_by,
                  elapsed_seconds, sla_due_at, sla_breached, units, ready_units,
                  allergy_count, allergy_acknowledged
             FROM fulfillment.kds_queue($1::uuid, $2::uuid)`,
          [tenantId, request.params.stationId],
        );
        return { tickets: rows };
      }),
  );

  /** One ticket, with everything a station must be shown before it starts. */
  app.get<{ Params: { ticketId: string } }>(
    '/s/v1/tickets/:ticketId',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        const ticket = await client.query(
          `SELECT t.id, t.state::text AS state, t.priority::text AS priority,
                  t.station_node_id, t.released_at, t.sla_due_at,
                  t.allergy_acknowledged_at IS NOT NULL AS allergy_acknowledged,
                  o.order_number
             FROM fulfillment.ticket t
             JOIN ordering.customer_order o
               ON o.id = t.order_id AND o.tenant_id = t.tenant_id
            WHERE t.tenant_id = $1::uuid AND t.id = $2::uuid`,
          [tenantId, request.params.ticketId],
        );
        if (ticket.rowCount === 0) {
          reply.code(404);
          return { error: 'not found' };
        }
        const lines = await client.query(
          `SELECT id, quantity, ready_quantity, item_code, canonical_name
             FROM fulfillment.ticket_line
            WHERE tenant_id = $1::uuid AND ticket_id = $2::uuid
            ORDER BY canonical_name`,
          [tenantId, request.params.ticketId],
        );
        // The emphasis comes from the database, whole. This route does not compute
        // salience, does not rank, and cannot drop the words and keep the glyph: they
        // arrive in one row or not at all.
        const allergies = await client.query(
          `SELECT kitchen_code, written_warning, acknowledgement_text,
                  emphasis_rank, emphasis_glyph
             FROM fulfillment.ticket_allergy_emphasis($1::uuid, $2::uuid)`,
          [tenantId, request.params.ticketId],
        );
        const notes = await client.query(
          `SELECT kind::text AS kind, body
             FROM fulfillment.ticket_kitchen_notes($1::uuid, $2::uuid)
            WHERE kind = 'kitchen_instruction'`,
          [tenantId, request.params.ticketId],
        );
        return {
          ticket: ticket.rows[0],
          lines: lines.rows,
          allergies: allergies.rows,
          notes: notes.rows,
        };
      }),
  );

  /** FR-FUL-009. Expo: station readiness reassembled, and why service is blocked. */
  app.get<{ Params: { orderId: string } }>(
    '/s/v1/orders/:orderId/expo',
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        const view = await client.query(
          `SELECT ticket_id, station_node_id, station_kind::text AS station_kind,
                  state::text AS state, priority::text AS priority, units, ready_units,
                  sla_due_at, allergy_declarations, allergy_acknowledged
             FROM fulfillment.expo_view($1::uuid, $2::uuid)`,
          [tenantId, request.params.orderId],
        );
        const blocks = await client.query(
          `SELECT reason, ticket_id, detail
             FROM fulfillment.service_block_reasons($1::uuid, $2::uuid)`,
          [tenantId, request.params.orderId],
        );
        const state = await client.query(
          `SELECT fulfillment.order_fulfillment_state($1::uuid, $2::uuid) AS state`,
          [tenantId, request.params.orderId],
        );
        return {
          tickets: view.rows,
          blocking: blocks.rows,
          fulfillmentState: state.rows[0]?.state ?? null,
        };
      }),
  );
}
