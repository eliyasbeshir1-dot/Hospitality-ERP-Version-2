/**
 * The outlet continuity node's own API.
 *
 * These routes exist only when the process runs under a node profile. They are what makes
 * M5a's tables reachable by a person rather than by a test — the distinction
 * tools/uncalled_routes.py was split in two to keep honest, and the reason four gates in a
 * row shipped behaviour nobody could get to.
 *
 * ONE ROUTE HERE IS DELIBERATELY UNAUTHENTICATED, and it is worth saying why before
 * somebody finds it and assumes it was an oversight. FR-EDG-009 requires the connectivity
 * state to be shown to CUSTOMERS as well as staff, and a guest holding a phone at a table
 * has no staff session. GET /n/v1/connectivity therefore answers without a token — and it
 * can, safely, because a node serves exactly one outlet and the only thing the route
 * discloses is whether that outlet can currently reach the cloud. That is a fact anybody
 * standing in the room can already observe: the wifi works or it does not. Everything
 * else — readiness, conflicts, the queue, the estate — needs a staff session, because
 * those describe the business rather than the weather.
 *
 * NOTHING HERE DECIDES ANYTHING. Every route is a call to a function 0039–0045 built, for
 * the reason staff.ts records about ordering: a rule implemented twice is a rule that will
 * disagree with itself, and the second implementation is always the one nobody tests.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, signatureOf, type Database } from '../db';
import type { StructuredLogger } from '../logging';
import type { NodeProfile } from '../node/identity';

export interface NodeDependencies {
  db: Database;
  logger: StructuredLogger;
  profile: NodeProfile;
}

const LOCALES = new Set(['en', 'am', 'ar']);

function locale(request: FastifyRequest): string {
  const raw = (request.query as { locale?: string } | undefined)?.locale;
  return typeof raw === 'string' && LOCALES.has(raw) ? raw : 'en';
}

function staffToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

export function registerNodeRoutes(app: FastifyInstance, deps: NodeDependencies): void {
  const { tenantId, outletId, nodeId } = {
    tenantId: deps.profile.tenantId,
    outletId: deps.profile.outletId,
    nodeId: deps.profile.nodeId,
  };

  async function asStaff<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: PoolClient, userId: string) => Promise<T>,
  ): Promise<T | { error: string }> {
    const token = staffToken(request);
    if (!token) {
      reply.code(401);
      return { error: 'authentication required' };
    }
    try {
      return await deps.db.withSession(token, async (client, context) => {
        // THE NODE SERVES ONE OUTLET, AND THE SESSION MUST BE FOR THAT OUTLET. Row level
        // security would already deny the rows, but denying them looks like "there is
        // nothing here" rather than "you are at the wrong outlet", and a manager reading
        // an empty conflict list would draw the wrong conclusion.
        if (context.tenantId !== tenantId || context.outletId !== outletId) {
          reply.code(403);
          return { error: 'this node serves a different outlet' } as T & { error: string };
        }
        const { rows } = await client.query(
          'SELECT user_account_id FROM identity.session WHERE id = $1::uuid',
          [context.sessionId],
        );
        if (rows.length === 0 || !rows[0].user_account_id) {
          reply.code(401);
          return { error: 'authentication required' } as T & { error: string };
        }
        return work(client, rows[0].user_account_id as string);
      });
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        deps.logger.warn('node authentication refused', {
          correlationId: request.id, event: 'node.refused', errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  // -------------------------------------------------------------------------
  // FR-EDG-009 — what everybody in the room can see
  // -------------------------------------------------------------------------

  app.get('/n/v1/connectivity', async (request) => {
    const wanted = locale(request);
    return deps.db.withoutContext(async (client) => {
      // Read under the node's own context rather than a caller's: this is the node
      // describing itself, and there is no session to take a scope from.
      await client.query('SELECT set_config($1,$2,true), set_config($3,$4,true)',
                         ['app.tenant_id', tenantId, 'app.outlet_id', outletId]);
      const { rows } = await client.query(
        `SELECT COALESCE(s.connectivity::text, 'local_continuity') AS connectivity,
                s.paused_reason,
                s.last_contact_at
           FROM edge.node n
           LEFT JOIN integration.sync_state s ON s.node_id = n.id
          WHERE n.tenant_id = $1::uuid AND n.id = $2::uuid`,
        [tenantId, nodeId],
      );
      return {
        node: deps.profile.nodeCode,
        outletId,
        connectivity: rows[0]?.connectivity ?? 'local_continuity',
        pausedReason: rows[0]?.paused_reason ?? null,
        lastContactAt: rows[0]?.last_contact_at ?? null,
        locale: wanted,
      };
    });
  });

  // -------------------------------------------------------------------------
  // FR-EDG-025 — what the node holds
  // -------------------------------------------------------------------------

  app.get('/n/v1/readiness', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT element::text, held, is_held, detail
           FROM edge.readiness_report($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      return {
        elements: rows,
        ready: rows.every((row: { is_held: boolean }) => row.is_held),
      };
    }),
  );

  // -------------------------------------------------------------------------
  // FR-EDG-017 — health, all seven components
  // -------------------------------------------------------------------------

  app.get('/n/v1/health', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT component::text, state::text, detail, observed_at
           FROM edge.node_health($1::uuid, $2::uuid)`,
        [tenantId, nodeId],
      );
      return { components: rows };
    }),
  );

  // -------------------------------------------------------------------------
  // FR-POS-008 — the five states, in plain language
  // -------------------------------------------------------------------------

  app.get('/n/v1/sync-states', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT state::text, operations, wording
           FROM edge.staff_sync_summary($1::uuid, $2::uuid, $3::menu.customer_locale)`,
        [tenantId, outletId, locale(request)],
      );
      return { states: rows };
    }),
  );

  // -------------------------------------------------------------------------
  // FR-EDG-010 — may this be done now, and what do we tell them
  // -------------------------------------------------------------------------

  app.get<{ Params: { code: string } }>('/n/v1/action/:code', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      try {
        const { rows } = await client.query(
          `SELECT disposition::text, explanation
             FROM edge.action_disposition($1::uuid, $2::uuid, $3, $4::menu.customer_locale)`,
          [tenantId, outletId, request.params.code, locale(request)],
        );
        return rows[0];
      } catch (error) {
        // An unclassified action is a defect in the registry, not a bad request, and
        // saying so is more useful than 400. The signature carries which it was.
        const signature = signatureOf(error);
        if (signature === 'ACTION_UNCLASSIFIED' || signature === 'PHRASE_UNWORDED') {
          reply.code(500);
          return { error: signature };
        }
        throw error;
      }
    }),
  );

  // -------------------------------------------------------------------------
  // FR-EDG-008 — the operator surface for a disagreement
  // -------------------------------------------------------------------------

  app.get('/n/v1/conflicts', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT id, subject::text, subject_id, local_value, remote_value,
                local_occurred_at, remote_occurred_at, detected_at, detail
           FROM integration.conflict
          WHERE tenant_id = $1::uuid AND node_id = $2::uuid AND resolution IS NULL
          ORDER BY detected_at`,
        [tenantId, nodeId],
      );
      return { conflicts: rows };
    }),
  );

  app.post<{ Params: { id: string }; Body: { resolution?: string; note?: string } }>(
    '/n/v1/conflicts/:id/resolve',
    {
      schema: {
        body: {
          type: 'object',
          required: ['resolution', 'note'],
          properties: { resolution: { type: 'string' }, note: { type: 'string' } },
        },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, userId) => {
        try {
          await client.query(
            `SELECT integration.resolve_conflict(
                      $1::uuid, $2::uuid, $3::integration.conflict_resolution, $4::uuid, $5)`,
            [tenantId, request.params.id, request.body.resolution, userId, request.body.note],
          );
          return { resolved: true };
        } catch (error) {
          const signature = signatureOf(error);
          if (signature === 'CONFLICT_RESOLUTION_UNEXPLAINED') {
            reply.code(422);
            return { error: signature };
          }
          if (signature === 'CONFLICT_ALREADY_RESOLVED') {
            reply.code(409);
            return { error: signature };
          }
          if (signature === 'CONFLICT_UNKNOWN') {
            reply.code(404);
            return { error: signature };
          }
          throw error;
        }
      }),
  );

  // -------------------------------------------------------------------------
  // FR-EDG-029 — the print queue and what the printers are doing
  // -------------------------------------------------------------------------

  app.get('/n/v1/print-queue', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows: printers } = await client.query(
        `SELECT printer_id, display_name, has_passed_a_test, queued, abandoned,
                oldest_queued_at, last_printed_at, consecutive_failures
           FROM docs.printer_health($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      const { rows: jobs } = await client.query(
        `SELECT id, receipt_id, printer_id, state::text, attempts, max_attempts,
                is_reprint, last_error, enqueued_at, printed_at
           FROM docs.print_job
          WHERE tenant_id = $1::uuid AND outlet_id = $2::uuid
            AND state <> 'printed'
          ORDER BY enqueued_at`,
        [tenantId, outletId],
      );
      return { printers, jobs };
    }),
  );

  // -------------------------------------------------------------------------
  // FR-OPS-018 — the estate
  // -------------------------------------------------------------------------

  app.get('/n/v1/estate', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows: coverage } = await client.query(
        `SELECT asset_class::text, recorded, is_covered
           FROM ops.asset_register($1::uuid, $2::uuid)`,
        [tenantId, outletId],
      );
      const { rows: assets } = await client.query(
        `SELECT asset_class::text, asset_tag, display_name, location,
                support_owner_user_id, support_owner_external
           FROM ops.outlet_asset
          WHERE tenant_id = $1::uuid AND outlet_id = $2::uuid AND status = 'active'
          ORDER BY asset_class, asset_tag`,
        [tenantId, outletId],
      );
      return { coverage, assets };
    }),
  );
}
