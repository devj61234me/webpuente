# WebPuente API reference

The backend publishes an always-current, interactive reference of every endpoint at **`/api/docs/`** (Swagger UI) and the machine-readable OpenAPI schema at **`/api/schema/`** (switch off with `ENABLE_API_DOCS=false`). This page explains the conventions and lists the endpoints in plain words.

Base path: `/api`. All bodies are JSON unless stated (file uploads use `multipart/form-data`).

## Conventions

**Authentication.** `POST /api/auth/login/` returns `{"user": {...}, "access": "...", "refresh": "..."}`. Send `Authorization: Bearer <access>` on every other call. Access tokens last 15 minutes; `POST /api/auth/refresh/` with `{"refresh": "..."}` returns a new access token **and a new refresh token** (the old one stops working). Refresh tokens last 7 days and can be revoked (`logout`, `logout-all`, password change).

**Errors.** Every error has the same shape and never contains internal details:

```json
{"error": {"code": "many_to_one_confirmation_required", "message": "2 other old URL(s) already point to this destination. …", "details": {"count": 2}}}
```

`code` is stable and meant for programs; `message` is for people; `details` holds field errors (`{"field": ["message"]}`) or extra facts. Common HTTP statuses: 400 validation, 401 not signed in, 403 forbidden/feature off, 404 not found **(also returned for other users' data, so existence is never revealed)**, 409 conflict (for example an analysis already running), 413 too large, 429 rate limited.

**Pagination.** List endpoints take `?page=1&page_size=50` (maximum 100) and return `{"count", "next", "previous", "results"}`.

**Rate limits** (per user or address, adjustable in settings): login/registration/refresh 20 per minute, imports 60/hour, analysis 30/hour, exports 60/hour, website fetching 10/hour.

**Data isolation.** Every project query is filtered by the signed-in owner. Another user's project, mapping, export or URL is indistinguishable from one that does not exist (404).

## Endpoints

### Service
| Method | Path | Auth | What it does |
|---|---|---|---|
| GET | `/api/health/` | public | `200 {"status":"ok","database":"ok"}` or `503` if the database is unreachable. Use as the host's health check |
| GET | `/api/config/` | public | limits and feature switches the frontend needs (no secrets) |

### Account
| Method | Path | Auth | What it does |
|---|---|---|---|
| POST | `/api/auth/register/` | public | create an account (`email`, `password`, optional names) and sign in |
| POST | `/api/auth/login/` | public | sign in; the failure message is the same for unknown email and wrong password |
| POST | `/api/auth/refresh/` | public | exchange a refresh token for new tokens |
| POST | `/api/auth/logout/` | login | revoke this device's refresh token |
| POST | `/api/auth/logout-all/` | login | revoke every refresh token of the user |
| GET / PATCH | `/api/auth/me/` | login | read / update the profile (names) |
| DELETE | `/api/auth/me/` | login | delete the account and all its data; body `{"password": "..."}` |
| POST | `/api/auth/change-password/` | login | `current_password`, `new_password`; signs out other devices and returns new tokens |
| POST | `/api/auth/password-reset/` | public | request a reset email; always answers the same way |
| POST | `/api/auth/password-reset/confirm/` | public | `uid`, `token` (from the email link), `new_password` |

### Projects
| Method | Path | What it does |
|---|---|---|
| GET / POST | `/api/projects/` | list / create (`name`, `old_site_url`, `new_site_url`, `description`, optional `settings`) |
| GET / PATCH | `/api/projects/{id}/` | read / update (changing normalization settings re-normalizes the saved lists) |
| DELETE | `/api/projects/{id}/` | delete everything in the project; body `{"confirm_name": "<exact project name>"}` |
| GET | `/api/dashboard/` | totals and per-project progress for the signed-in user |
| GET | `/api/projects/{id}/dashboard/` | counts, confidence mix, review progress, risks and run history for one project |
| GET | `/api/projects/{id}/audit/` | activity log (`?action=mapping.` filters by prefix) |
| GET | `/api/projects/{id}/urls/` | imported URLs (`?side=old\|new&search=`), used by the destination picker |

### Import
| Method | Path | What it does |
|---|---|---|
| POST | `/api/projects/{id}/imports/preview/` | read a file (`file`) or pasted text (`text`) and return headers, a sample and a suggested column mapping. **Saves nothing** |
| POST | `/api/projects/{id}/imports/` | save the URLs: `kind` (`old`\|`new`), `mode` (`append`\|`replace`), `column_map` (`{"url": 0, "title": 1, …}`), and the file or text. Returns counts and every skipped row |
| GET | `/api/projects/{id}/imports/` | import history |
| GET | `/api/projects/{id}/imports/{batch}/` | one import with its row-level errors |
| POST | `/api/projects/{id}/fetch-metadata/` | *optional, off by default (403 `fetch_disabled`)*: read titles/headings of public pages (`side`, optional `ids`) |

### Matching
| Method | Path | What it does |
|---|---|---|
| POST | `/api/projects/{id}/analyze/` | start a matching run → `202` with the run. `409 analysis_in_progress` if one is active; `400 lists_missing` if either list is empty |
| GET | `/api/projects/{id}/runs/` | runs, newest first (`status`, `progress`, `stats`, warnings) |
| GET | `/api/projects/{id}/runs/{run}/` | one run (poll this for progress) |
| GET | `/api/projects/{id}/runs/compare/?a=&b=` | which old URLs got a different suggestion between two completed runs |

### Review workspace
| Method | Path | What it does |
|---|---|---|
| GET | `/api/projects/{id}/mappings/` | rows with filters `search`, `band`, `status`, `match_type`, `unmatched`, `ambiguous`, `has_risk`, `origin` and `ordering` (`id`, `score`, `-score`, `old_url`, `status`) |
| GET / PATCH | `/api/projects/{id}/mappings/{m}/` | read one row (reasons, score breakdown, alternatives) / change `note` or `redirect_status` (301/302/307/308) |
| POST | `…/mappings/{m}/approve/` | approve. May answer `low_confidence_confirmation_required` or `many_to_one_confirmation_required`; repeat with `confirm_low_confidence` / `confirm_many_to_one` set to `true` |
| POST | `…/mappings/{m}/reject/` | reject |
| POST | `…/mappings/{m}/reset/` | back to pending with the engine's own suggestion |
| POST | `…/mappings/{m}/undo/` | restore the state before the last decision |
| POST | `…/mappings/{m}/assign/` | choose the destination: `new_url_id` **or** `url` (any valid URL, added to the project's new URLs). Counts as approved; `self_redirect` and many-to-one are refused or confirmed |
| POST | `/api/projects/{id}/mappings/bulk/` | `{"action": "approve"\|"reject"\|"reset", "ids": [...], "confirm": true, "include_low": false, "confirm_many_to_one": false}` → `{"updated", "skipped": {…}, "requested"}`. At most 500 ids; approval **requires** `confirm` and never silently approves rows without a destination |

### Quality and exports
| Method | Path | What it does |
|---|---|---|
| GET | `/api/projects/{id}/quality/` | findings (`?severity=`, `?kind=`), counts, `stale` flag and the list of what the checks cannot know |
| POST | `/api/projects/{id}/quality/run/` | recompute the findings now |
| GET / POST | `/api/projects/{id}/exports/` | list / create. `format`: `csv`, `xlsx`, `json`, `htaccess`, `nginx`, `report`; optional `redirect_status`; `include_pending` needs `confirm_pending: true` |
| GET | `/api/projects/{id}/exports/{e}/download/` | the file (`Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`) |

Export behaviour worth knowing: only **approved** rows are included unless pending rows are explicitly confirmed; `htaccess` and `nginx` skip rows with high-severity problems (loops, self-redirects, excluded paths, invalid or duplicate sources) and list them in `warnings`; spreadsheet cells that start with `= + - @` are neutralized; each export is stored with its SHA-256.
