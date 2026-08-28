/**
 * Database access as the least-privileged application role.
 *
 * Two rules hold everywhere in this file:
 *
 *  1. Every statement is parameterized. No caller concatenates a value into SQL, so there
 *     is no injection surface to defend (FR-SEC-004).
 *  2. Request context is established inside a transaction and is transaction-local, so
 *     it cannot leak to the next request that borrows the same pooled connection.
 *
 * Rule 2 was documented here before it was true. withSession opened a transaction, but
 * identity.establish_session_context set its context with set_config(..., false) — a
 * plain SET, which outlives COMMIT and travels back to the pool with the connection.
 * Migration 0005 makes that context transaction-local, so the guarantee this comment
 * describes is now enforced by the database rather than asserted by the comment.
 */
import { Pool, PoolClient } from 'pg';

export interface RequestContext {
  tenantId: string;
  outletId: string | null;
  sessionId: string | null;
}

export class Database {
  constructor(private readonly pool: Pool) {}

  static fromUrl(databaseUrl: string): Database {
    return new Database(new Pool({ connectionString: databaseUrl, max: 8 }));
  }

  async close(): Promise<void> {
    await this.pool.end();
  }

  /**
   * Run without any tenant context. Row level security denies tenant-owned rows.
   *
   * This is the method that would have exposed the leak: borrow a pooled connection a
   * scoped request had just released, and any context that survived would still be set.
   * The M1-D suite proves it sees nothing on a connection that has just served a scoped
   * request.
   */
  async withoutContext<T>(work: (client: PoolClient) => Promise<T>): Promise<T> {
    const client = await this.pool.connect();
    try {
      return await work(client);
    } finally {
      client.release();
    }
  }

  /**
   * Authenticate a bearer token and run inside the resulting context.
   *
   * The token carries the tenant and outlet it claims in a non-secret prefix; the
   * database checks that claim against the stored digest under ordinary RLS, so a forged
   * prefix simply finds no row.
   */
  async withSession<T>(
    token: string,
    work: (client: PoolClient, context: RequestContext) => Promise<T>,
  ): Promise<T> {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new ContextRefused('MALFORMED_SESSION_TOKEN');
    }
    const [tenantId, outletId] = parts as [string, string, string];
    const digest = await sha256Hex(token);

    const client = await this.pool.connect();
    try {
      await client.query('BEGIN');
      const { rows } = await client.query(
        'SELECT identity.establish_session_context($1::uuid, $2::uuid, decode($3, $4)) AS session_id',
        [tenantId, outletId, digest, 'hex'],
      );
      const context: RequestContext = {
        tenantId,
        outletId,
        sessionId: rows[0]?.session_id ?? null,
      };
      const result = await work(client, context);
      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK').catch(() => undefined);
      if (error instanceof ContextRefused) throw error;
      throw new ContextRefused('SESSION_NOT_ESTABLISHED');
    } finally {
      client.release();
    }
  }
}

export class ContextRefused extends Error {
  constructor(public readonly signature: string) {
    super(signature);
    this.name = 'ContextRefused';
  }
}

async function sha256Hex(value: string): Promise<string> {
  const { createHash } = await import('node:crypto');
  return createHash('sha256').update(value).digest('hex');
}
