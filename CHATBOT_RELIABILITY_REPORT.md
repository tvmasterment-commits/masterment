# Chatbot investigation — October 8, 2026

## Production evidence and root-cause limits

Read-only public checks: homepage and /api/chat/session return 200; /health returns 200. The live homepage still has the old title, so the previously pushed SEO commit is not reflected there. The served chat script includes the session-initialization gate.

An authenticated-by-cookie GET to /api/conversations/<random nonexistent UUID> returned 500 rather than the expected 404. This lookup opens the database and queries conversations.owner_hash, without calling OpenAI. A session is established successfully first. This reproduces a production failure on the database-backed conversation-history path, independent of the model. The exact exception remains unknown without logs. Possible causes include database connectivity/permissions, a wrong database target, missing table/column, or a mismatched deployment/schema. A green /health only establishes process liveness; it never checks database access.

No production message was submitted, no synthetic production lead was created, and no production database was inspected, reset, migrated or changed. Thus production write capability is not established. Local tests prove it works with a compatible isolated SQLite schema; they do not prove production database health or live PostgreSQL writes.

## Confirmed code fixes

- In chat.js, await of session/history initialization was outside the submission try/finally. A rejected session promise could leave input/Send disabled and be permanently reused on retry. Initialization is now within error handling, session failures clear the cached promise, and retry re-establishes identity before sending. Existing request IDs remain stable across message retries, protecting against duplicate leads/messages.
- History database failures previously escaped as HTML 500 responses. They now return safe JSON 503 with no-store caching and an explicit retry message. Storage/history diagnostic logs include exception class, database backend and PostgreSQL SQLSTATE only. They never print exception text, connection strings, SQL, cookies or customer messages.
- Existing model errors already fall back to deterministic replies. OpenAI requests have a 20-second timeout and no SDK retries; provider refusal, invalid results, timeout and authentication failures are caught. Conversations/lead details are saved before the model call, with no database connection held during it. No provider behavior change was necessary.

These recovery/diagnostic fixes do not repair a missing production table or unavailable database. Production restoration still depends on identifying and resolving that infrastructure issue safely.

## Regression coverage

Added tests for history database failures and sanitized logs, message storage outage then successful retry without duplicates, and photography lead/contact capture despite provider timeout. A Node harness executes the actual browser chat.js against controlled session, history and submission failures; it checks controls unlock, recovery, stable request identity and single displayed messages.

Commands:

```powershell
node tests/chat_submission.cjs
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Validation: **144 Python tests passed in 27.467 seconds**, including all existing chatbot, CRM, pricing, contact, database and SEO tests. Both Node scenarios passed (fresh browser session and existing conversation). `git diff --check` passed. No CSS, templates, chatbot catalog/prices, CRM behavior, database config/schema or production credentials were changed.

## Exactly what logs/configuration to retrieve

For the existing failing history request or a naturally occurring customer failure, retrieve the timestamp/timezone, deployed commit SHA, request method/path (redact conversation UUID), HTTP status and final exception class. For /api/chat look for `chat_storage_failure category=...`; for model fallback look for `ai_result_rejected category=...`. The current unhandled history failure should have a Gunicorn/Flask traceback: supply only application file/line/function and the final database error with credentials, URLs, customer data and bind values removed. After deploying the fix, history emits `chat_history_failure category=... backend=... sqlstate=...` without sensitive exception text.

Useful distinctions: PostgreSQL 42P01 = undefined table, 42703 = undefined column, 42501 = insufficient privilege; OperationalError may indicate connectivity or SQLite path/permissions. A missing-schema report requires separate owner-approved investigation; do not run migrations or recreate a database as a troubleshooting shortcut.

Check configuration names/presence only: APP_ENV should be production, DATABASE_URL presence determines PostgreSQL versus DATABASE_PATH for SQLite, FLASK_SECRET_KEY must be a stable configured secret across workers, OPENAI_API_KEY presence and OPENAI_MODEL name. Never send values of credentials or database URLs. Confirm the deployed repository/branch/commit and start command, persistent disk mount if using SQLite, and whether the configured target is the intended existing lead database. Startup validates schema read-only in production; it does not migrate it.

## Safe deployment

1. Obtain the production failure category first. Verify the intended existing database target and read/write privileges without changing or migrating it. If schema is incompatible, stop and plan an owner-approved database repair separately. A deployment alone is not guaranteed to resolve database failure.
2. Run the tests above, review the diff, and stage only app/routes.py, app/static/chat.js, tests/test_chat_reliability.py, tests/chat_submission.cjs and this report. Exclude unrelated untracked artifacts, databases and the earlier deployment workflow.
3. Create a new reviewed commit with `[skip render]` if publishing should not trigger Render automatically; push normally after checking remote history. Explicitly deploy that new commit only when ready. The previously prepared deploy-render.yml is pinned to b609fa4 and will NOT include these chatbot fixes; do not use it to publish this change without separately updating/reviewing its target SHA.
4. Leave production secrets/database settings and schema unchanged. Restart workers through the approved deployment process to refresh content-versioned chat.js URLs. Confirm the new asset is served and the correct commit is live.
5. Repeat the nonexistent-ID history lookup: expect 404, not 500/503. Then use an explicitly approved test inquiry or observe a real inquiry to verify chat response, retry behavior, history and CRM lead capture. Do not delete customer leads. A sanitized 503 means the storage issue still needs resolution.
