from unittest import mock

import requests
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from projects.models import AnalysisRun, MappingRecommendation, MappingReview, OldURL

from .base import ApiTest, error_of


class AnalysisTests(ApiTest):
    def test_run_creates_recommendations_and_nothing_is_auto_approved(self):
        project = self.analyzed_project()
        rows = self.mappings(project["id"])
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["status"] == "pending" for r in rows))
        self.assertTrue(all(r["decided_at"] is None for r in rows))
        about = self.mapping_for(project["id"], "/about")
        self.assertEqual(about["recommended_url"], "https://new.example.com/about")
        self.assertEqual(about["match_type"], "exact_path")
        legacy = self.mapping_for(project["id"], "/legacy/zzz-unrelated")
        self.assertEqual((legacy["band"], legacy["final_url"], legacy["final_new_url_id"]), ("unmatched", "", None))

    def test_run_stats_and_progress(self):
        project = self.analyzed_project()
        run = self.api.get(f"/api/projects/{project['id']}/runs/").json()["results"][0]
        self.assertEqual((run["status"], run["progress"]), ("completed", 100))
        stats = run["stats"]
        self.assertEqual(stats["total"], 6)
        self.assertEqual(stats["high"] + stats["medium"] + stats["low"] + stats["unmatched"], 6)
        self.assertIsNotNone(run["finished_at"])

    def test_lists_must_be_imported_first(self):
        project = self.create_project()
        r = self.api.post(f"/api/projects/{project['id']}/analyze/")
        self.assertEqual(error_of(r)["code"], "lists_missing")
        self.import_text(project["id"], "old", "https://old.example.com/a")
        self.assertEqual(error_of(self.api.post(f"/api/projects/{project['id']}/analyze/"))["code"], "lists_missing")

    def test_duplicate_submission_is_blocked_while_a_run_is_active(self):
        project = self.project_with_urls()
        AnalysisRun.objects.create(project_id=project["id"], status="running", heartbeat_at=timezone.now())
        r = self.api.post(f"/api/projects/{project['id']}/analyze/")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(error_of(r)["code"], "analysis_in_progress")

    def test_a_dead_run_is_marked_failed_so_a_new_one_can_start(self):
        project = self.project_with_urls()
        stale = AnalysisRun.objects.create(project_id=project["id"], status="running")
        AnalysisRun.objects.filter(pk=stale.pk).update(heartbeat_at=timezone.now() - timezone.timedelta(hours=2))
        self.analyze(project["id"])
        stale.refresh_from_db()
        self.assertEqual(stale.status, "failed")
        self.assertIn("interrupted", stale.error_message)

    def test_a_crash_marks_the_run_failed_and_leaves_no_partial_results(self):
        project = self.project_with_urls()
        with mock.patch("projects.analysis.MappingRecommendation.objects.bulk_create", side_effect=RuntimeError("boom")):
            run = self.analyze(project["id"])
        self.assertEqual(run["status"], "failed")
        self.assertNotIn("boom", run["error_message"])  # internal details are not shown to users
        self.assertEqual(MappingRecommendation.objects.count(), 0)
        self.assertEqual(MappingReview.objects.count(), 0)
        again = self.analyze(project["id"])  # and a retry works
        self.assertEqual(again["status"], "completed")

    # ---- re-running keeps human decisions
    def approve(self, pid, row, **body):
        return self.api.post(f"/api/projects/{pid}/mappings/{row['id']}/approve/", {"confirm_low_confidence": True, "confirm_many_to_one": True, **body}, format="json")

    def test_rerun_keeps_approved_decisions(self):
        project = self.analyzed_project()
        pid = project["id"]
        about = self.mapping_for(pid, "/about")
        self.assertEqual(self.approve(pid, about).status_code, 200)
        self.analyze(pid)
        again = self.mapping_for(pid, "/about")
        self.assertEqual(again["status"], "approved")
        self.assertEqual(again["id"], about["id"])  # the same review row, not a new one
        run = self.api.get(f"/api/projects/{pid}/runs/").json()["results"][0]
        self.assertEqual(run["stats"]["decisions_preserved"], 1)

    def test_rerun_keeps_manual_assignments(self):
        project = self.analyzed_project()
        pid = project["id"]
        legacy = self.mapping_for(pid, "/legacy/zzz-unrelated")
        r = self.api.post(f"/api/projects/{pid}/mappings/{legacy['id']}/assign/", {"url": "https://new.example.com/special"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.analyze(pid)
        again = self.mapping_for(pid, "/legacy/zzz-unrelated")
        self.assertEqual((again["origin"], again["status"], again["final_url"]), ("manual", "approved", "https://new.example.com/special"))

    def test_rerun_with_changed_destination_resets_a_rejected_decision(self):
        project = self.analyzed_project()
        pid = project["id"]
        row = self.mapping_for(pid, "/products/running-shoes")
        self.api.post(f"/api/projects/{pid}/mappings/{row['id']}/reject/")
        self.analyze(pid)  # same suggestion again -> the rejection is respected
        self.assertEqual(self.mapping_for(pid, "/products/running-shoes")["status"], "rejected")
        self.import_text(pid, "new", "https://new.example.com/products/running-shoes-pro", mode="append")
        self.analyze(pid)
        after = self.mapping_for(pid, "/products/running-shoes")
        if after["final_url"] != row["final_url"]:
            self.assertEqual(after["status"], "pending")  # a different suggestion deserves a fresh review

    def test_new_old_urls_get_reviews_on_rerun(self):
        project = self.analyzed_project()
        pid = project["id"]
        self.import_text(pid, "old", "https://old.example.com/brand-new-page")
        self.analyze(pid)
        self.assertEqual(len(self.mappings(pid)), 7)

    def test_compare_runs(self):
        project = self.analyzed_project()
        pid = project["id"]
        self.import_text(pid, "new", "https://new.example.com/legacy/zzz-unrelated")
        self.analyze(pid)
        runs = self.api.get(f"/api/projects/{pid}/runs/").json()["results"]
        diff = self.api.get(f"/api/projects/{pid}/runs/compare/", {"a": runs[1]["id"], "b": runs[0]["id"]}).json()
        self.assertEqual(diff["newly_matched"], 1)
        self.assertEqual(diff["same"] + diff["changed"] + diff["newly_matched"] + diff["newly_unmatched"], 6)

    # ---- worker mode
    @override_settings(JOB_MODE="worker")
    def test_worker_mode_queues_and_the_worker_command_runs_it(self):
        project = self.project_with_urls()
        run = self.analyze(project["id"])
        self.assertEqual(run["status"], "queued")
        call_command("run_worker", "--once")
        done = self.api.get(f"/api/projects/{project['id']}/runs/{run['id']}/").json()
        self.assertEqual(done["status"], "completed")

    # ---- optional semantic matching
    def semantic_project(self):
        project = self.project_with_urls(
            old="https://old.example.com/footwear/sneakers\n", new="https://new.example.com/footwear/trainers\nhttps://new.example.com/garden/tools\n",
            settings={"use_embeddings": True},
        )
        return project

    @override_settings(EMBEDDINGS_ENABLED=True, EMBEDDINGS_API_KEY="test-key", EMBEDDINGS_MODEL="test-model")
    def test_semantic_scores_are_used_when_the_provider_answers(self):
        project = self.semantic_project()

        def fake_post(url, headers=None, json=None, timeout=None):
            vectors = [{"index": i, "embedding": [1.0, 0.0] if ("sneakers" in t or "trainers" in t) else [0.0, 1.0]} for i, t in enumerate(json["input"])]
            return mock.Mock(status_code=200, json=lambda: {"data": vectors})

        with mock.patch("services.embeddings.requests.post", side_effect=fake_post):
            run = self.analyze(project["id"])
        self.assertTrue(run["stats"]["semantic_used"])
        row = self.mappings(project["id"])[0]
        self.assertEqual(row["evidence"], "semantic")
        self.assertEqual(row["final_url"], "https://new.example.com/footwear/trainers")

    @override_settings(EMBEDDINGS_ENABLED=True, EMBEDDINGS_API_KEY="test-key", EMBEDDINGS_MODEL="test-model")
    def test_provider_failure_falls_back_and_says_so(self):
        project = self.semantic_project()
        with mock.patch("services.embeddings.requests.post", side_effect=requests.ConnectionError()), mock.patch("services.embeddings.time.sleep"):
            run = self.analyze(project["id"])
        self.assertEqual(run["status"], "completed")
        self.assertFalse(run["stats"]["semantic_used"])
        self.assertTrue(any("Semantic matching was skipped" in w for w in run["stats"]["warnings"]))

    def test_semantic_requested_but_not_configured_is_reported(self):
        project = self.semantic_project()
        run = self.analyze(project["id"])
        self.assertFalse(run["stats"]["semantic_used"])
        self.assertTrue(any("no embedding provider" in w for w in run["stats"]["warnings"]))

    @override_settings(EMBEDDINGS_ENABLED=True, EMBEDDINGS_API_KEY="test-key", EMBEDDINGS_MODEL="test-model")
    def test_bad_embedding_key_is_a_clear_warning(self):
        project = self.semantic_project()
        with mock.patch("services.embeddings.requests.post", return_value=mock.Mock(status_code=401)):
            run = self.analyze(project["id"])
        self.assertTrue(any("rejected the API key" in w for w in run["stats"]["warnings"]))

    def test_larger_run_finishes_and_filters_candidates(self):
        old = "\n".join(f"https://old.example.com/section-{i % 25}/article-{i}" for i in range(1500))
        new = "\n".join(f"https://new.example.com/section-{i % 25}/article-{i}" for i in range(1500))
        project = self.project_with_urls(old=old, new=new)
        run = self.analyze(project["id"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["stats"]["total"], 1500)
        self.assertEqual(run["stats"]["unmatched"], 0)
        self.assertLess(run["stats"]["seconds"], 60)
