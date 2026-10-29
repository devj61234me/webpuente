# WebPuente – Deployment Guide

*You deploy WebPuente yourself. Nothing here has been deployed for you, and nothing in this project logs in to a hosting account on your behalf. Follow the stages in order. Every stage says **where** to work, **what** to do, **what you should see**, and **what to do if you don't**.*

> **Honest status of this guide.** The code was tested by its author on Linux with Python 3.13 and MariaDB 10.11, and the production settings were started under gunicorn (see `README.md → Testing status`). The *host dashboards* (Render, Aiven, Vercel, GitHub) were **not** operated by the author. Their screens and wording change, so each step names the setting you need rather than promising an exact button position. Where a host rule matters I give the official link; **check those pages for current limits and prices before you rely on a free plan.**

---

## The plan in one picture

```
 Visitor's browser
        │  https
        ▼
 ┌───────────────┐   API calls (https, JSON)    ┌────────────────────────┐        ┌───────────────┐
 │ Frontend      │ ───────────────────────────▶ │ Backend (Django+DRF)   │ ─────▶ │ MySQL         │
 │ React site    │                              │ gunicorn, JWT login    │  SSL   │ database      │
 │ on Vercel     │                              │ on Render              │        │ on Aiven      │
 └───────────────┘                              └────────────────────────┘        └───────────────┘
   static files only                              also runs the matching job        all user data lives here
```

| Part | What it is | Suggested host | Why |
|---|---|---|---|
| Frontend | the website people see (static files) | **Vercel** | free static hosting, automatic HTTPS |
| Backend | the API + the matching engine | **Render** (web service) | runs Python, HTTPS built in |
| Database | MySQL | **Aiven** (free MySQL plan) | Render's own free database is PostgreSQL, but WebPuente is built for MySQL |

You can swap any host for a similar one (the app only needs: a place to run Python, a MySQL database, and a place for static files). The rest of this guide uses the three above.

### Facts about the suggested free plans (checked against the hosts' own pages while writing)

| Host | What the page says | What it means for you |
|---|---|---|
| Render free web service ([docs](https://render.com/docs/free)) | spins down after 15 minutes without traffic; waking takes about a minute; 750 free instance hours per month per workspace; no persistent disk; no shell access; *background workers and cron jobs are not free* | the **first visit after idle is slow**; uploaded files cannot be stored on disk (WebPuente does not store uploads, see Stage 12); you cannot open a shell, so admin tasks run from **your own computer** (Stage 7); the matching job runs inside the web service (`JOB_MODE=thread`) |
| Render deploys ([docs](https://render.com/docs/deploys)) | the *pre-deploy command* is for paid services | database migrations are run by the **start command** instead |
| Render Python version ([docs](https://render.com/docs/python-version)) | new services default to Python 3.14.x; you can pin with the `PYTHON_VERSION` variable | **WebPuente was tested on 3.13, so pin it** (Stage 5) |
| Aiven free MySQL ([docs](https://aiven.io/docs/products/mysql/concepts/mysql-free-tier)) | 1 GB disk, 1 GB RAM, max 76 connections, backups included, no static IP; Aiven *may power off* a free service that sees no activity | good for a trial or a small project; **not** an always-on guarantee. If it gets powered off, switch it back on in the Aiven console |
| Vercel Hobby ([docs](https://docs.vercel.com/docs/limits)) | 100 GB fast data transfer, 100 deployments per day, 45-minute build limit | plenty for this site. **Read Vercel's terms yourself about commercial use on the free plan** |

Prices and limits change. If any of these no longer holds, the *design* still works on any host that offers the three things above.

---

## Table of contents

1. [Prerequisites and accounts](#stage-1--prerequisites-and-accounts)
2. [Local installation and testing](#stage-2--local-installation-and-testing)
3. [Git setup and upload to GitHub](#stage-3--git-setup-and-upload-to-github)
4. [Production MySQL database](#stage-4--production-mysql-database)
5. [Deploy the Django backend](#stage-5--deploy-the-django-backend)
6. [Environment variables (full reference)](#stage-6--environment-variables)
7. [Migrations and the admin user](#stage-7--migrations-and-the-admin-user)
8. [Deploy the React frontend](#stage-8--deploy-the-react-frontend)
9. [Verify frontend ↔ backend ↔ database](#stage-9--verify-the-connections)
10. [Custom domain and HTTPS](#stage-10--custom-domain-and-https-optional)
11. [End-to-end production testing](#stage-11--end-to-end-production-testing)
12. [Troubleshooting, backups, maintenance, and how the moving parts work](#stage-12--troubleshooting-backups-and-maintenance)

**Order matters because of a chicken-and-egg problem:** the backend needs to know the frontend's address (for CORS and email links), and the frontend needs the backend's address. The solution is a three-step order, which Stages 5, 8 and 9 follow: (1) deploy the backend with a placeholder frontend address, (2) deploy the frontend using the real backend address, (3) go back and put the real frontend address into the backend.

---

## Stage 1 – Prerequisites and accounts

### 1.1 Accounts (all have free options; you will need an email address and, for some, a phone for verification)

| Account | Used for | Where |
|---|---|---|
| GitHub | stores your code; Render and Vercel deploy from it | https://github.com |
| Aiven | the MySQL database | https://aiven.io |
| Render | the backend | https://render.com |
| Vercel | the frontend | https://vercel.com |
| *(optional)* an email-sending service | password-reset emails | any SMTP provider |
| *(optional)* a domain registrar | your own web address | any |

Tip: sign in to Render and Vercel **with your GitHub account**; it makes connecting the repository one click.

Some hosts ask for a payment card even for free plans. Read each sign-up screen carefully. **Never paste a card number or any password into a chat or a file in the project.**

### 1.2 Software on your Windows computer

| Tool | Version | Check it with (PowerShell) | Download |
|---|---|---|---|
| Python | **3.13** (3.11–3.13 are fine) | `py -3.13 --version` | https://www.python.org/downloads/ (tick **“Add python.exe to PATH”**) |
| Node.js | 20 LTS or 22 LTS | `node -v` and `npm -v` | https://nodejs.org |
| Git | any recent | `git --version` | https://git-scm.com |
| MySQL **or** MariaDB (for local testing) | MySQL 8.x or MariaDB 10.6+ | `mysql --version` | https://dev.mysql.com/downloads/installer/ |
| *(optional)* GitHub Desktop | – | – | https://desktop.github.com |

> **Python 3.14**: if you have only 3.14, install 3.13 too. The pinned libraries were not tested on 3.14.

**Expected result of Stage 1:** the four version commands print versions and you can sign in to the four websites.

---

## Stage 2 – Local installation and testing

*Work on your own computer, in **PowerShell**. Replace `C:\Projects\webpuente` with wherever you keep the project.*

Always get the app working on your computer before putting it on the internet. If it fails here, it will fail on the host too, and local errors are much easier to read.

### 2.1 Create the local database

Open **MySQL Workbench** (or the `mysql` command line) as the `root` user and run:

```sql
CREATE DATABASE webpuente CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create the user for BOTH "localhost" and "127.0.0.1". They count as different hosts, and a missing one causes error 1045.
CREATE USER 'webpuente_user'@'localhost'  IDENTIFIED BY 'CHOOSE_A_PASSWORD';
CREATE USER 'webpuente_user'@'127.0.0.1' IDENTIFIED BY 'CHOOSE_A_PASSWORD';
GRANT ALL PRIVILEGES ON webpuente.*       TO 'webpuente_user'@'localhost';
GRANT ALL PRIVILEGES ON webpuente.*       TO 'webpuente_user'@'127.0.0.1';

-- Only needed if you want to run the test suite against MySQL (Django makes a temporary "test_webpuente" database):
GRANT ALL PRIVILEGES ON `test\_webpuente`.* TO 'webpuente_user'@'localhost';
GRANT ALL PRIVILEGES ON `test\_webpuente`.* TO 'webpuente_user'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### 2.2 Backend

```powershell
cd C:\Projects\webpuente\backend
py -3.13 -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell says *“running scripts is disabled”*, run this once and try again (it only affects this window):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

You should now see `(venv)` at the start of the line.

```powershell
pip install -r requirements.txt
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Open `backend\.env` in Notepad and set:

* `DJANGO_SECRET_KEY=` → paste the long random text printed above
* `DB_PASSWORD=` → the password you chose in 2.1
* leave everything else as it is for local work

Then:

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Expected:** `migrate` prints a list of `OK` lines; `runserver` prints `Starting development server at http://127.0.0.1:8000/`. Open http://127.0.0.1:8000/api/health/ → you should see `{"status":"ok","database":"ok"}`. Open http://127.0.0.1:8000/api/docs/ for the interactive API documentation.

Leave this window running.

### 2.3 Frontend (a second PowerShell window)

```powershell
cd C:\Projects\webpuente\frontend
npm install
npm run dev
```

**Expected:** `Local: http://localhost:5173/`. Open it. In development the frontend forwards `/api` calls to the backend automatically, so no extra setting is needed.

### 2.4 Run the automated tests

Backend (fast, uses a temporary in-memory database, no MySQL needed):

```powershell
cd C:\Projects\webpuente\backend
.\venv\Scripts\Activate.ps1
python manage.py test tests --settings=core.settings.test
```

Expected ending: `Ran 149 tests … OK` (a few extra tests that start a real nginx or Apache are skipped automatically if those programs are not installed on your computer).

Same tests on your real MySQL (needs the extra grant from 2.1):

```powershell
python manage.py test tests --settings=core.settings.test_mysql --noinput
```

Frontend:

```powershell
cd C:\Projects\webpuente\frontend
npm test
npm run build
```

Expected: `14 passed`, and `✓ built in …`.

### 2.5 A quick manual try (5 minutes)

1. Register an account at http://localhost:5173.
2. **New project** → name it, enter any two addresses (for example `https://old.example.com` and `https://new.example.com`).
3. **Import URLs** → paste a few old URLs (one per line) → *Preview* → *Import*. Switch “Which list is this?” to *New website URLs* and import the new ones.
4. **Overview → Find matches** → **Review** → approve a row → **Export** → *Create and download*.

If this works, the app is healthy. Stage 11 repeats this on the live site.

---

## Stage 3 – Git setup and upload to GitHub

*Goal: put the code in a GitHub repository **without** any secret. Work in PowerShell in the project's top folder.*

### 3.1 What must never be uploaded

| Never commit | Why |
|---|---|
| `backend\.env` (and any `.env.*` except `.env.example`) | holds your secret key and database password |
| `backend\venv\`, `frontend\node_modules\` | huge, rebuilt by the host |
| any file containing a password, API key, or card number | anyone who can read the repository could use it |

The included `.gitignore` already ignores these. **Verify it anyway** (3.3).

### 3.2 Create the repository

On https://github.com click **New repository** → name `webpuente` → *Private* is a good default (you can make it public later) → **do not** tick “Add a README” → *Create repository*. Copy the address it shows, like `https://github.com/YOUR-NAME/webpuente.git`.

```powershell
cd C:\Projects\webpuente
git init
git add .
git status
```

### 3.3 Check before you commit (important)

`git status` lists what will be uploaded. Make sure **none** of these appear: `.env`, `venv`, `node_modules`. Then run:

```powershell
git ls-files | Select-String -Pattern "\.env$|\.pem$|venv|node_modules"
```

**Expected: no output.** If a line appears, run `git rm --cached -r <that path>` and check `.gitignore` before continuing.

```powershell
git commit -m "WebPuente: first version"
git branch -M main
git remote add origin https://github.com/YOUR-NAME/webpuente.git
git push -u origin main
```

GitHub may open a browser window to sign you in the first time. **Expected:** after `git push`, refresh the repository page and you see `backend`, `frontend`, `README.md`, `DEPLOYMENT_GUIDE.md`.

**If you pushed a secret by mistake:** deleting the file in a later commit is **not** enough, because it stays in history. Treat that secret as stolen: change the password / create a new secret key, then ask for help cleaning the history.

---

## Stage 4 – Production MySQL database

*Work in the Aiven web console. (Another MySQL provider works the same way: you need a host, port, user, password, database name, and a CA certificate if it requires encryption.)*

1. Sign in to Aiven → **Create service** → choose **MySQL** → choose the **Free** plan (see the limits in the table at the top) → pick a cloud region **close to where your Render backend will run** (low delay matters because every request talks to the database) → **Create**.
2. Wait until the service shows as **Running**.
3. Open the service's **Overview**. Note these values (write them in a private note, not in the project):
   * **Host**, **Port**, **User**, **Password**, and the **database name** shown (often `defaultdb`)
   * Download the **CA certificate** (a `ca.pem` file) from the same page. It is **public** information, not a secret.
4. Optional but recommended: create a dedicated database for WebPuente. Using the Aiven console's database/user tools (or any MySQL client with the values above):

   ```sql
   CREATE DATABASE webpuente CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   Then use `webpuente` as `DB_NAME`. If you skip this, use the default database name shown in the console.
5. **Allowed IP addresses.** Free services have no static IP, and Render's free instances do not have a fixed address either, so you cannot restrict the database to one IP. Leave the default. The protection comes from the strong password and mandatory encryption. If your computer later cannot connect (Stage 7), check the service's *allowed IP addresses* setting.

**Expected result:** you have Host, Port, User, Password, Database name and `ca.pem`.

**Test the connection from your computer** (optional but saves time later). In PowerShell:

```powershell
cd C:\Projects\webpuente\backend
.\venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "core.settings.development"
$env:DJANGO_SECRET_KEY = "temporary-test-key-1234567890"
$env:DB_HOST = "THE-HOST"; $env:DB_PORT = "THE-PORT"; $env:DB_USER = "THE-USER"
$env:DB_PASSWORD = "THE-PASSWORD"; $env:DB_NAME = "webpuente"
$env:DB_SSL_CA = "C:\path\to\ca.pem"
python manage.py check --database default
python -c "import django; django.setup(); from django.db import connection; c=connection.cursor(); c.execute('SELECT 1'); print('database reachable:', c.fetchone())"
```

**Expected:** `database reachable: (1,)`. These `$env:` values exist only in this PowerShell window and vanish when you close it. If this fails, jump to *Troubleshooting → Database connection errors*.

---

## Stage 5 – Deploy the Django backend

*Work in the Render dashboard (https://dashboard.render.com).*

### 5.1 Create the web service

1. **New +** → **Web Service** → connect your GitHub account if asked → select the `webpuente` repository.
2. Fill in:

| Setting | Value |
|---|---|
| Name | `webpuente-api` (your address becomes `https://webpuente-api.onrender.com`; if the name is taken Render adds letters, so **read the real address it shows**) |
| Region | the same area as your database |
| Branch | `main` |
| **Root Directory** | `backend` |
| Runtime / Language | **Python 3** |
| **Build Command** | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| **Start Command** | `python manage.py migrate --noinput && gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120` |
| Instance type | Free (or a paid type for always-on service) |
| Health Check Path *(under Advanced)* | `/api/health/` |

Why these commands:

* `collectstatic` gathers the admin site's CSS so it displays correctly.
* `migrate` creates/updates the database tables every time the service starts (Render's pre-deploy command is not available on free plans). It is safe to run repeatedly.
* `gunicorn` is the production web server. **Never** use `manage.py runserver` on a server.
* `--workers 1 --threads 8` keeps memory use small on a small instance. WebPuente works with more workers too (a database lock prevents duplicate matching runs).

### 5.2 Add the environment variables **before the first deploy**

The production settings **refuse to start** (on purpose) if essential values are missing, and the build step also loads them. So, still on the creation screen, open **Environment Variables** and add every variable from the *“Required for the first deploy”* table in Stage 6 **before** clicking **Create Web Service**.

For the first deploy use a **placeholder** for the frontend address (the real one does not exist yet):

```
FRONTEND_URL          = https://placeholder.example.com
CORS_ALLOWED_ORIGINS  = https://placeholder.example.com
```

(It must not contain the word `localhost`; the app rejects that in production.) You will replace these in Stage 9.

### 5.3 Create it and read the logs

Click **Create Web Service**. Render builds and starts it; open the **Logs** tab.

**Expected in the logs:**

```
Successfully installed Django-5.1.x ...
... static files copied ... post-processed
Running migrations:
  Applying contenttypes.0001_initial... OK
  ...
[INFO] Listening at: http://0.0.0.0:10000
Your service is live
```

When the page shows **Live**, open `https://YOUR-SERVICE.onrender.com/api/health/`.

**Expected:** `{"status":"ok","database":"ok"}`

If you see an error instead, go to *Troubleshooting* (missing variables and database errors are the most common first-deploy problems). Write down the service's real address, for example `https://webpuente-api.onrender.com`. You need it in Stage 8.

---

## Stage 6 – Environment variables

*An environment variable is a named setting that lives on the host instead of in your code, so secrets never enter GitHub. On Render: your service → **Environment**. On Vercel: your project → **Settings → Environment Variables**.*

**Every variable is documented in `backend/.env.example` and `frontend/.env.example`.** Those files contain placeholders only.

### Required for the first deploy (Render, backend)

| Name | Value | Notes |
|---|---|---|
| `PYTHON_VERSION` | `3.13.5` *(any 3.13.x that Render offers)* | **pins Python to the tested version**; the default is newer |
| `DJANGO_SETTINGS_MODULE` | `core.settings.production` | turns on the safe production behaviour |
| `DJANGO_SECRET_KEY` | long random text | make one with `python -c "import secrets; print(secrets.token_urlsafe(64))"`. **Treat as a password.** Changing it later logs everyone out |
| `DB_HOST` | Aiven host | from Stage 4 |
| `DB_PORT` | Aiven port | |
| `DB_NAME` | `webpuente` (or the default name) | |
| `DB_USER` | Aiven user | |
| `DB_PASSWORD` | Aiven password | secret |
| `DB_SSL_CA_PEM` | the **full text** of `ca.pem` (from `-----BEGIN CERTIFICATE-----` to `-----END CERTIFICATE-----`) | Render has no file storage, so the certificate text goes in a variable. Pasting multiple lines in the value box works. If your screen only takes one line, replace each line break with `\n` |
| `ALLOWED_HOSTS` | `webpuente-api.onrender.com` | your backend's address, **no** `https://`. Use the real one |
| `CORS_ALLOWED_ORIGINS` | `https://placeholder.example.com` | later → your Vercel address |
| `FRONTEND_URL` | `https://placeholder.example.com` | later → your Vercel address |
| `CSRF_TRUSTED_ORIGINS` | `https://webpuente-api.onrender.com` | needed for the `/admin/` login over HTTPS |
| `JOB_MODE` | `thread` | matching runs inside the web service (free hosts have no worker) |

### Recommended (Render, backend)

| Name | Value | Notes |
|---|---|---|
| `ADMIN_URL` | `manage-xxxxx/` | a less guessable admin address (keep the trailing `/`) |
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | see 6.1 |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` | from your email provider | secret: password |
| `SECURE_HSTS_SECONDS` | `3600` for now | raise to `31536000` after Stage 10 works everywhere |

### Frontend (Vercel)

| Name | Value | Notes |
|---|---|---|
| `VITE_API_URL` | `https://webpuente-api.onrender.com` | **no trailing slash**. It is baked into the site at build time and is public, so it must never hold a secret. Changing it requires a **redeploy** |

### Optional features (all off unless you set them)

| Feature | Variables | Explanation |
|---|---|---|
| AI/“meaning” matching | `EMBEDDINGS_ENABLED=true`, `EMBEDDINGS_API_KEY`, `EMBEDDINGS_MODEL`, optionally `EMBEDDINGS_BASE_URL` | Sends URL paths and page titles to an OpenAI-compatible embeddings service. **Costs money with most providers** and was not tested with a live provider. The app works fully without it |
| Fetch live page titles | `ENABLE_WEBSITE_FETCH=true` | The server downloads public pages; private/internal addresses are blocked. Off by default. Not tested against live websites |
| Limits | `MAX_UPLOAD_MB`, `MAX_IMPORT_ROWS`, `AUTH_RATE`, … | defaults are in `.env.example` |

### 6.1 Email (password reset)

* **Without email set up:** WebPuente prints the reset email in the server log (`EMAIL_BACKEND` defaults to the console). Users cannot receive it. You (the owner) can still set a user's password in the `/admin/` site (Stage 7).
* **With email:** choose any SMTP provider (check its current free allowance), create an SMTP login there, and enter the six `EMAIL_*` values. Use a sender address you are allowed to send from. Test with **Forgot password** on the live site (Stage 11).

### 6.2 Secret handling rules

* Put secrets **only** in the host dashboards. Never in GitHub, screenshots, chats, or emails.
* If a secret is exposed: change it at its source (database password in Aiven, SMTP password at the provider, `DJANGO_SECRET_KEY` anywhere) and update the variable.

After changing any variable on Render the service restarts automatically. On Vercel you must trigger a new deployment.

---

## Stage 7 – Migrations and the admin user

### 7.1 Migrations

Already done: the start command ran `migrate`. To confirm, open your Aiven database with any MySQL client and run `SHOW TABLES;`. You should see tables such as `accounts_...`, `projects_migrationproject`, `django_migrations`.

### 7.2 Create the admin (owner) user — from **your computer**

Render's free plan has no shell, so you run the command on your own computer, **pointed at the production database**:

```powershell
cd C:\Projects\webpuente\backend
.\venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "core.settings.development"
$env:DJANGO_SECRET_KEY = "temporary-key-for-this-window-only"
$env:DB_HOST = "AIVEN-HOST"; $env:DB_PORT = "AIVEN-PORT"; $env:DB_USER = "AIVEN-USER"
$env:DB_PASSWORD = "AIVEN-PASSWORD"; $env:DB_NAME = "webpuente"
$env:DB_SSL_CA = "C:\path\to\ca.pem"
python manage.py createsuperuser
```

Enter an email and a strong password when asked. **Expected:** `Superuser created successfully.`

Close the PowerShell window afterwards so the `$env:` values disappear.

> **Why the `development` settings here?** They are used only to run this one command from your computer; the live service uses `production`. The temporary secret key is irrelevant for this command.

### 7.3 Use the admin site

Open `https://YOUR-API.onrender.com/admin/` (or your `ADMIN_URL`). Sign in with the superuser. You can see users and projects, and reset a user's password. **Do not edit URL mappings by hand there; use the app.**

---

## Stage 8 – Deploy the React frontend

*Work in the Vercel dashboard (https://vercel.com/dashboard).*

1. **Add New… → Project** → import the `webpuente` repository.
2. Configure:

| Setting | Value |
|---|---|
| **Root Directory** | `frontend` (click *Edit* and choose the folder) |
| Framework Preset | **Vite** (usually detected) |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Install Command | `npm install` |

3. Open **Environment Variables** and add `VITE_API_URL` = your Render address from Stage 5 (for example `https://webpuente-api.onrender.com`, **no slash at the end**). Make sure it applies to **Production**.
4. Click **Deploy**.

The included `frontend/vercel.json` makes page refreshes and direct links (like `/projects/3/review`) work, because the site is a single-page app.

**Expected:** the build log ends with `✓ built in …` and Vercel shows a **Congratulations** screen with your address, like `https://webpuente.vercel.app`. **Copy the exact address** shown (including any extra letters).

Opening it now will show the login page, but logging in will fail with a network/CORS message until Stage 9 is done. That is expected.

---

## Stage 9 – Verify the connections

### 9.1 Put the real frontend address into the backend

In Render → your service → **Environment**, change:

```
FRONTEND_URL          = https://YOUR-SITE.vercel.app
CORS_ALLOWED_ORIGINS  = https://YOUR-SITE.vercel.app
```

(no trailing slash; use your real address; if you have a preview or custom domain too, put several in `CORS_ALLOWED_ORIGINS` separated by commas). Save. Render restarts the service; wait for **Live**.

### 9.2 Three checks, in this order

1. **Database ↔ backend:** open `https://YOUR-API.onrender.com/api/health/` → `{"status":"ok","database":"ok"}`.
   *(If the service was asleep, the first request can take about a minute.)*
2. **Backend documentation:** open `https://YOUR-API.onrender.com/api/docs/` → the interactive API page loads.
3. **Frontend ↔ backend:** open `https://YOUR-SITE.vercel.app/register` and create an account.
   *Expected:* you land on the Dashboard showing “No projects yet”.

### 9.3 Look at the browser’s own error log (very useful)

In Chrome: press **F12 → Console** and **Network**, then try to log in.

| You see | Meaning | Fix |
|---|---|---|
| `blocked by CORS policy … No 'Access-Control-Allow-Origin'` | the backend does not list your frontend address | fix `CORS_ALLOWED_ORIGINS` exactly (scheme `https://`, no trailing `/`, same spelling as the browser bar) |
| requests go to `https://YOUR-SITE.vercel.app/api/...` and return 404 | `VITE_API_URL` was empty or missing at build time | set it in Vercel and **redeploy** |
| `net::ERR_NAME_NOT_RESOLVED` / “Cannot reach the server” | wrong or misspelled API address | correct `VITE_API_URL`, redeploy |
| `400 Bad Request` from the API with HTML | the API's address is missing from `ALLOWED_HOSTS` | add it (no `https://`) |
| `502`/very slow first request | free backend waking up | wait ~1 minute and retry |

---

## Stage 10 – Custom domain and HTTPS (optional)

HTTPS already works on the `*.vercel.app` and `*.onrender.com` addresses. Only do this if you want your own name.

1. **Frontend:** Vercel → project → **Settings → Domains** → add `app.yourdomain.com` (or the bare domain). Vercel shows the DNS record to create (usually a `CNAME`, or an `A` record for a bare domain). Create it at your domain registrar's DNS page. Wait (minutes to hours). Vercel issues the HTTPS certificate itself.
2. **Backend (optional):** Render → service → **Settings → Custom Domains** → add `api.yourdomain.com` → create the DNS record Render shows → wait for the certificate.
3. **Update the settings that contain addresses** (this is the step people forget):
   * Render: `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL` → your new frontend address; `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` → add the new API address
   * Vercel: `VITE_API_URL` → the new API address, then **redeploy**
4. After everything works for a few days, raise `SECURE_HSTS_SECONDS` to `31536000` (one year) on Render. HSTS tells browsers to *only ever* use HTTPS for your site. It is hard to undo, so wait until HTTPS is confirmed everywhere before raising it.

**Expected:** the padlock appears in the browser and the site works at the new address.

---

## Stage 11 – End-to-end production testing

*Do these on the live site, in a normal browser window. The URLs below are **made up for testing**. Use them or your own lists.*

**Old URLs (paste into “Old website URLs”):**

```
https://old.example.com/about
https://old.example.com/contact
https://old.example.com/products/running-shoes
https://old.example.com/blog/best-running-shoes
https://old.example.com/blog/trail-guide
https://old.example.com/legacy/zzz-unrelated
```

**New URLs (paste into “New website URLs”):**

```
https://new.example.com/about
https://new.example.com/contact-us
https://new.example.com/shop/running-shoes
https://new.example.com/journal/best-running-shoes-2024
https://new.example.com/journal/trail-guide
https://new.example.com/
```

| # | Test | What to do | Expected result |
|---|---|---|---|
| 1 | **Registration** | `/register` → fill the form | you land on the Dashboard. A too-short password shows a clear message |
| 2 | **Login / logout** | *Sign out* (left menu) → sign in again | back on the Dashboard. A wrong password says “Incorrect email or password.” |
| 3 | **Session survives reload** | press F5 on any page | you stay signed in |
| 4 | **Password reset** *(only if email is set up)* | *Forgot your password?* → enter your email | you receive an email within a few minutes; the link opens “Choose a new password”; the new password works. Without email set up, the text is in the Render logs instead |
| 5 | **Create a project** | Projects → *New project* | you land on *Import URLs* |
| 6 | **Upload URLs** | paste the old list → *Preview* → check the columns → *Import*. Repeat for the new list (change “Which list is this?”) | “6 added” each time. Try a **CSV file** too: first line `URL,Title`, then rows |
| 7 | **Mapping recommendations** | Overview → *Find matches* | progress bar, then charts. Review shows 6 rows; **none are approved automatically**. `/about` is “Same path”, `running-shoes` pairs with `shop/running-shoes`, `zzz-unrelated` has “No destination” |
| 8 | **Explanations** | Review → *Details* on a row | a plain-language “Why this suggestion” list and a score breakdown |
| 9 | **Approval workflow** | approve one row with the ✓ button; tick several rows → *Approve…* | single approval works. Bulk approval **asks for confirmation** and reports skipped rows (for example the one with no destination) |
| 10 | **Manual choice and undo** | Details on the unmatched row → *Choose another destination…* → type `https://new.example.com/archive` → *Use*; then *Undo last change* | the row becomes approved by you, and undo restores its previous state |
| 11 | **Quality checks** | Quality → *Run checks* | findings appear (for example “No destination”); the list “What these checks cannot tell you” is shown |
| 12 | **Exports** | Export → CSV → *Create and download*; repeat with *Excel*, *JSON*, *Apache* and *Nginx* | each file downloads; CSV contains only **approved** rows; the server-rule files carry the “test before you go live” warning |
| 13 | **Database persistence** | sign out, close the browser, open the site again, sign in | your project, URLs and decisions are all still there |
| 14 | **Persistence across restarts** | Render → *Manual Deploy → Deploy latest commit* (or just let the free service sleep and wake) → reload the site | data is unchanged. Data lives in Aiven, not on the web service |
| 15 | **Data isolation** | register a **second** account in a private window | it sees an empty Dashboard and cannot open the first account's project (a direct link returns to the project list) |
| 16 | **Activity log** | project → Activity | each approval, import, check and export is listed |
| 17 | **Phone** | open the site on your phone | pages fit the screen; menu button works |
| 18 | **Cleanup** | delete the test project in *Settings → Danger zone* (type its name) | removed; and *Profile → Delete my account* removes a test account |

If any test fails, note exactly what you clicked and what you saw, then use the Troubleshooting table below.

---

## Stage 12 – Troubleshooting, backups, and maintenance

### 12.1 Troubleshooting by symptom

#### Database connection errors

| Message (in Render logs) | Likely cause | Fix |
|---|---|---|
| `OperationalError (2003, "Can't connect to MySQL server on …")` | wrong `DB_HOST`/`DB_PORT`, or the database service is **powered off** | check the values; open the Aiven console and switch the service on |
| `OperationalError (1045, "Access denied for user …")` | wrong user or password (or user not allowed from this address) | re-copy `DB_USER`/`DB_PASSWORD` from Aiven; check for stray spaces |
| `OperationalError (2026, "SSL connection error …")` or certificate verify failed | the CA certificate is missing or damaged | re-paste the complete text of `ca.pem` into `DB_SSL_CA_PEM` (both BEGIN and END lines) or set `DB_SSL=true` if your provider uses a public certificate |
| `OperationalError (1049, "Unknown database …")` | `DB_NAME` does not exist | create it (Stage 4, step 4) or use the default name from Aiven |
| `/api/health/` returns `{"status":"error","database":"unreachable"}` with HTTP 503 | database unreachable right now | same as the first two rows |
| `Too many connections` | the free plan allows 76 | keep `--workers 1`; do not run several services against the same database |

#### CORS errors
See the table in Stage 9.3. The rule: `CORS_ALLOWED_ORIGINS` must contain the **exact** frontend address, `https://…`, with no trailing slash, and the service must have restarted after the change. Check the address in the browser bar character by character.

#### Failed builds

| Where | Message | Fix |
|---|---|---|
| Render build | `ImproperlyConfigured: ALLOWED_HOSTS must be set …` (or `CORS_ALLOWED_ORIGINS`, `DB_PASSWORD`, `FRONTEND_URL`) | add the variable (Stage 6) **and redeploy** |
| Render build | `ImproperlyConfigured: DJANGO_SECRET_KEY is required` | add `DJANGO_SECRET_KEY` |
| Render build | errors while installing a package (compilation) | check `PYTHON_VERSION` is `3.13.x` (not 3.14) |
| Render start | `No open ports detected` / timeout | the start command must bind `0.0.0.0:$PORT` (copy it exactly from Stage 5) |
| Vercel build | `Could not resolve entry module` / `npm ERR! enoent package.json` | **Root Directory** must be `frontend` |
| Vercel build | `vite: command not found` | Install Command must be `npm install` (not skipped) |
| Vercel | blank page after deploy | open F12 → Console. Usually a wrong `VITE_API_URL`, or the Output Directory is not `dist` |
| Direct link (like `/projects/3`) shows 404 | `vercel.json` not in `frontend/` | it must be committed in the `frontend` folder |

#### Missing or wrong environment variables
* The service refuses to start and the log says exactly which one is missing. Fix and redeploy.
* The frontend shows “Cannot reach the server”: `VITE_API_URL` missing at build time. Add it and **redeploy** (changing it without redeploying does nothing).
* Typos: names are case-sensitive; values have no quotes and no trailing spaces.

#### API errors you may see in the app

| What the user sees | Meaning |
|---|---|
| “Cannot reach the server …” | wrong API address, the backend is asleep (wait ~1 minute) or it is down; test `/api/health/` |
| “Too many requests. Please wait …” (HTTP 429) | the protection limits were hit; wait a minute. Raise `AUTH_RATE`, `IMPORT_RATE`, … only if needed |
| “The server had a problem” (HTTP 5xx) | read the Render logs at that moment; the log line has the real error (users are never shown internal details) |
| “The file is larger than 5 MB” | raise `MAX_UPLOAD_MB` (and mind your host's memory) |
| Analysis stays on “running…” a long time | on the free tier the CPU is small; large lists take longer. If the service restarted mid-run, WebPuente marks the run failed after `JOB_STALE_MINUTES` and you can start it again. Nothing is lost |
| “analysis_in_progress” | another run is active for the project; wait for it |

#### Where to look
* **Render → your service → Logs**: backend errors, in real time.
* **Vercel → project → Deployments → (a deployment) → Logs**: build errors.
* **Browser F12 → Console / Network**: frontend errors and the exact failing request.

### 12.2 Backups

Your data is in the database; the web services hold nothing worth backing up.

* **Aiven:** backups are included in the free plan (the retention period is not stated on the page I checked; see the Aiven console for what you actually get). **Do not rely on that alone.**
* **Your own copy with `mysqldump`** (from a computer that can reach the database; MySQL's client tools must be installed):

  ```powershell
  mysqldump --host=AIVEN-HOST --port=AIVEN-PORT --user=AIVEN-USER --password --ssl-ca="C:\path\to\ca.pem" --single-transaction --no-tablespaces webpuente > webpuente-backup.sql
  ```

  Enter the password when prompted. Store the file somewhere private (it contains your users' data). Do this before every upgrade and on a regular schedule.
* **Restore test:** a backup you have never restored is a hope, not a backup. Restore into a scratch database occasionally: `mysql ... newdb < webpuente-backup.sql`.
* **User exports:** every user can download their approved redirects from the Export page; the files remain stored in the database.

### 12.3 Maintenance routine

| How often | What |
|---|---|
| each release | `git push` → Render and Vercel redeploy automatically; check `/api/health/` and do tests 2, 6, 9, 12 of Stage 11 |
| monthly | `pip list --outdated` / `npm outdated`; read Django's security release notes (https://www.djangoproject.com/weblog/); upgrade in a branch, run the tests (Stage 2.4), then deploy |
| monthly | check Render hours/bandwidth, Aiven storage (1 GB on free), Vercel usage |
| when staff leave or a secret may be exposed | rotate `DB_PASSWORD`, `EMAIL_HOST_PASSWORD`, `DJANGO_SECRET_KEY`; remove old GitHub collaborators |
| before going public | work through `PRODUCTION_CHECKLIST.md` |

Updating the database structure after a code change is automatic: the start command runs `migrate`. **Take a backup first** when a release contains a new file in `backend/projects/migrations/` or `backend/accounts/migrations/`.

### 12.4 How the moving parts work (so you can make decisions)

**Background worker.** Matching a big list takes time, so it runs as a *job* and the page shows progress. `JOB_MODE` chooses where the job runs:

* `thread` (default, used in this guide): inside the web service. Works on free hosts. Limitation: if the service restarts during a run, that run is lost (it is marked failed after `JOB_STALE_MINUTES`; start it again; nothing else is damaged, results of a failed run are never half-saved).
* `worker`: a *second* service runs `python manage.py run_worker`. This is sturdier for large projects. On Render that means a **Background Worker** service (not free), same repository, Root Directory `backend`, the **same environment variables**, and start command `python manage.py run_worker`. Then set `JOB_MODE=worker` on **both** services.
* `inline`: runs during the web request. For tests only.

**File storage.** WebPuente does **not** store uploaded files. A CSV/Excel upload is read in memory, the URLs are extracted and saved in the database, and the file's fingerprint (SHA-256) and name are recorded. Export files are stored **in the database**. This is why the free web service's lack of disk does not matter. The price is that very large exports use database space (limits: `MAX_EXPORT_ROWS`, 1 GB on the free database).

**Email.** Only used for password reset. Set up SMTP (6.1) for real use.

**Optional AI (embeddings).** Off by default. The matcher is fully explainable without it (URL, path, folder, page-name, title, heading and description evidence). When turned on, URL paths and titles are sent to the provider you configure, only after you tick the option in the project's Settings; it may cost money, and if the provider fails the run completes without it and tells the user.

**Website fetching.** Off by default. When on, the server downloads only public pages on standard ports, checks every address (and every redirect hop) is public, obeys `robots.txt`, and limits size and time.

**Login security.** Passwords are stored hashed. Login uses short-lived (15 min) access tokens and 7-day refresh tokens that rotate and can be revoked (*Profile → Sign out everywhere*). The refresh token is kept in the browser's local storage so people stay signed in; the access token lives only in memory. The trade-off: a script injected into the page could read the refresh token, which is why the app never renders raw HTML. Moving to HTTP-only cookies is a possible future hardening.

### 12.5 Official documentation

* Render: https://render.com/docs/free · https://render.com/docs/deploys · https://render.com/docs/python-version
* Aiven MySQL free plan: https://aiven.io/docs/products/mysql/concepts/mysql-free-tier
* Vercel limits: https://docs.vercel.com/docs/limits
* Django deployment checklist: https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/
* Vite environment variables: https://vite.dev/guide/env-and-mode

---

**You are done when:** Stage 9's three checks pass, Stage 11's tests 1–15 pass, and `PRODUCTION_CHECKLIST.md` has no unticked item you care about.
