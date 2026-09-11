"""Passive subdomain discovery (crt.sh), live HTTP probing, and report assembly."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import requests

from .network import check_dangling_cname, get_tls_info, lookup_asn_batch, resolve_ips
from .utils import is_valid_hostname

log = logging.getLogger("reconcave")


def discover_subdomains_crtsh(domain: str, session: requests.Session) -> set:
    """Passive subdomain discovery via certificate transparency logs
    (crt.sh). Public data, read-only, no requests sent to the target
    itself. Filters out email addresses and other non-hostname junk that
    crt.sh's name_value field sometimes contains."""
    subs = set()
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        entries = resp.json()
    except (requests.RequestException, ValueError) as e:
        log.warning("crt.sh lookup failed for %s: %s", domain, e)
        return subs

    raw_count = 0
    for entry in entries:
        name_value = entry.get("name_value", "")
        for name in name_value.split("\n"):
            raw_count += 1
            name = name.strip().lower().lstrip("*.")
            if is_valid_hostname(name) and name.endswith(domain):
                subs.add(name)

    filtered = raw_count - len(subs)
    log.info(
        "crt.sh returned %d candidate names for %s; %d valid hostnames kept (%d filtered as junk/duplicates)",
        raw_count, domain, len(subs), filtered,
    )
    return subs


def probe_host(session: requests.Session, host: str, timeout: float = 8.0, capture_headers: bool = False) -> dict:
    """Best-effort liveness probe for a bare host: try https then http,
    GET rather than HEAD (some servers mishandle HEAD), short timeout so
    one slow host can't stall the whole batch."""
    for scheme in ("https", "http"):
        url = f"{scheme}://{host}/"
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            title = None
            if "html" in resp.headers.get("Content-Type", ""):
                # cheap title extraction without a full parse
                text = resp.text[:5000]
                start = text.lower().find("<title>")
                end = text.lower().find("</title>")
                if start != -1 and end != -1:
                    title = text[start + 7:end].strip()[:200]
            result = {
                "scheme": scheme,
                "status_code": resp.status_code,
                "final_url": resp.url,
                "title": title,
            }
            if capture_headers:
                interesting = ("Server", "X-Powered-By", "Strict-Transport-Security", "Content-Security-Policy")
                result["headers"] = {h: resp.headers[h] for h in interesting if h in resp.headers}
            return result
        except requests.exceptions.RequestException:
            continue
    return {"scheme": None, "status_code": None, "final_url": None, "title": None}


def build_subdomain_report(
    hosts: set,
    session: requests.Session,
    crawl_host_info: dict = None,
    resolve_dns: bool = True,
    probe_live: bool = True,
    lookup_asn: bool = False,
    check_tls: bool = False,
    capture_headers: bool = False,
    check_cname: bool = False,
    max_workers: int = 20,
) -> list:
    """Resolve IPs (and optionally ASN/org, TLS metadata, HTTP headers, and
    dangling-CNAME risk) for every discovered host, concurrently. Merges in
    any info already collected from the crawl step (status code, page
    title) so we don't re-fetch pages we already have data for.

    Pressing Ctrl+C mid-run cancels any still-pending work and returns
    whatever has completed so far, rather than crashing."""
    crawl_host_info = crawl_host_info or {}
    report = []
    lock = Lock()

    def process(host: str):
        ips = resolve_ips(host) if resolve_dns else []
        entry = {
            "host": host,
            "ips": ips,
            "resolves": (bool(ips) if resolve_dns else None),
            "status_code": None,
            "final_url": None,
            "title": None,
            "source": [],
        }

        crawled = crawl_host_info.get(host)
        if crawled:
            entry["status_code"] = crawled.get("status_code")
            entry["title"] = crawled.get("title")
            entry["source"].append("crawl")

        should_probe = probe_live and (not resolve_dns or ips) and entry["status_code"] is None
        if should_probe:
            probed = probe_host(session, host, capture_headers=capture_headers)
            if probed["status_code"] is not None:
                entry["status_code"] = probed["status_code"]
                entry["final_url"] = probed["final_url"]
                entry["title"] = entry["title"] or probed["title"]
                entry["source"].append("probe")
                if capture_headers and probed.get("headers"):
                    entry["headers"] = probed["headers"]

        if check_tls:
            entry["tls"] = get_tls_info(host)

        if check_cname:
            entry["cname"] = check_dangling_cname(host)

        if not entry["source"]:
            entry["source"].append("passive")

        return entry

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process, h): h for h in sorted(hosts)}
        try:
            for fut in as_completed(futures):
                with lock:
                    report.append(fut.result())
        except KeyboardInterrupt:
            log.warning(
                "Stopped by user — cancelling remaining lookups, showing %d of %d results gathered so far.",
                len(report), len(futures),
            )
            pool.shutdown(wait=False, cancel_futures=True)

    report.sort(key=lambda r: r["host"])

    if lookup_asn and report:
        all_ips = sorted({ip for r in report for ip in r["ips"]})
        asn_map = lookup_asn_batch(all_ips)
        for r in report:
            orgs = {asn_map[ip]["org"] for ip in r["ips"] if ip in asn_map and asn_map[ip]["org"]}
            r["asn_org"] = sorted(orgs) if orgs else None

    return report
