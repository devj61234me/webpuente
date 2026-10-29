"""
Optional page fetching (titles, descriptions, H1, canonical URL, status code), built to be safe:

SSRF protection (stops the server being tricked into calling internal addresses):
  * only http/https on the standard ports 80 and 443
  * the host name is resolved by us and EVERY resulting IP must be a public address
    (no loopback, private, link-local, multicast, reserved or "this network" ranges, including IPv4-mapped IPv6)
  * we then connect to that exact IP, so the name cannot resolve somewhere else a moment later (DNS rebinding)
  * redirects are followed by hand (max 3) and each hop goes through the same checks
Politeness and limits: robots.txt is obeyed, timeouts, response size cap, HTML only, no cookies, no logins.
We never try to get around CAPTCHAs, authentication or robots rules.
"""
import ipaddress
import socket
import time
from html.parser import HTMLParser
from urllib import robotparser
from urllib.parse import urljoin, urlsplit

import urllib3
from django.conf import settings


class FetchError(Exception):
    """A readable reason a page could not be fetched."""


# ---------------------------------------------------------------- address checks
def is_public_ip(ip_text):
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 must be treated as 127.0.0.1
    return ip.is_global and not ip.is_multicast  # is_global is False for private/loopback/link-local/reserved


def resolve_public(host, port):
    """Resolve a host name and return one public IP, or raise FetchError if ANY address is not public."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError("The host name could not be resolved.")
    addresses = [info[4][0] for info in infos]
    if not addresses:
        raise FetchError("The host name could not be resolved.")
    for address in addresses:
        if not is_public_ip(address):
            raise FetchError("Blocked: this address points to a private or restricted network.")
    return addresses[0]


def check_url(url):
    """Validate scheme, port and host, and return (parts, public_ip)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https addresses can be fetched.")
    if not parts.hostname:
        raise FetchError("The address has no host name.")
    if parts.username or parts.password:
        raise FetchError("Addresses with a user name or password are not allowed.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise FetchError("The port is not valid.")
    if port not in (80, 443):
        raise FetchError("Only the standard ports 80 and 443 can be fetched.")
    return parts, port, resolve_public(parts.hostname, port)


# ---------------------------------------------------------------- one HTTP request pinned to a checked IP
def _request(url, accept, max_bytes):
    parts, port, ip = check_url(url)
    host = parts.hostname
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    timeout = urllib3.Timeout(connect=settings.FETCH_TIMEOUT_SECONDS, read=settings.FETCH_TIMEOUT_SECONDS)
    if parts.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(ip, port, timeout=timeout, retries=False, assert_hostname=host, server_hostname=host)
    else:
        pool = urllib3.HTTPConnectionPool(ip, port, timeout=timeout, retries=False)
    try:
        response = pool.urlopen(
            "GET", path, redirect=False, preload_content=False,
            headers={"Host": parts.netloc, "User-Agent": settings.FETCH_USER_AGENT, "Accept": accept, "Accept-Encoding": "identity"},
        )
        body = b""
        for chunk in response.stream(8192):
            body += chunk
            if len(body) > max_bytes:
                body = body[:max_bytes]  # keep the start of the page; titles and headings live there
                break
        response.release_conn()
        return response.status, response.headers, body
    except urllib3.exceptions.HTTPError as exc:
        raise FetchError(f"The page could not be reached ({exc.__class__.__name__}).")
    except OSError:
        raise FetchError("The page could not be reached.")
    finally:
        pool.close()


def fetch(url, accept="text/html,application/xhtml+xml", max_bytes=None):
    """GET with manual redirects. Returns (final_url, status, headers, body)."""
    max_bytes = max_bytes or settings.FETCH_MAX_BYTES
    current = url
    for _ in range(settings.FETCH_MAX_REDIRECTS + 1):
        status, headers, body = _request(current, accept, max_bytes)
        if status in (301, 302, 303, 307, 308) and headers.get("Location"):
            current = urljoin(current, headers["Location"])  # next loop re-checks the new address
            continue
        return current, status, headers, body
    raise FetchError("Too many redirects.")


# ---------------------------------------------------------------- reading the page
class _Meta(HTMLParser):
    """Collects title, meta description, first H1 and canonical link from HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = self.h1 = self.description = self.canonical = ""
        self._in = None
        self._done_title = self._done_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title" and not self._done_title:
            self._in = "title"
        elif tag == "h1" and not self._done_h1:
            self._in = "h1"
        elif tag == "meta" and (attrs.get("name") or "").lower() == "description" and not self.description:
            self.description = (attrs.get("content") or "").strip()
        elif tag == "link" and (attrs.get("rel") or "").lower() == "canonical" and not self.canonical:
            self.canonical = (attrs.get("href") or "").strip()

    def handle_endtag(self, tag):
        if tag == "title":
            self._done_title, self._in = True, None
        elif tag == "h1":
            self._done_h1, self._in = True, None

    def handle_data(self, data):
        if self._in == "title":
            self.title += data
        elif self._in == "h1":
            self.h1 += data


def parse_page(body, content_type=""):
    charset = "utf-8"
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip() or "utf-8"
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    parser = _Meta()
    try:
        parser.feed(text)
    except Exception:  # noqa: BLE001 - broken HTML must not stop the batch
        pass
    clean = lambda value, limit: " ".join(value.split())[:limit]  # noqa: E731
    return {
        "title": clean(parser.title, 500),
        "h1": clean(parser.h1, 500),
        "meta_description": clean(parser.description, 1000),
        "canonical_url": clean(parser.canonical, settings.MAX_URL_LENGTH),
    }


class RobotsCache:
    """robots.txt per host, fetched once per batch. An unreachable robots.txt means 'allowed'
    (the standard convention); an explicit disallow is always respected."""

    def __init__(self):
        self._cache = {}

    def allowed(self, url):
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        if key not in self._cache:
            parser = robotparser.RobotFileParser()
            try:
                _, status, _, body = fetch(f"{key}/robots.txt", accept="text/plain", max_bytes=200 * 1024)
                if status in (401, 403):
                    parser.disallow_all = True  # access restricted: be conservative
                elif status == 200:
                    parser.parse(body.decode("utf-8", errors="replace").splitlines())
                else:
                    parser.allow_all = True
            except FetchError:
                parser.allow_all = True
            self._cache[key] = parser
        return self._cache[key].can_fetch(settings.FETCH_USER_AGENT, url)


def fetch_page_details(url, robots):
    """Fetch one page politely. Returns a dict with status_code and any metadata found, or an 'error' text."""
    try:
        if not robots.allowed(url):
            return {"error": "Blocked by robots.txt (not fetched)."}
        final_url, status, headers, body = fetch(url)
    except FetchError as exc:
        return {"error": str(exc)}
    result = {"status_code": status, "final_url": final_url}
    content_type = headers.get("Content-Type", "")
    if status == 200 and "html" in content_type.lower():
        result.update(parse_page(body, content_type))
    elif status == 200:
        result["error"] = "Not an HTML page, so no details were read."
    time.sleep(settings.FETCH_DELAY_SECONDS)  # rate limit: never hammer a site
    return result
