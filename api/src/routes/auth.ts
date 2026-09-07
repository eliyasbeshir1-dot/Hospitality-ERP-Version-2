/**
 * The route that turns a credential into a session.
 *
 * This is the step M1-B did not build. identity held credential, auth_attempt,
 * auth_lockout, otp_transmission, recovery_request and session, and every one of them was
 * proved — and nothing turned a presented secret into a row in identity.session, so every
 * staff token in this build existed because a fixture inserted one. The whole of the
 * decision lives in identity.authenticate_credential(); this file derives a key, calls it,
 * and formats the answer.
 *
 * WHY THIS PATH IS NOT UNDER /s/v1. Every /s/ route authenticates a staff session, and
 * there is no session here yet — that is the point of the route. It sits under /v1/auth,
 * which is also where the rate limiter defined at M1-D has been waiting: RATE_LIMIT_RULES
 * carries { prefix: '/v1/auth', limit: 10 } and matches with startsWith, so a route under
 * /s/v1/auth would have silently inherited nothing. FR-AUTH-007 asks for rate limits on
 * the authentication surface and they were built before the surface was.
 *
 * WHY THE KEY DERIVATION HAPPENS HERE. No extension in this database provides scrypt or
 * Argon2id; pgcrypto has neither and is not installed. Node's crypto.scrypt is native and
 * needs no dependency, so the service stretches and the database decides. That is the same
 * split db.ts already uses for session tokens, where Node computes sha256(token) and
 * identity.establish_session_context compares it.
 *
 * WHAT THE SERVICE MAY NOT DECIDE. It does not decide whether the secret matched, whether
 * the membership is live, whether a quick PIN is on a trusted terminal, or what strength
 * the session carries. It hands over 32 bytes and the database settles all of it in one
 * transaction, so a route that wanted to skip a check would have to not call the function.
 */
import { createHash, randomBytes, scrypt as scryptCallback } from 'node:crypto';
import { promisify } from 'node:util';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { ContextRefused, signatureOf, type Database } from '../db';
import type { StructuredLogger } from '../logging';

const scrypt = promisify(scryptCallback) as (
  secret: string, salt: Buffer, keylen: number,
  options: { N: number; r: number; p: number; maxmem: number },
) => Promise<Buffer>;

export interface AuthDependencies {
  db: Database;
  logger: StructuredLogger;
}

/** The derived key is 32 bytes because identity.credential says a digest is 32 bytes. */
const DERIVED_KEY_BYTES = 32;

/**
 * The parameters a NEW credential is written under.
 *
 * Read by the seed and by any future credential writer, and deliberately not read when
 * VERIFYING: verification uses the parameters stored on the row, which is what lets this
 * constant be raised later without invalidating a credential already written under a
 * lower one. The schema enforces the floor; this is the current setting above it.
 */
export const CURRENT_KDF = {
  algorithm: 'scrypt' as const,
  cost: 16384,          // N — memory hardness, 16 MiB at r=8
  blockSize: 8,         // r
  parallelization: 1,   // p
};

/** scrypt needs to be told it may use the memory its own parameters imply. */
function maxmemFor(cost: number, blockSize: number): number {
  return Math.max(32 * 1024 * 1024, 256 * cost * blockSize * 2);
}

export async function deriveKey(
  secret: string,
  salt: Buffer,
  params: { cost: number; blockSize: number; parallelization: number },
): Promise<Buffer> {
  return scrypt(secret, salt, DERIVED_KEY_BYTES, {
    N: params.cost, r: params.blockSize, p: params.parallelization,
    maxmem: maxmemFor(params.cost, params.blockSize),
  });
}

/** The token carries its tenant and outlet in a non-secret prefix, as db.ts expects. */
function mintToken(tenantId: string, outletId: string): { token: string; digest: string } {
  const token = `${tenantId}.${outletId}.${randomBytes(32).toString('base64url')}`;
  return { token, digest: createHash('sha256').update(token).digest('hex') };
}

interface LoginBody {
  tenantId?: string;
  outletId?: string;
  channel?: 'phone' | 'email';
  channelValue?: string;
  kind?: 'password' | 'quick_pin' | 'otp';
  secret?: string;
  deviceId?: string;
}

export function registerAuthRoutes(app: FastifyInstance, deps: AuthDependencies): void {
  /**
   * FR-AUTH-001. Verified phone or email, password or OTP, and a quick PIN for re-entry.
   *
   * ONE REFUSAL, WHATEVER WENT WRONG. A caller is told 'authentication failed' whether the
   * channel is unknown, the secret is wrong, the credential is revoked or the membership
   * is gone. The database distinguishes all of those and says which in its own signature;
   * the log records that signature and the response does not, because a login endpoint
   * that reports WHY it refused is an oracle for the thing it is protecting. The two
   * exceptions are deliberate: a lockout and a rate limit are told plainly, because a
   * caller who is locked out needs to know to stop rather than to try harder.
   */
  app.post<{ Body: LoginBody }>('/v1/auth/login', async (request, reply) => {
    const body = request.body ?? {};
    const { tenantId, outletId, channel, channelValue, kind, secret, deviceId } = body;

    if (!tenantId || !outletId || !channel || !channelValue || !kind || !secret) {
      reply.code(400);
      return { error: 'tenantId, outletId, channel, channelValue, kind and secret are required' };
    }
    if (channel !== 'phone' && channel !== 'email') {
      reply.code(400);
      return { error: 'channel must be phone or email' };
    }
    if (kind !== 'password' && kind !== 'quick_pin' && kind !== 'otp') {
      reply.code(400);
      return { error: 'kind must be password, quick_pin or otp' };
    }

    try {
      return await deps.db.withoutContext(async (client) => {
        // The salt and the parameters this credential was written under. Answered for a
        // channel with no credential too, with a stable decoy, so the work below costs
        // the same either way.
        const challenge = await client.query(
          `SELECT salt, digest_algorithm, kdf_params
             FROM identity.credential_key_derivation($1::uuid, $2::identity.channel_kind,
                                                     $3::text, $4::identity.credential_kind,
                                                     $5::uuid)`,
          // The outlet is passed because a quick PIN is outlet-scoped: without it the
          // credential is out of scope, the lookup finds nothing and the decoy comes
          // back — a correct PIN refused as though it were wrong.
          [tenantId, channel, channelValue, kind, outletId],
        );
        const row = challenge.rows[0] as
          | { salt: Buffer | null; digest_algorithm: string;
              kdf_params: { cost: number; blockSize: number; parallelization: number } | null }
          | undefined;
        if (!row) {
          reply.code(401);
          return { error: 'authentication failed' };
        }

        // AN OTP IS NOT STRETCHED, AND THAT IS NOT AN OVERSIGHT. It is a single-use random
        // value with a short life, so there is no low-entropy secret for a KDF to protect;
        // sha-256 of it is what the schema stores and what M1-B proved. The branch is here
        // rather than hidden in a helper because the asymmetry is the interesting part.
        let derived: Buffer;
        if (row.digest_algorithm === 'scrypt') {
          const params = row.kdf_params ?? CURRENT_KDF;
          derived = await deriveKey(secret, row.salt ?? randomBytes(16), params);
        } else if (row.digest_algorithm === 'sha-256') {
          derived = createHash('sha256').update(secret).digest();
        } else {
          // A stored algorithm this build cannot compute is refused, never guessed at.
          deps.logger.warn('unsupported credential algorithm', {
            correlationId: request.id, event: 'auth.algorithm_unsupported',
            errorClass: 'CREDENTIAL_ALGORITHM_UNSUPPORTED',
          });
          reply.code(401);
          return { error: 'authentication failed' };
        }

        const { token, digest } = mintToken(tenantId, outletId);
        const issued = await client.query(
          `SELECT session_id, user_account_id, outlet_id,
                  established_with::text AS established_with, refusal
             FROM identity.authenticate_credential(
                    $1::uuid, $2::identity.channel_kind, $3::text,
                    $4::identity.credential_kind, $5::bytea, decode($6, 'hex'),
                    $7::uuid, $8::uuid)`,
          [tenantId, channel, channelValue, kind, derived, digest, deviceId ?? null, outletId],
        );
        // A REFUSAL COMES BACK AS A ROW, NOT AS AN EXCEPTION, so that the failed attempt
        // the function recorded survives — an exception would roll the attempt back with
        // it and the lockout could never count to five. The reason reaches the log and
        // never the caller.
        const session = issued.rows[0];
        if (!session || !session.session_id) {
          deps.logger.warn('authentication refused', {
            correlationId: request.id, event: 'auth.refused',
            errorClass: session?.refusal ?? 'AUTHENTICATION_FAILED',
          });
          reply.code(401);
          return { error: 'authentication failed' };
        }

        deps.logger.info('session issued', {
          correlationId: request.id, event: 'auth.session_issued',
        });
        return {
          token,
          sessionId: session.session_id,
          userAccountId: session.user_account_id,
          outletId: session.outlet_id,
          establishedWith: session.established_with,
        };
      });
    } catch (error) {
      const signature = signatureOf(error);

      // A lockout is told plainly. It is the one refusal where silence harms the honest
      // caller more than it protects the account: five failures already happened, the
      // subject is locked either way, and a staff member standing at a terminal needs to
      // know to wait rather than to keep trying.
      if (signature === 'SUBJECT_LOCKED_OUT') {
        reply.code(429);
        deps.logger.warn('authentication refused', {
          correlationId: request.id, event: 'auth.locked_out', errorClass: signature,
        });
        return { error: 'too many attempts; this subject is locked out' };
      }

      // Everything else is one answer. The signature goes to the log, where an operator
      // can read it, and not to the caller, who would be reading an oracle.
      deps.logger.warn('authentication refused', {
        correlationId: request.id, event: 'auth.refused',
        errorClass: signature ?? 'AUTHENTICATION_FAILED',
      });
      reply.code(401);
      return { error: 'authentication failed' };
    }
  });

  /**
   * FR-AUTH-004. A session ends when its holder says so.
   *
   * Revocation already existed — revoke_sessions_on_membership_change retires sessions
   * when a membership goes — and what did not exist was a way for the person holding a
   * session to end it. Scoped to the presented token: this revokes the caller's own
   * session and cannot be pointed at anybody else's.
   */
  app.post('/v1/auth/logout', async (request: FastifyRequest, reply) => {
    const header = request.headers.authorization;
    if (!header || !header.toLowerCase().startsWith('bearer ')) {
      reply.code(401);
      return { error: 'authentication required' };
    }
    const token = header.slice(7).trim();
    const digest = createHash('sha256').update(token).digest('hex');

    // THROUGH withSession, NOT withoutContext, and the reason is row level security.
    // identity.session is scoped by app.row_in_scope, so an UPDATE with no context
    // established matches nothing and a valid token would be told it was invalid. Going
    // through withSession also makes the caller prove it holds the session before it can
    // end it, which is the property this route needs anyway.
    try {
      return await deps.db.withSession(token, async (client) => {
        const { rowCount } = await client.query(
          `UPDATE identity.session
              SET revoked_at = now(), revoked_reason = 'signed_out'
            WHERE token_digest = decode($1, 'hex') AND revoked_at IS NULL`,
          [digest],
        );
        return { revoked: (rowCount ?? 0) > 0 };
      });
    } catch (error) {
      if (error instanceof ContextRefused) {
        reply.code(401);
        return { error: 'authentication required' };
      }
      throw error;
    }
  });
}
