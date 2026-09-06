#!/usr/bin/env bash
# Deployment entrypoint. NOT gate work — this file exists only on deploy/railway.
#
# Ordered so that each step runs under the identity that step is entitled to:
#
#   SUPER_URL      creates the two roles, once, and sets their passwords. Present
#                  only on the first deployment; removed afterwards so the running
#                  service cannot reach a superuser credential at all.
#   MIGRATOR_URL   applies migrations and seeds. Never used at runtime.
#   DATABASE_URL   the app identity, and the only one the server is given.
#
# Nothing here relaxes FR-OPS-001. The server decides for itself whether the
# identity in DATABASE_URL may run, and this script has no say in it.
set -euo pipefail
cd /src

if [ -n "${SUPER_URL:-}" ]; then
  echo "=== 1. roles, from the repository's own tools/bootstrap_database.sql ==="
  psql "$SUPER_URL" -v ON_ERROR_STOP=1 -f tools/bootstrap_database.sql
  echo "=== 2. authentication, from the deployment secret store, never from the file ==="
  # Fed through stdin, not -c: psql interpolates :'var' when reading a file or
  # standard input and sends -c verbatim to the server, which is why the first
  # attempt failed with a syntax error at ":". Interpolation is what keeps the
  # password out of the process list and correctly quoted whatever it contains.
  printf "ALTER ROLE hospitality_migrator PASSWORD :'mp';\nALTER ROLE hospitality_app PASSWORD :'ap';\n" \
    | psql "$SUPER_URL" -v ON_ERROR_STOP=1 -v mp="$MIGRATOR_PW" -v ap="$APP_PW" -f -
  echo "=== 3. role attributes as the managed cluster holds them ==="
  psql "$SUPER_URL" -v ON_ERROR_STOP=1 -c \
    "SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolcanlogin
       FROM pg_roles WHERE rolname LIKE 'hospitality%' ORDER BY rolname"
else
  echo "=== 1-3. skipped: no superuser credential in this deployment, by design ==="
fi

echo "=== 4. migrations, as the migrator ==="
python3 tools/migrate.py --dsn "$MIGRATOR_URL" --migrations migrations apply

echo "=== 5. seeds ==="
python3 tools/seed.py --dsn "$MIGRATOR_URL" --content-dsn "$DATABASE_URL" --seeds seeds apply

echo "=== 6. the identity the server is about to be handed ==="
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "SELECT current_user, r.rolsuper, r.rolbypassrls, r.rolcreaterole, r.rolcreatedb
     FROM pg_roles r WHERE r.rolname = current_user"

# The two endpoints, read back from inside the container and printed into the
# deploy log. This is not decoration: the operator running this deployment cannot
# reach *.up.railway.app from where they sit, so the only honest way to show what
# /health and /ready actually answer on the managed database is to have the
# service answer, and to print the body verbatim rather than a summary of it.
(
  for _ in $(seq 1 90); do
    if curl -sf "http://127.0.0.1:${PORT:-8080}/health" -o /tmp/health.json 2>/dev/null; then
      echo "=== 8. GET /health ==="
      cat /tmp/health.json; echo
      if curl -sf "http://127.0.0.1:${PORT:-8080}/ready" -o /tmp/ready.json 2>/dev/null; then
        echo "=== 9. GET /ready ==="
        cat /tmp/ready.json; echo
      else
        echo "=== 9. GET /ready did not answer 2xx ==="
      fi
      break
    fi
    sleep 2
  done
) &

# FR-OPS-001, both directions, against the managed database — run here rather
# than by pointing DATABASE_URL at a superuser, because on this platform a
# variable change re-resolves the service's source to the repository's tracked
# branch: a harmless probe variable was enough to make the next deploy build the
# wrong branch and fail. Driving it from code keeps the deploy on this branch and
# never leaves a privileged credential configured as the runtime identity.
#
# This CALLS the guard. It does not reimplement it, weaken it, or stand in for
# it: readRoleFacts and assertUnprivileged are the same exported functions
# server.js uses at boot, out of the same compiled dist.
if [ -n "${SUPER_URL:-}" ]; then
  echo "=== 6b. FR-OPS-001 against this managed database, both directions ==="
  node -e '
    const { readRoleFacts, assertUnprivileged, privilegeViolations } = require("/workspace/dist/env.js");
    (async () => {
      const superFacts = await readRoleFacts(process.env.SUPER_URL);
      try {
        assertUnprivileged(superFacts);
        console.log("NOT REFUSED for " + superFacts.currentUser + " — that is a defect");
        process.exit(1);
      } catch (error) {
        console.log("REFUSED  " + error.signature);
        console.log("         " + error.message);
        console.log("         violations: " + privilegeViolations(superFacts).join("; "));
      }
      const appFacts = await readRoleFacts(process.env.DATABASE_URL);
      assertUnprivileged(appFacts);
      console.log("PERMITTED " + appFacts.currentUser +
                  " — superuser=" + appFacts.isSuperuser +
                  " bypassrls=" + appFacts.bypassesRls +
                  " createrole=" + appFacts.canCreateRole +
                  " createdb=" + appFacts.canCreateDb +
                  " ownsTables=" + appFacts.ownsApplicationTables +
                  " canCreateInAppSchemas=" + appFacts.canCreateInAppSchemas +
                  " inheritsSuperuser=" + appFacts.inheritsSuperuser);
      process.exit(0);
    })().catch((e) => { console.log("CHECK FAILED: " + e.message); process.exit(1); });
  '
fi

echo "=== 7. starting the service; FR-OPS-001 now decides ==="
exec node /workspace/dist/server.js
