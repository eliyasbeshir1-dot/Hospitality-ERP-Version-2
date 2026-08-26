# Cloud API — M1 surface

Fastify on Node, TypeScript, talking to PostgreSQL as the least-privileged application
role. It exposes tenancy, identity, memberships, sessions and configuration. There is no
menu, no order, no check and no payment surface here — those are M2, M3 and M4.

## Why the build output lives outside this repository

`tools/verify_m1.py` treats `node_modules/`, `dist/` and `build/` as forbidden surface and
checks the **filesystem**, not the Git index. A `.gitignore` entry would keep them out of
commits but would not stop the gate failing on a developer machine after a build.

Rather than argue with the gate, the build simply happens somewhere else.
`api/build.sh` installs dependencies and compiles into a workspace directory —
`$M1D_WORKSPACE`, default `/var/lib/m1d-workspace` — where `node_modules` sits beside the
compiled `dist/`. Node resolves modules by walking up from the running file, so this is an
ordinary layout; it is only in an unusual place.

The repository therefore contains source and nothing else, at every moment, with no
cleanup step to forget.

## Commands

```bash
bash api/build.sh                      # install dependencies and compile
bash api/build.sh --run                # build, then start the service
```

See `docs-local/CROSS_PLATFORM_COMMANDS.md` for the Windows and Linux equivalents and for
what tool discovery does when something is missing.
