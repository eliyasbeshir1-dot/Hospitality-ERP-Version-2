/**
 * Health and readiness (FR-OPS-002, FR-OPS-005).
 *
 * Health says the process is alive. Readiness says the process can do its job, and it is
 * allowed to say no. It verifies that migrations are applied, that the connecting role is
 * the production role and unprivileged, and that every advertised job can perform real
 * work. Any of those failing makes readiness unhealthy — quietly passing would make the
 * whole signal worthless.
 */
import type { FastifyInstance, FastifyRequest } from 'fastify';
import type { Database } from '../db';
import { probeJobs, PHASE_1_JOBS } from '../jobs';
import { ROLE_FACTS_SQL, privilegeViolations, toRoleFacts, type RoleFacts } from '../env';
import { ContextRefused } from '../db';

export interface HealthDependencies {
  db: Database;
  /** What the role was at boot. Readiness re-reads it; this is only the startup record. */
  roleFacts: RoleFacts;
  serviceName: string;
  environmentName: string;
  startedAt: Date;
}

export function registerHealthRoutes(app: FastifyInstance, deps: HealthDependencies): void {
  app.get('/health', async () => ({
    status: 'alive',
    service: deps.serviceName,
    environment: deps.environmentName,
    startedAt: deps.startedAt.toISOString(),
  }));

  /**
   * Readiness.
   *
   * Two decisions are recorded here.
   *
   * Role privilege is re-read from the database on every probe, not taken from the
   * boot-time snapshot. `ALTER ROLE hospitality_app BYPASSRLS` needs no restart, and a
   * check that answers from a snapshot would keep reporting 200 with an empty problem
   * list while the process ran with row level security disabled under it.
   *
   * The detail is scoped to the caller. An unauthenticated probe — a load balancer, an
   * operator, anyone who can reach the port — gets everything needed to act on the
   * signal: the verdict, the problems, how many migrations and seeds are applied, the
   * highest migration version, and each advertised job's name and health. It does NOT
   * get the migration and seed FILENAMES or the database role name, which describe the
   * deployment rather than its health. Those require a valid session token.
   */
  app.get('/ready', async (request, reply) => {
    const problems: string[] = [];

    let migrations: { version: number; filename: string }[] = [];
    let seeds: { version: number; filename: string }[] = [];
    try {
      await deps.db.withoutContext(async (client) => {
        const m = await client.query(
          'SELECT version, filename FROM migration.schema_migrations ORDER BY version',
        );
        migrations = m.rows;
        const s = await client.query(
          'SELECT version, filename FROM seed_history.applied_seed ORDER BY version',
        );
        seeds = s.rows;
      });
    } catch {
      problems.push('migration or seed history is unreadable');
    }
    if (migrations.length === 0) problems.push('no migration has been applied');

    // Re-read, every time. Fails closed: a role we could not interrogate is treated as
    // unverified, not as unprivileged.
    const roleNow = await currentRoleFacts();
    const violations = roleNow === null
      ? ['role privilege could not be verified']
      : privilegeViolations(roleNow);
    const privileged = violations.length > 0;
    if (privileged) {
      problems.push(`the connecting role is privileged: ${violations.join(', ')}`);
    }

    const jobs = await probeJobs(deps.db, PHASE_1_JOBS);
    for (const job of jobs) {
      if (!job.healthy) problems.push(`advertised job ${job.name} cannot perform its work`);
    }

    const ready = problems.length === 0;
    reply.code(ready ? 200 : 503);

    const body: Record<string, unknown> = {
      status: ready ? 'ready' : 'unready',
      problems,
      migrations: {
        applied: migrations.length,
        latest: migrations.length > 0
          ? String(migrations[migrations.length - 1]!.version).padStart(4, '0')
          : null,
      },
      seeds: { applied: seeds.length },
      role: { privileged },
      jobs,
      rateLimiting: {
        scope: 'singleInstance',
        note: 'in-process limits only; distributed enforcement is deferred to M6',
      },
      detail: 'restricted',
    };

    if (await hasValidSession(request)) {
      body.migrations = {
        ...(body.migrations as object),
        files: migrations.map((m) => `${String(m.version).padStart(4, '0')} ${m.filename}`),
      };
      body.seeds = {
        ...(body.seeds as object),
        files: seeds.map((s) => `${String(s.version).padStart(4, '0')} ${s.filename}`),
      };
      body.role = { privileged, name: roleNow?.currentUser ?? deps.roleFacts.currentUser };
      body.detail = 'full';
    }

    return body;
  });

  /** What the connecting role is right now, or null if it could not be determined. */
  async function currentRoleFacts(): Promise<RoleFacts | null> {
    try {
      return await deps.db.withoutContext(async (client) => {
        const { rows } = await client.query(ROLE_FACTS_SQL);
        return rows[0] ? toRoleFacts(rows[0]) : null;
      });
    } catch {
      return null;
    }
  }

  /** True when the request carries a bearer token that authenticates. */
  async function hasValidSession(request: FastifyRequest): Promise<boolean> {
    const header = request.headers.authorization;
    if (!header || !header.toLowerCase().startsWith('bearer ')) return false;
    const token = header.slice(7).trim();
    if (token.length === 0) return false;
    try {
      await deps.db.withSession(token, async () => undefined);
      return true;
    } catch (error) {
      if (error instanceof ContextRefused) return false;
      throw error;
    }
  }
}
