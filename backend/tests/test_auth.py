from django.core import mail
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from rest_framework.test import APIClient

from .base import PASSWORD, ApiTest, User, error_of


class AuthTests(ApiTest):
    def test_register_returns_user_and_tokens(self):
        r = APIClient().post("/api/auth/register/", {"email": "New@Example.com", "password": PASSWORD, "first_name": "Ana"}, format="json")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["user"]["email"], "new@example.com")  # emails are stored in lower case
        self.assertTrue(body["access"] and body["refresh"])
        self.assertNotIn("password", str(body))

    def test_password_is_hashed_in_database(self):
        APIClient().post("/api/auth/register/", {"email": "h@example.com", "password": PASSWORD}, format="json")
        stored = User.objects.get(email="h@example.com").password
        self.assertNotIn(PASSWORD, stored)
        self.assertTrue(stored.startswith(("pbkdf2", "md5")))  # md5 only in the test settings

    def test_weak_and_short_passwords_are_rejected(self):
        for bad in ["short1!", "password123456", "1234567890123"]:
            r = APIClient().post("/api/auth/register/", {"email": "w@example.com", "password": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
            self.assertEqual(error_of(r)["code"], "validation_error")
            self.assertIn("password", error_of(r)["details"])

    def test_duplicate_email_rejected_case_insensitively(self):
        r = APIClient().post("/api/auth/register/", {"email": "OWNER@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", error_of(r)["details"])

    def test_login_wrong_password_and_unknown_user_look_the_same(self):
        a = APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": "wrong-password-1"}, format="json")
        b = APIClient().post("/api/auth/login/", {"email": "nobody@example.com", "password": "wrong-password-1"}, format="json")
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        self.assertEqual(error_of(a)["message"], error_of(b)["message"])

    def test_protected_routes_need_a_token(self):
        for url in ("/api/projects/", "/api/dashboard/", "/api/auth/me/"):
            r = APIClient().get(url)
            self.assertEqual(r.status_code, 401, url)
            self.assertEqual(error_of(r)["code"], "not_authenticated")
        bad = APIClient()
        bad.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(bad.get("/api/projects/").status_code, 401)

    def test_refresh_rotates_and_old_refresh_stops_working(self):
        login = APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": PASSWORD}, format="json").json()
        first = APIClient().post("/api/auth/refresh/", {"refresh": login["refresh"]}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.json()["refresh"], login["refresh"])
        replay = APIClient().post("/api/auth/refresh/", {"refresh": login["refresh"]}, format="json")  # stolen/old token
        self.assertEqual(replay.status_code, 401)

    def test_logout_revokes_the_refresh_token(self):
        login = APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": PASSWORD}, format="json").json()
        self.assertEqual(self.api.post("/api/auth/logout/", {"refresh": login["refresh"]}, format="json").status_code, 200)
        self.assertEqual(APIClient().post("/api/auth/refresh/", {"refresh": login["refresh"]}, format="json").status_code, 401)

    def test_logout_all_revokes_every_session(self):
        tokens = [APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": PASSWORD}, format="json").json()["refresh"] for _ in range(2)]
        self.assertEqual(self.api.post("/api/auth/logout-all/").status_code, 200)
        for token in tokens:
            self.assertEqual(APIClient().post("/api/auth/refresh/", {"refresh": token}, format="json").status_code, 401)

    def test_change_password(self):
        r = self.api.post("/api/auth/change-password/", {"current_password": PASSWORD, "new_password": "An0ther-Strong-Pass!"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": PASSWORD}, format="json").status_code, 401)
        self.assertEqual(APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": "An0ther-Strong-Pass!"}, format="json").status_code, 200)

    def test_change_password_checks_current_password(self):
        r = self.api.post("/api/auth/change-password/", {"current_password": "nope-nope-nope", "new_password": "An0ther-Strong-Pass!"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("current_password", error_of(r)["details"])

    def test_password_reset_flow(self):
        r = APIClient().post("/api/auth/password-reset/", {"email": "owner@example.com"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn("/reset-password?uid=", body)
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].split()[0]
        done = APIClient().post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "Reset-Strong-Pass-1!"}, format="json")
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": "Reset-Strong-Pass-1!"}, format="json").status_code, 200)
        reuse = APIClient().post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "Reset-Strong-Pass-2!"}, format="json")
        self.assertEqual(reuse.status_code, 400)  # a reset link works only once

    def test_password_reset_does_not_reveal_whether_an_account_exists(self):
        known = APIClient().post("/api/auth/password-reset/", {"email": "owner@example.com"}, format="json")
        unknown = APIClient().post("/api/auth/password-reset/", {"email": "ghost@example.com"}, format="json")
        self.assertEqual(known.json(), unknown.json())
        self.assertEqual(len(mail.outbox), 1)  # nothing is sent for the unknown address

    def test_reset_link_with_bad_token_or_weak_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        bad = APIClient().post("/api/auth/password-reset/confirm/", {"uid": uid, "token": "bad-token", "new_password": "Reset-Strong-Pass-1!"}, format="json")
        self.assertEqual(error_of(bad)["code"], "invalid_reset_link")
        token = default_token_generator.make_token(self.user)
        weak = APIClient().post("/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "new_password": "12345"}, format="json")
        self.assertEqual(weak.status_code, 400)

    def test_profile_update_and_account_deletion_removes_data(self):
        self.assertEqual(self.api.patch("/api/auth/me/", {"first_name": "Dev"}, format="json").json()["first_name"], "Dev")
        project = self.project_with_urls()
        wrong = self.api.delete("/api/auth/me/", {"password": "wrong-password"}, format="json")
        self.assertEqual(wrong.status_code, 400)
        self.assertEqual(self.api.delete("/api/auth/me/", {"password": PASSWORD}, format="json").status_code, 204)
        from projects.models import MigrationProject, OldURL
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(MigrationProject.objects.filter(pk=project["id"]).exists())
        self.assertEqual(OldURL.objects.count(), 0)

    @override_settings(AUTH_RATE="3/min")
    def test_login_is_rate_limited(self):
        from django.core.cache import cache
        cache.clear()
        codes = [APIClient().post("/api/auth/login/", {"email": "owner@example.com", "password": "bad-password-1"}, format="json").status_code for _ in range(5)]
        self.assertEqual(codes[:3], [401, 401, 401])
        self.assertEqual(codes[3], 429)
        self.assertEqual(error_of(APIClient().post("/api/auth/login/", {"email": "x@example.com", "password": "bad"}, format="json"))["code"], "rate_limited")
