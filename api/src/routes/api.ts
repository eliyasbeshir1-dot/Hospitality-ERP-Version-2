/**
 * The M1 API surface: tenancy, identity, memberships, sessions, configuration.
 *
 * There is no menu, order, check or payment route here. Those belong to M2, M3 and M4 and
 * are not stubbed, not registered and not reserved.
 *
 * Every route below authenticates a bearer token and runs inside the resulting tenant and
 * outlet context, under ordinary row level security. A request without a usable token
 * receives 401 and no data — the route never falls back to an unscoped read.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { ContextRefused, type Database, type RequestContext } from '../db';
import type { StructuredLogger } from '../logging';

export interface ApiDependencies {
  db: Database;
  logger: StructuredLogger;
}

const UUID = { type: 'string', format: 'uuid' } as const;

function bearerToken(request: FastifyRequest): string | null {
  const header = request.headers.authorization;
  if (!header || !header.toLowerCase().startsWith('bearer ')) return null;
  const token = header.slice(7).trim();
  return token.length > 0 ? token : null;
}

export function registerApiRoutes(app: FastifyInstance, deps: ApiDependencies): void {
  /** Run a handler inside an authenticated context, or answer 401. */
  async function scoped<T>(
    request: FastifyRequest,
    reply: FastifyReply,
    work: (client: Parameters<Parameters<Database['withSession']>[1]>[0],
           context: RequestContext) => Promise<T>,
  ): Promise<T | { error: string }> {
    const token = bearerToken(request);
    if (!token) {
      reply.code(401);
      // The response says a credential is required. It does not say which part was
      // missing or wrong, because that is a probing oracle (FR-SEC-007).
      return { error: 'authentication required' };
    }
    try {
      return await deps.db.withSession(token, work);
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        deps.logger.warn('authentication refused', {
          correlationId: request.id,
          event: 'auth.refused',
          errorClass: error.signature,
        });
        return { error: 'authentication required' };
      }
      throw error;
    }
  }

  app.get('/v1/tenant', async (request, reply) =>
    scoped(request, reply, async (client) => {
      const { rows } = await client.query(
        'SELECT id, tenant_code, display_name, status FROM org.tenant',
      );
      return { tenant: rows[0] ?? null };
    }));

  app.get('/v1/outlets', async (request, reply) =>
    scoped(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT id, reference_code, display_name, status
         FROM org.org_node WHERE kind = 'outlet' ORDER BY reference_code`,
      );
      return { outlets: rows };
    }));

  app.get('/v1/memberships', async (request, reply) =>
    scoped(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT m.id, m.user_account_id, m.outlet_id, r.role_code, m.status
         FROM identity.membership m
         JOIN identity.role r ON r.id = m.role_id AND r.tenant_id = m.tenant_id
         ORDER BY r.role_code`,
      );
      return { memberships: rows };
    }));

  app.get('/v1/sessions', async (request, reply) =>
    scoped(request, reply, async (client) => {
      // The token digest is never selected, so it cannot reach a response or a log.
      const { rows } = await client.query(
        `SELECT id, user_account_id, device_id, established_with,
                issued_at, expires_at, revoked_at, revoked_reason
         FROM identity.session ORDER BY issued_at DESC`,
      );
      return { sessions: rows };
    }));

  app.delete('/v1/sessions/:sessionId', {
    schema: { params: { type: 'object', required: ['sessionId'], properties: { sessionId: UUID } } },
  }, async (request, reply) =>
    scoped(request, reply, async (client, context) => {
      const { sessionId } = request.params as { sessionId: string };
      const { rowCount } = await client.query(
        `UPDATE identity.session
         SET revoked_at = now(), revoked_reason = 'administrator_revoked', row_version = row_version
         WHERE id = $1 AND revoked_at IS NULL`,
        [sessionId],
      );
      deps.logger.info('session revoked', {
        correlationId: request.id, event: 'session.revoke',
        tenantId: context.tenantId, outletId: context.outletId,
        revoked: rowCount ?? 0,
      });
      return { revoked: rowCount ?? 0 };
    }));

  app.get('/v1/configuration/:category', {
    schema: {
      params: {
        type: 'object',
        required: ['category'],
        properties: {
          category: {
            type: 'string',
            // Enumerated, so an unknown category is refused by the schema before any
            // domain code runs (FR-SEC-003).
            enum: ['branding', 'locale', 'currency', 'timezone', 'tax', 'calendar',
                   'numbering', 'payment_method', 'service', 'feature', 'connector'],
          },
        },
      },
    },
  }, async (request, reply) =>
    scoped(request, reply, async (client, context) => {
      const { category } = request.params as { category: string };
      const { rows } = await client.query(
        'SELECT config.effective_configuration($1::uuid, $2::config.configuration_category) AS payload',
        [context.tenantId, category],
      );
      return { category, payload: rows[0]?.payload ?? null };
    }));

  app.get('/v1/entitlements/:featureKey', {
    schema: {
      params: {
        type: 'object',
        required: ['featureKey'],
        // maxLength sits below Fastify's maxParamLength (100), so the declared bound is
        // the one that actually governs. A larger value here would be unreachable: the
        // router would refuse with 414 before the schema was ever consulted.
        properties: { featureKey: { type: 'string', minLength: 1, maxLength: 64,
                                    pattern: '^[a-z][a-z0-9_]*$' } },
      },
    },
  }, async (request, reply) =>
    scoped(request, reply, async (client, context) => {
      const { featureKey } = request.params as { featureKey: string };
      const { rows } = await client.query(
        'SELECT config.is_entitled($1, $2::uuid) AS granted',
        [featureKey, context.outletId],
      );
      return { featureKey, granted: rows[0]?.granted === true };
    }));

  app.get('/v1/reason-codes/:category', {
    schema: {
      params: {
        type: 'object',
        required: ['category'],
        properties: {
          category: {
            type: 'string',
            enum: ['order_cancellation', 'void', 'refund', 'discount', 'complimentary_item',
                   'payment_reversal', 'tip_correction', 'service_failure', 'printer_failure',
                   'manager_override'],
          },
        },
      },
    },
  }, async (request, reply) =>
    scoped(request, reply, async (client) => {
      const { category } = request.params as { category: string };
      const { rows } = await client.query(
        `SELECT rc.code, rc.requires_approval, l.locale, l.label
         FROM config.reason_code rc
         LEFT JOIN config.reason_code_label l ON l.reason_code_id = rc.id
         WHERE rc.category = $1::config.reason_code_category
         ORDER BY rc.code, l.locale`,
        [category],
      );
      return { category, reasonCodes: rows };
    }));
}
