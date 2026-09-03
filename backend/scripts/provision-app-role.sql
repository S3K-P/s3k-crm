-- ---------------------------------------------------------------------------
-- The role a DEPLOYED backend connects as, and the database it owns.
--
-- Run ONCE per deployed PostgreSQL, connected as that server's superuser
-- (on Railway that is `postgres`, against the `railway` database):
--
--   psql "$SUPERUSER_URL" \
--        -v app_role=s3k_app -v app_db=s3k_app -v app_password="$NEW_PASSWORD" \
--        -f scripts/provision-app-role.sql
--
-- Why it is needed at all: a managed Postgres hands you a SUPERUSER, and a
-- superuser is exempt from every row-level security policy. Connecting the
-- application as it means tenant isolation silently does not apply and every
-- organization can read every other one's rows — so
-- `app.core.database.enforce_rls_is_not_bypassed` refuses to start outside
-- development, and a production deployment on the default role crash-loops.
-- This is the same shape as the local role in
-- infra/postgres/init/10-application-role.sql, for the same reason.
--
--   NOSUPERUSER NOBYPASSRLS  the point of the exercise
--   CREATEROLE               the integration suite provisions throwaway roles;
--                            CREATEROLE cannot grant a privilege the grantor
--                            lacks, so it does not re-open BYPASSRLS
--   OWNER of its database    so `CREATE EXTENSION pgcrypto` / `pg_trgm` work,
--                            both trusted extensions a database owner may add
--
-- Idempotent: safe to re-run, and re-running rotates the password to the value
-- passed in. No password is stored in this file.
-- ---------------------------------------------------------------------------

\set ON_ERROR_STOP on

-- Create the role only if it is absent...
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB CREATEROLE NOBYPASSRLS',
    :'app_role'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_role')
\gexec

-- ...then set the password unconditionally, so a re-run rotates it and the
-- privilege bits are re-asserted even on a role that predates this script.
SELECT format(
    'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS',
    :'app_role', :'app_password'
)
\gexec

-- The application's own database, owned by that role. CREATE DATABASE cannot
-- run inside a transaction block, which is why every statement here is emitted
-- through \gexec rather than wrapped in a DO block.
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_role')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db')
\gexec

-- Confirm the guarantee actually holds; this is what the backend checks at
-- startup, so seeing `f` here means the deployment will boot.
SELECT rolname AS role,
       rolsuper AS is_superuser,
       rolbypassrls AS bypasses_rls
FROM pg_roles
WHERE rolname = :'app_role';
