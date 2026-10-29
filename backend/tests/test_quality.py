from .base import ApiTest


class QualityTests(ApiTest):
    def kinds(self, pid):
        return {r["kind"] for r in self.api.get(f"/api/projects/{pid}/quality/").json()["results"]}

    def run_quality(self, pid):
        r = self.api.post(f"/api/projects/{pid}/quality/run/")
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_not_checked_list_is_always_present(self):
        project = self.analyzed_project()
        self.assertTrue(self.run_quality(project["id"])["not_checked"])

    def test_no_destination_and_orphans(self):
        project = self.analyzed_project()
        self.run_quality(project["id"])
        kinds = self.kinds(project["id"])
        self.assertIn("no_destination", kinds)
        self.assertIn("orphan_new_url", kinds)

    def test_self_redirect_is_found_and_blocks_nothing_silently(self):
        project = self.project_with_urls(old="https://old.example.com/a\n", new="https://new.example.com/a\n",
                                          old_site_url="https://same.example.com", new_site_url="https://same.example.com")
        pid = project["id"]
        self.import_text(pid, "old", "https://same.example.com/x")
        self.import_text(pid, "new", "https://same.example.com/x")
        self.analyze(pid)
        self.run_quality(pid)
        self.assertIn("self_redirect", self.kinds(pid))

    def test_duplicate_and_many_to_one(self):
        project = self.analyzed_project()
        pid = project["id"]
        for suffix in ("/blog/trail-guide", "/legacy/zzz-unrelated"):
            row = self.mapping_for(pid, suffix)
            self.api.post(f"/api/projects/{pid}/mappings/{row['id']}/assign/",
                          {"url": "https://new.example.com/one", "confirm_many_to_one": True}, format="json")
        self.run_quality(pid)
        self.assertIn("many_to_one", self.kinds(pid))

    def test_loop_and_chain(self):
        project = self.create_project()
        pid = project["id"]
        self.import_text(pid, "old", "https://old.example.com/a\nhttps://old.example.com/b\n")
        self.import_text(pid, "new", "https://old.example.com/b\nhttps://old.example.com/a\n")
        self.analyze(pid)
        for row in self.mappings(pid):
            self.api.post(f"/api/projects/{pid}/mappings/{row['id']}/approve/", {"confirm_low_confidence": True, "confirm_many_to_one": True}, format="json")
        self.run_quality(pid)
        self.assertTrue({"self_redirect", "redirect_loop", "redirect_chain"} & self.kinds(pid))

    def test_staleness_flag_after_new_decision(self):
        project = self.analyzed_project()
        pid = project["id"]
        self.run_quality(pid)
        self.assertFalse(self.api.get(f"/api/projects/{pid}/quality/").json()["stale"])
        row = self.mapping_for(pid, "/about")
        self.api.post(f"/api/projects/{pid}/mappings/{row['id']}/approve/", {}, format="json")
        self.assertTrue(self.api.get(f"/api/projects/{pid}/quality/").json()["stale"])

    def test_rerunning_replaces_findings_instead_of_duplicating(self):
        project = self.analyzed_project()
        first = self.run_quality(project["id"])["total"]
        second = self.run_quality(project["id"])["total"]
        self.assertEqual(first, second)
        count = self.api.get(f"/api/projects/{project['id']}/quality/").json()["count"]
        self.assertEqual(count, second)
