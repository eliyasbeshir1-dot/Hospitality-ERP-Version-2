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

  app.get<{ Params: { '*': string } }>('/app/*', async (request, reply) => {
    const file = loaded.get(request.params['*']);
    if (!file) { reply.code(404); return { error: 'not found' }; }
    reply.type(file.type);
    return file.body;
  });
}
