"""Default per-project settings and their validation. Stored as JSON on MigrationProject.settings."""

DEFAULT_SETTINGS = {
    # How URLs are normalised before comparing (the original URL is always kept untouched).
    "normalization": {
        "ignore_case": False,          # treat /About and /about as the same path
        "strip_trailing_slash": True,  # treat /about/ and /about as the same path
        "query_mode": "keep",          # keep | drop_all | drop_listed
        "drop_params": ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"],
        "ignore_www": False,
    },
    # How strongly each kind of evidence counts. Missing evidence (e.g. no page titles) is skipped.
    "weights": {"slug": 0.30, "path": 0.15, "hierarchy": 0.10, "title": 0.25, "h1": 0.10, "meta": 0.05, "semantic": 0.35},
    # Score limits (0-100). These are starting points, not guarantees of correctness.
    "thresholds": {"high": 90, "medium": 70, "min_accept": 40, "ambiguity_gap": 5, "fuzzy_cap": 95},
    "redirect_status": 301,
    "excluded_patterns": [],  # path patterns that must never be redirected, e.g. /wp-admin/*
    "use_embeddings": False,
}

QUERY_MODES = ("keep", "drop_all", "drop_listed")
REDIRECT_STATUSES = (301, 302, 307, 308)


def merged_settings(stored):
    """Fill any missing keys with defaults so older projects keep working."""
    stored = stored or {}
    result = {}
    for key, default in DEFAULT_SETTINGS.items():
        value = stored.get(key, default)
        if isinstance(default, dict):
            value = {**default, **(value if isinstance(value, dict) else {})}
        result[key] = value
    return result
