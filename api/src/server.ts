/**
 * Service entry point.
 *
 * The order below is the requirement, not a preference (FR-OPS-001): environment,
 * prerequisites and credential privilege are all validated BEFORE the HTTP listener
 * opens and therefore before the process can make any healthy or startup claim. A service
 * that binds first and validates second has already told an orchestrator it is fine.
 */
import { join } from 'node:path';
import Fastify from 'fastify';
import { Database } from './db';
import {
  assertRuntimePrerequisites, assertUnprivileged, readEnvironment, readRoleFacts,
  StartupRefusal,
} from './env';
import { StructuredLogger } from './logging';
import { InMemoryObservability, type ObservabilityProvider } from './observability';
import { registerApiRoutes } from './routes/api';
import { registerAuthRoutes } from './routes/auth';
import { guestContext, registerCustomerRoutes } from './routes/customer';
import { registerServiceRoutes } from './routes/service';
import { registerBillingRoutes } from './routes/billing';
import { registerPaymentRoutes } from './routes/payments';
import { registerDocumentRoutes } from './routes/documents';
import { registerReportRoutes } from './routes/reports';
import { registerStaffRoutes } from './routes/staff';
import { registerStationRoutes } from './routes/station';
import { registerSurfaceRoutes } from './routes/surface';
import { registerHealthRoutes } from './routes/health';
import { registerCloudConnectivityRoute, registerNodeRoutes } from './routes/node';
import { registerResolveRoutes } from './routes/resolve';
import { authenticateNode, isNodeProfile, type NodeProfile } from './node/identity';
import {
  InProcessRateLimiter, registerCsrfGuard, registerCustomerSurfaceHeaders,
  registerRateLimits, registerSecurityHeaders,
} from './security';

export async function start(): Promise<{ close(): Promise<void>; port: number }> {
  // ---- 1. Environment, before anything else -----------------------------------
  const env = readEnvironment();
  const logger = new StructuredLogger(env.serviceName, env.logLevel as never);

  assertRuntimePrerequisites();

  // ---- 2. Credential privilege, before the listener opens ----------------------
  const roleFacts = await readRoleFacts(env.databaseUrl);
  assertUnprivileged(roleFacts);

  logger.info('environment validated', {
    event: 'startup.validated',
    role: roleFacts.currentUser,
    environment: env.environmentName,
  });

  // ---- 2b. If this is an outlet node, prove which outlet ------------------------
  //
  // FR-CFG-001E: the node starts only with the correct outlet identity. Before the
  // listener opens, for the same reason the privilege check is: a node that binds first
  // and checks its outlet second has already told a waiter's tablet it is the right node.
  let nodeProfile: NodeProfile | null = null;
  if (isNodeProfile()) {
    nodeProfile = await authenticateNode(env.databaseUrl);
    logger.info('node identity proved', {
      event: 'startup.node',
      node: nodeProfile.nodeCode,
      outletId: nodeProfile.outletId,
    });
  }

  // ---- 3. Only now is it safe to build the service -----------------------------
  const db = Database.fromUrl(env.databaseUrl);
  const observability: ObservabilityProvider = new InMemoryObservability();
  const app = Fastify({ logger: false, disableRequestLogging: true, trustProxy: false });

  registerSecurityHeaders(app);
  registerCustomerSurfaceHeaders(app);
  registerCsrfGuard(app);
  registerRateLimits(app, new InProcessRateLimiter());

  app.addHook('onRequest', async (request) => {
    (request as { span?: unknown }).span = observability.startSpan('http.request', {
      method: request.method, route: request.url,
    });
  });

  app.addHook('onResponse', async (request, reply) => {
    const span = (request as { span?: { setAttribute(k: string, v: string | number): void; end(): void } }).span;
    span?.setAttribute('status', reply.statusCode);
    span?.end();
    observability.counter('http.response', 1, {
      method: request.method, status: String(reply.statusCode),
    });
    logger.info('request completed', {
      correlationId: request.id,
      event: 'http.request',
      method: request.method,
      route: request.url,
      status: reply.statusCode,
    });
  });

  app.setErrorHandler((error: Error & { statusCode?: number; validation?: unknown }, request, reply) => {
    // A schema rejection is the client's fault, not the server's. Fastify sets
    // statusCode 400 on it; taking only reply.statusCode turned every validation
    // failure into a 500, which both misreports the fault and hides the refusal.
    const status = error.statusCode
      ?? (reply.statusCode >= 400 ? reply.statusCode : 500);
    logger.error('request failed', {
      correlationId: request.id,
      event: 'http.error',
      errorClass: error.name,   // classification only, never error.message
      route: request.url,
      status,
    });
    reply.code(status);
    // The client is told the classification, never the underlying message, which could
    // carry a value from a failing statement.
    return reply.send({
      error: status >= 500 ? 'internal error'
           : error.validation ? 'request failed validation'
           : 'request refused',
    });
  });

  registerHealthRoutes(app, {
    db, roleFacts, serviceName: env.serviceName,
    environmentName: env.environmentName, startedAt: new Date(),
  });
  registerApiRoutes(app, { db, logger });
  // Before the staff surfaces, because it is what produces the credential they carry.
  registerAuthRoutes(app, { db, logger });
  registerCustomerRoutes(app, { db, logger });
  registerStationRoutes(app, { db, logger });
  registerStaffRoutes(app, { db, logger });
  registerServiceRoutes(app, { db, logger, asGuest: guestContext({ db, logger }) });
  registerBillingRoutes(app, { db, logger, asGuest: guestContext({ db, logger }) });
  registerPaymentRoutes(app, { db, logger });
  registerDocumentRoutes(app, { db, logger });
  registerReportRoutes(app, { db, logger });
  // The node's own routes only when this process IS one: the cloud has no node to
  // describe, and routes that answered about one would be answering about nothing.
  //
  // Connectivity is the exception, and it is registered EITHER WAY. The four surfaces ask
  // for it on every deployment, and a cloud-only one that answered 404 put a resource
  // error in every guest's browser forever — which is what tests/m2c saw. The cloud's
  // answer is true rather than a placeholder: a browser that reached this service reached
  // the cloud.
  if (nodeProfile) {
    registerNodeRoutes(app, { db, logger, profile: nodeProfile });
  } else {
    registerCloudConnectivityRoute(app);
  }
  // ON BOTH PROFILES, WHICH IS WHAT SAME-QR MEANS. The name in the QR resolves to the
  // cloud from the street and to the node in the dining room, and both answers have to be
  // able to say where to go. The answers differ — a node knows the request reached the
  // LAN — and the difference is the mechanism, not an inconsistency.
  registerResolveRoutes(app, {
    db,
    logger,
    node: nodeProfile
      ? { tenantId: nodeProfile.tenantId, outletId: nodeProfile.outletId, nodeId: nodeProfile.nodeId }
      : undefined,
  });
  // The compiled surface sits beside the compiled server, so one build produces both and
  // there is no second artefact to deploy or forget.
  registerSurfaceRoutes(app, join(__dirname, 'public'));

  app.get('/metrics', async () => observability.snapshot());

  await app.listen({ port: env.port, host: env.host });
  logger.info('service listening', { event: 'startup.listening', port: env.port });

  return {
    port: env.port,
    async close() {
      await app.close();
      await db.close();
    },
  };
}

if (require.main === module) {
  start().catch((error: unknown) => {
    if (error instanceof StartupRefusal) {
      // Loudly, on stderr, with the signature an operator can search for — and without
      // the credential that caused it.
      process.stderr.write(`STARTUP REFUSED — ${error.message}\n`);
      process.exit(78);   // EX_CONFIG
    }
    process.stderr.write(`STARTUP FAILED — ${(error as Error).name}\n`);
    process.exit(70);     // EX_SOFTWARE
  });
}
