/**
 * The continuity node's own identity, proved before it serves anything.
 *
 * FR-CFG-001E asks that the node be registered, bound to one tenant and one outlet, and
 * proved to start ONLY with the correct outlet identity. The database half of that is
 * edge.authenticate_node(), which refuses an unknown code, a revoked node, a wrong
 * fingerprint and a wrong outlet as four separate refusals. This is the process half: it
 * asks, before the listener opens, and exits if the answer is no.
 *
 * THE ORDER MATTERS FOR THE SAME REASON IT DOES IN env.ts. A service that binds first and
 * validates second has already told an orchestrator it is fine. A node that binds first
 * and checks its outlet second has already told a waiter's tablet it is the right node.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO: mint, hold or verify a private key. The fingerprint
 * is read from the node's own configuration and compared against what was registered. A
 * real deployment binds that configuration to hardware — a TPM, a file only the node's
 * user can read — and none of that exists here. planning/M5A_FINDINGS.md records the
 * bound rather than this file implying it is closed.
 */
import { Client } from 'pg';
import { StartupRefusal } from '../env';

export interface NodeProfile {
  nodeId: string;
  nodeCode: string;
  tenantId: string;
  outletId: string;
  lanEndpoint: string;
}

const REQUIRED = ['NODE_CODE', 'NODE_TENANT_ID', 'NODE_OUTLET_ID', 'NODE_FINGERPRINT'] as const;

/** True when this process was asked to run as an outlet node rather than as the cloud. */
export function isNodeProfile(source: NodeJS.ProcessEnv = process.env): boolean {
  return (source.NODE_CODE ?? '').trim() !== '';
}

/**
 * Prove the node is the node it says it is, at the outlet it says it serves.
 *
 * Returns the profile on success. Throws StartupRefusal on every failure, carrying the
 * database's own signature — NODE_OUTLET_MISMATCH is a different operational problem from
 * NODE_IDENTITY_MISMATCH and an operator should not have to guess which they have.
 */
export async function authenticateNode(
  databaseUrl: string,
  source: NodeJS.ProcessEnv = process.env,
): Promise<NodeProfile> {
  const missing = REQUIRED.filter((name) => (source[name] ?? '').trim() === '');
  if (missing.length > 0) {
    throw new StartupRefusal(
      'NODE_ENVIRONMENT_ABSENT',
      `missing or empty: ${missing.join(', ')}. A node that does not know which outlet it `
      + 'serves must not serve one',
    );
  }

  const nodeCode = source.NODE_CODE as string;
  const tenantId = source.NODE_TENANT_ID as string;
  const outletId = source.NODE_OUTLET_ID as string;
  const fingerprint = source.NODE_FINGERPRINT as string;

  const client = new Client({ connectionString: databaseUrl });
  await client.connect();
  try {
    // THE FINGERPRINT IS THE CONTEXT, NOT THE OUTLET.
    //
    // edge.node carries FORCE row level security. The first version of this set the
    // outlet context to the outlet the node BELIEVED it served — and so a node booted
    // with the wrong outlet id looked for its registration in a scope the registration is
    // not in, found nothing, and was told the node was not registered. The refusal that
    // names the mistake was unreachable. Migration 0046 replaces that scope with a policy
    // that lets a node find its own row by presenting what only it holds.
    //
    // AND IT IS ALL ONE TRANSACTION, WHICH IS NOT A DETAIL.
    //
    // set_config(..., true) is TRANSACTION-local. Without an explicit BEGIN each
    // statement is its own transaction, so the context was gone before the next statement
    // read it — every start, including a correct one, saw no context at all, matched no
    // row, and refused. The refusal looked like a sensible answer to a wrong fingerprint,
    // which is why it survived being tested three ways: all three arms of the test agreed,
    // and they agreed because none of them was reaching the check.
    await client.query('BEGIN');
    await client.query('SELECT set_config($1, $2, true), set_config($3, $4, true)',
                       ['app.tenant_id', tenantId, 'app.node_fingerprint', fingerprint]);
    const { rows } = await client.query(
      'SELECT edge.authenticate_node($1::uuid, $2, $3::character(64), $4::uuid) AS node_id',
      [tenantId, nodeCode, fingerprint, outletId],
    );
    const nodeId = rows[0]?.node_id as string;

    const { rows: detail } = await client.query(
      'SELECT lan_endpoint FROM edge.node WHERE tenant_id = $1::uuid AND id = $2::uuid',
      [tenantId, nodeId],
    );
    await client.query('COMMIT');

    return {
      nodeId,
      nodeCode,
      tenantId,
      outletId,
      lanEndpoint: detail[0]?.lan_endpoint ?? '',
    };
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    // The database named the refusal. Carrying it through is the difference between "the
    // node would not start" and "this node is bound to the other outlet".
    const message = error instanceof Error ? error.message : String(error);
    const signature = /\b(NODE_[A-Z_]+)\b/.exec(message)?.[1] ?? 'NODE_NOT_AUTHENTICATED';
    throw new StartupRefusal(signature, message.split('\n')[0] ?? signature);
  } finally {
    await client.end();
  }
}
