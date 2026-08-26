/**
 * Structured logging with redaction (FR-OPS-003, FR-SEC-007).
 *
 * Every line carries correlation, tenant, outlet, actor, event and error classification.
 *
 * Redaction is applied to the whole record on the way out rather than at each call site.
 * A call site that forgets is the normal case, not the exception, so the guarantee has to
 * live somewhere a caller cannot bypass.
 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogContext {
  correlationId?: string;
  tenantId?: string | null;
  outletId?: string | null;
  actorId?: string | null;
  event?: string;
  errorClass?: string;
  [key: string]: unknown;
}

/** Field names whose values are never emitted, at any nesting depth. */
const SECRET_KEYS = [
  'password', 'token', 'secret', 'credential', 'authorization', 'cookie',
  'otp', 'pin', 'apikey', 'api_key', 'sessiontoken', 'session_token',
  'tokendigest', 'token_digest', 'secretdigest', 'secret_digest', 'dsn',
  'databaseurl', 'database_url', 'connectionstring', 'connection_string',
];

/** Value shapes that look like a secret even under an innocent key name. */
const SECRET_VALUE_PATTERNS: RegExp[] = [
  /\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*/gi,   // bearer tokens
  /postgres(?:ql)?:\/\/[^\s"']+/gi,          // connection strings with credentials
  // Query parameters that name a secret. Request URLs are logged, and a client that puts
  // a credential in the query string is a real and common leak path — the log line is
  // honest, the value in it must not be.
  /([?&](?:token|secret|password|passwd|pin|otp|api[_-]?key|session[_-]?token|access[_-]?token)=)[^&\s"']+/gi,
  /\b[A-Za-z0-9_-]{40,}\b/g,                 // long opaque strings: tokens, digests, keys
];

export const REDACTED = '[redacted]';

function isSecretKey(key: string): boolean {
  const flat = key.toLowerCase().replace(/[^a-z]/g, '');
  return SECRET_KEYS.some((candidate) => flat.includes(candidate.replace(/[^a-z]/g, '')));
}

function redactString(value: string): string {
  let out = value;
  for (const pattern of SECRET_VALUE_PATTERNS) {
    // A rule with a capture group keeps the parameter name and replaces only its value,
    // so a log line still says WHICH parameter was present without saying what it was.
    out = out.replace(pattern, (match, keep?: string) => (keep ? `${keep}${REDACTED}` : REDACTED));
  }
  return out;
}

/** Recursively redact a value. Depth-limited so a cyclic structure cannot hang a log call. */
export function redact(value: unknown, depth = 0): unknown {
  if (depth > 6) return REDACTED;
  if (value === null || value === undefined) return value;
  if (typeof value === 'string') return redactString(value);
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  if (Array.isArray(value)) return value.map((item) => redact(item, depth + 1));
  if (value instanceof Error) {
    return { name: value.name, message: redactString(value.message) };
  }
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
      out[key] = isSecretKey(key) ? REDACTED : redact(inner, depth + 1);
    }
    return out;
  }
  return REDACTED;
}

export interface LogSink {
  write(line: string): void;
}

export class StructuredLogger {
  constructor(
    private readonly serviceName: string,
    private readonly level: LogLevel = 'info',
    private readonly sink: LogSink = { write: (line) => process.stdout.write(line + '\n') },
  ) {}

  private readonly order: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

  log(level: LogLevel, message: string, context: LogContext = {}): void {
    if (this.order[level] < this.order[this.level]) return;
    const record = {
      timestamp: new Date().toISOString(),
      level,
      service: this.serviceName,
      message,
      ...context,
    };
    this.sink.write(JSON.stringify(redact(record)));
  }

  debug(m: string, c?: LogContext) { this.log('debug', m, c); }
  info(m: string, c?: LogContext) { this.log('info', m, c); }
  warn(m: string, c?: LogContext) { this.log('warn', m, c); }
  error(m: string, c?: LogContext) { this.log('error', m, c); }
}
