# PostgreSQL preparation (local only)

No production database or Render environment is changed by this work.

## Configuration and explicit schema migration

SQLite remains the default when DATABASE_URL is empty. Install requirements to obtain Psycopg 3. A PostgreSQL URL selects PostgreSQL; unsupported schemes fail instead of falling back to SQLite. Explicit test configurations with DATABASE_PATH use SQLite unless DATABASE_URL is also supplied.

Application startup validates PostgreSQL schema/history in a read-only transaction, even in development. Production SQLite startup also validates read-only and never creates/migrates a file. Local SQLite development keeps its existing bootstrap behavior.

On an explicitly selected staging database, set DATABASE_URL securely in the environment and run `python -m app.migrations --postgres`. This creates baseline version 0 and Checkpoint B version 1 in one transaction. Re-running verifies checksums. Startup never invokes this command. Existing SQLite migration SQL and checksums are unchanged; PostgreSQL has a separate dialect history because identity syntax differs.

The small adapter translates bound question-mark markers to Psycopg markers, preserving quoted literals, and passes values separately. Psycopg dict rows match the existing application's named row access. SQLite uses sqlite3.Row. Both use ON CONFLICT and RETURNING for message IDs. UTC ISO text timestamps and JSON-as-text deliberately retain existing application semantics. Parameter names and dynamic update columns come from application allowlists.

Short chat write transactions serialize through SQLite BEGIN IMMEDIATE or PostgreSQL transaction-scoped advisory lock 734821906. The lock also serializes PostgreSQL migrations. It protects first-request replay races and revision allocation without holding any connection during model calls. Global writer serialization is conservative and may limit throughput; it can later be replaced with a carefully tested per-request/per-conversation lock order. No unsafe automatic transaction retries are introduced.

## Required real PostgreSQL verification

No PostgreSQL server was available locally during implementation. Boundary tests and SQLite regressions do not prove PostgreSQL execution. Create a disposable local test database whose name contains `test`, set POSTGRES_TEST_URL to its loopback URL, and run `python tests/postgres_integration.py`. The runner creates a unique private schema, executes actual migrations twice, checks history/startup, persists chats/leads/requests/transitions, verifies ownership/admin/status changes and concurrent duplicate replay, and removes only its own schema. Never use production credentials for this test. Also run stale-response and load tests against the staging PostgreSQL database before activation.

## Existing SQLite data transfer before production activation

1. Identify and back up the actual current production SQLite database before its ephemeral instance is replaced. A free-service filesystem may lose data on replacement; a local development copy cannot establish production contents.
2. Stop writes for a consistent export. Validate source version/checksum, foreign keys, row counts, and ownership/session-secret continuity. Keep the original SQLite file and its schema_migrations as an immutable audit artifact.
3. Explicitly create/migrate the staging PostgreSQL schema. Transfer, in dependency order, conversations, leads, messages, chat_requests, sales_transitions. Preserve all columns, numeric IDs, timestamps, owner hashes, revisions, evidence, request response JSON, and legacy status/review flags. Do not substitute PostgreSQL checksums for the source audit history: each dialect keeps its own original migration records.
4. Import in a single transaction into an empty target, assert counts and selected records, and reset the leads/messages/sales_transitions identity sequences above their imported maximum IDs. Otherwise the next insert can collide. Test repeat-request replay and correction ownership after transfer.
5. Confirm SSL/network access, supported database version, connection capacity, backups/restore, secret continuity, and rollback on staging. Only after real integration/data verification should an explicitly authorized later deployment configure Render DATABASE_URL.

Data export/import tooling and production transfer are intentionally still required activation work; no production data was read, created or copied. This runbook is preparation, not authorization to activate PostgreSQL.

Driver behavior follows the [Psycopg transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html). PostgreSQL transactions commit on success, roll back on failure, and connections always close at the adapter boundary.
