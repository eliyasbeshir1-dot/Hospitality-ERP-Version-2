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

      // ONLY THE AUTHENTICATION STEP MAY BE REPORTED AS AN AUTHENTICATION FAILURE.
      //
      // This block used to wrap the caller's work as well: any error the handler did not
      // recognise was rethrown as ContextRefused('SESSION_NOT_ESTABLISHED'), and every
      // route turns that into 401 'authentication required'. So a billing refusal, a
      // constraint violation, a bug in a fold — anything at all — reached the caller as
      // a login problem. The first HTTP call ever made to POST /s/v1/checks reported a
      // duplicate check number as an authentication failure, and an operator would have
      // spent that outage looking at sessions.
      //
      // A diagnostic must not name a cause it did not verify. The rule has been enforced
      // in the test harnesses four times; this is the shipped service, where it matters
      // more. The authentication attempt is the only thing this method is entitled to
      // draw a conclusion about, so only it is caught here.
      let context: RequestContext;
      try {
        const { rows } = await client.query(
          'SELECT identity.establish_session_context($1::uuid, $2::uuid, decode($3, $4)) AS session_id',
          [tenantId, outletId, digest, 'hex'],
        );
        context = { tenantId, outletId, sessionId: rows[0]?.session_id ?? null };
      } catch (error) {
        // The database says WHY it refused — SESSION_NOT_LIVE, NO_ACTIVE_MEMBERSHIP —
        // and that reason is more useful than a single flattened signature, so it is
        // carried through rather than replaced.
        throw new ContextRefused(signatureOf(error) ?? 'SESSION_NOT_ESTABLISHED');
      }

      const result = await work(client, context);
      await client.query('COMMIT');
      return result;
    } catch (error) {
      // The transaction still unwinds for every failure. What does not happen any more
      // is the failure being renamed on its way out.
      await client.query('ROLLBACK').catch(() => undefined);
      throw error;
    } finally {
      client.release();
    }
  }
}

/**
 * The signature a PostgreSQL error carries, or null when it carries none.
 *
 * Two shapes, because the database refuses in two ways. A function that RAISEs names its
 * own reason in capitals — SESSION_NOT_LIVE, BILL_NOT_SETTLED — and that name is the
 * signature. A constraint refuses with an SQLSTATE and the constraint's own name, and no
 * capitals at all, which is why an unhandled unique violation used to fall through every
 * mapper in the service and be reported as something else entirely.
 */
export function signatureOf(error: unknown): string | null {
  const named = /\b([A-Z][A-Z_]{4,})\b/.exec(error instanceof Error ? error.message : '');
  if (named && named[1]) return named[1];

  const code = (error as { code?: string } | null)?.code;
  const constraint = (error as { constraint?: string } | null)?.constraint;
  const CONSTRAINT_REFUSALS: Record<string, string> = {
    '23505': 'UNIQUE_VIOLATION',
    '23503': 'FOREIGN_KEY_VIOLATION',
    '23514': 'CHECK_VIOLATION',
    '23502': 'NOT_NULL_VIOLATION',
    '23P01': 'EXCLUSION_VIOLATION',
  };
  const kind = code ? CONSTRAINT_REFUSALS[code] : undefined;
  if (!kind) return null;
  // The constraint's name is the actionable half — "which rule" rather than "some rule".
  return constraint ? `${kind}:${constraint}` : kind;
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
