# WebPuente – Production Readiness Checklist

Tick each box yourself. Items marked **(verify)** are things only you can confirm on your live site.
The author tested the code in a sandbox; **no live deployment has been done**, so every "(verify)" item is open until you check it.

## 1. Secrets and access
- [ ] `DJANGO_SECRET_KEY` is a long random value generated for production (not the one used locally)
- [ ] No `.env` file, password, key, or certificate-private-key is in GitHub (`git ls-files | Select-String "\.env$"` prints nothing)
- [ ] Secrets exist only in the host dashboards (Render, Vercel, Aiven)
- [ ] Database password is strong and unique; GitHub, Render, Vercel, Aiven accounts use strong passwords and two-factor sign-in
- [ ] `ADMIN_URL` changed from the default `admin/`; the admin account has a strong password
- [ ] No test accounts or test projects left in the live database

## 2. Backend configuration
- [ ] `DJANGO_SETTINGS_MODULE=core.settings.production`; `DEBUG` is not enabled
- [ ] `PYTHON_VERSION` pinned to the tested 3.13.x
- [ ] `ALLOWED_HOSTS` lists only your API address(es)
- [ ] `CORS_ALLOWED_ORIGINS` lists only your real frontend address(es) (exact, `https://`, no trailing slash)
- [ ] `FRONTEND_URL` is the real frontend address (used in reset emails)
- [ ] Start command binds `0.0.0.0:$PORT` and runs `migrate` then `gunicorn` (never `runserver`)
- [ ] Health check path `/api/health/` configured and returns `{"status":"ok","database":"ok"}` **(verify)**
- [ ] `ENABLE_API_DOCS` decision made (interactive docs at `/api/docs/` are public if left on)
- [ ] `ENABLE_WEBSITE_FETCH` and `EMBEDDINGS_ENABLED` are off unless you intentionally want them (and understand the cost/outbound requests)

## 3. Database
- [ ] MySQL is reachable only with its password and an encrypted connection (`DB_SSL_CA_PEM` / `DB_SSL`)
- [ ] Database uses `utf8mb4`
- [ ] Migrations applied; `SHOW TABLES;` lists the WebPuente tables **(verify)**
- [ ] You know what your plan's backup retention really is, and you made **your own** `mysqldump` copy
- [ ] You restored a backup into a scratch database at least once **(verify)**
- [ ] Free-plan limits understood (storage, connections, possible power-off for inactivity)

## 4. Frontend
- [ ] `VITE_API_URL` is the real API address (no trailing slash, no secrets) and the site was redeployed after setting it
- [ ] Output directory `dist`, root directory `frontend`, `vercel.json` present (page refresh and direct links work) **(verify)**
- [ ] Browser console shows no red errors on the main pages **(verify)**

## 5. HTTPS and domain
- [ ] Both addresses open with a padlock **(verify)**
- [ ] Custom domain (if any): DNS records created, certificates issued, and `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `VITE_API_URL` updated to match
- [ ] `SECURE_HSTS_SECONDS` raised to `31536000` only after HTTPS was confirmed everywhere

## 6. Email
- [ ] SMTP configured and a real password-reset email was received and worked **(verify)**
- [ ] Sender address is one you are allowed to send from; SMTP password is only in the host dashboard

## 7. Functional tests on the live site (Stage 11 of the guide)
- [ ] Register / login / logout / reload keeps session
- [ ] Import (paste and file) → match → review → approve (single + bulk with confirmation) → manual destination → undo
- [ ] Quality checks run; exports download (CSV at least; server rules reviewed and tested on a staging server before real use)
- [ ] Data persists after sign-out and after a restart/redeploy
- [ ] A second account cannot see the first account's data
- [ ] Works on a phone

## 8. Operations
- [ ] You know where the logs are (Render Logs, Vercel deployment logs) and have seen one real log line
- [ ] Free-tier behaviour understood: first request after idle is slow
- [ ] A person is named who watches usage/limits monthly and applies security updates (`pip list --outdated`, `npm outdated`, `npm audit`)
- [ ] Rollback plan: Render and Vercel can redeploy a previous version; take a database backup before releases that add migrations

## 9. Before you rely on the redirect rules
- [ ] Generated `.htaccess` / nginx rules were tested on a **staging copy** of your server
- [ ] A sample of important old URLs was checked by hand after launch (status 301 and the right final page)
- [ ] You kept the old site reachable until the redirects were confirmed
