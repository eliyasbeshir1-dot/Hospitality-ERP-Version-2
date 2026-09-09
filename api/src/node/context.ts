/**
 * Setting request context, in the one place that gets it right.
 *
 * THIS FILE EXISTS BECAUSE THE SAME DEFECT HAPPENED FOUR TIMES IN ONE GATE.
 *
 * `set_config(key, value, true)` is TRANSACTION-local. That is deliberate and it is what
 * M1-D's migration 0005 changed it to: context that outlived COMMIT travelled back to the
 * pool with the connection and leaked into the next request. The guarantee is real and
 * worth keeping.
 *
 * What nothing wrote down is the other half: outside an explicit transaction, every
 * statement is its own transaction, so a context set that way is gone before the next
 * statement reads it. It does not error. It does not warn. The next statement runs with
 * no context at all, row level security matches nothing, and the caller gets an empty
 * result that looks exactly like an honest one.
 *
 * In M5a it produced four different wrong answers in four files:
 *
 *   api/src/node/identity.ts     every node refused to start, with a message about
 *                                fingerprints that looked like a sensible answer
 *   api/src/routes/node.ts       the connectivity banner answered CONNECTED, because a
 *                                node it could not see read as an outlet with no node
 *   api/src/node/sync-worker.ts  every synchronization round failed
 *   api/src/node/realtime-gateway.ts  the watermark read zeros forever, so nothing was
 *                                ever pushed and the screens silently stopped updating
 *
 * Four symptoms, one cause, none of them saying "you have no context". Three of the four
 * were plausible enough to be believed. So the fix is not four fixes: it is one function
 * that cannot be called without a transaction, and every caller uses it.
 *
 * db.ts's withSession() already does this correctly for request-scoped work. This is its
 * counterpart for the node's own processes, which have no session to take a scope from —
 * a worker acts as the outlet, not as a person.
 */
import type { Client, PoolClient } from 'pg';

export interface NodeScope {
  tenantId: string;
  outletId: string;
}

type AnyClient = Client | PoolClient;

/**
 * Run work inside a transaction with the node's own tenant and outlet context set.
 *
 * The transaction is not an optimisation and not a nicety: it is the thing that makes the
 * context exist at all for the statements inside. Committing on success and rolling back
 * on failure is the ordinary part.
 */
export async function withNodeContext<T>(
  client: AnyClient,
  scope: NodeScope,
  work: (client: AnyClient) => Promise<T>,
): Promise<T> {
  await client.query('BEGIN');
  try {
    await client.query(
      'SELECT set_config($1, $2, true), set_config($3, $4, true)',
      ['app.tenant_id', scope.tenantId, 'app.outlet_id', scope.outletId],
    );
    const result = await work(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  }
}

/**
 * The same, for the one caller that identifies itself by fingerprint rather than outlet.
 *
 * A node authenticating at startup cannot set an outlet scope, because the outlet is the
 * thing being checked — see migration 0046. It presents what only it holds instead.
 */
export async function withFingerprintContext<T>(
  client: AnyClient,
  tenantId: string,
  fingerprint: string,
  work: (client: AnyClient) => Promise<T>,
): Promise<T> {
  await client.query('BEGIN');
  try {
    await client.query(
      'SELECT set_config($1, $2, true), set_config($3, $4, true)',
      ['app.tenant_id', tenantId, 'app.node_fingerprint', fingerprint],
    );
    const result = await work(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  }
}
