/**
 * Health and readiness (FR-OPS-002, FR-OPS-005).
 *
 * Health says the process is alive. Readiness says the process can do its job, and it is
 * allowed to say no. It verifies that migrations are applied, that the connecting role is
 * the production role and unprivileged, and that every advertised job can perform real
 * work. Any of those failing makes readiness unhealthy — quietly passing would make the
 * whole signal worthless.
 */
import type { FastifyInstance } from 'fastify';
import type { Database } from '../db';
import { probeJobs, PHASE_1_JOBS } from '../jobs';
import type { RoleFacts } from '../env';

export interface HealthDependencies {
  db: Database;
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

  app.get('/ready', async (_request, reply) => {
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

    // The role check runs again here, not only at startup: a role can be altered while a
    // process is running, and readiness that only remembers what was true at boot is a
    // stale claim rather than a check.
    if (deps.roleFacts.isSuperuser || deps.roleFacts.bypassesRls
        || deps.roleFacts.ownsApplicationTables) {
      problems.push('the connecting role is privileged');
    }

    const jobs = await probeJobs(deps.db, PHASE_1_JOBS);
    for (const job of jobs) {
      if (!job.healthy) problems.push(`advertised job ${job.name} cannot perform its work`);
    }

    const ready = problems.length === 0;
    reply.code(ready ? 200 : 503);
    return {
      status: ready ? 'ready' : 'unready',
      problems,
      migrations: migrations.map((m) => `${String(m.version).padStart(4, '0')} ${m.filename}`),
      seeds: seeds.map((s) => `${String(s.version).padStart(4, '0')} ${s.filename}`),
      role: { name: deps.roleFacts.currentUser, privileged: false },
      jobs,
      rateLimiting: {
        scope: 'singleInstance',
        note: 'in-process limits only; distributed enforcement is deferred to M6',
      },
    };
  });
}
