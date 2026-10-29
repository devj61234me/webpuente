"""Shared helpers for the tests. All data here is made up for testing and lives only in the temporary test database."""
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

User = get_user_model()
PASSWORD = "Str0ng-Test-Pass!"

OLD_URLS = """https://old.example.com/about
https://old.example.com/contact
https://old.example.com/products/running-shoes
https://old.example.com/blog/best-running-shoes
https://old.example.com/blog/trail-guide
https://old.example.com/legacy/zzz-unrelated
"""
NEW_URLS = """https://new.example.com/about
https://new.example.com/contact-us
https://new.example.com/shop/running-shoes
https://new.example.com/journal/best-running-shoes-2024
https://new.example.com/journal/trail-guide
https://new.example.com/
"""


def error_of(response):
    return response.json().get("error", {})


class ApiTest(APITestCase):
    def make_user(self, email="owner@example.com"):
        return User.objects.create_user(username=email, email=email, password=PASSWORD)

    def client_for(self, user):
        client = APIClient()
        login = client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        return client

    def setUp(self):
        self.user = self.make_user()
        self.api = self.client_for(self.user)

    # ---- project helpers
    def create_project(self, api=None, name="Site move", **extra):
        api = api or self.api
        body = {"name": name, "old_site_url": "https://old.example.com", "new_site_url": "https://new.example.com", **extra}
        response = api.post("/api/projects/", body, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def import_text(self, pid, kind, text, mode="append", api=None, expect=201):
        api = api or self.api
        response = api.post(f"/api/projects/{pid}/imports/", {"kind": kind, "text": text, "mode": mode}, format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def project_with_urls(self, old=OLD_URLS, new=NEW_URLS, api=None, **extra):
        project = self.create_project(api=api, **extra)
        self.import_text(project["id"], "old", old, api=api)
        self.import_text(project["id"], "new", new, api=api)
        return project

    def analyze(self, pid, api=None, expect=202):
        api = api or self.api
        response = api.post(f"/api/projects/{pid}/analyze/", format="json")
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def analyzed_project(self, **kwargs):
        project = self.project_with_urls(**kwargs)
        run = self.analyze(project["id"])
        self.assertEqual(run["status"], "completed", run)
        return project

    def mappings(self, pid, api=None, **params):
        api = api or self.api
        response = api.get(f"/api/projects/{pid}/mappings/", {"page_size": 100, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def mapping_for(self, pid, old_suffix, api=None):
        for row in self.mappings(pid, api=api):
            if row["old_url"]["original"].endswith(old_suffix):
                return row
        self.fail(f"no mapping for {old_suffix}")
