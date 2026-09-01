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
] as const;

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

  app.get('/', async (_request, reply) => {
    const file = loaded.get('index.html');
    if (!file) { reply.code(503); return { error: 'surface not built' }; }
    reply.type(file.type);
    return file.body;
  });

  // The station surface's document. A separate entry point from the customer surface's
  // '/', because they are separate surfaces with separate audiences: nothing a guest can
  // reach serves this, and it carries the same locked-down policy.
  app.get('/station', async (_request, reply) => {
    const file = loaded.get('station.html');
    if (!file) { reply.code(503); return { error: 'surface not built' }; }
    reply.type(file.type);
    return file.body;
  });

  // The waiter surface's document. Third entry point, and for the same reason again:
  // a screen a guest could reach by scanning a QR code would be a defect, not a feature.
  app.get('/waiter', async (_request, reply) => {
    const file = loaded.get('waiter.html');
    if (!file) { reply.code(503); return { error: 'surface not built' }; }
    reply.type(file.type);
    return file.body;
  });

  app.get<{ Params: { '*': string } }>('/app/*', async (request, reply) => {
    const file = loaded.get(request.params['*']);
    if (!file) { reply.code(404); return { error: 'not found' }; }
    reply.type(file.type);
    return file.body;
  });
}
