from django.test import SimpleTestCase, override_settings

from services.urlnorm import NormRules, normalize_url, slug_of, tokens


class NormalizationTests(SimpleTestCase):
    def full(self, url, **rules):
        result = normalize_url(url, NormRules(**rules))
        self.assertTrue(result.ok, result.error)
        return result.full

    def test_scheme_host_default_port_and_fragment(self):
        self.assertEqual(self.full("HTTP://Example.COM:80/A#top"), "http://example.com/A")
        self.assertEqual(self.full("https://example.com:443/"), "https://example.com/")
        self.assertEqual(self.full("https://example.com:8443/x"), "https://example.com:8443/x")

    def test_original_is_never_changed(self):
        result = normalize_url("  HTTP://Example.COM/A/  ")
        self.assertEqual(result.original, "  HTTP://Example.COM/A/  ")

    def test_dot_segments_removed(self):
        self.assertEqual(self.full("https://e.com/a/./b/../c"), "https://e.com/a/c")

    def test_trailing_slash_rule(self):
        self.assertEqual(self.full("https://e.com/about/"), "https://e.com/about")
        self.assertEqual(self.full("https://e.com/about/", strip_trailing_slash=False), "https://e.com/about/")
        self.assertEqual(self.full("https://e.com/"), "https://e.com/")  # the root always keeps its slash

    def test_case_rule(self):
        self.assertEqual(self.full("https://e.com/About"), "https://e.com/About")
        self.assertEqual(self.full("https://e.com/About%2fX", ignore_case=True), "https://e.com/about%2Fx")

    def test_percent_encoding_is_canonical_without_changing_meaning(self):
        self.assertEqual(self.full("https://e.com/%7euser/caf%c3%a9"), "https://e.com/~user/caf%C3%A9")
        self.assertEqual(self.full("https://e.com/a%2Fb"), "https://e.com/a%2Fb")  # %2F is not a slash
        self.assertEqual(self.full("https://e.com/100%/x"), "https://e.com/100%25/x")
        self.assertEqual(self.full("https://e.com/über"), "https://e.com/%C3%BCber")

    def test_double_slash_in_path_is_kept(self):
        self.assertEqual(self.full("https://e.com/a//b"), "https://e.com/a//b")

    def test_query_modes(self):
        self.assertEqual(self.full("https://e.com/p?b=2&a=1"), "https://e.com/p?a=1&b=2")
        self.assertEqual(self.full("https://e.com/p?b=2&a=1", query_mode="drop_all"), "https://e.com/p")
        self.assertEqual(self.full("https://e.com/p?utm_source=x&id=7", query_mode="drop_listed", drop_params=("utm_source",)), "https://e.com/p?id=7")

    def test_www_rule_and_idn(self):
        self.assertEqual(self.full("https://www.e.com/x", ignore_www=True), "https://e.com/x")
        self.assertEqual(self.full("https://www.e.com/x"), "https://www.e.com/x")
        self.assertEqual(self.full("https://bücher.de/"), "https://xn--bcher-kva.de/")

    def test_relative_paths_use_the_site_address(self):
        self.assertEqual(normalize_url("/about/", NormRules(), base="https://old.com").full, "https://old.com/about")
        self.assertFalse(normalize_url("/about", NormRules()).ok)  # no base: cannot guess the host

    def test_invalid_values_have_clear_reasons(self):
        cases = {
            "": "Empty", "example.com/page": "Only http", "ftp://e.com/x": "Only http", "javascript:alert(1)": "Only http",
            "https://": "host", "https://u:p@e.com/": "user name", "https://e.com/a b": "spaces", "https://e.com:99999/": "not valid",
        }
        for value, fragment in cases.items():
            result = normalize_url(value)
            self.assertFalse(result.ok, value)
            self.assertIn(fragment.lower(), result.error.lower(), value)

    @override_settings(MAX_URL_LENGTH=50)
    def test_length_limit(self):
        self.assertFalse(normalize_url("https://e.com/" + "a" * 60).ok)

    def test_tokens_and_slug(self):
        self.assertEqual(tokens("Best-Running_Shoes.html"), ["best", "running", "shoes", "html"])
        self.assertEqual(slug_of(["blog", "post-one.php"]), "post-one")
        self.assertEqual(slug_of(["blog", "index.html"]), "blog")
        self.assertEqual(slug_of([]), "")
