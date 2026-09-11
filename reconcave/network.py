"""HTTP session, robots.txt handling, rate limiting, DNS and ASN helpers."""

import logging
import secrets
import socket
import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import dns.resolver as _dns_resolver
    _HAS_DNSPYTHON = True
except ImportError:  # pragma: no cover
    _dns_resolver = None
    _HAS_DNSPYTHON = False

log = logging.getLogger("reconcave")

DEFAULT_USER_AGENT = "ReconCave/1.0 (+https://github.com/paula07x/reconcave)"


def build_session(user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=32)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


class RobotsCache:
    """Fetches and caches robots.txt per host, thread-safe."""

    def __init__(self, session: requests.Session, user_agent: str):
        self.session = session
        self.user_agent = user_agent
        self._cache = {}
        self._lock = Lock()

    def _get_parser(self, url: str) -> RobotFileParser:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            if root in self._cache:
                return self._cache[root]
        rp = RobotFileParser()
        try:
            resp = self.session.get(urljoin(root, "/robots.txt"), timeout=5)
            rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
        except requests.RequestException:
            rp.parse([])
            log.warning("Could not fetch robots.txt for %s; allowing all", root)
        with self._lock:
            self._cache[root] = rp
        return rp

    def allowed(self, url: str) -> bool:
        try:
            return self._get_parser(url).can_fetch(self.user_agent, url)
        except Exception:
            return True


@dataclass
class RateLimiter:
    """Per-host delay enforcement, thread-safe."""

    delay: float
    _last_hit: dict = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def wait(self, netloc: str):
        if self.delay <= 0:
            return
        wait_for = 0.0
        with self._lock:
            last = self._last_hit.get(netloc, 0.0)
            now = time.monotonic()
            wait_for = self.delay - (now - last)
            self._last_hit[netloc] = (last + self.delay) if wait_for > 0 else now
        if wait_for > 0:
            time.sleep(wait_for)


def resolve_ips(hostname: str) -> list:
    """Resolve a hostname to its IPv4/IPv6 addresses via plain DNS."""
    ips = set()
    try:
        for _family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(hostname, None):
            ips.add(sockaddr[0])
    except socket.gaierror:
        pass
    return sorted(ips)


def detect_wildcard_dns(domain: str) -> bool:
    """Probe a random, almost-certainly-nonexistent subdomain. If it
    resolves, the zone has a wildcard DNS record, meaning ANY subdomain
    name will appear to 'resolve' — a common false-positive source for
    brute-forced or guessed subdomains."""
    probe = f"{secrets.token_hex(12)}.{domain}"
    return bool(resolve_ips(probe))


def dns_records(domain: str) -> dict:
    """Best-effort NS/MX/TXT lookup for the apex domain. Returns an empty
    dict (with a note) if dnspython isn't installed — this is an optional
    enrichment, not a hard requirement."""
    if not _HAS_DNSPYTHON:
        return {"available": False}

    result = {"available": True, "NS": [], "MX": [], "TXT": []}
    for rtype in ("NS", "MX", "TXT"):
        try:
            answers = _dns_resolver.resolve(domain, rtype, lifetime=5)
            result[rtype] = sorted(str(r).strip('"') for r in answers)
        except Exception:
            result[rtype] = []
    return result


def dnspython_available() -> bool:
    return _HAS_DNSPYTHON


def get_tls_info(host: str, port: int = 443, timeout: float = 6.0) -> dict:
    """Best-effort TLS certificate metadata for a host: issuer, subject,
    and expiry. Non-fatal — returns {"available": False} on any failure
    (host doesn't speak TLS, times out, self-signed and rejected, etc.)."""
    import ssl

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        issuer = dict(x[0] for x in cert.get("issuer", []))
        subject = dict(x[0] for x in cert.get("subject", []))
        return {
            "available": True,
            "issuer": issuer.get("organizationName") or issuer.get("commonName"),
            "subject_cn": subject.get("commonName"),
            "not_after": cert.get("notAfter"),
            "not_before": cert.get("notBefore"),
            "san_count": len(cert.get("subjectAltName", [])),
        }
    except Exception:
        return {"available": False}


def get_cname(hostname: str) -> str:
    """Return the CNAME target for a hostname, or None. Requires
    dnspython — plain socket.getaddrinfo() resolves *through* CNAMEs
    transparently and never exposes them."""
    if not _HAS_DNSPYTHON:
        return None
    try:
        answers = _dns_resolver.resolve(hostname, "CNAME", lifetime=5)
        return str(answers[0].target).rstrip(".")
    except Exception:
        return None


def check_dangling_cname(hostname: str) -> dict:
    """Flags a classic subdomain-takeover setup: a CNAME pointing at a
    target that itself no longer resolves (e.g. a decommissioned cloud
    resource — S3 bucket, Heroku app, etc. that was never cleaned up from
    DNS). This is read-only DNS inspection of your own zone; it does not
    attempt to claim or interact with the dangling target."""
    if not _HAS_DNSPYTHON:
        return {"checked": False, "reason": "dnspython not installed"}

    cname = get_cname(hostname)
    if not cname:
        return {"checked": True, "has_cname": False}

    target_resolves = bool(resolve_ips(cname))
    return {
        "checked": True,
        "has_cname": True,
        "cname_target": cname,
        "target_resolves": target_resolves,
        "possible_takeover": not target_resolves,
    }


def email_security_info(domain: str) -> dict:
    """SPF (from apex TXT records) and DMARC (from _dmarc.<domain> TXT)
    presence — standard, read-only email-security posture checks. Requires
    dnspython; returns an 'available: False' stub without it."""
    if not _HAS_DNSPYTHON:
        return {"available": False, "reason": "dnspython not installed"}

    result = {"available": True, "spf": None, "dmarc": None, "mx": []}

    try:
        for r in _dns_resolver.resolve(domain, "TXT", lifetime=5):
            txt = str(r).strip('"')
            if txt.lower().startswith("v=spf1"):
                result["spf"] = txt
    except Exception:
        pass

    try:
        for r in _dns_resolver.resolve(f"_dmarc.{domain}", "TXT", lifetime=5):
            txt = str(r).strip('"')
            if txt.lower().startswith("v=dmarc1"):
                result["dmarc"] = txt
    except Exception:
        pass

    try:
        result["mx"] = sorted(str(r.exchange).rstrip(".") for r in _dns_resolver.resolve(domain, "MX", lifetime=5))
    except Exception:
        pass

    return result


def lookup_asn_batch(ips: list, timeout: float = 10.0) -> dict:
    """Best-effort ASN/org lookup for a batch of IPs via ip-api.com's free
    batch endpoint (no API key, rate-limited to ~15 req/min by the
    provider). Returns {ip: {"org": ..., "as": ..., "country": ...}}.
    Silently returns {} on any failure — this is a nice-to-have, never a
    blocker for the rest of the scan."""
    if not ips:
        return {}
    out = {}
    session = requests.Session()
    batch_size = 100  # ip-api.com's documented batch limit
    fields = "query,org,as,country,status"
    try:
        for i in range(0, len(ips), batch_size):
            chunk = ips[i:i + batch_size]
            payload = [{"query": ip, "fields": fields} for ip in chunk]
            resp = session.post(
                f"http://ip-api.com/batch?fields={fields}",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            for entry in resp.json():
                if entry.get("status") == "success":
                    out[entry["query"]] = {
                        "org": entry.get("org") or entry.get("as"),
                        "as": entry.get("as"),
                        "country": entry.get("country"),
                    }
    except (requests.RequestException, ValueError) as e:
        log.warning("ASN lookup failed (non-fatal): %s", e)
    return out
