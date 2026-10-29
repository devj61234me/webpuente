"""
Settings shared by every environment. Everything that changes between machines
(secrets, database, URLs, limits) is read from environment variables.
Local development reads them from backend/.env; production reads them from the host's dashboard.
"""
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")  # does nothing if the file does not exist (e.g. on a host)


# ---------------------------------------------------------------- helpers
def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ImproperlyConfigured(
            f"Environment variable {name} is required. Copy backend/.env.example to backend/.env and fill it in."
        )
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, str(default))).strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return int(default)


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------- core
SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
ROOT_URLCONF = "core.urls"
WSGI_APPLICATION = "core.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_TZ = True
LANGUAGE_CODE = "en-us"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",  # lets us revoke refresh tokens (logout, rotation)
    "drf_spectacular",
    "accounts",
    "projects",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# ---------------------------------------------------------------- database (MySQL)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("DB_NAME", "webpuente"),
        "USER": env("DB_USER", "webpuente_user"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "3306"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"charset": "utf8mb4"},
    }
}
# Managed MySQL hosts normally require an encrypted connection.
#   DB_SSL=true              -> verify the server with the system CA list
#   DB_SSL_CA=path/ca.pem    -> verify with the certificate file your host gives you
#   DB_SSL_CA_PEM="-----BEGIN CERTIFICATE-----..."  -> same, but the certificate TEXT is pasted into an
#                              environment variable (for hosts without file storage, e.g. Render). A CA certificate is
#                              public information, not a secret.
def _db_ca_path():
    pem = env("DB_SSL_CA_PEM", "").replace("\\n", "\n").strip()
    if pem:
        import hashlib
        import tempfile

        path = Path(tempfile.gettempdir()) / f"webpuente-db-ca-{hashlib.sha256(pem.encode()).hexdigest()[:16]}.pem"
        if not path.exists():
            path.write_text(pem + "\n")
        return str(path)
    return env("DB_SSL_CA", "")


_ca_path = _db_ca_path()
if env_bool("DB_SSL", False) or _ca_path:
    import certifi

    DATABASES["default"]["OPTIONS"]["ssl"] = {"ca": _ca_path or certifi.where()}

# ---------------------------------------------------------------- passwords
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------- static files (admin + API docs)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------- REST framework + JWT
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 7)),
    "ROTATE_REFRESH_TOKENS": True,  # every refresh gives a new refresh token...
    "BLACKLIST_AFTER_ROTATION": True,  # ...and the old one stops working
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
SPECTACULAR_SETTINGS = {
    "TITLE": "WebPuente API",
    "DESCRIPTION": "Website content migration and URL mapping assistant.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
ENABLE_API_DOCS = env_bool("ENABLE_API_DOCS", True)

# ---------------------------------------------------------------- CORS
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = False  # tokens travel in the Authorization header, not cookies

# ---------------------------------------------------------------- limits (all configurable)
MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 5)
MAX_IMPORT_ROWS = env_int("MAX_IMPORT_ROWS", 20000)
MAX_URL_LENGTH = 2048
MAX_PROJECTS_PER_USER = env_int("MAX_PROJECTS_PER_USER", 50)
MAX_URLS_PER_PROJECT = env_int("MAX_URLS_PER_PROJECT", 50000)
MAX_BULK_ITEMS = 500
MATCH_MAX_CANDIDATES = env_int("MATCH_MAX_CANDIDATES", 50)
MAX_EXPORT_ROWS = env_int("MAX_EXPORT_ROWS", 50000)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024 + 1024 * 1024  # form size ceiling

# Request-rate limits (per IP for login/reset, per user for everything else).
AUTH_RATE = env("AUTH_RATE", "20/min")
IMPORT_RATE = env("IMPORT_RATE", "60/hour")
ANALYSIS_RATE = env("ANALYSIS_RATE", "30/hour")
EXPORT_RATE = env("EXPORT_RATE", "60/hour")
FETCH_RATE = env("FETCH_RATE", "10/hour")

# ---------------------------------------------------------------- background jobs
# thread : analysis runs in a background thread of the web process (works on free hosts, no extra service)
# worker : the web process only queues the run; a separate `python manage.py run_worker` process executes it
# inline : runs immediately inside the request (used by the automated tests)
JOB_MODE = env("JOB_MODE", "thread").lower()
JOB_STALE_MINUTES = env_int("JOB_STALE_MINUTES", 30)

# ---------------------------------------------------------------- optional: semantic matching
# Off by default. Needs an OpenAI-compatible /embeddings endpoint and costs money with most providers.
EMBEDDINGS_ENABLED = env_bool("EMBEDDINGS_ENABLED", False)
EMBEDDINGS_BASE_URL = env("EMBEDDINGS_BASE_URL", "https://api.openai.com/v1")
EMBEDDINGS_API_KEY = env("EMBEDDINGS_API_KEY", "")
EMBEDDINGS_MODEL = env("EMBEDDINGS_MODEL", "")
EMBEDDINGS_TIMEOUT_SECONDS = env_int("EMBEDDINGS_TIMEOUT_SECONDS", 30)
EMBEDDINGS_BATCH_SIZE = env_int("EMBEDDINGS_BATCH_SIZE", 64)
EMBEDDINGS_MAX_PAGES = env_int("EMBEDDINGS_MAX_PAGES", 5000)  # safety limit so one run cannot cost too much

# ---------------------------------------------------------------- optional: website fetching
# Off by default. When on, the server downloads pages the user lists (SSRF-protected, robots.txt respected).
ENABLE_WEBSITE_FETCH = env_bool("ENABLE_WEBSITE_FETCH", False)
FETCH_TIMEOUT_SECONDS = env_int("FETCH_TIMEOUT_SECONDS", 8)
FETCH_MAX_BYTES = env_int("FETCH_MAX_BYTES", 512 * 1024)
FETCH_MAX_URLS_PER_REQUEST = env_int("FETCH_MAX_URLS_PER_REQUEST", 25)
FETCH_MAX_REDIRECTS = 3
FETCH_DELAY_SECONDS = float(env("FETCH_DELAY_SECONDS", "0.3"))
FETCH_USER_AGENT = env("FETCH_USER_AGENT", "WebPuenteBot/1.0 (+migration assistant)")

# ---------------------------------------------------------------- email (password reset)
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "WebPuente <no-reply@localhost>")
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")
PASSWORD_RESET_TIMEOUT = 60 * 60  # reset links stay valid for one hour

# ---------------------------------------------------------------- logging (stdout; meeting-style private data is never logged)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
