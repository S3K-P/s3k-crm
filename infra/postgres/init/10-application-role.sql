-- ---------------------------------------------------------------------------
-- The role the application connects as locally.
--
-- Run once by the postgres image on first initialisation of the data volume
-- (files in /docker-entrypoint-initdb.d are executed in name order).
--
-- Why this exists at all: POSTGRES_USER is created SUPERUSER, and a superuser
-- is exempt from every row-level security policy. Connecting the application
-- as it means tenant isolation silently does not apply -- locally, in CI, and
-- anywhere else the same shortcut is taken. That is not a theoretical concern:
-- it hid a defect that made organization provisioning impossible under any
-- correctly privileged role, through the whole test suite.
--
-- So local development gets the same shape as production: an ordinary role,
-- owning its own database, with no way to see past a policy.
--
--   NOSUPERUSER NOBYPASSRLS  the point of the exercise
--   CREATEROLE               tests/integration/test_crm_rls.py and
--                            test_tenant_isolation.py provision a throwaway
--                            role to connect as. CREATEROLE cannot grant a
--                            privilege the grantor lacks, so this does not
--                            re-open BYPASSRLS.
--   OWNER of s3k_app         so `CREATE EXTENSION pgcrypto` / `pg_trgm` work;
--                            both are trusted extensions a database owner may
--                            install.
--
-- The password is a local placeholder and matches backend/.env.example. It is
-- not a credential: this database is reachable only from the developer's own
-- machine, and nothing outside docker-compose ever uses it.
-- ---------------------------------------------------------------------------

CREATE ROLE s3k_app LOGIN PASSWORD 'app-local-only'
    NOSUPERUSER NOCREATEDB CREATEROLE NOBYPASSRLS;

CREATE DATABASE s3k_app OWNER s3k_app;
