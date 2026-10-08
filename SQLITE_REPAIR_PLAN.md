# Production SQLite repair preparation — October 8, 2026

## Confirmed production findings

Read-only authenticated Render API/CLI inspection:

- Service `masterment` / `srv-dathsg7avr4c73djsaag`, Python runtime, free plan, one instance, zero attached persistent disks.
- Live commit: `76ad9d9565921dadefe4f411e9cee2b0cc7d3e21`. Deployments of `156e33e` and `b609fa4` have `update_failed` status. Failed-deployment causes were not inspected in this preparation.
- Application entrypoint: `app:create_app()`. Repository root is the service root.
- Direct service settings have APP_ENV=production, no DATABASE_PATH override and no DATABASE_URL. No environment groups are linked.
- At the live commit, BASE_DIR is the repository directory and DATABASE_PATH defaults to BASE_DIR/instance/masterment.sqlite3. Therefore the deployment-default resolved path is `/opt/render/project/src/instance/masterment.sqlite3`. This is source/configuration evidence, not a direct filesystem verification; a runtime .env or other override is not ruled out.
- Production logs confirm SQLite and `sqlite3.OperationalError: no such column: owner_hash` in the conversation-history query. The complete schema and migration history are still inaccessible.

The free service has no durable SQLite storage. Render's ephemeral files are lost across instance replacement. Free web services also do not support shell/SSH access. A CLI SSH attempt was blocked in noninteractive mode; the free-plan restriction independently prevents using a live shell for export. We did not create an ephemeral instance: it would not contain the running instance's database.

References: [Render persistent disks](https://render.com/docs/disks), [SSH compatibility](https://render.com/docs/ssh).

## Current decision

**Production repair is NOT ready to execute. No production backup exists from this investigation and none has been verified.** Do not restart, redeploy, attach a disk, change plan, alter database settings, migrate, recreate the database or switch to PostgreSQL before safely extracting the existing live SQLite data. Attaching a disk triggers a deployment and does not automatically preserve the current ephemeral database.

Exact next action: ask Render Support whether they can arrange a read-only, consistent export from the currently running instance without replacing it. Suggested request:

> Please preserve the currently running instance of service srv-dathsg7avr4c73djsaag (masterment). It is a free Python web service with SQLite customer data on ephemeral storage and no shell access. We need a read-only inspection of the effective runtime SQLite path (deployment default /opt/render/project/src/instance/masterment.sqlite3) and a consistent sqlite3.Connection.backup export, including any WAL contents, delivered securely with SHA-256 and integrity-check result. Do not restart, redeploy, upgrade, migrate or replace the instance before export. Please confirm whether you can provide this recovery access without losing the existing file.

This support capability is not guaranteed. If Support cannot provide it, we must design another approved extraction method before changing the service. Existing CRM CSV/export access alone cannot substitute for a full SQLite backup with messages and migration metadata. We have not sent this request.

## Prepared local verification tool

`tests/rehearse_sqlite_repair.py` accepts an existing accessible SQLite export. It never migrates its source. It creates private copies in a new output directory: verified-backup.sqlite3, rehearsal.sqlite3 and smoke-test.sqlite3. Use an access-restricted, encrypted location under ignored instance/; never commit or share these files. POSIX output directory/file modes are 0700/0600; on Windows, ensure the parent directory's ACL restricts access to the authorized operator. Gitignore is not an access control.

After securely obtaining the actual export, and ONLY locally:

```powershell
.\.venv\Scripts\python.exe tests/rehearse_sqlite_repair.py --source instance\recovery\production-export.sqlite3 --output instance\recovery\verified-rehearsal
```

The input path above is a proposed local export filename, not an existing backup. The output directory must not already exist. An unsuccessful run is a stop condition; do not rename a failed artifact to verified.

The tool uses SQLite's online backup API with a read-only source, performs full integrity_check and foreign_key_check, reports schema DDL/columns through sqlite_master and migration history/user_version without printing records, and verifies the backup SHA-256 remains unchanged. It migrates only rehearsal.sqlite3, validates checksummed migration history and required schema, and compares fingerprints of every original table's original columns before/after. New bookkeeping fields and migration history are allowed; existing lead, conversation, message and custom-table rows must remain unchanged.

Chat tests execute on a separate smoke-test copy: photography response, idempotent replay, contact capture, four-message history, cross-visitor denial and denial of legacy unowned conversations. Synthetic test records are never inserted into the export, verified backup or production database.

## Migration candidate and ownership

The repository's sole SQLite migration is `migrations/001_sales_intelligence.sql` (version 1). It adds conversations.owner_hash/revision, sales/qualification fields on leads, chat_requests, sales_transitions, related indexes, and a legacy-review flag for Booked leads. It does not delete the base customer tables or records. This is the likely required migration, **not a confirmed production migration set**, because production migration history and all columns remain uninspected. Do not infer the full schema solely from the missing owner_hash column.

The migration leaves existing conversations.owner_hash NULL. Keep it NULL: existing records remain visible to authorized CRM administrators, but public history/turns require a matching owner hash and cannot claim old conversations using only their public UUID. Do not backfill every old conversation to a current visitor or relax ownership checks. Visitors may need a new conversation; existing records must remain intact. The rehearsal checks that original fields are preserved and unowned histories return 404.

If a partially applied schema or checksum mismatch is found, the normal migration must stop; design and test a specific reconciliation plan on copies before production approval. The prepared tool deliberately rejects a partial schema rather than patching it blindly.

## Conditional production procedure — do not execute now

1. Obtain and verify a consistent live export, record its checksum and creation time, inspect the complete schema/history, and successfully rehearse the exact approved migration. Keep the unmodified export and verified backup outside the service's ephemeral filesystem.
2. Obtain a separate approved durable-storage transition plan. Since adding a disk replaces the instance, preserve all data before that operation. A transition with writes must quiesce database-writing traffic and take a final consistent export before cutover; an earlier backup alone cannot preserve later leads. Coordinate this maintenance rather than silently disabling the chatbot.
3. Establish a paid disk-backed instance using the same hosting provider, restore the verified final export to the approved persistent path, and verify integrity, table fingerprints/counts and permissions before application writes resume. Do not overwrite an existing customer database. These future operations require explicit authorization and are not performed here.
4. With the verified database existing at its approved durable path and all application writes quiesced, the migration command is `python -m app.migrations --database <verified-absolute-sqlite-path>`. Replace the placeholder only after recording the real path and confirming the approved repair plan. Never run it on the current ephemeral service as a shortcut.
5. Validate schema/checksums read-only, compare all preexisting rows/columns and ownership state, then resume the approved application. Confirm history returns 404 for nonexistent/unowned IDs, chat responses save messages/leads and authorized CRM access still works. Approve any production test inquiry explicitly.
6. Re-enable traffic only after successful checks. If repair fails before commit, the migration transaction rolls back. Do not restore an older backup over newly accepted customer writes; preserve both versions and reconcile them before any rollback.

The older live application skips automatic migration in production and only initializes base tables, explaining how a newer chat workflow can run against a legacy schema. Current source validates schema read-only at production startup. This supports the repair diagnosis but does not establish why the last two Render deployments failed.

## Local verification status

Two new synthetic tests cover a legacy Booked lead/conversation/message: the additive migration, original-file SHA preservation, row fingerprints, secure legacy access, chatbot/lead capture/replay, and safe abort for a partially migrated schema. **All 146 Python tests passed in 28.038 seconds**, and `git diff --check` passed. Production schema/export testing is still blocked; synthetic tests do not verify any real customer backup.
