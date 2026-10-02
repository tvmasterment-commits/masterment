# Masterment AI

Flask and SQLite lead qualification for Masterment creative production. It includes a branded chat page, deterministic structured extraction, a model-led conversational response when `OPENAI_API_KEY` is set, a no-key fallback, and a protected admin dashboard.

## Local development (Windows PowerShell)

From the project directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set these values in `.env` for local use:

- `OPENAI_API_KEY`: OpenAI key; leave blank to use the deterministic local fallback.
- `OPENAI_MODEL`: model name, default `gpt-4o-mini`.
- `APP_ENV`: `development` locally; set to `production` for deployment.
- `ADMIN_USERNAME` and `ADMIN_PASSWORD`: dashboard credentials. Production requires a non-default password of at least 16 characters.
- `FLASK_SECRET_KEY`: Flask signing key. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Production requires at least 32 characters.
- `DATABASE_PATH`: SQLite file path; default `instance/masterment.sqlite3`.
- `PORT`: local development port; default `5000`.

Replace the placeholders in `knowledge/business.json` with approved company information. Never put actual credentials in `.env.example` or source control. `.env` is gitignored.

The approved service catalog, prices, exclusions, network policies, and sales guidance are centralized in `knowledge/business.json`. `business_knowledge` contains the approved sections; `catalog` maps inquiry patterns, exact price headings, and relevant intake questions to those sections. `responses` contains the approved no-key response wording. Keep price headings consistent with the catalog when editing and run the complete test suite. Prices are read from the approved sections, not copied into Python or frontend files.

The model receives the complete knowledge and conversation context. Local checks reject unsupported dollar amounts, lost starting-price qualifiers, and explicit discount/result promises. These checks are deliberately limited; mocked-model tests do not establish the quality of every possible live-model response. When no API key is configured, catalog answers and relevant intake questions remain available. A configured provider failure retains the existing error response and still saves lead details.

Expanded project requirements are stored in the existing lead `description` field, with full conversation history preserved in `messages`. No database migration, new dependency, or new environment variable is required for the catalog update. Hours, public contact details, and booking policies still need owner-approved values where marked as placeholders.

Start local development with:

```powershell
python run.py
```

Open the customer experience at http://127.0.0.1:5000/, admin at http://127.0.0.1:5000/admin, and health check at http://127.0.0.1:5000/health.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The Pricing navigation item opens a native dialog rendered from the same approved knowledge as the chatbot. Presentation text lives in `public_pricing`; monetary values and monthly inclusions are read through the shared `offer_data` parser. No separate public pricing database is maintained. Package selection prefills the existing contact message, preserving the visitor's draft; it does not create or submit a lead until the existing form is submitted. If the combined text would exceed the form's existing limit, the draft is preserved without adding the selection.

Optional browser regression checks use Playwright as a development tool and an installed Chrome executable:

```powershell
node tests/browser_pricing.cjs
```

Performance verification and the saved local comparison are documented in `PERFORMANCE_REPORT.md`.
Public HTML, CSS, and JavaScript negotiate gzip compression; videos retain byte-range support.
Static URLs receive content hashes at application startup. Matching versions may be cached for a year;
HTML, unversioned assets, and stale versions revalidate. Restart application workers whenever static
files change so the URL hashes and precompressed files are refreshed. No production dependency was added.

If Playwright is installed outside this project, set `NODE_PATH` to that installation's `node_modules` directory. `PYTHON` and `CHROME_PATH` can override the test executable paths. The test starts its own loopback-only Flask server on port 5057, uses an isolated database, and saves screenshots/results under ignored `.pricing-verification/`. It checks desktop, tablet, and two mobile viewport sizes, navigation, details, focus, scrolling, package handoff, local form submission, and the existing chatbot. There is no new runtime dependency.

## Production start

Install the pinned-range dependencies from `requirements.txt`, then set production secrets in the hosting platform's secret manager or process environment. Example for PowerShell:

```powershell
$env:APP_ENV = "production"
$env:FLASK_SECRET_KEY = "<generated random value, at least 32 characters>"
$env:ADMIN_USERNAME = "<unique admin username>"
$env:ADMIN_PASSWORD = "<unique password, at least 16 characters>"
$env:OPENAI_API_KEY = "<OpenAI API key>"
$env:DATABASE_PATH = "D:\MastermentData\masterment.sqlite3"
waitress-serve --listen=0.0.0.0:8000 run:app
```

`python run.py` remains for local development. Waitress is the production WSGI server and is suitable for Windows. Terminate TLS at a trusted reverse proxy or hosting load balancer; expose the service publicly only over HTTPS. Do not enable Flask debug mode in production.

## Database persistence and deployment considerations

SQLite stores the leads, conversations, and messages in `DATABASE_PATH`. Production must provide a durable, writable local disk or persistent volume for that file; ephemeral container filesystems lose data when replaced. Keep the database on a local mounted filesystem, use regular encrypted backups, and test restore procedures. Run one application instance against a SQLite file; do not share that file across hosts or a network filesystem. Set the absolute database path and ensure its parent directory is writable by the app process.

The chat endpoint has a small in-process limit of 20 messages per IP per 60 seconds. This helps with basic abuse but is not a shared limiter across multiple processes or instances. Behind a reverse proxy, configure client-IP forwarding only from trusted proxy addresses or rate limiting may see all traffic as the proxy.

## Security notes and remaining work before public launch

- Admin routes require environment-configured HTTP Basic credentials. Admin status changes also require a session CSRF token. Serve behind HTTPS; Basic credentials are not safe over plain HTTP.
- Production startup rejects a missing/short Flask secret and default/short admin password. Session cookies are HTTP-only, SameSite=Lax, and Secure in production.
- User messages are length-limited and validated. Jinja autoescapes HTML templates; browser chat text is inserted with `textContent`. SQL values are parameterized, and dynamic update columns come from a fixed allowlist.
- The app returns generic errors for model failures and does not expose API keys to frontend code. Keep secrets in the deployment secret manager and rotate any key that was committed or shared.
- This is not a complete security certification. Add shared rate limiting, deployment-specific proxy/host configuration, monitoring and alerting, data retention controls, dependency update review, and an incident/backup process before a broad public launch. Review CSRF/session/auth behavior and HTTPS configuration in the actual hosting environment.

## Structure

```text
app/
  assistant.py       Extraction, conversational response, approved knowledge and fallback
  db.py              SQLite schema and lead persistence
  limiter.py         Lightweight process-local chat request limiter
  routes.py          Customer API, health check, and authenticated admin routes
  static/            Responsive visual design and chat client
  templates/         Customer, lead list, and lead detail views
knowledge/
  business.json      Editable, approved Masterment facts and placeholders
tests/
  test_app.py        Customer flow, security, extraction, model behavior, and admin checks
run.py               Local Flask entry point and Waitress WSGI target
```
