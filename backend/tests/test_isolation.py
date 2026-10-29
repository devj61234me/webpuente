"""One user must never see or change another user's data."""
from .base import ApiTest


class IsolationTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.project = self.analyzed_project()
        self.pid = self.project["id"]
        self.other = self.make_user("intruder@example.com")
        self.intruder = self.client_for(self.other)
        self.review_id = self.mappings(self.pid)[0]["id"]

    def test_other_user_cannot_see_the_project_anywhere(self):
        self.assertEqual(self.intruder.get("/api/projects/").json()["count"], 0)
        paths = ["", "dashboard/", "mappings/", "quality/", "exports/", "runs/", "imports/", "audit/", "urls/"]
        for path in paths:
            r = self.intruder.get(f"/api/projects/{self.pid}/{path}")
            self.assertEqual(r.status_code, 404, path)

    def test_other_user_cannot_change_or_delete(self):
        self.assertEqual(self.intruder.patch(f"/api/projects/{self.pid}/", {"name": "Hacked"}, format="json").status_code, 404)
        self.assertEqual(self.intruder.delete(f"/api/projects/{self.pid}/", {"confirm_name": "Site move"}, format="json").status_code, 404)
        self.assertEqual(self.api.get(f"/api/projects/{self.pid}/").json()["name"], "Site move")

    def test_other_user_cannot_act_on_mappings(self):
        base = f"/api/projects/{self.pid}/mappings/{self.review_id}"
        for action in ("approve", "reject", "reset", "undo", "assign"):
            self.assertEqual(self.intruder.post(f"{base}/{action}/", {"url": "https://x.example.com/a"}, format="json").status_code, 404, action)
        self.assertEqual(self.intruder.get(f"{base}/").status_code, 404)

    def test_other_user_cannot_import_analyze_or_export(self):
        self.assertEqual(self.intruder.post(f"/api/projects/{self.pid}/imports/", {"kind": "old", "text": "https://old.example.com/x"}, format="json").status_code, 404)
        self.assertEqual(self.intruder.post(f"/api/projects/{self.pid}/analyze/").status_code, 404)
        self.assertEqual(self.intruder.post(f"/api/projects/{self.pid}/exports/", {"format": "csv"}, format="json").status_code, 404)

    def test_other_user_cannot_download_an_export(self):
        self.api.post(f"/api/projects/{self.pid}/mappings/{self.review_id}/approve/", {"confirm_low_confidence": True, "confirm_many_to_one": True}, format="json")
        export = self.api.post(f"/api/projects/{self.pid}/exports/", {"format": "csv"}, format="json").json()
        url = f"/api/projects/{self.pid}/exports/{export['id']}/download/"
        self.assertEqual(self.api.get(url).status_code, 200)
        self.assertEqual(self.intruder.get(url).status_code, 404)

    def test_bulk_action_with_foreign_ids_changes_nothing(self):
        mine = self.create_project(api=self.intruder, name="Intruder project")
        r = self.intruder.post(f"/api/projects/{mine['id']}/mappings/bulk/", {"action": "reject", "ids": [self.review_id]}, format="json")
        self.assertEqual(r.json()["updated"], 0)
        self.assertEqual(self.mapping_for(self.pid, "/about")["status"], "pending")

    def test_dashboard_shows_only_own_projects(self):
        self.assertEqual(self.intruder.get("/api/dashboard/").json()["totals"]["projects"], 0)
        self.assertEqual(self.api.get("/api/dashboard/").json()["totals"]["projects"], 1)

    def test_same_project_name_allowed_for_different_users(self):
        self.assertEqual(self.intruder.post("/api/projects/", {"name": "Site move", "old_site_url": "https://a.example.com", "new_site_url": "https://b.example.com"}, format="json").status_code, 201)

    def test_unknown_ids_are_404_with_the_standard_error_shape(self):
        r = self.api.get("/api/projects/999999/")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.json())
