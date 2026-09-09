/**
 * The realtime gateway — the fifth of FR-EDG-002A's named services, and the smallest.
 *
 * A kitchen screen and a waiter's tablet need to learn that something changed without
 * asking every second. On the outlet network that is a push, and this is the process that
 * does the pushing.
 *
 * WHY SERVER-SENT EVENTS AND NOT WEBSOCKETS. The traffic is one-directional: the node
 * tells the screens, the screens tell the API. SSE is that shape, it is plain HTTP, it
 * reconnects on its own, and it costs no dependency — the API has carried exactly two
 * runtime dependencies since M1-D and a realtime library would be the third, on the
 * process a kitchen tablet holds open all service.
 *
 * WHAT IT PUSHES, AND WHAT IT DELIBERATELY DOES NOT. It pushes CHANGE NOTICES — "the
 * connectivity state moved", "a ticket at your station changed", "a conflict was raised" —
 * and never the row itself. A screen that learns something changed and then asks the API
 * gets the data under the same row level security every other read passes. A gateway that
 * pushed rows would be a second read path with its own scope, which is the shape of a
 * cross-outlet leak.
 *
 * IT IS THE ONE SERVICE AN OUTAGE DOES NOT TOUCH. It talks to the local database and the
 * local network. If it stops, screens fall back to asking; nothing becomes wrong, only
 * slower. That is why it holds no queue and keeps no state a restart would lose.
 */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { Client } from 'pg';
import { StructuredLogger } from '../logging';
import { withNodeContext } from './context';
import { authenticateNode } from './identity';

export interface GatewayOptions {
  databaseUrl: string;
  port: number;
  host?: string;
  logger: StructuredLogger;
  pollMs?: number;
}

interface Watermark {
  connectivity: string | null;
  pausedReason: string | null;
  openConflicts: number;
  pendingEvents: number;
  queuedPrintJobs: number;
}

async function readWatermark(client: Client, tenantId: string, outletId: string,
                             nodeId: string): Promise<Watermark> {
  // Inside a transaction, because context set outside one is gone before the next
  // statement — the watermark then read zeros forever and the screens silently stopped
  // updating. See api/src/node/context.ts.
  const rows = await withNodeContext(client, { tenantId, outletId }, async (scoped) =>
    (await scoped.query(
    `SELECT (SELECT s.connectivity::text FROM integration.sync_state s
              WHERE s.node_id = $3::uuid)                                AS connectivity,
            (SELECT s.paused_reason FROM integration.sync_state s
              WHERE s.node_id = $3::uuid)                                AS paused_reason,
            (SELECT count(*) FROM integration.conflict c
              WHERE c.node_id = $3::uuid AND c.resolution IS NULL)       AS open_conflicts,
            (SELECT count(*) FROM integration.outbox o
              WHERE o.node_id = $3::uuid AND o.state = 'pending')        AS pending_events,
            (SELECT count(*) FROM docs.print_job j
              WHERE j.tenant_id = $1::uuid AND j.outlet_id = $2::uuid
                AND j.state IN ('queued','claimed','failed'))            AS queued_print_jobs`,
    [tenantId, outletId, nodeId])).rows);
  const row = rows[0] ?? {};
  return {
    connectivity: row.connectivity ?? null,
    pausedReason: row.paused_reason ?? null,
    openConflicts: Number(row.open_conflicts ?? 0),
    pendingEvents: Number(row.pending_events ?? 0),
    queuedPrintJobs: Number(row.queued_print_jobs ?? 0),
  };
}

function changed(a: Watermark | null, b: Watermark): boolean {
  if (a === null) return true;
  return a.connectivity !== b.connectivity
      || a.pausedReason !== b.pausedReason
      || a.openConflicts !== b.openConflicts
      || a.pendingEvents !== b.pendingEvents
      || a.queuedPrintJobs !== b.queuedPrintJobs;
}

export async function start(options: GatewayOptions): Promise<{ close(): Promise<void>;
                                                                port: number }> {
  const profile = await authenticateNode(options.databaseUrl);
  const client = new Client({ connectionString: options.databaseUrl });
  await client.connect();

  const listeners = new Set<ServerResponse>();
  let last: Watermark | null = null;
  let running = true;

  const server = createServer((request: IncomingMessage, response: ServerResponse) => {
    if (request.url?.startsWith('/r/v1/stream') !== true) {
      response.writeHead(404, { 'content-type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify({ error: 'not found' }));
      return;
    }
    response.writeHead(200, {
      'content-type': 'text/event-stream; charset=utf-8',
      'cache-control': 'no-store',
      connection: 'keep-alive',
      // The screens are served from the node's own origin, so nothing else may listen.
      'access-control-allow-origin': 'null',
    });
    // Tell it what is true now, so a screen that connects mid-outage does not wait for
    // the next change to find out it is in one.
    if (last) response.write(`event: state\ndata: ${JSON.stringify(last)}\n\n`);
    listeners.add(response);
    request.on('close', () => listeners.delete(response));
  });

  await new Promise<void>((resolve) => {
    server.listen(options.port, options.host ?? '0.0.0.0', () => resolve());
  });
  options.logger.info('realtime gateway listening', {
    event: 'gateway.listening', port: options.port,
  });

  const poll = (async () => {
    while (running) {
      try {
        const now = await readWatermark(client, profile.tenantId, profile.outletId,
                                        profile.nodeId);
        if (changed(last, now)) {
          last = now;
          const frame = `event: state\ndata: ${JSON.stringify(now)}\n\n`;
          for (const listener of listeners) listener.write(frame);
        }
      } catch (error) {
        options.logger.error('gateway poll failed', {
          event: 'gateway.failed', errorClass: (error as Error).name,
        });
      }
      await new Promise((resolve) => setTimeout(resolve, options.pollMs ?? 1000));
    }
  })();

  return {
    port: options.port,
    async close() {
      running = false;
      await poll;
      for (const listener of listeners) listener.end();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await client.end();
    },
  };
}

if (require.main === module) {
  const logger = new StructuredLogger('hospitality-node-realtime', 'info');
  start({
    databaseUrl: process.env.DATABASE_URL ?? '',
    port: Number(process.env.REALTIME_PORT ?? 7102),
    host: process.env.HOST ?? '0.0.0.0',
    logger,
  }).catch((error: unknown) => {
    process.stderr.write(`REALTIME GATEWAY FAILED — ${(error as Error).message}\n`);
    process.exit(70);
  });
}
