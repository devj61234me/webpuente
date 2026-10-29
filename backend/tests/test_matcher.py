from django.test import SimpleTestCase

from projects.defaults import merged_settings
from services.matcher import Matcher, Page
from services.urlnorm import normalize_url


def page(pid, url, **kw):
    n = normalize_url(url)
    assert n.ok, n.error
    return Page(pid, n.full, n.path_key, **kw)


def engine(new_pages, **overrides):
    config = merged_settings({})
    for key, value in overrides.items():
        config[key] = {**config[key], **value}
    return Matcher(new_pages, config)


NEW = [
    page(1, "https://new.example.com/shop/running-shoes"),
    page(2, "https://new.example.com/journal/best-running-shoes-2024", title="Best running shoes 2024"),
    page(3, "https://new.example.com/about-us"),
    page(4, "https://new.example.com/contact"),
    page(5, "https://new.example.com/"),
]


class MatcherTests(SimpleTestCase):
    def test_exact_url_beats_everything(self):
        r = engine(NEW).match(page(10, "https://new.example.com/contact/"))
        self.assertEqual((r.new_id, r.score, r.match_type, r.band), (4, 100, "exact_url", "high"))

    def test_same_path_on_a_different_host(self):
        r = engine(NEW).match(page(10, "https://old.example.com/contact"))
        self.assertEqual((r.new_id, r.match_type, r.band), (4, "exact_path", "high"))
        self.assertEqual(r.score, 97)

    def test_home_page_maps_to_home_page(self):
        self.assertEqual(engine(NEW).match(page(10, "https://old.example.com/")).new_id, 5)

    def test_slug_match_with_different_sections(self):
        r = engine(NEW).match(page(10, "https://old.example.com/products/running-shoes"))
        self.assertEqual(r.new_id, 1)
        self.assertEqual(r.match_type, "slug")
        self.assertIn(r.band, ("medium", "high"))
        self.assertTrue(any("page name" in reason for reason in r.reasons))

    def test_every_recommendation_explains_itself(self):
        for url in ["https://old.example.com/about", "https://old.example.com/blog/best-running-shoes"]:
            r = engine(NEW).match(page(10, url))
            self.assertTrue(r.reasons and all(isinstance(x, str) and x for x in r.reasons))
            self.assertTrue(r.components)

    def test_url_only_matches_say_so(self):
        r = engine(NEW).match(page(10, "https://old.example.com/about"))
        self.assertEqual(r.evidence, "url_only")
        self.assertTrue(any("URL only" in reason for reason in r.reasons))

    def test_titles_are_used_when_supplied(self):
        old = page(10, "https://old.example.com/blog/best-running-shoes", title="The best running shoes of 2024")
        r = engine(NEW).match(old)
        self.assertEqual(r.new_id, 2)
        self.assertEqual(r.evidence, "metadata")
        self.assertIn("title", r.components)

    def test_unrelated_page_is_unmatched_and_no_destination_is_invented(self):
        r = engine(NEW).match(page(10, "https://old.example.com/zzz/unrelated-thing"))
        self.assertEqual((r.new_id, r.band, r.score, r.match_type), (None, "unmatched", 0, "none"))

    def test_fuzzy_scores_never_exceed_the_cap(self):
        news = [page(1, "https://new.example.com/a/very-specific-page-name", title="Very specific page name")]
        old = page(10, "https://old.example.com/a/very-specific-page-name.html", title="Very specific page name")
        r = engine(news).match(old)
        self.assertLessEqual(r.score, 95)  # "very similar" is never shown as "certainly the same"

    def test_ambiguity_is_flagged(self):
        news = [page(1, "https://new.example.com/blog/shoes-guide-a"), page(2, "https://new.example.com/blog/shoes-guide-b")]
        r = engine(news).match(page(10, "https://old.example.com/blog/shoes-guide"))
        self.assertTrue(r.ambiguous)
        self.assertTrue(r.alternatives)

    def test_thresholds_are_configurable(self):
        old = page(10, "https://old.example.com/products/running-shoes")
        strict = engine(NEW, thresholds={"high": 99, "medium": 95, "min_accept": 90}).match(old)
        self.assertEqual(strict.band, "unmatched")
        loose = engine(NEW, thresholds={"high": 60, "medium": 50}).match(old)
        self.assertEqual(loose.band, "high")

    def test_weights_are_configurable(self):
        old = page(10, "https://old.example.com/blog/best-running-shoes", title="Completely different words here")
        only_url = engine(NEW, weights={"title": 0.0}).match(old)
        with_title = engine(NEW).match(old)
        self.assertGreater(only_url.score, with_title.score)

    def test_candidate_filter_limits_work(self):
        news = [page(i, f"https://new.example.com/section/item-{i}") for i in range(1, 400)]
        m = Matcher(news, merged_settings({}), max_candidates=20)
        old = page(1000, "https://old.example.com/section/item-77")
        self.assertLessEqual(len(m.candidates(old)), 20)

    def test_semantic_scores_are_used_only_when_vectors_exist(self):
        news = [page(1, "https://new.example.com/footwear/trainers")]
        m = Matcher(news, merged_settings({}), new_vectors={1: [1.0, 0.0]})
        old = page(10, "https://old.example.com/footwear/sneakers")
        plain = m.match(old)
        semantic = m.match(old, old_vec=[1.0, 0.0])
        self.assertNotIn("semantic", plain.components)
        self.assertEqual(semantic.components["semantic"], 100)
        self.assertEqual(semantic.evidence, "semantic")

    def test_results_are_deterministic(self):
        m = engine(NEW)
        old = page(10, "https://old.example.com/about")
        self.assertEqual(m.match(old), m.match(old))
