/**
 * API security controls (FR-SEC-003, FR-SEC-005, FR-SEC-006, FR-SEC-016).
 *
 * These waited for M1-D because they are properties of an HTTP surface, and an HTTP
 * surface did not exist until now. Asserting them earlier would have produced exactly the
 * unfalsifiable green this project spent five package revisions removing.
 */
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';

/**
 * Response headers required on every response, including errors.
 *
 * Sent on error responses too: an error page is still a page, and a missing CSP on the
 * 500 is as exploitable as a missing CSP on the 200.
 */
export const REQUIRED_HEADERS: Record<string, string> = {
  'content-security-policy':
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
  'strict-transport-security': 'max-age=31536000; includeSubDomains',
  'x-frame-options': 'DENY',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'permissions-policy': 'geolocation=(), camera=(), microphone=(), payment=()',
};

export function registerSecurityHeaders(app: FastifyInstance): void {
  app.addHook('onSend', async (_request, reply, payload) => {
    for (const [name, value] of Object.entries(REQUIRED_HEADERS)) {
      reply.header(name, value);
    }
    return payload;
  });
}

/**
 * The customer surface needs to load its own script and stylesheet, which
 * `default-src 'none'` forbids — correctly, for a JSON API that serves no documents.
 *
 * Rather than loosening the policy every route inherits, the surface paths get their own,
 * applied after the M1 headers and only to them. It is still deny-by-default: no inline
 * script, no inline style, no external origin, no framing, and the only permitted
 * connect target is this same origin. A page that cannot execute an injected `<script>`
 * tag is worth more here than anywhere else in the system, because this is the surface an
 * untrusted device loads.
 *
 * The M1 header set above is untouched, and every response still carries all six.
 */
export const SURFACE_CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; " +
  "font-src 'self'; connect-src 'self'; manifest-src 'self'; " +
  "frame-ancestors 'none'; base-uri 'none'; form-action 'none'";

export function registerCustomerSurfaceHeaders(app: FastifyInstance): void {
  app.addHook('onSend', async (request, reply, payload) => {
    // The PATH, not the URL. The entry point carries the QR code as a query string, so
    // comparing the whole URL matched nothing and the document was served the API's
    // deny-everything policy — which refused the surface's own stylesheet and script.
    // The browser said so plainly; a check that only looked at the response header would
    // have called this correct.
    const path = request.url.split('?')[0] ?? '';
    // '/station' joins the list for the same reason '/' is on it: it serves a DOCUMENT
    // that loads its own stylesheet and script, and the API's deny-everything policy
    // would refuse both. Its assets come from /app/ like the customer surface's.
    if (path === '/' || path === '/station' || path.startsWith('/app/')) {
      reply.header('content-security-policy', SURFACE_CSP);
    }
    return payload;
  });
}

/**
 * Cookie attributes for any cookie this service sets (FR-SEC-005).
 *
 * The M1 surface authenticates with a bearer token in the Authorization header, which a
 * browser does not attach automatically and which therefore carries no CSRF exposure. The
 * policy is defined here anyway so that the first route to need a cookie inherits it
 * rather than inventing it, and so a reviewer can see the intended posture now.
 */
export const COOKIE_POLICY = {
  httpOnly: true,
  secure: true,
  sameSite: 'strict' as const,
  path: '/',
};

/** State-changing methods that require a CSRF token when authentication is cookie-borne. */
const STATE_CHANGING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function registerCsrfGuard(app: FastifyInstance): void {
  app.addHook('preHandler', async (request: FastifyRequest, reply: FastifyReply) => {
    if (!STATE_CHANGING.has(request.method)) return;
    // Bearer-authenticated requests are not CSRF-eligible: a browser will not attach an
    // Authorization header on a cross-site request. A cookie-authenticated request is,
    // so it must present a matching token.
    const usesCookieAuth = Boolean(request.headers.cookie) && !request.headers.authorization;
    if (!usesCookieAuth) return;

    const presented = request.headers['x-csrf-token'];
    const expected = readCookie(request.headers.cookie ?? '', 'csrf_token');
    if (!presented || !expected || presented !== expected) {
      reply.code(403);
      throw new Error('CSRF_TOKEN_INVALID');
    }
  });
}

function readCookie(header: string, name: string): string | null {
  for (const part of header.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return rest.join('=');
  }
  return null;
}

/**
 * Rate limiting for the authentication, search and export surfaces (FR-SEC-016).
 *
 * IN-PROCESS ONLY. This limits one instance. It is not distributed production rate
 * limiting, it does not survive a restart, and running two instances doubles the
 * effective allowance. Distributed enforcement is M6 infrastructure. The readiness
 * payload reports this as `singleInstance` so no operator can mistake it for more.
 */
export interface RateLimitRule {
  prefix: string;
  limit: number;
  windowMs: number;
}

export const RATE_LIMIT_RULES: RateLimitRule[] = [
  { prefix: '/v1/auth', limit: 10, windowMs: 60_000 },
  { prefix: '/v1/search', limit: 30, windowMs: 60_000 },
  { prefix: '/v1/export', limit: 5, windowMs: 60_000 },
];

export class InProcessRateLimiter {
  private readonly hits = new Map<string, number[]>();

  constructor(private readonly rules: RateLimitRule[] = RATE_LIMIT_RULES) {}

  ruleFor(path: string): RateLimitRule | null {
    return this.rules.find((rule) => path.startsWith(rule.prefix)) ?? null;
  }

  /** Returns true when the caller is inside its allowance. */
  admit(key: string, rule: RateLimitRule, now = Date.now()): boolean {
    const window = (this.hits.get(key) ?? []).filter((at) => now - at < rule.windowMs);
    if (window.length >= rule.limit) {
      this.hits.set(key, window);
      return false;
    }
    window.push(now);
    this.hits.set(key, window);
    return true;
  }

  reset(): void {
    this.hits.clear();
  }
}

export function registerRateLimits(app: FastifyInstance, limiter: InProcessRateLimiter): void {
  app.addHook('onRequest', async (request: FastifyRequest, reply: FastifyReply) => {
    const rule = limiter.ruleFor(request.url);
    if (!rule) return;
    const key = `${rule.prefix}|${request.ip}`;
    if (!limiter.admit(key, rule)) {
      reply.code(429);
      reply.header('retry-after', String(Math.ceil(rule.windowMs / 1000)));
      throw new Error('RATE_LIMIT_EXCEEDED');
    }
  });
}
