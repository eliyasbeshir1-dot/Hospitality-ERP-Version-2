/**
 * Dashboards, the sales report, the signed-off snapshot and the export.
 *
 * EVERY FIGURE ARRIVES WITH ITS SOURCE AND ITS FRESHNESS ATTACHED, and not because this
 * file adds them. report.reading() is the only constructor for a metric value and it
 * refuses to build one without both — FR-RPT-002's labelling is a property of the value
 * rather than something a surface is supposed to remember to draw. There are two
 * freshness facts and that is deliberate: computedAt says when the arithmetic ran and
 * latestSourceRowAt says how recent the data under it was, and a report computed a second
 * ago over yesterday's data is exactly the case where one number cannot say both.
 *
 * A NULL VALUE IS AN EMPTY STATE, NOT A ZERO. FR-UX-014 forbids fabricated analytics, and
 * the distinction it needed is that a quiet hour genuinely had zero orders while a median
 * preparation time over no tickets has no value at all. The catalog declares which is
 * which per metric and report.reading() raises FABRICATED_METRIC in both directions, so
 * a null reaching this file means "nothing to summarise" and the surface renders the
 * instructive empty state rather than a plausible number.
 *
 * THE SCOPING IS THE DATABASE'S. Every report function is SECURITY INVOKER — 0029 refuses
 * to apply if any function in the report schema is not — so an export cannot reach a row
 * the caller could not have selected. FR-RPT-013's tenant and outlet scoping is therefore
 * not a WHERE clause this file appends and could forget.
 *
 * NOTHING HERE CAN WRITE A SNAPSHOT. The application role holds no INSERT on
 * report.shift_snapshot or report.shift_snapshot_value at all; the snapshot is written by
 * a trigger at the instant a shift is signed off. The recomputation route below records
 * what a recomputation found and cannot change what was signed.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { PoolClient } from 'pg';
import { ContextRefused, type Database } from '../db';
import type { StructuredLogger } from '../logging';

export interface ReportDependencies {
  db: Database;
  logger: StructuredLogger;
}

const UUID = { type: 'string', format: 'uuid' } as const;
const WINDOW = {
  from: { type: 'string' },
  to: { type: 'string' },
  currency: { type: 'string', minLength: 3, maxLength: 3 },
} as const;

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
  FABRICATED_METRIC: 422,
  METRIC_UNCATALOGUED: 422,
  METRIC_CURRENCY_MISMATCH: 422,
  SALES_COMPONENT_UNCLASSIFIED: 422,
  SNAPSHOT_NOT_FOUND: 404,
  SNAPSHOT_INCOMPLETE: 422,
  SNAPSHOT_SEAL_BROKEN: 409,
  FINANCIAL_LEDGER_MUTATED: 409,
  SESSION_NOT_LIVE: 401,
};

export function registerReportRoutes(app: FastifyInstance, deps: ReportDependencies): void {
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
      event: 'report.unmapped', errorClass: reason ?? 'UNKNOWN', sqlstate,
    });
    return { error: 'refused', reason: reason ?? 'UNMAPPED_REFUSAL', sqlstate };
  }

  /** The window, defaulted to the last day. Instants throughout (FR-RPT-015). */
  function windowOf(query: { from?: string; to?: string; currency?: string }) {
    return [query.from ?? null, query.to ?? null, query.currency ?? 'ETB'] as const;
  }

  // -------------------------------------------------------------------------
  // The catalog itself (FR-RPT-015)
  // -------------------------------------------------------------------------

  app.get('/s/v1/reports/catalog', async (request, reply) =>
    asStaff(request, reply, async (client) => {
      const { rows } = await client.query(
        `SELECT m.key, m.unit, m.title, m.formula, m.timezone_rule, m.currency_rule,
                m.inclusion_rule, m.source_relation::text AS source_relation,
                m.empty_window_is_zero, m.empty_window_reason
           FROM report.metric m ORDER BY m.key::text`);
      const version = await client.query('SELECT report.catalog_version() AS version');
      return { version: version.rows[0].version as number, metrics: rows };
    }));

  // -------------------------------------------------------------------------
  // Role dashboards (FR-RPT-001, FR-RPT-002)
  // -------------------------------------------------------------------------

  /**
   * WHICH ROLES HAVE A DASHBOARD IS NOT LISTED HERE. report.dashboard_role is an enum and
   * a copy of it in this file would be the drift this repository refuses everywhere else.
   * An unknown role fails the cast and comes back as a named refusal — including
   * 'technical_operator', which is M5a's and has no label at this gate.
   */
  app.get<{ Params: { role: string };
            Querystring: { from?: string; to?: string; currency?: string } }>(
    '/s/v1/reports/dashboards/:role', {
      schema: {
        params: { type: 'object', required: ['role'],
                  properties: { role: { type: 'string', minLength: 1, maxLength: 40 } } },
        querystring: { type: 'object', properties: WINDOW },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        const [from, to, currency] = windowOf(request.query);
        try {
          const { rows } = await client.query(
            `SELECT display_order AS "displayOrder", metric, title, unit, value,
                    currency_code AS "currencyCode",
                    observation_count AS "observationCount",
                    source::text AS source,
                    computed_at AS "computedAt",
                    latest_source_row_at AS "latestSourceRowAt"
               FROM report.dashboard_for($1::report.dashboard_role, $2::uuid, $3::uuid,
                      coalesce($4::timestamptz, now() - interval '1 day'),
                      coalesce($5::timestamptz, now()), $6::char(3))`,
            [request.params.role, tenantId, outletId, from, to, currency]);
          return { role: request.params.role, panels: rows };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  // -------------------------------------------------------------------------
  // Sales, service and kitchen (FR-RPT-003, FR-RPT-004, FR-RPT-005)
  // -------------------------------------------------------------------------

  /**
   * ALL SEVEN CLASSIFICATIONS, ALWAYS, and tips are one of them. The rows come from
   * report.sales_report(), which enumerates the classifications from the type rather than
   * from the data — so "we take no service charge" and "the service charge query broke"
   * do not render the same.
   */
  app.get<{ Querystring: { from?: string; to?: string; currency?: string } }>(
    '/s/v1/reports/sales', {
      schema: { querystring: { type: 'object', properties: WINDOW } },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        const [from, to, currency] = windowOf(request.query);
        try {
          const { rows } = await client.query(
            `SELECT classification, value, currency_code AS "currencyCode",
                    observation_count AS "observationCount", source::text AS source,
                    computed_at AS "computedAt",
                    latest_source_row_at AS "latestSourceRowAt"
               FROM report.sales_report($1::uuid, $2::uuid,
                      coalesce($3::timestamptz, now() - interval '1 day'),
                      coalesce($4::timestamptz, now()), $5::char(3))`,
            [tenantId, outletId, from, to, currency]);
          return { sales: rows };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  app.get<{ Querystring: { from?: string; to?: string; currency?: string } }>(
    '/s/v1/reports/metrics', {
      schema: { querystring: { type: 'object', properties: WINDOW } },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId) => {
        const [from, to, currency] = windowOf(request.query);
        try {
          const { rows } = await client.query(
            `SELECT (v).metric AS metric, (v).unit AS unit, (v).value AS value,
                    (v).currency_code AS "currencyCode",
                    (v).observation_count AS "observationCount",
                    (v).source::text AS source,
                    (v).computed_at AS "computedAt",
                    (v).latest_source_row_at AS "latestSourceRowAt"
               FROM report.metric_values($1::uuid, $2::uuid,
                      coalesce($3::timestamptz, now() - interval '1 day'),
                      coalesce($4::timestamptz, now()), $5::char(3)) v
              ORDER BY 1`,
            [tenantId, outletId, from, to, currency]);
          return { metrics: rows };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  // -------------------------------------------------------------------------
  // The signed-off snapshot (FR-RPT-014)
  // -------------------------------------------------------------------------

  app.get<{ Params: { shiftId: string } }>(
    '/s/v1/reports/shifts/:shiftId/snapshot', {
      schema: {
        params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId) => {
        const { rows } = await client.query(
          `SELECT s.id, s.catalog_version AS "catalogVersion", s.currency_code AS "currencyCode",
                  s.window_from AS "windowFrom", s.window_to AS "windowTo",
                  s.signed_off_by_user_id AS "signedOffByUserId",
                  s.signed_off_at AS "signedOffAt",
                  s.content_digest AS "contentDigest",
                  (SELECT jsonb_agg(jsonb_build_object(
                            'metric', v.metric, 'unit', v.unit, 'value', v.value,
                            'currencyCode', v.currency_code,
                            'observationCount', v.observation_count,
                            'source', v.source_relation,
                            'latestSourceRowAt', v.latest_source_row_at)
                          ORDER BY v.metric::text)
                     FROM report.shift_snapshot_value v
                    WHERE v.tenant_id = s.tenant_id AND v.snapshot_id = s.id) AS values
             FROM report.shift_snapshot s
            WHERE s.tenant_id = $1::uuid AND s.shift_id = $2::uuid`,
          [tenantId, request.params.shiftId]);
        if (rows.length === 0) {
          reply.code(404);
          return { error: 'refused', reason: 'SNAPSHOT_NOT_FOUND' };
        }
        return { snapshot: rows[0] };
      }));

  /**
   * A RECOMPUTATION REPORTS; IT DOES NOT REWRITE. This route records what a
   * recomputation found and returns the divergences it named. There is no route, and no
   * grant, by which a recomputed figure could reach the signed-off snapshot.
   */
  app.post<{ Params: { shiftId: string } }>(
    '/s/v1/reports/shifts/:shiftId/recomputations', {
      schema: {
        params: { type: 'object', required: ['shiftId'], properties: { shiftId: UUID } },
      },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        try {
          const { rows } = await client.query(
            `SELECT report.recompute_shift_snapshot($1::uuid, $2::uuid, $3::uuid) AS id`,
            [tenantId, request.params.shiftId, userId]);
          const id = rows[0].id as string;
          const found = await client.query(
            `SELECT r.diverged, r.content_digest AS "contentDigest",
                    (SELECT jsonb_agg(jsonb_build_object(
                              'metric', d.metric,
                              'snapshotValue', d.snapshot_value,
                              'recomputedValue', d.recomputed_value,
                              'snapshotObservationCount', d.snapshot_observation_count,
                              'recomputedObservationCount', d.recomputed_observation_count)
                            ORDER BY d.metric::text)
                       FROM report.snapshot_divergence d
                      WHERE d.tenant_id = r.tenant_id AND d.recomputation_id = r.id)
                    AS divergences
               FROM report.recomputation r
              WHERE r.tenant_id = $1::uuid AND r.id = $2::uuid`,
            [tenantId, id]);
          return { recomputationId: id, ...found.rows[0] };
        } catch (error) {
          return answer(reply, error);
        }
      }));

  // -------------------------------------------------------------------------
  // Exports (FR-RPT-013)
  // -------------------------------------------------------------------------

  /**
   * CSV, RFC 4180, with a header row naming eight documented columns. It is returned as
   * text/csv because that is what it is; the scoping is not this route's doing, it is
   * report.export_metrics_csv() being SECURITY INVOKER under the caller's row level
   * security.
   */
  app.get<{ Querystring: { from?: string; to?: string; currency?: string } }>(
    '/s/v1/reports/exports/metrics.csv', {
      schema: { querystring: { type: 'object', properties: WINDOW } },
    },
    async (request, reply) =>
      asStaff(request, reply, async (client, tenantId, outletId, userId) => {
        const [from, to, currency] = windowOf(request.query);
        try {
          const { rows } = await client.query(
            `SELECT report.export_metrics_csv($1::uuid, $2::uuid,
                      coalesce($3::timestamptz, now() - interval '1 day'),
                      coalesce($4::timestamptz, now()), $5::char(3), $6::uuid) AS csv`,
            [tenantId, outletId, from, to, currency, userId]);
          reply.header('content-type', 'text/csv; charset=utf-8');
          return rows[0].csv as string;
        } catch (error) {
          return answer(reply, error);
        }
      }));
}
