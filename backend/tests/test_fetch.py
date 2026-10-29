import socket
from unittest import mock

from django.test import SimpleTestCase, override_settings

from services import safe_fetch

from .base import ApiTest, error_of


def addrinfo(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


class AddressTests(SimpleTestCase):
    def test_public_and_private_addresses(self):
        for ip in ("8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"):
            self.assertTrue(safe_fetch.is_public_ip(ip), ip)
        for ip in ("127.0.0.1", "10.0.0.5", "172.16.0.1", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1",
                   "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "224.0.0.1", "not-an-ip"):
            self.assertFalse(safe_fetch.is_public_ip(ip), ip)

    def test_url_checks(self):
        with mock.patch("socket.getaddrinfo", return_value=addrinfo("93.184.216.34")):
            parts, port, ip = safe_fetch.check_url("https://example.com/page")
            self.assertEqual((port, ip), (443, "93.184.216.34"))
        for bad in ("ftp://example.com/", "file:///etc/passwd", "https://user:pw@example.com/", "https://example.com:8080/", "http:///nohost"):
            with mock.patch("socket.getaddrinfo", return_value=addrinfo("93.184.216.34")), self.assertRaises(safe_fetch.FetchError, msg=bad):
                safe_fetch.check_url(bad)

    def test_host_resolving_to_a_private_address_is_blocked(self):
        with mock.patch("socket.getaddrinfo", return_value=addrinfo("127.0.0.1")), self.assertRaises(safe_fetch.FetchError):
            safe_fetch.check_url("https://looks-public.example.com/")

    def test_one_private_address_among_public_ones_blocks_the_host(self):
        with mock.patch("socket.getaddrinfo", return_value=addrinfo("93.184.216.34", "10.0.0.1")), self.assertRaises(safe_fetch.FetchError):
            safe_fetch.check_url("https://mixed.example.com/")

    def test_unresolvable_host(self):
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror), self.assertRaises(safe_fetch.FetchError):
            safe_fetch.check_url("https://nope.invalid/")

    def test_parse_page_reads_title_h1_description(self):
        html = b"<html><head><title> My  Title </title><meta name='description' content='Desc here'><link rel='canonical' href='/c'></head><body><h1>Heading</h1><script>var x=1</script></body></html>"
        info = safe_fetch.parse_page(html, "text/html")
        self.assertEqual((info["title"], info["h1"], info["meta_description"]), ("My Title", "Heading", "Desc here"))


class FetchEndpointTests(ApiTest):
    def test_disabled_by_default(self):
        project = self.project_with_urls()
        r = self.api.post(f"/api/projects/{project['id']}/fetch-metadata/", {"side": "old"}, format="json")
        self.assertEqual((r.status_code, error_of(r)["code"]), (403, "fetch_disabled"))

    @override_settings(ENABLE_WEBSITE_FETCH=True)
    def test_private_targets_are_reported_not_fetched(self):
        project = self.project_with_urls()
        with mock.patch("socket.getaddrinfo", return_value=addrinfo("127.0.0.1")):
            r = self.api.post(f"/api/projects/{project['id']}/fetch-metadata/", {"side": "old"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["fetched"], 0)
        self.assertTrue(all("private" in (x["error"] or "") for x in body["results"]))

    @override_settings(ENABLE_WEBSITE_FETCH=True)
    def test_validation_and_isolation(self):
        project = self.project_with_urls()
        self.assertEqual(error_of(self.api.post(f"/api/projects/{project['id']}/fetch-metadata/", {"side": "x"}, format="json"))["code"], "invalid_side")
        other = self.client_for(self.make_user("other@example.com"))
        self.assertEqual(other.post(f"/api/projects/{project['id']}/fetch-metadata/", {"side": "old"}, format="json").status_code, 404)
