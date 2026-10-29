# WebPuente architecture

## Overview

```
React SPA (Vite build, static files)
   │  JSON over HTTPS, Authorization: Bearer <JWT>
   ▼
Django + DRF  ──────────────►  MySQL (all state)
 ├─ accounts/   users, JWT, password reset
 ├─ projects/   models, views, jobs, audit
 ├─ services/   urlnorm · importer · matcher · embeddings · risks · exporters · safe_fetch
 └─ core/       settings (base/development/production/test), errors, pagination, throttles, health
```

The frontend is a static single-page app; it holds no data and no secrets. The backend is a normal Django project served by gunicorn. There is no cache, queue broker, or file store to operate: **MySQL is the only stateful part.**

## Data model (projects/models.py)

* `MigrationProject` (owner, old/new site URL, settings JSON, `last_decision_at`, `quality_checked_at`)
* `URLImportBatch` – every import (counts, row errors, file SHA-256; the file itself is **not** kept)
* `OldURL`, `NewURL` – share an abstract base: `original_url` (kept exactly as supplied), `normalized_url`, `url_hash` (SHA-256 used for uniqueness, because MySQL cannot index very long text), optional title / meta description / H1 / canonical / status code
* `AnalysisRun` – one matching run: status, progress, heartbeat, stats and warnings
* `MappingRecommendation` – the engine's suggestion per old URL **per run** (score, band, match type, reasons, per-signal components, alternatives, ambiguity). Immutable history
* `MappingReview` – the human decision per old URL (one per old URL, survives re-runs): status, origin (auto/manual), final destination, redirect type, note, `prev_state` for undo, who/when
* `RedirectRisk` – quality findings; `ExportJob` – generated files (bytes in the database); `AuditLog` – who did what

Separating **recommendation** (what the engine said in run N) from **review** (what a person decided) is what lets a re-run preserve decisions and lets two runs be compared.

## Matching engine (services/matcher.py)

1. URLs are normalized for *comparison only* (case, trailing slash, `www`, query handling, tracking-parameter removal are all project settings).
2. A cheap inverted index over path tokens shortlists up to `MATCH_MAX_CANDIDATES` new pages per old URL, so cost grows roughly linearly, not quadratically.
3. Scoring: exact URL = 100; same path on a different host = 97; otherwise a weighted blend of page-name (slug), path, folder hierarchy, title, H1, meta description and (optionally) semantic similarity. Weights are **renormalized over the evidence that actually exists**, so a URL-only import is judged on URL signals alone and is labelled "URL only". Approximate matches are capped (default 95) so "very similar" never looks like "certainly the same".
4. Bands from thresholds (default high ≥ 90, medium ≥ 70, low ≥ 40, below → no match). A runner-up within `ambiguity_gap` points flags the row as ambiguous. Every result carries human-readable reasons and up to three alternatives.
5. **No destination is ever invented.** Below the minimum score the row is "no match".

Semantic matching (optional): vectors for title/path text are requested from an OpenAI-compatible `/embeddings` endpoint (batched, retried, capped by `EMBEDDINGS_MAX_PAGES`) and only re-score the shortlisted candidates. Any provider failure produces a warning and the run completes without it.

## Decisions and re-runs

`MappingReview.status` is `pending`, `approved` or `rejected`. On a re-run: approved and manually chosen decisions are kept; a rejected decision is kept only if the engine suggests the same destination again, otherwise the row returns to pending for a fresh look; new old URLs get new reviews. A destination removed by a "replace" import resets the decisions that pointed to it.

## Jobs (projects/jobs.py, analysis.py)

`POST /analyze/` locks the project row (`select_for_update`), refuses a second active run, and claims the run with an atomic status update. `JOB_MODE` then decides who executes it: a thread in the web process, a separate `manage.py run_worker` process polling the database, or inline (tests). The run writes a heartbeat; runs without a heartbeat for `JOB_STALE_MINUTES` are marked failed. Results are written in one transaction, so a crash leaves **no** half-saved recommendations.

## Quality checks (services/risks.py)

Pure functions over the current proposal: missing destination, orphan new URLs, duplicate sources, many-to-one, self-redirect, loops, chains, invalid destination, weak match, home-page redirects (single and mass), excluded patterns. Findings are tagged `proposal` or `supplied_data` and a fixed list states what cannot be checked from the data (existing server redirects, whether pages really load, whether a destination is truly equivalent).

## Exports (services/exporters.py)

CSV/XLSX/JSON with formula-injection protection. **Apache:** `RewriteRule … [R=n,L,NE]` with every `%` escaped as `\%` (without that, mod_rewrite deletes `%20`-style sequences and Apache double-encodes destinations); rules for URLs with a query string come first. **nginx:** one `map $request_uri` per redirect status (nginx cannot take a variable status in `return`), keys literal, `$` in destinations percent-encoded. Both formats pass an internal syntax check *and* are exercised by tests against real nginx 1.24 / Apache 2.4.58 when those are installed.

## Security design

* Auth: Django password hashing + strong validators; SimpleJWT 15-minute access tokens, 7-day rotating refresh tokens with a blacklist; revoke-all on password change/reset.
* Isolation: one `get_project(request, pk)` helper filters by owner; every nested resource is reached through it; tested with a second user against projects, mappings (single and bulk), imports, analysis, exports and downloads, and the dashboard.
* Input: size/row/count limits, URL validation (only http/https, no credentials, no control characters), strict column-map validation, bounded pagination and bulk sizes.
* Output: one error format, no stack traces, generic login failure, Content-Disposition + `nosniff` on downloads.
* Network: CORS allow-list from environment; production refuses to start without `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DB_PASSWORD` and a real `FRONTEND_URL`; HTTPS redirect and secure cookies; HSTS configurable.
* Optional fetching (SSRF): standard ports only; every resolved address must be public (IPv4-mapped IPv6 included); the connection is pinned to the checked IP; each redirect hop is re-checked; robots.txt is obeyed; size, time and per-request counts are capped.
* Frontend: no raw HTML rendering; access token in memory only; refresh token in localStorage (documented trade-off); a single in-flight refresh request.

## Testing

`backend/tests` (149 tests) run on SQLite (`core.settings.test`) or on your MySQL (`core.settings.test_mysql`); `frontend/src/test` (Vitest) covers token handling, error mapping and shared UI; `e2e/smoke.cjs` drives a real browser through the full workflow. Test data is made up and exists only inside tests.
