"""
URL validation and normalisation.

Rules we follow:
- The user's original URL is never changed; we only build a separate "normalised" form for comparing.
- Normalising must not change what a URL means: no guessing a missing scheme, no collapsing // in paths,
  no lower-casing the path unless the user turned that rule on.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urljoin, urlsplit

from django.conf import settings

HEX = "0123456789ABCDEFabcdef"
UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
PATH_SAFE = UNRESERVED | set("/:@!$&'()*+,;=")
QUERY_SAFE = UNRESERVED | set("/:@!$&'()*+,;=?")
DEFAULT_PORTS = {"http": 80, "https": 443}
FILE_EXTENSIONS = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp", ".shtml")
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class NormRules:
    ignore_case: bool = False
    strip_trailing_slash: bool = True
    query_mode: str = "keep"  # keep | drop_all | drop_listed
    drop_params: tuple = ()
    ignore_www: bool = False

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        return cls(
            ignore_case=bool(data.get("ignore_case", False)),
            strip_trailing_slash=bool(data.get("strip_trailing_slash", True)),
            query_mode=data.get("query_mode", "keep"),
            drop_params=tuple(str(p).lower() for p in data.get("drop_params", [])),
            ignore_www=bool(data.get("ignore_www", False)),
        )


@dataclass
class NormalizedURL:
    original: str
    ok: bool
    error: str = ""
    full: str = ""        # normalised absolute URL
    host: str = ""
    path: str = ""
    query: str = ""
    path_key: str = ""    # path + ?query (host independent)
    segments: list = field(default_factory=list)  # decoded path segments


def _normalize_percent(text, safe, lower=False):
    """Re-encode text the canonical way: keep reserved characters as written, encode everything else,
    write percent escapes in upper case, and decode escapes of unreserved characters (%41 -> A).
    Escapes of reserved characters (for example %2F) stay encoded, because decoding them would change meaning."""
    out = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == "%":
            if i + 2 < len(text) and text[i + 1] in HEX and text[i + 2] in HEX:
                decoded = chr(int(text[i + 1 : i + 3], 16))
                if decoded in UNRESERVED:
                    out.append(decoded.lower() if lower else decoded)
                else:
                    out.append("%" + text[i + 1 : i + 3].upper())
                i += 3
                continue
            out.append("%25")  # a stray % is data, not an escape
            i += 1
            continue
        if char in safe:
            out.append(char.lower() if lower else char)
        else:
            out.append("".join("%{:02X}".format(b) for b in char.encode("utf-8")))
        i += 1
    return "".join(out)


def _remove_dot_segments(path):
    """RFC 3986 section 5.2.4: turn /a/b/../c/./d into /a/c/d."""
    output = []
    for segment in path.split("/"):
        if segment == "..":
            if len(output) > 1:
                output.pop()
        elif segment != ".":
            output.append(segment)
    result = "/".join(output)
    if path.endswith(("/..", "/.")) and not result.endswith("/"):
        result += "/"
    return result or "/"


def _normalize_query(query, rules):
    if not query or rules.query_mode == "drop_all":
        return ""
    parts = []
    for part in query.split("&"):
        if part == "":
            continue
        key = part.split("=", 1)[0]
        if rules.query_mode == "drop_listed" and _normalize_percent(key, QUERY_SAFE).lower() in rules.drop_params:
            continue
        parts.append(_normalize_percent(part, QUERY_SAFE))
    return "&".join(sorted(parts))  # parameter order rarely matters, so sort for stable comparison


def normalize_url(raw, rules=None, base=None):
    """Validate and normalise one URL. `base` lets a relative path like /about be resolved against a site URL."""
    rules = rules or NormRules()
    original = "" if raw is None else str(raw)
    text = original.strip()
    if not text:
        return NormalizedURL(original, False, "Empty value.")
    if len(text) > settings.MAX_URL_LENGTH:
        return NormalizedURL(original, False, f"URL is longer than {settings.MAX_URL_LENGTH} characters.")
    if re.search(r"[\s\x00-\x1f\x7f]", text):
        return NormalizedURL(original, False, "URL contains spaces or control characters.")
    if text.startswith("/") and not text.startswith("//") and base:
        text = urljoin(base, text)  # path-only lists are resolved against the project's site address
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        return NormalizedURL(original, False, "URL is not valid.")
    if parts.scheme.lower() not in ("http", "https"):
        return NormalizedURL(original, False, "Only http:// and https:// URLs are accepted (scheme is missing or not allowed).")
    if not parts.hostname:
        return NormalizedURL(original, False, "URL has no host name.")
    if parts.username or parts.password:
        return NormalizedURL(original, False, "URLs with a user name or password are not accepted.")

    scheme = parts.scheme.lower()
    host = parts.hostname.rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")  # internationalised domains -> punycode
    except UnicodeError:
        return NormalizedURL(original, False, "Host name is not valid.")
    if rules.ignore_www and host.startswith("www."):
        host = host[4:]
    host_part = f"[{host}]" if ":" in host else host
    if port and port != DEFAULT_PORTS[scheme]:
        host_part += f":{port}"

    path = _remove_dot_segments(parts.path or "/")
    path = _normalize_percent(path, PATH_SAFE, lower=rules.ignore_case)
    if rules.strip_trailing_slash and len(path) > 1:
        path = path.rstrip("/") or "/"
    query = _normalize_query(parts.query, rules)  # the #fragment is dropped: servers never see it

    path_key = path + (f"?{query}" if query else "")
    full = f"{scheme}://{host_part}{path_key}"
    segments = [unquote(s) for s in path.split("/") if s]
    return NormalizedURL(original, True, "", full, host, path, query, path_key, segments)


def tokens(text):
    """Lower-case word tokens: 'Best-Running_Shoes.html' -> ['best', 'running', 'shoes']."""
    return [t.lower() for t in TOKEN_RE.findall(text or "")]


def slug_of(segments):
    """The last path segment without a file extension (the 'slug')."""
    if not segments:
        return ""
    last = segments[-1]
    lowered = last.lower()
    for ext in FILE_EXTENSIONS:
        if lowered.endswith(ext):
            last = last[: -len(ext)]
            break
    if last.lower() in ("index", "default", "home") and len(segments) > 1:
        return segments[-2]  # /blog/index.html is really the 'blog' page
    return last
