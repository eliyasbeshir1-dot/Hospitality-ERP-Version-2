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
import { ContextRefused, signatureOf, type Database } from '../db';
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

  /**
   * The acting user, read from the session rather than accepted from the caller.
   *
   * Every writer below records WHO did the thing, and a body-supplied user id would let a
   * station attribute its own action to somebody else — which is the attribution defect
   * M3-B's priority control already refuses at the database. app.current_session_id() is
   * transaction-local and was set by establish_session_context, so this cannot be spoofed
   * by a request.
   */
  async function actingUser(client: PoolClient): Promise<string | null> {
    const { rows } = await client.query(
      `SELECT user_account_id FROM identity.session WHERE id = app.current_session_id()`,
    );
    return rows[0]?.user_account_id ?? null;
  }

  /**
   * Map a database refusal onto a status code, by the signature it named.
   *
   * The list is of SIGNATURES, not of rules. Nothing here decides whether a transition is
   * legal, whether an allergy was acknowledged or whether a set is complete — the database
   * decided all of that and said so, and this turns its word into an HTTP code. That
   * distinction is the whole of FR-ARCH's single-implementation claim: a second copy of a
   * rule in this file would be the divergence M3-D's structural check exists to catch.
   */
  function statusFor(signature: string | null): number {
    switch (signature) {
      case 'TICKET_NOT_FOUND':
      case 'ORDER_NOT_FOUND':
        return 404;
      case 'ILLEGAL_TICKET_TRANSITION':
      case 'TICKET_ALREADY_IN_STATE':
        return 409;
      case 'ALLERGY_NOT_ACKNOWLEDGED':
      case 'SERVICE_BLOCKED':
      case 'INCOMPLETE_SET_SERVED':
        return 412;
      default:
        return 422;
    }
  }

  /** One writer call, with the refusal reported as the database named it. */
  async function write<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    event: string,
    work: (client: PoolClient, tenantId: string, userId: string | null) => Promise<T>,
  ): Promise<T | { error: string; signature?: string }> {
    try {
      return (await asStaff(request, reply, async (client, tenantId) =>
        work(client, tenantId, await actingUser(client)),
      )) as T;
    } catch (error) {
      if (error instanceof ContextRefused) throw error;
      const signature = signatureOf(error);
      reply.code(statusFor(signature));
      deps.logger.warn('station write refused', {
        correlationId: request.id, event, errorClass: signature ?? 'UNMAPPED',
      });
      return { error: 'refused', signature: signature ?? undefined };
    }
  }

  /**
   * FR-FUL-003, FR-FUL-004, FR-FUL-005. Every state move a station makes, through one door.
   *
   * ONE ROUTE FOR ELEVEN STATES, AND THAT IS THE POINT. The obvious shape is a route per
   * verb — /acknowledge, /fire, /ready — and each one would carry a target state, which is
   * a small piece of the machine restated in TypeScript. This carries none: the caller
   * names the state it wants, fulfillment.transition_ticket() decides whether the move is
   * legal, and the projection trigger refuses it if it is not. There is no transition
   * table in this file to drift from the one in the database, and all 110 ordered pairs
   * stay proved where M3-B proved them.
   *
   * The allergy gate is the same story: transition_ticket refuses 'preparing' on a ticket
   * carrying an unacknowledged declaration where the station requires it. This route does
   * not check that, because checking it here is how the two copies start disagreeing.
   */
  app.post<{ Params: { ticketId: string }; Body: { toState?: string } }>(
    '/s/v1/tickets/:ticketId/transitions',
    async (request, reply) => {
      const toState = request.body?.toState;
      if (!toState) {
        reply.code(400);
        return { error: 'toState is required' };
      }
      return write(request, reply, 'station.transition', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.transition_ticket($1::uuid, $2::uuid,
                    $3::fulfillment.ticket_state, $4::uuid)`,
          [tenantId, request.params.ticketId, toState, userId],
        );
        const { rows } = await client.query(
          `SELECT state::text AS state FROM fulfillment.ticket
            WHERE tenant_id = $1::uuid AND id = $2::uuid`,
          [tenantId, request.params.ticketId],
        );
        return { ticketId: request.params.ticketId, state: rows[0]?.state ?? null };
      });
    },
  );

  /** FR-FUL-008. A station acknowledges the allergy declaration before it may prepare. */
  app.post<{ Params: { ticketId: string } }>(
    '/s/v1/tickets/:ticketId/allergy-acknowledgement',
    async (request, reply) =>
      write(request, reply, 'station.allergy_ack', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.acknowledge_allergy($1::uuid, $2::uuid, $3::uuid)`,
          [tenantId, request.params.ticketId, userId],
        );
        return { ticketId: request.params.ticketId, acknowledged: true };
      }),
  );

  /** FR-FUL-004. Progress by units, for a line a station finishes a few at a time. */
  app.post<{ Params: { ticketId: string }; Body: { ticketLineId?: string; readyQuantity?: number } }>(
    '/s/v1/tickets/:ticketId/unit-progress',
    async (request, reply) => {
      const { ticketLineId, readyQuantity } = request.body ?? {};
      if (!ticketLineId || typeof readyQuantity !== 'number') {
        reply.code(400);
        return { error: 'ticketLineId and readyQuantity are required' };
      }
      return write(request, reply, 'station.unit_progress', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.record_unit_progress($1::uuid, $2::uuid, $3::integer, $4::uuid)`,
          [tenantId, ticketLineId, readyQuantity, userId],
        );
        return { ticketLineId, readyQuantity };
      });
    },
  );

  /** FR-FUL-007. Priority, with the reason and the person who set it. */
  app.post<{ Params: { ticketId: string }; Body: { priority?: string; reasonCodeId?: string } }>(
    '/s/v1/tickets/:ticketId/priority',
    async (request, reply) => {
      const { priority, reasonCodeId } = request.body ?? {};
      if (!priority) {
        reply.code(400);
        return { error: 'priority is required' };
      }
      return write(request, reply, 'station.priority', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.set_priority($1::uuid, $2::uuid,
                    $3::fulfillment.priority_level, $4::uuid, $5::uuid)`,
          [tenantId, request.params.ticketId, priority, reasonCodeId ?? null, userId],
        );
        return { ticketId: request.params.ticketId, priority };
      });
    },
  );

  /** FR-FUL-005. A recall moves a ticket back; it never makes a second one. */
  app.post<{ Params: { ticketId: string }; Body: { reasonCodeId?: string } }>(
    '/s/v1/tickets/:ticketId/recall',
    async (request, reply) => {
      const reasonCodeId = request.body?.reasonCodeId;
      if (!reasonCodeId) {
        reply.code(400);
        return { error: 'reasonCodeId is required' };
      }
      return write(request, reply, 'station.recall', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.recall_ticket($1::uuid, $2::uuid, $3::uuid, $4::uuid)`,
          [tenantId, request.params.ticketId, reasonCodeId, userId],
        );
        return { ticketId: request.params.ticketId, recalled: true };
      });
    },
  );

  /** FR-FUL-011. A ticket moves to another station, with a reason. */
  app.post<{ Params: { ticketId: string }; Body: { toStationNodeId?: string; reasonCodeId?: string } }>(
    '/s/v1/tickets/:ticketId/transfer',
    async (request, reply) => {
      const { toStationNodeId, reasonCodeId } = request.body ?? {};
      if (!toStationNodeId || !reasonCodeId) {
        reply.code(400);
        return { error: 'toStationNodeId and reasonCodeId are required' };
      }
      return write(request, reply, 'station.transfer', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.transfer_ticket($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid)`,
          [tenantId, request.params.ticketId, toStationNodeId, reasonCodeId, userId],
        );
        return { ticketId: request.params.ticketId, stationNodeId: toStationNodeId };
      });
    },
  );

  /** FR-FUL-006. Waste, by kind and units, with the reason it was thrown away. */
  app.post<{
    Params: { ticketId: string };
    Body: { kind?: string; units?: number; reasonCodeId?: string; note?: string };
  }>(
    '/s/v1/tickets/:ticketId/waste',
    async (request, reply) => {
      const { kind, units, reasonCodeId, note } = request.body ?? {};
      if (!kind || typeof units !== 'number' || !reasonCodeId) {
        reply.code(400);
        return { error: 'kind, units and reasonCodeId are required' };
      }
      return write(request, reply, 'station.waste', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.record_waste($1::uuid, $2::uuid, $3::fulfillment.waste_kind,
                    $4::integer, $5::uuid, $6::uuid, $7::text)`,
          [tenantId, request.params.ticketId, kind, units, reasonCodeId, userId, note ?? null],
        );
        return { ticketId: request.params.ticketId, kind, units };
      });
    },
  );

  /**
   * FR-FUL-010. Serve confirmation: who collected it, who served it, and what went wrong.
   *
   * The exception is the load-bearing half. A serve with a missing or wrong item is still
   * a serve that happened, and recording it as an ordinary one would lose the only record
   * that the guest did not get what they ordered.
   */
  app.post<{
    Params: { ticketId: string };
    Body: { collectedBy?: string; servedBy?: string; exception?: string; exceptionNote?: string };
  }>(
    '/s/v1/tickets/:ticketId/serve',
    async (request, reply) => {
      const { collectedBy, servedBy, exception, exceptionNote } = request.body ?? {};
      return write(request, reply, 'station.serve', async (client, tenantId, userId) => {
        await client.query(
          `SELECT fulfillment.record_serve($1::uuid, $2::uuid, $3::uuid, $4::uuid,
                    $5::fulfillment.serve_exception, $6::text)`,
          [tenantId, request.params.ticketId, collectedBy ?? userId, servedBy ?? userId,
           exception ?? null, exceptionNote ?? null],
        );
        return { ticketId: request.params.ticketId, served: true, exception: exception ?? null };
      });
    },
  );

  /**
   * FR-FUL-009. Expo releases the order to service — and refuses an incomplete set.
   *
   * The refusal is not written here. fulfillment.release_to_service() holds it, and this
   * route reports what it said. An expo screen that decided for itself whether a set was
   * complete would be a second implementation of the rule that matters most on this
   * surface: a guest given half a table's food while the rest is still cooking.
   */
  app.post<{ Params: { orderId: string }; Body: { collectedBy?: string } }>(
    '/s/v1/orders/:orderId/release-to-service',
    async (request, reply) =>
      write(request, reply, 'station.release_to_service', async (client, tenantId, userId) => {
        const { rows } = await client.query(
          `SELECT fulfillment.release_to_service($1::uuid, $2::uuid, $3::uuid) AS released`,
          [tenantId, request.params.orderId, request.body?.collectedBy ?? userId],
        );
        return { orderId: request.params.orderId, released: rows[0]?.released ?? 0 };
      }),
  );

  /**
   * FR-ORD-004. Staff accept a submitted order, which is what admits it to the kitchen.
   *
   * THE STEP WITHOUT WHICH NO GUEST ORDER EVER REACHES A STATION. The ordering policy this
   * build seeds says guest_qr orders are 'staff_confirmed', so a placed order sits in
   * 'submitted' until somebody accepts it — and ordering.accept_order() existed with no
   * caller anywhere in api/src. Releasing is a trigger on acceptance
   * (ordering.release_accepted_order), so the tickets this gate is about are created by
   * the act this route performs. Found by placing an order and watching it stop.
   *
   * Nothing is decided here: the function checks the policy, the state and the actor.
   */
  app.post<{ Params: { orderId: string } }>(
    '/s/v1/orders/:orderId/accept',
    async (request, reply) =>
      write(request, reply, 'station.accept_order', async (client, tenantId, userId) => {
        await client.query(
          `SELECT ordering.accept_order($1::uuid, $2::uuid, $3::uuid)`,
          [tenantId, request.params.orderId, userId],
        );
        const { rows } = await client.query(
          `SELECT state::text AS state FROM ordering.customer_order
            WHERE tenant_id = $1::uuid AND id = $2::uuid`,
          [tenantId, request.params.orderId],
        );
        return { orderId: request.params.orderId, state: rows[0]?.state ?? null };
      }),
  );

  /** FR-FUL-003. Release an accepted order to the stations that will cook it. */
  app.post<{ Params: { orderId: string } }>(
    '/s/v1/orders/:orderId/release',
    async (request, reply) =>
      write(request, reply, 'station.release_order', async (client, tenantId, userId) => {
        const { rows } = await client.query(
          `SELECT fulfillment.release_order($1::uuid, $2::uuid, $3::uuid) AS tickets`,
          [tenantId, request.params.orderId, userId],
        );
        return { orderId: request.params.orderId, tickets: rows[0]?.tickets ?? 0 };
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
