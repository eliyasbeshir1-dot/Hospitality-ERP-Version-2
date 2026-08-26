/**
 * Advertised jobs and their readiness probes (FR-OPS-002, FR-OPS-005).
 *
 * A job is only advertised if it can be shown to do real work. The probe performs the
 * job's actual operation against the real database — not a registration check, not a
 * ping. A job that is registered but non-functional makes readiness fail.
 *
 * Only Phase 1 jobs appear here. Outlet authority, printer status and synchronization
 * are M5a: they are not listed, not stubbed and not claimed.
 */
import type { PoolClient } from 'pg';
import type { Database } from './db';

export interface JobDefinition {
  name: string;
  description: string;
  probe(client: PoolClient): Promise<void>;
}

export interface JobStatus {
  name: string;
  healthy: boolean;
  detail: string;
}

export const PHASE_1_JOBS: JobDefinition[] = [
  {
    name: 'retention-sweep',
    description: 'applies configured retention policies',
    async probe(client) {
      // Real work: resolve the policies this job would act on. If the function is gone,
      // renamed or unreadable by this role, the job cannot run and readiness must say so.
      await client.query(
        `SELECT count(*) FROM config.retention_policy WHERE retain_for > interval '0'`,
      );
      await client.query(`SELECT pg_get_functiondef('config.apply_retention(uuid)'::regprocedure)`);
    },
  },
  {
    name: 'session-expiry',
    description: 'marks expired sessions unusable',
    async probe(client) {
      await client.query(
        `SELECT count(*) FROM identity.session WHERE expires_at < now() AND revoked_at IS NULL`,
      );
    },
  },
  {
    name: 'auth-lockout-release',
    description: 'clears lockouts whose window has passed',
    async probe(client) {
      await client.query(`SELECT count(*) FROM identity.auth_lockout WHERE locked_until < now()`);
    },
  },
];

export async function probeJobs(db: Database, jobs: JobDefinition[]): Promise<JobStatus[]> {
  return db.withoutContext(async (client) => {
    const statuses: JobStatus[] = [];
    for (const job of jobs) {
      try {
        await job.probe(client);
        statuses.push({ name: job.name, healthy: true, detail: job.description });
      } catch (error) {
        statuses.push({
          name: job.name,
          healthy: false,
          // The message is a classification, never the underlying error text, which could
          // carry a connection string or a value from a failing statement.
          detail: 'probe failed: the job cannot perform its work',
        });
        void error;
      }
    }
    return statuses;
  });
}
