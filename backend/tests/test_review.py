from projects.models import AuditLog

from .base import ApiTest, error_of


class ReviewTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.project = self.analyzed_project()
        self.pid = self.project["id"]

    def url(self, row, action=""):
        return f"/api/projects/{self.pid}/mappings/{row['id']}/{action}"

    def test_approve_reject_reset_and_undo(self):
        row = self.mapping_for(self.pid, "/about")
        self.assertEqual(self.api.post(self.url(row, "approve/"), {}, format="json").json()["status"], "approved")
        self.assertEqual(self.api.post(self.url(row, "reject/")).json()["status"], "rejected")
        undone = self.api.post(self.url(row, "undo/")).json()
        self.assertEqual(undone["status"], "approved")
        reset = self.api.post(self.url(row, "reset/")).json()
        self.assertEqual((reset["status"], reset["origin"]), ("pending", "auto"))

    def test_undo_with_nothing_to_undo(self):
        row = self.mapping_for(self.pid, "/about")
        self.assertEqual(error_of(self.api.post(self.url(row, "undo/")))["code"], "nothing_to_undo")

    def test_cannot_approve_without_destination(self):
        row = self.mapping_for(self.pid, "/legacy/zzz-unrelated")
        self.assertEqual(error_of(self.api.post(self.url(row, "approve/"), {}, format="json"))["code"], "no_destination")

    def test_low_confidence_needs_explicit_confirmation(self):
        project = self.project_with_urls(
            old="https://old.example.com/products/running-shoes\n", new="https://new.example.com/shop/running-shoes\n",
            settings={"thresholds": {"high": 99, "medium": 98, "min_accept": 10}}, name="Strict",
        )
        pid = project["id"]
        self.analyze(pid)
        row = self.mappings(pid)[0]
        self.assertEqual(row["band"], "low")
        url = f"/api/projects/{pid}/mappings/{row['id']}/approve/"
        self.assertEqual(error_of(self.api.post(url, {}, format="json"))["code"], "low_confidence_confirmation_required")
        self.assertEqual(self.api.post(url, {"confirm_low_confidence": True}, format="json").status_code, 200)

    def test_manual_assign_creates_a_new_url_and_counts_as_approved(self):
        row = self.mapping_for(self.pid, "/legacy/zzz-unrelated")
        r = self.api.post(self.url(row, "assign/"), {"url": "https://new.example.com/archive"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual((body["status"], body["origin"]), ("approved", "manual"))
        self.assertEqual(body["final_url"], "https://new.example.com/archive")

    def test_assign_rejects_invalid_and_self_redirects(self):
        row = self.mapping_for(self.pid, "/legacy/zzz-unrelated")
        self.assertEqual(self.api.post(self.url(row, "assign/"), {"url": "javascript:alert(1)"}, format="json").status_code, 400)
        self.assertEqual(error_of(self.api.post(self.url(row, "assign/"), {}, format="json"))["code"], "destination_required")
        r = self.api.post(self.url(row, "assign/"), {"url": row["old_url"]["original"]}, format="json")
        self.assertEqual(error_of(r)["code"], "self_redirect")

    def test_many_to_one_requires_confirmation(self):
        a = self.mapping_for(self.pid, "/legacy/zzz-unrelated")
        b = self.mapping_for(self.pid, "/blog/trail-guide")
        dest = {"url": "https://new.example.com/one-page"}
        self.assertEqual(self.api.post(self.url(a, "assign/"), dest, format="json").status_code, 200)
        r = self.api.post(self.url(b, "assign/"), dest, format="json")
        self.assertEqual(error_of(r)["code"], "many_to_one_confirmation_required")
        self.assertEqual(self.api.post(self.url(b, "assign/"), {**dest, "confirm_many_to_one": True}, format="json").status_code, 200)

    def test_note_and_redirect_status_edit(self):
        row = self.mapping_for(self.pid, "/about")
        r = self.api.patch(self.url(row), {"note": "checked", "redirect_status": 302}, format="json")
        self.assertEqual((r.json()["note"], r.json()["redirect_status"]), ("checked", 302))
        self.assertEqual(error_of(self.api.patch(self.url(row), {"redirect_status": 200}, format="json"))["code"], "invalid_status")

    def test_bulk_requires_confirmation_and_reports_skips(self):
        ids = [r["id"] for r in self.mappings(self.pid)]
        r = self.api.post(f"/api/projects/{self.pid}/mappings/bulk/", {"action": "approve", "ids": ids}, format="json")
        self.assertEqual(error_of(r)["code"], "confirmation_required")
        r = self.api.post(f"/api/projects/{self.pid}/mappings/bulk/", {"action": "approve", "ids": ids, "confirm": True}, format="json").json()
        self.assertGreaterEqual(r["skipped"]["no_destination"], 1)  # the unmatched row is never silently approved
        self.assertEqual(r["updated"] + sum(r["skipped"].values()), r["requested"])
        statuses = {x["status"] for x in self.mappings(self.pid)}
        self.assertIn("pending", statuses)  # skipped rows stay pending

    def test_bulk_validation(self):
        base = f"/api/projects/{self.pid}/mappings/bulk/"
        self.assertEqual(error_of(self.api.post(base, {"action": "delete", "ids": [1]}, format="json"))["code"], "invalid_action")
        self.assertEqual(error_of(self.api.post(base, {"action": "reject", "ids": []}, format="json"))["code"], "ids_required")
        self.assertEqual(error_of(self.api.post(base, {"action": "reject", "ids": list(range(1000))}, format="json"))["code"], "too_many_items")

    def test_bulk_reject_and_reset(self):
        ids = [r["id"] for r in self.mappings(self.pid)][:3]
        base = f"/api/projects/{self.pid}/mappings/bulk/"
        self.assertEqual(self.api.post(base, {"action": "reject", "ids": ids}, format="json").json()["updated"], 3)
        self.assertEqual(self.api.post(base, {"action": "reset", "ids": ids}, format="json").json()["updated"], 3)
        self.assertEqual(len(self.mappings(self.pid, status="rejected")), 0)

    def test_filters_search_ordering_and_pagination(self):
        self.assertEqual(len(self.mappings(self.pid, band="unmatched")), 1)
        self.assertEqual(len(self.mappings(self.pid, unmatched="true")), 1)
        self.assertEqual(len(self.mappings(self.pid, search="running-shoes")), 2)
        self.assertEqual(len(self.mappings(self.pid, match_type="exact_path")), 1)
        r = self.api.get(f"/api/projects/{self.pid}/mappings/", {"page_size": 2}).json()
        self.assertEqual((len(r["results"]), r["count"]), (2, 6))
        big = self.api.get(f"/api/projects/{self.pid}/mappings/", {"page_size": 100000}).json()
        self.assertLessEqual(len(big["results"]), 100)

    def test_every_decision_is_audited(self):
        row = self.mapping_for(self.pid, "/about")
        self.api.post(self.url(row, "approve/"), {}, format="json")
        self.assertTrue(AuditLog.objects.filter(project_id=self.pid, action="mapping.approved").exists())
        feed = self.api.get(f"/api/projects/{self.pid}/audit/").json()["results"]
        self.assertIn("mapping.approved", [e["action"] for e in feed])
