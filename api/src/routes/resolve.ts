/**
 * Where a customer's browser should go, given how their phone actually resolved the name.
 *
 * FR-EDG-004B, FR-EDG-021, FR-EDG-028. This is the first thing a QR scan reaches and the
 * only thing that runs before a session exists, so it takes no credential — a guest who
 * has not yet been told where to go cannot be asked to authenticate to find out.
 *
 * IT IS REGISTERED ON BOTH PROFILES, and that is the whole point of same-QR. The name in
 * the QR resolves to the cloud from the street and to the node in the dining room; both
 * answers must be able to say what to do. A cloud-only deployment answering 404 here would
 * do to this what it did to the connectivity banner — put a resource error in every guest's
 * browser — and the honest answer differs between them rather than being absent from one.
 *
 * WHAT THE SERVER KNOWS AND WHAT THE CLIENT CLAIMS ARE KEPT APART.
 *
 * The server knows which horizon it IS: a node process serves the LAN, a cloud process
 * does not, and that is not a matter of opinion. It also knows whether the cloud is
 * reachable, because it is either the cloud or it is a node holding a lease.
 *
 * The client knows things the server cannot see — whether Private DNS is on, whether it
 * just joined the network, whether it asked for both address families. Those arrive as a
 * CLAIM, and a claim is exactly as trustworthy as its consequences. Here the worst a false
 * claim achieves is worse advice for the phone that made it: it cannot reach another
 * tenant's data, cannot skip the certificate check, and cannot produce a bypass, because
 * edge.resolve_customer_entry() has no outcome for one. So the claim is taken at face
 * value and the reason it is safe to is written here rather than assumed.
 */
import type { FastifyInstance } from 'fastify';
import type { Database } from '../db';
import type { StructuredLogger } from '../logging';
import { withNodeContext } from '../node/context';

export interface ResolveDependencies {
  db: Database;
  logger: StructuredLogger;
  /**
   * Set when this process is a node. A node serves the LAN horizon and knows whether it
   * currently has a path to the cloud; a cloud process is the cloud.
   */
  node?: { tenantId: string; outletId: string; nodeId: string } | undefined;
}

const CONDITIONS = [
  'lan_resolver',
  'cached_public_answer',
  'encrypted_dns',
  'dual_stack',
  'public_internet',
] as const;
type Condition = (typeof CONDITIONS)[number];

const LOCALES = ['en', 'am', 'ar'] as const;
type Locale = (typeof LOCALES)[number];

function condition(value: unknown): Condition | null {
  return typeof value === 'string' && (CONDITIONS as readonly string[]).includes(value)
    ? (value as Condition)
    : null;
}

function locale(value: unknown): Locale {
  // Not a refusal. A guest who asks in a language nobody configured still needs telling
  // where to go, and English is what every tenant has.
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value)
    ? (value as Locale)
    : 'en';
}

function secondsSinceJoin(value: unknown): number {
  const n = typeof value === 'string' ? Number.parseInt(value, 10) : Number.NaN;
  // A MISSING OR NONSENSE VALUE IS TREATED AS "JUST ARRIVED", which is the conservative
  // reading: it sends a cached-answer device to the cloud or to "wait a minute" rather
  // than to a node its resolver cannot yet find. Guessing the other way would produce a
  // page that does not load and no explanation.
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.min(n, 86_400);
}

export function registerResolveRoutes(app: FastifyInstance, deps: ResolveDependencies): void {
  app.get<{
    Params: { tenantId: string; outletId: string };
    Querystring: { condition?: string; sinceJoin?: string; locale?: string };
  }>('/c/v1/:tenantId/:outletId/resolve', async (request, reply) => {
    const { tenantId, outletId } = request.params;
    const asked = condition(request.query.condition);
    if (!asked) {
      reply.code(400);
      return { error: `condition must be one of: ${CONDITIONS.join(', ')}` };
    }

    // THE SERVER OVERRIDES THE CLIENT ON THE ONE THING IT ACTUALLY KNOWS. If this process
    // is the node for this outlet, the request arrived over the LAN — whatever the client
    // believes about its own DNS, it demonstrably found the node. Trusting the claim over
    // the evidence would send a guest who is already here somewhere else.
    const arrivedAtTheNode =
      deps.node !== undefined &&
      deps.node.tenantId === tenantId &&
      deps.node.outletId === outletId;
    const effective: Condition = arrivedAtTheNode ? 'lan_resolver' : asked;

    // A NODE ANSWERING THIS IS A NODE THAT WAS REACHED, and the question the resolver asks
    // is whether the CLOUD can be. A cloud process answering is proof of its own.
    const cloudReachable = deps.node === undefined || (await nodeSeesCloud(deps, tenantId, outletId));

    try {
      const row = await deps.db.withoutContext((client) =>
        // withNodeContext, not two bare set_config calls. Outside a transaction they are
        // silent no-ops and row level security then matches nothing — the defect that
        // produced four different plausible wrong answers in M5a and a fifth in its test
        // suite. The scope here is the outlet in the path, which is the outlet being
        // asked about whether or not this process is its node.
        withNodeContext(client, { tenantId, outletId }, async (scoped) => {
          const { rows } = await scoped.query(
            `SELECT outcome::text, endpoint, guidance, phrase_code
               FROM edge.resolve_customer_entry($1::uuid, $2::uuid, $3::edge.client_condition,
                                                $4::integer, $5::menu.customer_locale, $6::boolean)`,
            [
              tenantId,
              outletId,
              effective,
              secondsSinceJoin(request.query.sinceJoin),
              locale(request.query.locale),
              cloudReachable,
            ],
          );
          return rows[0];
        }),
      );

      // Logged because FR-EDG-028 is an ACCEPTANCE requirement: "accepted against real
      // client behaviour" means somebody has to be able to count what real clients did.
      // No guest identifier — the outlet and the condition are what a pilot needs.
      deps.logger.info('customer entry resolved', {
        correlationId: request.id,
        event: 'resolve.answered',
        outletId,
        claimed: asked,
        effective,
        cloudReachable,
        outcome: row.outcome,
      });

      return {
        outcome: row.outcome,
        endpoint: row.endpoint,
        guidance: row.guidance,
        phraseCode: row.phrase_code,
        // Stated so the caller does not have to infer it from a null endpoint, and so a
        // surface cannot render a "continue anyway" affordance by reading the absence of
        // something as permission.
        mayProceedToAnUntrustedEndpoint: false,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('OUTLET_HOSTNAME_UNDECLARED')) {
        // NOT AN ERROR THE GUEST CAUSED, and not one they can act on. An outlet with no
        // declared hostname has no LAN journey at all, so the cloud is the only place to
        // be, and on a cloud process this response is being served from it.
        reply.code(404);
        return { error: 'this outlet has no local journey configured' };
      }
      throw error;
    }
  });
}

/**
 * Whether this node currently has a path to the cloud.
 *
 * READ FROM THE LEASE RATHER THAN BY MAKING A REQUEST. FR-EDG-023's lease is already the
 * answer to "is the cloud there", it is bidirectional, and it expires on a clock rather
 * than on a cached boolean. A fresh HTTP probe from inside a request handler would add a
 * network round trip to the first thing a guest's phone does, and would answer a slightly
 * different question — whether the cloud is reachable from this process right now — which
 * is the question the lease exists to stop everybody asking separately.
 */
async function nodeSeesCloud(
  deps: ResolveDependencies,
  tenantId: string,
  outletId: string,
): Promise<boolean> {
  if (!deps.node) return true;
  try {
    return await deps.db.withoutContext((client) =>
      withNodeContext(client, { tenantId, outletId }, async (scoped) => {
        const { rows } = await scoped.query(
          'SELECT edge.may_forward($1::uuid, $2::uuid) AS ok',
          [tenantId, deps.node!.nodeId],
        );
        return rows.length > 0 && rows[0].ok === true;
      }),
    );
  } catch {
    // A NODE THAT CANNOT ANSWER THE QUESTION IS A NODE THAT SHOULD NOT CLAIM THE CLOUD IS
    // THERE. Saying "reachable" on an error would send a guest to an address that may not
    // answer; saying "not reachable" sends them to the node, which is where they already
    // are, or to an instruction. The safe direction is not symmetric here.
    return false;
  }
}
