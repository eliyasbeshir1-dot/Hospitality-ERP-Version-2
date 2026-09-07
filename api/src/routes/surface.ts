/**
 * Serving the customer surface's files.
 *
 * Written by hand rather than by adding a static-file plugin. The API has carried two
 * runtime dependencies since M1-D — fastify and pg — and the surface an untrusted device
 * loads is the wrong place to widen that. What a static server has to get right is a
 * short list, and all of it is here where it can be read:
 *
 *   - no path traversal: the request never becomes a path. It is looked up in a map of
 *     files decided at startup, so "../../etc/passwd" is not a path that escapes, it is a
 *     key that is not in the map.
 *   - correct content types, with charset, so a UTF-8 Amharic string is not decoded as
 *     cp1252 by a browser guessing.
 *   - no directory listing, because there is no directory walk at request time.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { FastifyInstance } from 'fastify';

const TYPES: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

/** Every file the surface is allowed to serve. Anything not here does not exist. */
const FILES = [
  'index.html',
  'app.css',
  'app.js',
  'manifest.webmanifest',
  // The station surface (M3-B). Separate files, not a mode of the customer surface: a
  // kitchen screen reachable by scanning a table's QR code would be a defect.
  'station.html',
  'station.css',
  'station.js',
  // The waiter surface (M3-D). Third entry point, same reasoning as the second.
  'waiter.html',
  'waiter.css',
  'waiter.js',
  // The till (OP-B). Fourth entry point, same reasoning a fourth time: a cashier screen a
  // guest could reach by scanning a table would be a defect, not a convenience.
  'cashier.html',
  'cashier.css',
  'cashier.js',
] as const;

/**
 * EVERY DOCUMENT THIS SERVICE SERVES, AND THE ONE PLACE THAT FACT IS WRITTEN.
 *
 * Each entry is a separate surface with a separate audience and separate authentication:
 * a guest, a kitchen, a waiter and a cashier. A till reachable by scanning a table's QR
 * code would be a defect, not a convenience, which is why none of these is a mode of
 * another.
 *
 * IT IS EXPORTED BECAUSE THE SECURITY LAYER NEEDS THE SAME LIST. A document loads its own
 * stylesheet and script, so it must be served the surface content-security-policy rather
 * than the API's deny-everything one. That list used to be typed out again in
 * security.ts, and the comment beside it recorded that a surface which "had to be listed
 * somewhere and was not would be served the API's deny-everything policy and would render
 * as a blank page with two console errors, which is how this was found the first time."
 *
 * It was found that way a fourth time when the till was added, because a hand-maintained
 * copy of a list is a copy that goes stale. Now there is one list: registering a document
 * here is what puts it in the policy, and forgetting is no longer possible.
 */
export const SURFACE_DOCUMENTS: readonly (readonly [string, string])[] = [
  ['/', 'index.html'],
  ['/station', 'station.html'],
  ['/waiter', 'waiter.html'],
  ['/cashier', 'cashier.html'],
] as const;

/** The paths that must carry the surface CSP, derived from the documents themselves. */
export const SURFACE_DOCUMENT_PATHS: readonly string[] =
  SURFACE_DOCUMENTS.map(([path]) => path);

export function registerSurfaceRoutes(app: FastifyInstance, publicDir: string): void {
  const loaded = new Map<string, { body: Buffer; type: string }>();
  for (const name of FILES) {
    const extension = name.slice(name.lastIndexOf('.'));
    try {
      loaded.set(name, {
        body: readFileSync(join(publicDir, name)),
        type: TYPES[extension] ?? 'application/octet-stream',
      });
    } catch {
      // A missing surface file is a build fault, and the readiness endpoint is where a
      // fault belongs. Refusing to start would take the API down for a missing
      // stylesheet.
    }
  }

  for (const [path, document] of SURFACE_DOCUMENTS) {
    app.get(path, async (_request, reply) => {
      const file = loaded.get(document);
      if (!file) { reply.code(503); return { error: 'surface not built' }; }
      reply.type(file.type);
      return file.body;
    });
  }

  app.get<{ Params: { '*': string } }>('/app/*', async (request, reply) => {
    const file = loaded.get(request.params['*']);
    if (!file) { reply.code(404); return { error: 'not found' }; }
    reply.type(file.type);
    return file.body;
  });
}
