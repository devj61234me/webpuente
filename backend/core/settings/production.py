"""
Production settings. Use with DJANGO_SETTINGS_MODULE=core.settings.production
behind gunicorn (never `manage.py runserver`) and an HTTPS-terminating proxy (every major host does this).
"""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env, env_bool, env_int, env_list

DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production (comma-separated host names).")
if not env_list("CORS_ALLOWED_ORIGINS"):
    raise ImproperlyConfigured("CORS_ALLOWED_ORIGINS must be set in production (your frontend https URL).")
if not env("DB_PASSWORD", ""):
    raise ImproperlyConfigured("DB_PASSWORD must be set in production.")
if "localhost" in env("FRONTEND_URL", "http://localhost"):
    raise ImproperlyConfigured("FRONTEND_URL must be your real https frontend address in production.")

# HTTPS and cookie hardening
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
# Hosts probe the health check over plain HTTP from inside their network; it reveals only "ok" / "unreachable".
SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # trust the host's proxy header
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 3600)  # raise to 31536000 once HTTPS is confirmed
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
ADMIN_URL = env("ADMIN_URL", "admin/")
