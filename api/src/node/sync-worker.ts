/**
 * The synchronization worker — one of the five services FR-EDG-002A names.
 *
 * It does four things, in this order, forever:
 *
 *   1. recovers anything that was in flight when the process last stopped
 *   2. asks the cloud what protocol it speaks, and pauses if the answer is out of range
 *   3. offers the cloud whatever may travel, in dependency order
 *   4. acknowledges what the cloud accepted, moving the cursor
 *
 * THE ORDER IS THE DESIGN. Recovery comes first because a worker that claimed a batch and
 * died left rows marked in-flight that nothing else will ever release; if it started by
 * claiming, those rows would sit forever behind a queue that looks busy. Compatibility
 * comes before offering because sending events a peer cannot parse is how a cloud ends up
 * with half a bill.
 *
 * WHAT AN OUTAGE DOES TO THIS LOOP: nothing except make step 2 throw. The worker records
 * local continuity, sleeps, and tries again. It does not exit, does not retry in a tight
 * loop, and does not touch business data — the outlet is serving customers and this
 * process has no opinion about that.
 *
 * IT NEVER ACKNOWLEDGES WHAT THE CLOUD DID NOT NAME. The exchange returns the ids it
 * accepted; anything absent stays pending and is offered again next round. An
 * acknowledge-everything-we-sent worker loses exactly the events that were in flight when
 * the link dropped, which is the only moment any of this matters.
 */
import { Client } from 'pg';
import { StructuredLogger } from '../logging';
import { withNodeContext } from './context';
import { authenticateNode } from './identity';
import { CloudUnreachable, cloudLinkFrom, type CloudLink } from './link';

const PROTOCOL = 'sync.event';

export interface WorkerOptions {
  databaseUrl: string;
  link: CloudLink;
  logger: StructuredLogger;
  batchSize?: number;
  /** How long to wait between rounds. Short enough to feel live, long enough to be idle. */
  intervalMs?: number;
}

export async function runOneRound(
  client: Client,
  profile: { tenantId: string; outletId: string; nodeId: string },
  link: CloudLink,
  logger: StructuredLogger,
  batchSize: number,
): Promise<{ offered: number; accepted: number; connected: boolean }> {
  const { tenantId, nodeId } = profile;

  // 1. Anything in flight when we last stopped belongs back in the queue. Inside a
  // transaction with context, because context set outside one does not survive to the
  // next statement — see api/src/node/context.ts for what that cost.
  await withNodeContext(client, { tenantId, outletId: profile.outletId }, async (scoped) => {
    await scoped.query('SELECT integration.recover_in_flight($1::uuid, $2::uuid)',
                       [tenantId, nodeId]);
  });

  // 2. Can we talk to them at all, and do we speak the same thing?
  let acknowledgement;
  try {
    acknowledgement = await link.exchange({ events: [] });
  } catch (error) {
    if (error instanceof CloudUnreachable) {
      await withNodeContext(client, { tenantId, outletId: profile.outletId }, (scoped) =>
        scoped.query(
          `SELECT integration.set_connectivity($1::uuid, $2::uuid,
                    'local_continuity'::edge.connectivity_state)`,
          [tenantId, nodeId]));
      logger.info('cloud unreachable; the outlet continues', {
        event: 'sync.local_continuity', endpoint: link.endpoint,
      });
      return { offered: 0, accepted: 0, connected: false };
    }
    throw error;
  }

  const compatible = await withNodeContext(client,
    { tenantId, outletId: profile.outletId },
    async (scoped) => (await scoped.query(
      'SELECT integration.check_peer_compatibility($1::uuid, $2::uuid, $3, $4) AS ok',
      [tenantId, nodeId, PROTOCOL, acknowledgement.protocolVersion])).rows);
  if (!compatible[0]?.ok) {
    // FR-EDG-012. Paused, recorded, and local service is untouched.
    logger.warn('peer protocol incompatible; synchronization paused', {
      event: 'sync.paused', peerVersion: String(acknowledgement.protocolVersion),
    });
    return { offered: 0, accepted: 0, connected: true };
  }

  // 3. What may travel — the claim refuses a child whose parent is unacknowledged.
  const batch = await withNodeContext(client, { tenantId, outletId: profile.outletId },
    async (scoped) => {
      await scoped.query(
        `SELECT integration.set_connectivity($1::uuid, $2::uuid,
                  'cloud_connected'::edge.connectivity_state)`,
        [tenantId, nodeId]);
      return (await scoped.query(
        `SELECT event_id, sequence::text AS sequence, subject::text, subject_id,
                event_kind, payload, occurred_at
           FROM integration.claim_outbox_batch($1::uuid, $2::uuid, $3)`,
        [tenantId, nodeId, batchSize])).rows;
    });
  if (batch.length === 0) return { offered: 0, accepted: 0, connected: true };

  const sent = await link.exchange({
    events: batch.map((row: Record<string, unknown>) => ({
      eventId: row.event_id as string,
      sequence: row.sequence as string,
      subject: row.subject as string,
      eventKind: row.event_kind as string,
      payload: row.payload,
      occurredAt: (row.occurred_at as Date).toISOString(),
    })),
  });

  // 4. Only what they named.
  await withNodeContext(client, { tenantId, outletId: profile.outletId }, async (scoped) => {
    for (const eventId of sent.accepted) {
      await scoped.query('SELECT integration.acknowledge_outbox($1::uuid, $2::uuid, $3::uuid)',
                         [tenantId, nodeId, eventId]);
    }
  });

  logger.info('synchronization round complete', {
    event: 'sync.round', offered: batch.length, accepted: sent.accepted.length,
  });
  return { offered: batch.length, accepted: sent.accepted.length, connected: true };
}

export async function start(options: WorkerOptions): Promise<{ stop(): Promise<void> }> {
  const profile = await authenticateNode(options.databaseUrl);
  const client = new Client({ connectionString: options.databaseUrl });
  await client.connect();

  const interval = options.intervalMs ?? 2000;
  const batchSize = options.batchSize ?? 100;
  let running = true;

  const loop = (async () => {
    while (running) {
      try {
        await runOneRound(client, profile, options.link, options.logger, batchSize);
      } catch (error) {
        // A round that fails is a round. The worker is the thing that must not stop,
        // because the queue it drains is what an outage fills.
        options.logger.error('synchronization round failed', {
          event: 'sync.failed', errorClass: (error as Error).name,
        });
      }
      await new Promise((resolve) => setTimeout(resolve, interval));
    }
  })();

  return {
    async stop() {
      running = false;
      await loop;
      await client.end();
    },
  };
}

if (require.main === module) {
  const databaseUrl = process.env.DATABASE_URL ?? '';
  const logger = new StructuredLogger('hospitality-node-sync', 'info');
  start({ databaseUrl, link: cloudLinkFrom(), logger }).catch((error: unknown) => {
    process.stderr.write(`SYNC WORKER FAILED — ${(error as Error).message}\n`);
    process.exit(70);
  });
}
