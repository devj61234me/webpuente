# WebPuente

**Migrate Smarter. Redirect with Confidence.**

WebPuente helps you move a website without losing visitors or search rankings. You give it the **old** site's URLs and the **new** site's URLs; it suggests which old page should redirect to which new page, **explains each suggestion**, lets you review and approve every decision, checks the result for common redirect problems, and exports redirect rules for your server.

A person always decides. Suggestions are never approved automatically, and scores are a guide to what to check first, not proof that two pages are equivalent.

* **Deploying it?** → [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) (12 stages, Windows/PowerShell, beginner-friendly)
* **Going live?** → [`PRODUCTION_CHECKLIST.md`](PRODUCTION_CHECKLIST.md)
* How it works → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · API reference → [`docs/API.md`](docs/API.md) (and interactive docs at `/api/docs/` on a running backend)

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 (JavaScript), Vite, React Router, Axios, Tailwind CSS, Recharts, Lucide React, React Toastify |
| Backend | Django 5.1, Django REST Framework, Simple JWT, django-cors-headers, drf-spectacular (OpenAPI), WhiteNoise, gunicorn |
| Database | MySQL (Django ORM + migrations). Developed and tested on MariaDB 10.11; designed for MySQL 8 |
| Jobs | in-process thread (default), or a separate `run_worker` process, or inline |

## What it does

* **Accounts:** register, login, logout (this device or everywhere), automatic token refresh, password reset by email, profile, change password, delete account. Each user only ever sees their own data.
* **Projects:** one per website move; settings for how URLs are compared, matching weights and thresholds, default redirect type, paths that must never be redirected; delete requires typing the project's name; re-running keeps your decisions; compare runs; activity log.
* **Import:** CSV, Excel (.xlsx) or pasted lists, with a column-mapping step, validation, de-duplication and clear reporting of every skipped row. Original URLs are always preserved; normalization is only used for comparing.
* **Matching engine (explainable):** exact URL → same path → page-name (slug) → folder structure → title / heading / description evidence → optional AI "meaning" comparison (off by default, falls back cleanly). Every suggestion has a score, a confidence band (high ≥ 90, medium ≥ 70, low, no match), plain-language reasons, a per-signal breakdown, close-call (ambiguity) flags and alternative candidates. No destination is ever invented.
* **Review workspace:** filters, search, sorting, side-by-side details, approve / reject / reset / **undo**, choose another destination (or type one), notes, redirect type per row, bulk actions that ask for confirmation and report what was skipped, and extra confirmation for low-confidence and many-to-one decisions.
* **Quality checks:** missing destinations, orphan new pages, duplicates, self-redirects, loops, chains, many-to-one, home-page mass redirects, weak matches, excluded paths. The page also lists what the checks **cannot** know.
* **Dashboards:** computed from real database data (counts, confidence mix, review progress, risks, trends across runs).
* **Exports:** CSV, Excel, JSON, Apache `.htaccess`, Nginx map, and a full report. Spreadsheet formula-injection is neutralized; server rules skip dangerous rows and carry a "test before going live" warning; every export is recorded.
* **Optional (off by default):** AI embeddings, fetching page titles from live public websites (SSRF-protected).
* **No fake data anywhere.** A new database is empty. Test fixtures exist only inside the automated tests.

## Run it on your computer

See **Stage 2 of the deployment guide** for the full, explained version. The short form (PowerShell):

```powershell
# one-time: create the MySQL database and user (SQL is in the guide), then
cd backend
py -3.13 -m venv venv ; .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then edit .env: DJANGO_SECRET_KEY and DB_PASSWORD
python manage.py migrate
python manage.py runserver    # http://127.0.0.1:8000/api/health/

# second window
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Tests

```powershell
cd backend
python manage.py test tests --settings=core.settings.test                       # in-memory SQLite, fast
python manage.py test tests --settings=core.settings.test_mysql --noinput       # same tests on your MySQL/MariaDB
cd ..\frontend
npm test
npm run build
```

Browser smoke test (needs both servers running and Playwright): see the header of `e2e/smoke.cjs`.

### Testing status when this was handed over

Built and tested in a Linux sandbox. **Verified there:**

| What | Result |
|---|---|
| Backend tests (accounts, data isolation, normalization, import, matcher, analysis/jobs, review, quality, exports, fetch safety, security/production settings) | **149 passed** on SQLite **and** on MariaDB 10.11 |
| Generated redirect rules loaded into **real nginx 1.24 and Apache 2.4.58** and requested over HTTP (spaces, `$`, quotes, unicode, regex characters, query strings, trailing slashes). This found and fixed two real bugs: Apache double-encoded `%XX` in destinations (`/x%20y` became `/x%2520y`), and nginx did not match a raw `$` in an old path | verified; these checks are part of the test suite and run automatically when `nginx` / `apache2` are installed |
| Frontend unit tests | **14 passed**; production build succeeds |
| Browser end-to-end run (real Chromium, real frontend, real backend, real MariaDB): register, reload keeps session, create project, paste + CSV import, matching, approve, bulk approve with confirmation, manual destination, quality checks, CSV + Nginx download, activity log, logout/login persistence, wrong-password message, no horizontal scroll at phone width, delete account | **20 / 20 checks passed** |
| Production settings under gunicorn with the real database: HTTPS redirect, health check (also over plain HTTP), API docs, admin with hashed static files, CORS allow/deny, bad `Host` rejected, startup refuses missing variables | verified |
| `manage.py check --deploy` (security checks) | clean except two intentional HSTS options |
| OpenAPI schema generation | works (some response fields are typed loosely) |

**Not verified (please test on your side):**

* **Any live deployment.** Nothing was deployed to Render, Vercel, Aiven or anywhere else; host dashboards were not operated. The guide follows the hosts' own documentation.
* **MySQL 8** itself (tests ran on MariaDB 10.11, which the hosting provider's MySQL differs from in small ways).
* **Docker files** (`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`): written but never run; Docker was not available.
* **Real email (SMTP)**, a **real embeddings provider**, and **fetching real websites**. Their logic is covered with mocks only.
* Generated rules were tested on one version each of nginx (1.24) and Apache (2.4.58) in a sandbox only. Other versions, **shared hosting that restricts `.htaccess`** (`AllowOverride None`), and CDNs/proxies in front of your server were not tested. Always test on a staging copy.
* Behaviour under heavy load (a 1,500-URL matching run completes in the tests; much larger projects were not measured).
* Browsers other than Chromium; screen readers (basic labels, roles and focus handling are in place, but there was no formal accessibility audit).

## Known limits and trade-offs

* **Jobs in `thread` mode are lost if the server restarts mid-run.** The run is marked failed and can be started again; nothing is half-saved. Use `JOB_MODE=worker` plus a worker service for sturdier processing.
* **Uploaded files are not stored.** They are parsed in memory; the URLs are saved and the file's SHA-256 and name are recorded. Exports are stored in the database.
* **Login tokens:** the refresh token lives in browser local storage (the access token is memory-only) so people stay signed in. HTTP-only cookies would be stronger and are a possible future change.
* **Query strings in redirect rules.** Rules for old URLs that *have* a query string match the *sorted, normalized* query exactly (unusual orderings need manual rules). For plain old paths, the Apache file also redirects requests that carry extra parameters (such as `?utm_source=…`) and passes them on, while the nginx map matches the exact request line, so those requests are *not* redirected by the nginx file. Adjust by hand if you need the same behaviour on both.
* **Semantic matching** only re-scores candidates already shortlisted by text similarity, and costs money with most providers.
* **Free hosting** has real limits (sleep after inactivity, small memory, no background workers). See the table at the top of the deployment guide.
* **Dependency advisories (`npm audit`, checked 2026-10-28 after upgrading axios, react-router-dom, vite, vitest and postcss to their patched releases within the same major versions).** 8 advisories remain:
  * *React Router 6 (moderate, ships in the site):* an open-redirect via backslash paths in `<Link>`/`useNavigate`, and a server-side-rendering hydration issue. The app only navigates to its own fixed paths and does no server-side rendering. The real fix is React Router 7, a breaking upgrade that was not attempted.
  * *vite 5 / esbuild / vitest 2 / tinypool (development and test tooling only):* these run on your computer while you develop or test, never on the server or in visitors' browsers (the built site contains none of them). Fixing needs vite 8 / vitest 5, major upgrades that were not attempted. Avoid opening untrusted websites while `npm run dev` is running.
  * Re-run `npm audit` and `pip list --outdated` before you go live and again every month.

## Project layout

```
backend/    Django project (core/ settings+urls, accounts/, projects/, services/ = matching, import, export, safe fetch, tests/)
frontend/   React app (src/pages, src/components, src/api, src/auth, src/lib, src/test)
docs/       ARCHITECTURE.md, API.md
e2e/        Playwright smoke test
DEPLOYMENT_GUIDE.md, PRODUCTION_CHECKLIST.md, docker-compose.yml
```

## Security notes in brief

Passwords hashed (Django); JWT access (15 min) + rotating, revocable refresh tokens; per-user data isolation enforced in every query and tested; rate limits on login/import/analysis/export/fetch; upload size and row limits; formula-injection protection on exports; SSRF protection on optional fetching; consistent error format that never leaks internals; production settings refuse to start without safe configuration; no secrets in the repository (`.env` is git-ignored, `.env.example` has placeholders only).

## License / responsibility

You are responsible for testing generated redirect rules on a staging copy of your own server before using them in production.
