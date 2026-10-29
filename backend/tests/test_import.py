import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from openpyxl import Workbook

from projects.models import NewURL, OldURL, URLImportBatch

from .base import ApiTest, error_of


def upload(name, data, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def xlsx_bytes(rows):
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class ImportTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.project = self.create_project()
        self.pid = self.project["id"]

    def post_file(self, kind, name, data, **extra):
        return self.api.post(f"/api/projects/{self.pid}/imports/", {"kind": kind, "file": upload(name, data), **extra}, format="multipart")

    # ---- paste
    def test_paste_without_header_and_original_is_preserved(self):
        body = self.import_text(self.pid, "old", "HTTPS://Old.Example.com/About/\nhttps://old.example.com/contact\n")
        self.assertEqual((body["imported_count"], body["invalid_count"], body["duplicate_count"]), (2, 0, 0))
        first = OldURL.objects.get(project_id=self.pid, original_url="HTTPS://Old.Example.com/About/")
        self.assertEqual(first.normalized_url, "https://old.example.com/About")  # compared form is separate
        self.assertEqual(first.row_number, 1)

    def test_invalid_and_duplicate_rows_are_reported_not_hidden(self):
        text = "https://old.example.com/a\nnot a url\nftp://old.example.com/b\nhttps://old.example.com/a/\n=cmd|' /C calc'!A0\nhttps://old.example.com/ok"
        body = self.import_text(self.pid, "old", text)
        self.assertEqual(body["total_rows"], 6)
        self.assertEqual(body["imported_count"], 2)
        self.assertEqual(body["invalid_count"], 3)
        self.assertEqual(body["duplicate_count"], 1)
        rows = {e["row"]: e for e in body["errors"]}
        self.assertEqual(rows[2]["type"], "invalid")
        self.assertIn("Duplicate of row 1", rows[4]["reason"])
        self.assertIn("=cmd", rows[5]["value"])  # reported, never executed or dropped silently
        self.assertEqual(OldURL.objects.filter(project_id=self.pid).count(), 2)

    def test_nothing_valid_means_nothing_saved(self):
        body = self.import_text(self.pid, "old", "nope\nalso nope", expect=400)
        self.assertEqual(body["error"]["code"], "no_valid_urls")
        self.assertEqual(URLImportBatch.objects.count(), 0)

    def test_relative_paths_are_resolved_against_the_project_site(self):
        self.import_text(self.pid, "old", "/about\n/blog/post/")
        urls = sorted(OldURL.objects.filter(project_id=self.pid).values_list("normalized_url", flat=True))
        self.assertEqual(urls, ["https://old.example.com/about", "https://old.example.com/blog/post"])

    def test_empty_input_and_bad_kind(self):
        r = self.api.post(f"/api/projects/{self.pid}/imports/", {"kind": "old"}, format="json")
        self.assertEqual(error_of(r)["code"], "input_required")
        r = self.api.post(f"/api/projects/{self.pid}/imports/", {"kind": "sideways", "text": "https://a.com/"}, format="json")
        self.assertEqual(error_of(r)["code"], "invalid_kind")

    # ---- files
    def test_csv_with_crawler_headers_is_detected(self):
        csv = ("Address,Status Code,Title 1,Meta Description 1,H1-1,Canonical Link Element 1\n"
               "https://new.example.com/shop,200,Shop,All our shoes,Shoes,https://new.example.com/shop\n"
               "https://new.example.com/old-page,301,,,,\n").encode()
        preview = self.api.post(f"/api/projects/{self.pid}/imports/preview/", {"kind": "new", "file": upload("crawl.csv", csv)}, format="multipart").json()
        self.assertTrue(preview["has_header"])
        self.assertEqual(preview["suggested_mapping"], {"url": 0, "status_code": 1, "title": 2, "meta_description": 3, "h1": 4, "canonical_url": 5})
        body = self.post_file("new", "crawl.csv", csv).json()
        self.assertEqual(body["imported_count"], 2)
        shop = NewURL.objects.get(project_id=self.pid, original_url="https://new.example.com/shop")
        self.assertEqual((shop.title, shop.h1, shop.status_code), ("Shop", "Shoes", 200))

    def test_manual_column_mapping(self):
        csv = b"id,page,name\n1,https://old.example.com/a,Page A\n2,https://old.example.com/b,Page B\n"
        body = self.post_file("old", "pages.csv", csv, column_map='{"url": 1, "title": 2}').json()
        self.assertEqual(body["imported_count"], 2)
        self.assertEqual(OldURL.objects.get(project_id=self.pid, original_url="https://old.example.com/b").title, "Page B")

    def test_wrong_column_choice_is_rejected(self):
        csv = b"url\nhttps://old.example.com/a\n"
        r = self.post_file("old", "p.csv", csv, column_map='{"url": 7}')
        self.assertEqual(error_of(r)["code"], "invalid_column_map")

    def test_xlsx_import(self):
        data = xlsx_bytes([["URL", "Title"], ["https://old.example.com/x", "X page"], ["https://old.example.com/y", "Y page"]])
        body = self.post_file("old", "list.xlsx", data).json()
        self.assertEqual(body["imported_count"], 2)
        self.assertEqual(OldURL.objects.get(project_id=self.pid, original_url="https://old.example.com/y").title, "Y page")

    def test_csv_formats_utf8_bom_semicolon_and_cp1252(self):
        bom = ("﻿url;title\nhttps://old.example.com/a;Café\n").encode("utf-8")
        self.assertEqual(self.post_file("old", "a.csv", bom).json()["imported_count"], 1)
        self.assertEqual(OldURL.objects.get(project_id=self.pid).title, "Café")
        cp = "url,title\nhttps://old.example.com/b,Crème\n".encode("cp1252")
        self.assertEqual(self.post_file("old", "b.csv", cp).json()["imported_count"], 1)
        self.assertEqual(OldURL.objects.get(project_id=self.pid, original_url="https://old.example.com/b").title, "Crème")

    def test_disallowed_and_fake_files_are_refused(self):
        self.assertEqual(error_of(self.post_file("old", "run.exe", b"MZ\x90\x00"))["code"], "file_type_not_allowed")
        self.assertEqual(error_of(self.post_file("old", "list.xlsx", b"just text, not a zip"))["code"], "file_invalid")
        self.assertEqual(error_of(self.post_file("old", "list.csv", b"a\x00b\x00c\x00"))["code"], "file_invalid")
        self.assertEqual(error_of(self.post_file("old", "empty.csv", b""))["code"], "file_empty")
        self.assertEqual(OldURL.objects.count(), 0)

    @override_settings(MAX_UPLOAD_MB=1)
    def test_file_size_limit(self):
        big = b"url\n" + b"https://old.example.com/page\n" * 50000  # about 1.4 MB
        r = self.post_file("old", "big.csv", big)
        self.assertEqual(r.status_code, 413)
        self.assertEqual(error_of(r)["code"], "file_too_large")

    @override_settings(MAX_IMPORT_ROWS=20)
    def test_row_limit(self):
        text = "\n".join(f"https://old.example.com/p{i}" for i in range(30))
        r = self.api.post(f"/api/projects/{self.pid}/imports/", {"kind": "old", "text": text}, format="json")
        self.assertEqual(r.status_code, 413)
        self.assertEqual(error_of(r)["code"], "too_many_rows")
        self.assertEqual(OldURL.objects.count(), 0)

    @override_settings(MAX_URLS_PER_PROJECT=5)
    def test_per_project_url_limit(self):
        self.import_text(self.pid, "old", "\n".join(f"https://old.example.com/p{i}" for i in range(4)))
        body = self.import_text(self.pid, "old", "\n".join(f"https://old.example.com/q{i}" for i in range(4)), expect=413)
        self.assertEqual(body["error"]["code"], "too_many_urls")
        self.assertEqual(OldURL.objects.filter(project_id=self.pid).count(), 4)  # all-or-nothing

    def test_large_import_within_limits(self):
        text = "\n".join(f"https://old.example.com/section-{i % 40}/article-number-{i}" for i in range(4000))
        body = self.import_text(self.pid, "old", text)
        self.assertEqual(body["imported_count"], 4000)

    # ---- append / replace
    def test_append_adds_and_updates_without_blanking(self):
        self.post_file("new", "a.csv", b"url,title\nhttps://new.example.com/a,Title A\n")
        body = self.import_text(self.pid, "new", "https://new.example.com/a\nhttps://new.example.com/b\n")
        self.assertEqual((body["imported_count"], body["updated_count"]), (1, 0))
        self.assertEqual(NewURL.objects.get(project_id=self.pid, original_url="https://new.example.com/a").title, "Title A")  # not blanked
        body = self.post_file("new", "b.csv", b"url,title\nhttps://new.example.com/a,Better title\n").json()
        self.assertEqual(body["updated_count"], 1)

    def test_replace_removes_urls_that_are_gone_and_resets_decisions_that_used_them(self):
        project = self.analyzed_project(name="Replace test")
        pid = project["id"]
        about = self.mapping_for(pid, "/about")
        self.assertEqual(self.api.post(f"/api/projects/{pid}/mappings/{about['id']}/approve/", {"confirm_low_confidence": True, "confirm_many_to_one": True}, format="json").status_code, 200)
        body = self.import_text(pid, "new", "https://new.example.com/contact-us\nhttps://new.example.com/\n", mode="replace")
        self.assertEqual(body["removed_count"], 4)
        refreshed = self.mapping_for(pid, "/about")
        self.assertEqual(refreshed["status"], "pending")  # the approved destination no longer exists
        self.assertIsNone(refreshed["final_new_url_id"])

    def test_replace_with_nothing_valid_deletes_nothing(self):
        self.import_text(self.pid, "old", "https://old.example.com/keep")
        self.import_text(self.pid, "old", "garbage", mode="replace", expect=400)
        self.assertEqual(OldURL.objects.filter(project_id=self.pid).count(), 1)

    def test_import_history_and_provenance(self):
        csv = b"url\nhttps://old.example.com/a\n"
        self.post_file("old", "history.csv", csv)
        history = self.api.get(f"/api/projects/{self.pid}/imports/").json()["results"]
        self.assertEqual(history[0]["filename"], "history.csv")
        self.assertEqual(len(history[0]["file_sha256"]), 64)  # the file's fingerprint is kept, the file itself is not
        detail = self.api.get(f"/api/projects/{self.pid}/imports/{history[0]['id']}/").json()
        self.assertEqual(detail["imported_count"], 1)

    def test_normalisation_rules_apply_and_can_be_changed_later(self):
        self.import_text(self.pid, "old", "https://old.example.com/About\nhttps://old.example.com/about\n")
        self.assertEqual(OldURL.objects.filter(project_id=self.pid).count(), 2)  # case-sensitive by default
        settings = {"normalization": {"ignore_case": True}}
        r = self.api.patch(f"/api/projects/{self.pid}/", {"settings": settings}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["update_info"]["merged"], 1)  # the two collapsed into one
        self.assertEqual(OldURL.objects.filter(project_id=self.pid).count(), 1)
