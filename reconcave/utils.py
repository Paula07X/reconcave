"""URL, hostname and domain-name helpers.

Uses ``tldextract`` when it's installed (accurate public-suffix-list based
domain splitting). Falls back to a small heuristic covering the most common
two-part TLDs when it isn't, so the package has zero hard dependencies.
"""

import re
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse  # noqa: F401  (urljoin re-exported for convenience)

try:
    import tldextract as _tldextract
    _HAS_TLDEXTRACT = True
except ImportError:  # pragma: no cover - exercised only when dep is missing
    _tldextract = None
    _HAS_TLDEXTRACT = False


# A conservative RFC-1123-ish hostname check. Rejects emails, whitespace,
# and other junk that sometimes leaks into crt.sh's name_value field.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)


def is_valid_hostname(name: str) -> bool:
    """Return True if `name` looks like a real DNS hostname.

    Filters out email addresses (contain '@'), wildcards left un-stripped,
    and other malformed entries that public data sources sometimes emit.
    """
    if not name or "@" in name or " " in name:
        return False
    if name.startswith("*"):
        return False
    return bool(_HOSTNAME_RE.match(name))


def normalize_url(url: str) -> str:
    """Strip fragments and trailing-slash quirks so equivalent URLs dedupe."""
    url, _frag = urldefrag(url)
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


_TWO_PART_TLDS = {
    "co.uk", "com.au", "co.jp", "com.br", "co.in", "co.nz", "co.za",
    "com.mx", "com.sg", "com.tr", "co.kr", "com.hk",
}


def registrable_domain(netloc: str) -> str:
    """Reduce a host to its registrable domain, e.g.
    'a.b.example.co.uk' -> 'example.co.uk'.

    Uses tldextract (public suffix list) when available; otherwise a small
    hardcoded set of common two-part TLDs, which covers most real-world
    cases but is not exhaustive.
    """
    netloc = netloc.split(":")[0].lower()  # drop a port if present

    if _HAS_TLDEXTRACT:
        ext = _tldextract.extract(netloc)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
        return netloc

    parts = netloc.split(".")
    if len(parts) <= 2:
        return netloc
    last_two = ".".join(parts[-2:])
    if last_two in _TWO_PART_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def same_domain(url: str, base_netloc: str, include_subdomains: bool) -> bool:
    netloc = urlparse(url).netloc.lower()
    if include_subdomains:
        return netloc == base_netloc or netloc.endswith("." + base_netloc)
    return netloc == base_netloc


def tldextract_available() -> bool:
    return _HAS_TLDEXTRACT
