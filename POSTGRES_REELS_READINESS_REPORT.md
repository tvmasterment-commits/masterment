# PostgreSQL and reels readiness — October 7, 2026

Local implementation completed on main, starting from `76ad9d9565921dadefe4f411e9cee2b0cc7d3e21`. No commit, push, deployment, Render resource creation, Render environment change, or Checkpoint C work occurred. Existing untracked reports, temporary artifacts, and customer.csscd were preserved.

## 1. Root cause investigation for the reported reels

| Reel | Original file | Confirmed original container problem | Current served file |
|---|---|---|---|
| 1 | videos/reels/reels-1.MP4 | moov after mdat; metadata at end | videos/portfolio-web/reels-1.mp4 |
| 2 | videos/reels/reels-2.MP4 | moov after mdat; metadata at end | videos/portfolio-web/reels-2.mp4 |
| 3 | videos/reels/reels-3.MP4 | moov after mdat; metadata at end | videos/portfolio-web/reels-3.mp4 |
| 5 | videos/reels/reels-5.MP4 | moov after mdat; metadata at end | videos/portfolio-web/reels-5.mp4 |
| 9 | videos/reels/reels-9.MP4 | moov after mdat; metadata at end | videos/portfolio-web/reels-9.mp4 |

All five originals have trailing metadata, while working Reels 4, 6, 7, and 8 have front-loaded metadata. All nine use H.264 High/yuv420p video and HE-AAC audio, so codec type does not explain a five-versus-four difference. The five current served files already have fast-start metadata from Checkpoint B. All eleven current files passed full FFmpeg video/audio decoding, exact-path checks, and atom inspection. The existing template uses the correct lowercase optimized URLs for the five originals with uppercase extensions. Both project originals also have trailing metadata; their current remuxes are front-loaded.

**The reported live failure was not reproduced with the current files in local Chrome.** Trailing metadata is a confirmed historical bottleneck, but cannot be asserted as the sole cause of the reported production failure without its device/request/error trace. No current corrupt-file or unsupported-codec diagnosis is claimed.

Two current shared frontend weaknesses were identified and addressed: rejected autoplay had no actionable recovery UI, and asynchronous play-promise callbacks could act on a newer source load. A browser test deliberately rejects autoplay for each of the five reels and verifies trusted click/tap recovery; another holds an old play promise across unloading/reloading and verifies that its late rejection cannot change current playback. These are demonstrated failure/recovery paths, not proof that they caused the original production report.

## 2. Exact fix for Reels 1, 2, 3, 5, and 9

Preserved the existing correct fast-start files and templates. No video was re-encoded or substituted: current files decode and play, and unnecessary encoding would alter quality without evidence of a codec fault.

The shared scheduler now:

- Initializes once, preventing duplicate media handlers/buttons.
- Allows one outstanding play attempt per source generation.
- Ignores promise results from cancelled/replaced generations, including delayed rejections.
- Exposes a Play video button when autoplay is denied or media errors occur. The button calls play directly within a trusted click/tap; a media error can reload the source through that gesture.
- Supports video click/keyboard pause and explicit resume. User pause survives scroll/resize scheduler updates.
- Permits explicit project-video playback under reduced motion while retaining the existing automatic reduced-motion behavior.

Posters, 600-pixel preparation range, viewport playback, deferred sources/preload none, progressive scheduling, original ordering, highlights, all items, arrows, and normal layout remain. Recovery controls appear only when needed or explicitly paused. The scheduler remains shared with no competing media initializer in customer.js. Distant loads increment their generation before cancellation. Existing poster overlays use pointer-events none and remain visible until actual playback.

## 3. Every portfolio item's test result

Paths below are relative to app/static. Each desktop/mobile result includes actual readyState >= 3 playback/currentTime, no media error, hidden poster during playback, explicit pause surviving resize, trusted resume, and HTTP 206 byte-range response with video/mp4 MIME and expected Content-Range.

| Item | Served path | Full decode / fast-start | Desktop | Mobile Chrome | Forced autoplay denial recovery |
|---|---|---|---|---|---|
| Reel 1 | videos/portfolio-web/reels-1.mp4 | Pass / Pass | Pass | Pass | Click and tap pass |
| Reel 2 | videos/portfolio-web/reels-2.mp4 | Pass / Pass | Pass | Pass | Click and tap pass |
| Reel 3 | videos/portfolio-web/reels-3.mp4 | Pass / Pass | Pass | Pass | Click and tap pass |
| Reel 4 | videos/reels/reels-4.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |
| Reel 5 | videos/portfolio-web/reels-5.mp4 | Pass / Pass | Pass | Pass | Click and tap pass |
| Reel 6 | videos/reels/reels-6.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |
| Reel 7 | videos/reels/reels-7.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |
| Reel 8 | videos/reels/reels-8.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |
| Reel 9 | videos/portfolio-web/reels-9.mp4 | Pass / Pass | Pass | Pass | Click and tap pass |
| Project work-01, current BALA label | videos/portfolio-web/work-01.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |
| Project work-03, current MEMORIES label | videos/portfolio-web/work-03.mp4 | Pass / Pass | Pass | Pass | Standard pause/resume pass |

Existing browser_performance additionally passed all 11 items on mobile, desktop and without IntersectionObserver, plus project highlight loops and reduced motion. Duplicate initialization and returning to previously unloaded reels passed. The controlled delayed-rejection race passed on mobile.

Actual request URLs, including cache-version query strings, are recorded in `.performance-verification/reels-runtime-results.json` (33 result rows). Atom/stream/original comparisons are in `portfolio-codecs.json`. Media and error test results are in `media-results.json`.

Cold throttled portfolio audit (`portfolio-postgres-reels.json`): zero initial portfolio requests/bytes on both devices. First three posters after scripted approach: 41 ms mobile, 8 ms desktop. First playback: 3,271 ms throttled mobile, 529 ms desktop. Ten-second post-scroll observations received 1.35 MB mobile and 10.51 MB desktop, with 4 and 5 range requests respectively. These are single local lab runs. No initial video weight was added; media bytes are unchanged. Desktop/mobile saved-reference text and geometry comparisons passed, and the new mobile portfolio screenshot was visually inspected.

## 4. PostgreSQL architecture and audit

The smallest change uses the existing SQL application with a thin database adapter and Psycopg 3, rather than adding an ORM or duplicating the sales workflow.

- DATABASE_URL from environment selects PostgreSQL; empty URL retains DATABASE_PATH/SQLite. Unsupported URL schemes fail clearly. Explicit test DATABASE_PATH configurations retain SQLite unless DATABASE_URL is also explicitly supplied.
- SQLite continues to use sqlite3.Row; PostgreSQL uses dict rows. Application access is by column name; generated message IDs now use RETURNING rather than SQLite last_insert_rowid.
- Bound values stay separate. The adapter translates question-mark bind markers outside quoted SQL literals to Psycopg %s markers and escapes literal percentages. Dynamic columns remain application-controlled allowlists. This is a small translator for the application's SQL subset, not a general SQL parser.
- INSERT OR IGNORE became portable ON CONFLICT with explicit conflict targets. SQLite PRAGMA, AUTOINCREMENT, and BEGIN IMMEDIATE remain only in the SQLite adapter/bootstrap/migration branch. PostgreSQL schema uses GENERATED BY DEFAULT AS IDENTITY, references, checks, unique constraints, and indexes.
- UTC ISO timestamps are created by application code; SQLite datetime('now') was removed from admin writes. Dates and JSON/evidence/response payloads retain existing TEXT semantics across both databases. Boolean-like flags remain integers.
- Successful transactions commit, failures roll back, and connections close. PostgreSQL chat writers use a transaction-scoped advisory lock, mirroring the short SQLite writer serialization, including first-turn request races without an existing conversation row. No model call runs under a connection/transaction. Revision and stale-response logic remains unchanged.
- Global PostgreSQL writer serialization is intentionally conservative; it may limit high-volume throughput. No automatic write retry is added, avoiding duplicate external/model side effects. Connection and SQLite busy timeouts are 10 seconds.
- Original SQLite migration `001_sales_intelligence.sql` and its history/checksums are unchanged. PostgreSQL baseline 0 and Checkpoint B 1 have their own checksummed dialect history. Explicit `python -m app.migrations --postgres` reads DATABASE_URL securely from environment and migrates transactionally under the same advisory lock.
- PostgreSQL application startup performs read-only schema/history validation even in development. Production SQLite startup also validates read-only and does not bootstrap a missing file. Missing or incompatible schema fails startup without silently creating/modifying production data. Local SQLite bootstrap remains available.

The driver boundary follows [Psycopg transaction documentation](https://www.psycopg.org/psycopg3/docs/basic/transactions.html). No production connection was opened. No local PostgreSQL server/client/Docker installation was found, so actual PostgreSQL execution remains unverified. Unit tests cover selection, query binding, RETURNING, transaction/lock lifecycle, migration dispatch/history and read-only startup. The full SQLite suite continues to cover application persistence, ownership, admin, sales, corrections, request replay, and threaded stale-result behavior.

## 5. Files changed/created

Changed: `.env.example`, `README.md`, `requirements.txt`, `app/__init__.py`, `app/db.py`, `app/migrations.py`, `app/routes.py`, `app/workflow.py`, `app/static/reels.js`, `app/static/reels.css`.

Created: `migrations/postgresql/000_base.sql`, `migrations/postgresql/001_checkpoint_b.sql`, `tests/test_database.py`, `tests/postgres_integration.py`, `tests/inspect_portfolio.py`, `tests/reels_runtime.cjs`, `POSTGRES_MIGRATION_RUNBOOK.md`, `POSTGRES_REELS_READINESS_REPORT.md`.

Local generated evidence is in ignored `.performance-verification` and `.pricing-verification`. Pre-existing `.test-tmp` files and reports were retained. No media assets, pricing, templates, or customer.csscd were changed. Psycopg was installed in the local ignored virtual environment and declared in requirements.

## 6. Full Python results

`python -m unittest discover -s tests`: **136 tests passed in 27.938 seconds**, including all 130 existing tests and six new database boundary tests. No tests were removed. Expected simulated provider/contact failures log errors within passing tests.

Full codec audit: **11/11 video and audio streams decoded without errors**, all current served files fast-start. Python compile checks and migration CLI help passed. `tests/postgres_integration.py` compiles but was not executed: no real local PostgreSQL server is available.

## 7. Frontend results

- Existing chat frontend harness: both scenario groups pass (duplicate/history overlap and network retry/idempotency).
- New reels runtime: 22 actual desktop/mobile item checks, 10 forced-autoplay-rejection click/tap recoveries, and one controlled stale-promise race pass.
- Existing media browser suite: mobile, desktop, fallback, reduced-motion cases pass; all 11 media items checked per standard mode.
- Existing pricing browser suite: desktop, tablet, mobile and small mobile pass, including navigation, pricing modal keyboard/focus, Start a Project, contact submission, chatbot response and mobile layout.
- Existing visual comparison: desktop/mobile text and geometry preserved. Portfolio audit completed for both devices with zero initial portfolio transfer.
- JavaScript syntax and git diff whitespace checks pass.

The first new delayed-promise fixture timed out because scrolling to the top did not move the first reel beyond the scheduler's cancellation margin. The fixture now scrolls to the page bottom to exercise genuine unload/reload; the final suite passes. No failing functional assertion was removed.

## 8. Remaining PostgreSQL production steps

Follow `POSTGRES_MIGRATION_RUNBOOK.md`. Before activation: obtain an actual consistent backup of the current production SQLite contents; run real PostgreSQL migration/application/concurrency integration tests; implement and rehearse data transfer into an empty staging target, preserving rows/IDs/revisions/ownership/request replay/evidence and source migration audit history; reset identity sequences after imported IDs; verify counts, constraints and restore/rollback. Validate staging SSL/connectivity, capacity, backups and stable session secret. Only a separately authorized later step may create Render Postgres, change DATABASE_URL, or deploy.

The opt-in real integration runner accepts only a loopback database whose name includes test, creates a unique private schema, migrates twice, validates startup, and tests conversations/leads/messages/chat_requests/sales_transitions, ownership, replay, admin/status and concurrent duplicate reservation. It cleans up only its schema. Additional real-server stale-correction/load tests and production transfer remain required. No data-transfer or PostgreSQL activation is claimed complete.

## 9. What could still fail on Render

- Existing free-service SQLite storage is ephemeral; a replacement may lose data. The new production startup intentionally fails on a missing/unmigrated schema instead of silently creating an empty database.
- PostgreSQL behavior has not run against a real server. SQL/migration permissions, SSL/networking, version, advisory-lock behavior under concurrency, and connection limits need staging verification.
- Incorrect data import/identity reset can break references, request replay, or subsequent inserts. Changing the session secret invalidates existing visitor ownership cookies.
- Production media files, case, range response/cache behavior, client network stalls, or device autoplay policy can differ from local Flask/Chrome. No live production trace was captured.
- Mobile validation uses real Chrome with mobile viewport/touch emulation. Physical iOS/Safari, Safari media decoder compatibility, and actual user devices remain unverified. HE-AAC remains unchanged because it is shared by working reels and no codec failure was demonstrated locally.
- Media errors from permanently unavailable files cannot be solved by a play button; it provides recovery for transient failures/autoplay restrictions while preserving the poster.

## 10. SAFE TO COMMIT

**YES — safe to commit the intended code, migrations, tests, runbook and report for review.** Local SQLite regressions and browser checks pass; no credentials or media-quality changes are included. Exclude temporary databases/server helpers and unrelated pre-existing untracked reports/customer.csscd unless separately intended.

This is not approval to activate PostgreSQL or deploy: real-server integration and migration/data-transfer rehearsal are required first. Nothing has been staged or committed. Stopped after implementation, tests and this report; Checkpoint C remains untouched.
