# Deploying the backend to Railway

The Railway service **s3k-crm** (environment `production`) runs the FastAPI
backend from `backend/` and nothing else. The frontend is hosted separately and
is not part of this service.

---

## 1. Why the build was failing

Railway reported, before a single layer ran:

```
dockerfile invalid: flag '--mount=type=cache,target=/root/.cache/uv'
is missing an id argument at Line 19
dockerfile invalid: flag '--mount=type=cache,target=/root/.cache/uv'
is missing an id argument at Line 26
```

Lines 19 and 26 were `backend/Dockerfile`'s own two `RUN --mount=type=cache`
instructions. The Dockerfile was the source of the error, not something Railway
generated: Railway's builder namespaces every build cache to a service, so it
rejects a cache mount carrying no `id=`, where local BuildKit is happy to
default one.

That is also why `RAILPACK_DISABLE_CACHES=*` changed nothing. Railpack is the
*zero-config* builder Railway uses when a repository has no Dockerfile, and
that variable only suppresses caches in a plan Railpack itself generates. This
repository ships a Dockerfile, so Railpack never ran and the variable had
nothing to act on. **`RAILPACK_DISABLE_CACHES` can be deleted from the
service.**

The fix is in the Dockerfile: it no longer uses BuildKit `--mount` flags at
all. Dependencies install from a plain `COPY pyproject.toml uv.lock` layer, so
Docker's ordinary layer cache still skips the install whenever the lockfile has
not moved — which is where nearly all of the speed came from anyway — and the
same file now builds on Railway, on plain Docker and in CI.

---

## 2. Services this backend needs

| Railway service | Why |
| --- | --- |
| `s3k-crm` | the FastAPI backend itself |
| PostgreSQL | required; the process refuses to start without `DATABASE_URL` |
| Redis | required; refresh-token and rate-limit state (ADR-013) |
| Cloudflare R2 (external) | attachments; **required** when `ENVIRONMENT=production` |

PostgreSQL and Redis are reached over Railway's private network. Reference them
with Railway's own variable references rather than pasting host names, so a
service rebuild cannot leave a stale address behind.

---

## 3. Service settings

| Setting | Value |
| --- | --- |
| Root Directory | `backend` |
| Builder | Dockerfile (`backend/railway.json` pins it) |
| Config-as-code path | `railway.json`, relative to the root directory |
| Start command | `sh /app/scripts/start.sh` |
| Health check path | `/health` |
| Replicas | 1 |

`backend/railway.json` carries all of these except the root directory, which is
a dashboard-only setting. Root Directory **must** be `backend`: the Dockerfile's
build context is the backend tree, so a repo-root context cannot find
`pyproject.toml` or `uv.lock`.

The container binds `$PORT`, which Railway assigns — never a fixed 8000.

---

## 4. One-time: the database role

A managed Postgres hands you a superuser, and a superuser is exempt from every
row-level security policy. Connecting the application as it means tenant
isolation silently does not apply, so `enforce_rls_is_not_bypassed` aborts
startup outside development and the deployment crash-loops on boot.

Create an ordinary role and its own database, once, as the Postgres superuser.
From `backend/`:

```bash
railway link
railway connect Postgres
```

then, at the `psql` prompt:

```
\set app_role s3k_app
\set app_db s3k_app
\set app_password 'the-password-you-generated'
\i scripts/provision-app-role.sql
```

The script is idempotent and prints the role's `rolsuper` / `rolbypassrls`
flags at the end; both must read `f`. `DATABASE_URL` then points the backend at
`s3k_app`, not at `postgres` — see the table below.

### Without a local psql

`railway connect` needs either a registered SSH key or a public TCP proxy, and
`scripts/provision-app-role.sql` uses psql meta-commands (`\set`, `\gexec`)
that a web query console cannot run. Paste this equivalent into the Postgres
service's **Data → Query** tab instead, substituting the password. Run the
three statements one at a time: `CREATE DATABASE` cannot share a transaction
with anything else, which is the whole reason the psql version needs `\gexec`.

```sql
-- 1. The role, idempotently.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 's3k_app') THEN
    CREATE ROLE s3k_app LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOBYPASSRLS;
  END IF;
END
$$;

-- 2. Its password and privilege bits (re-running rotates the password).
ALTER ROLE s3k_app LOGIN PASSWORD 'PASTE_APP_DB_PASSWORD_HERE'
    NOSUPERUSER NOBYPASSRLS;

-- 3. The database it owns. Must run on its own.
CREATE DATABASE s3k_app OWNER s3k_app;
```

Then confirm the guarantee holds — both columns must read `f`, or the backend
will refuse to start:

```sql
SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 's3k_app';
```

Schema migrations run automatically on every boot (`alembic upgrade head` in
`scripts/start.sh`). If this service is ever scaled past one replica, move that
to Railway's pre-deploy command so replicas cannot race.

---

## 5. Environment variables

Set on the **s3k-crm** service, `production` environment.

### Required

| Variable | Value | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | turns on every strict check below |
| `DEBUG` | `false` | startup aborts if true in production |
| `DB_ECHO` | `false` | startup aborts if true in production |
| `DATABASE_URL` | `postgresql+asyncpg://s3k_app:<pw>@<postgres-private-host>:5432/s3k_app` | the `postgresql+asyncpg://` scheme is validated; Railway's own `DATABASE_URL` uses `postgresql://` and is rejected |
| `REDIS_URL` | Railway's Redis URL | must start `redis://`, `rediss://` or `unix://` |
| `JWT_PRIVATE_KEY` | Ed25519 PEM | required in production; literal `\n` accepted |
| `JWT_PUBLIC_KEY` | Ed25519 PEM | as above |
| `STORAGE_BUCKET` | e.g. `s3k-attachments` | required in production |
| `STORAGE_ACCESS_KEY_ID` | R2 API token key | required in production |
| `STORAGE_SECRET_ACCESS_KEY` | R2 API token secret | required in production |
| `STORAGE_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` | |
| `CORS_ALLOWED_ORIGINS` | the frontend origin | comma-separated, no wildcard — see §6 |

Prefer Railway's variable references for the datastore hosts, so they follow a
rebuilt service: the Postgres private domain and the Redis URL are both
available as references in the variable editor.

Generate the JWT keypair with:

```bash
openssl genpkey -algorithm ed25519 -out jwt-private.pem
openssl pkey -in jwt-private.pem -pubout -out jwt-public.pem
```

Keep both out of the repository. Set them from the files without echoing them:

```bash
railway variables --set "JWT_PRIVATE_KEY=$(cat jwt-private.pem)" --set "JWT_PUBLIC_KEY=$(cat jwt-public.pem)"
```

### Recommended

| Variable | Value | Notes |
| --- | --- | --- |
| `LOG_JSON` | `true` | one JSON object per line, which is what Railway's log search indexes |
| `LOG_LEVEL` | `INFO` | |
| `STORAGE_REGION` | `auto` | R2 ignores it, boto3 requires it |
| `STORAGE_FORCE_PATH_STYLE` | `true` | R2 addresses buckets by path |

### Optional

| Variable | Notes |
| --- | --- |
| `ANTHROPIC_API_KEY` | unset is a supported state: AI endpoints answer 503 `ai_not_configured` and the interface shows "AI is not connected". Nothing is faked in its place. |

### Delete

| Variable | Why |
| --- | --- |
| `RAILPACK_DISABLE_CACHES` | never applied — the repo has a Dockerfile, so Railpack does not run (§1) |

---

## 6. CORS and the refresh cookie

`CORS_ALLOWED_ORIGINS` must name the frontend's exact origin, comma-separated.
A wildcard is not accepted and cannot be: the refresh cookie makes these
credentialed requests, and the CORS specification forbids credentials alongside
`*`.

**CORS on its own is not enough when the frontend is on an unrelated domain.**
The refresh cookie is `SameSite=Lax` (`app/platform/auth/router.py`), and a Lax
cookie is not sent on a cross-site `fetch`. Login would succeed and then every
session would end silently once the 15-minute access token expired, because
`POST /api/v1/auth/refresh` would arrive with no cookie. Pick one of:

1. **Reverse proxy — what doc 11 assumes.** Serve the API under the frontend's
   own origin at `/api/v1`, leave `NEXT_PUBLIC_API_BASE_URL` empty, and the
   whole question disappears: no CORS, no cross-site cookie.
2. **Shared parent domain.** Frontend on `app.example.com`, backend on
   `api.example.com`, plus `COOKIE_DOMAIN=.example.com`. Same site, so the Lax
   cookie travels.
3. Backend on its `*.up.railway.app` domain with the frontend elsewhere. Access
   tokens work; **refresh does not**, and switching the cookie to
   `SameSite=None` is an application and security decision, not a deployment
   setting.

---

## 7. Verify

```bash
curl -fsS https://<backend-domain>/health
curl -fsS https://<backend-domain>/health/ready
```

`/health` is liveness and touches nothing. `/health/ready` returns 503 with a
per-dependency breakdown until both datastores respond, which is the first
place to look when a deployment is green but requests fail.

OpenAPI docs are disabled in production by design (`docs_url` is `None`), so a
404 at `/docs` is correct behaviour, not a broken deployment.
