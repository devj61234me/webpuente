"""Settings for the automated tests: in-memory SQLite, jobs run inline, fast password hashing."""
import logging
import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key-not-for-production-use-0123456789")

from .base import *  # noqa: F401,F403,E402

DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # speed only; tests only
JOB_MODE = "inline"
CORS_ALLOWED_ORIGINS = ["http://localhost:5173"]
AUTH_RATE = IMPORT_RATE = ANALYSIS_RATE = EXPORT_RATE = FETCH_RATE = "10000/min"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

logging.disable(logging.CRITICAL)  # keep test output readable (expected 404/401 warnings)
