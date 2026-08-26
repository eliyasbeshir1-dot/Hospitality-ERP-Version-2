/**
 * Environment validation, run before the process makes any healthy or startup claim.
 *
 * Requirements: FR-OPS-001, FR-OPS-020, FR-INT-010.
 *
 * The rule this file exists to enforce: a service that cannot prove it is running as a
 * least-privileged identity must refuse to start, loudly, rather than start and report
 * itself healthy. M1-A proved that property in tests; this is its runtime twin.
 */
import { Client } from 'pg';

export interface Environment {
  databaseUrl: string;
  port: number;
  host: string;
  logLevel: string;
  serviceName: string;
  environmentName: string;
}

export class StartupRefusal extends Error {
  constructor(public readonly signature: string, message: string) {
    super(`${signature}: ${message}`);
    this.name = 'StartupRefusal';
  }
}

const REQUIRED_VARS = ['DATABASE_URL', 'PORT', 'ENVIRONMENT_NAME'] as const;

/** Read and validate required environment. Throws before anything else happens. */
export function readEnvironment(source: NodeJS.ProcessEnv = process.env): Environment {
  const missing = REQUIRED_VARS.filter((name) => {
    const value = source[name];
    return value === undefined || value.trim() === '';
  });
  if (missing.length > 0) {
    throw new StartupRefusal(
      'REQUIRED_ENVIRONMENT_ABSENT',
      `missing or empty: ${missing.join(', ')}`,
    );
  }

  const port = Number(source.PORT);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new StartupRefusal('REQUIRED_ENVIRONMENT_INVALID', 'PORT is not a valid port number');
  }

  // Credentials are read from the environment and never logged, never echoed in an
  // error, and never written to disk by this process (FR-SEC-007).
  return {
    databaseUrl: source.DATABASE_URL as string,
    port,
    host: source.HOST ?? '127.0.0.1',
    logLevel: source.LOG_LEVEL ?? 'info',
    serviceName: source.SERVICE_NAME ?? 'hospitality-os-api',
    environmentName: source.ENVIRONMENT_NAME as string,
  };
}

export interface RoleFacts {
  currentUser: string;
  isSuperuser: boolean;
  bypassesRls: boolean;
  canCreateRole: boolean;
  canCreateDb: boolean;
  ownsApplicationTables: boolean;
  canCreateInAppSchemas: boolean;
  inheritsSuperuser: boolean;
}

/** Ask the database what the connecting identity actually is. */
export async function readRoleFacts(databaseUrl: string): Promise<RoleFacts> {
  const client = new Client({ connectionString: databaseUrl });
  await client.connect();
  try {
    const { rows } = await client.query(`
      SELECT current_user                                            AS current_user,
             r.rolsuper                                              AS is_superuser,
             r.rolbypassrls                                          AS bypasses_rls,
             r.rolcreaterole                                         AS can_create_role,
             r.rolcreatedb                                           AS can_create_db,
             EXISTS (SELECT 1 FROM pg_class c
                     JOIN pg_namespace n ON n.oid = c.relnamespace
                     WHERE n.nspname IN ('org','identity','config','audit')
                       AND c.relkind = 'r'
                       AND pg_catalog.pg_get_userbyid(c.relowner) = current_user)
                                                                     AS owns_application_tables,
             (pg_catalog.has_schema_privilege(current_user,'org','CREATE')
              OR pg_catalog.has_schema_privilege(current_user,'identity','CREATE')
              OR pg_catalog.has_schema_privilege(current_user,'config','CREATE'))
                                                                     AS can_create_in_app_schemas,
             EXISTS (SELECT 1 FROM pg_auth_members m
                     JOIN pg_roles g ON g.oid = m.roleid
                     WHERE m.member = r.oid AND g.rolsuper)           AS inherits_superuser
      FROM pg_roles r WHERE r.rolname = current_user
    `);
    const row = rows[0];
    return {
      currentUser: row.current_user,
      isSuperuser: row.is_superuser,
      bypassesRls: row.bypasses_rls,
      canCreateRole: row.can_create_role,
      canCreateDb: row.can_create_db,
      ownsApplicationTables: row.owns_application_tables,
      canCreateInAppSchemas: row.can_create_in_app_schemas,
      inheritsSuperuser: row.inherits_superuser,
    };
  } finally {
    await client.end();
  }
}

/**
 * Refuse to continue if the connecting identity is privileged.
 *
 * Owner, superuser, BYPASSRLS and maintenance credentials are all rejected. There is no
 * override flag and no fallback path: an operator who needs a different identity supplies
 * a different identity (FR-OPS-020).
 */
export function assertUnprivileged(facts: RoleFacts): void {
  const violations: string[] = [];
  if (facts.isSuperuser) violations.push('is a superuser');
  if (facts.bypassesRls) violations.push('has BYPASSRLS');
  if (facts.inheritsSuperuser) violations.push('is a member of a superuser role');
  if (facts.canCreateRole) violations.push('has CREATEROLE');
  if (facts.canCreateDb) violations.push('has CREATEDB');
  if (facts.ownsApplicationTables) violations.push('owns application tables');
  if (facts.canCreateInAppSchemas) violations.push('can create objects in application schemas');

  if (violations.length > 0) {
    throw new StartupRefusal(
      'PRIVILEGED_RUNTIME_CREDENTIAL_ACCEPTED',
      `${facts.currentUser} ${violations.join(', ')} — refusing to start`,
    );
  }
}

/** Required binaries and paths, discovered before the first healthy claim. */
export function assertRuntimePrerequisites(): void {
  const [major] = process.versions.node.split('.');
  if (Number(major) < 20) {
    throw new StartupRefusal(
      'RUNTIME_PREREQUISITE_ABSENT',
      `Node 20 or newer is required; this is ${process.versions.node}`,
    );
  }
}
