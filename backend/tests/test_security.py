import os
import subprocess
import sys
from pathlib import Path

from django.test import override_settings

from .base import ApiTest

BACKEND = Path(__file__).resolve().parent.parent


def run_manage(args, env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DB_", "ALLOWED_", "CORS_", "FRONTEND_"))}
    env.update(env_extra)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "manage.py", *args], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)


class ProductionSettingsTests(ApiTest):
    PROD = {"DJANGO_SETTINGS_MODULE": "core.settings.production", "DJANGO_SECRET_KEY": "k9Qz!r2Vb7Lm#Xe4Tn8Wc5Yd1Hf6Ja3Pg0Su9Io2Zq7Rv4Bx8Nt5Mk"}

    def test_production_refuses_to_start_without_required_values(self):
        result = run_manage(["check"], self.PROD)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOWED_HOSTS", result.stderr + result.stdout)

    def test_production_starts_with_all_required_values_and_passes_deploy_check(self):
        env = {**self.PROD, "ALLOWED_HOSTS": "api.example.com", "CORS_ALLOWED_ORIGINS": "https://app.example.com",
               "FRONTEND_URL": "https://app.example.com", "DB_PASSWORD": "not-a-real-password", "DB_HOST": "db.example.com",
               "DB_NAME": "x", "DB_USER": "x"}
        result = run_manage(["check", "--deploy", "--tag", "security"], env)
        output = result.stderr + result.stdout
        self.assertEqual(result.returncode, 0, output)
        # HSTS subdomains/preload are deliberately left off (they are hard to undo); nothing else may be flagged.
        flagged = {w for w in ("W004", "W008", "W012", "W016", "W018", "W020", "W009", "W006", "W007") if f"security.{w}" in output}
        self.assertEqual(flagged, set(), output)

    def test_production_rejects_localhost_frontend(self):
        env = {**self.PROD, "ALLOWED_HOSTS": "api.example.com", "CORS_ALLOWED_ORIGINS": "https://app.example.com",
               "FRONTEND_URL": "http://localhost:5173", "DB_PASSWORD": "x"}
        self.assertNotEqual(run_manage(["check"], env).returncode, 0)


class ApiSecurityTests(ApiTest):
    def test_protected_routes_need_a_token(self):
        from rest_framework.test import APIClient
        anon = APIClient()
        for path in ("/api/projects/", "/api/dashboard/", "/api/auth/me/"):
            self.assertEqual(anon.get(path).status_code, 401, path)

    def test_health_and_config_are_public_and_leak_nothing(self):
        from rest_framework.test import APIClient
        anon = APIClient()
        health = anon.get("/api/health/")
        self.assertEqual(health.status_code, 200)
        config = anon.get("/api/config/").json()
        for key in list(config) + list(health.json()):
            self.assertFalse(any(w in key for w in ("secret", "api_key", "token", "host", "user")), key)
        self.assertTrue(all(isinstance(v, (bool, int)) or v in ("inline", "thread", "worker") for v in config.values()))

    def test_errors_use_one_format_and_hide_internals(self):
        r = self.api.get("/api/projects/999999/")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(set(r.json()["error"]), {"code", "message", "details"})

    def test_unknown_project_fields_cannot_change_the_owner(self):
        project = self.create_project()
        other = self.make_user("other@example.com")
        r = self.api.patch(f"/api/projects/{project['id']}/", {"owner": other.id, "owner_id": other.id}, format="json")
        self.assertEqual(r.status_code, 200)
        from projects.models import MigrationProject
        self.assertEqual(MigrationProject.objects.get(pk=project["id"]).owner_id, self.user.id)

    @override_settings(MAX_UPLOAD_MB=1)
    def test_oversized_upload_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        project = self.create_project()
        big = SimpleUploadedFile("big.csv", b"url\n" + b"https://old.example.com/a\n" * 80000, content_type="text/csv")
        r = self.api.post(f"/api/projects/{project['id']}/imports/", {"kind": "old", "file": big, "mode": "append"}, format="multipart")
        self.assertIn(r.status_code, (400, 413))

    def test_security_headers_present(self):
        r = self.api.get("/api/health/")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")


class DatabaseSslSettingTests(ApiTest):
    def test_ca_certificate_can_be_supplied_as_text(self):
        code = (
            "from django.conf import settings; import os; "
            "p = settings.DATABASES['default']['OPTIONS']['ssl']['ca']; "
            "print(p); print(open(p).read().strip().splitlines()[0])"
        )
        env = {"DJANGO_SETTINGS_MODULE": "core.settings.development", "DJANGO_SECRET_KEY": "k" * 60, "DB_SSL_CA_PEM": "-----BEGIN CERTIFICATE-----\\nABC\\n-----END CERTIFICATE-----"}
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env={**{k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DB_"))}, **env},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("-----BEGIN CERTIFICATE-----", result.stdout)


class HealthCheckRedirectTests(ApiTest):
    def test_only_the_health_check_is_exempt_from_the_https_redirect(self):
        env = {**ProductionSettingsTests.PROD, "ALLOWED_HOSTS": "api.example.com", "CORS_ALLOWED_ORIGINS": "https://app.example.com",
               "FRONTEND_URL": "https://app.example.com", "DB_PASSWORD": "x"}
        code = "from django.conf import settings; print(settings.SECURE_REDIRECT_EXEMPT, settings.SECURE_SSL_REDIRECT)"
        full = {**{k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "DB_", "ALLOWED_", "CORS_", "FRONTEND_"))}, **env}
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=full, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "['^api/health/$'] True")
