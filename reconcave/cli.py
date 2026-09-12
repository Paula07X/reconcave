"""Command-line interface for ReconCave."""

import argparse
import csv
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    # Normal case: reconcave is being imported/run as a package
    # (`pip install -e .` + `reconcave ...`, or `python -m reconcave ...`).
    from . import __version__
    from .crawler import Crawler
    from .diff import DEFAULT_STATE_DIR, compute_diff, load_previous_hosts, save_current_hosts
    from .network import (
        DEFAULT_USER_AGENT,
        build_session,
        detect_wildcard_dns,
        dns_records,
        email_security_info,
    )
    from .recon import build_subdomain_report, discover_subdomains_crtsh
    from .report_html import render_html_report
    from .utils import registrable_domain
except ImportError:
    # Fallback: this file was launched directly as a bare script (e.g. an
    # IDE's "Run" button, which is exactly what Visual Studio's Open Folder
    # mode does), so Python has no idea `reconcave` is a package and the
    # relative imports above fail. Patch sys.path with the project root
    # (the parent of this file's directory) and retry as absolute imports.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from reconcave import __version__
    from reconcave.crawler import Crawler
    from reconcave.diff import DEFAULT_STATE_DIR, compute_diff, load_previous_hosts, save_current_hosts
    from reconcave.network import (
        DEFAULT_USER_AGENT,
        build_session,
        detect_wildcard_dns,
        dns_records,
        email_security_info,
    )
    from reconcave.recon import build_subdomain_report, discover_subdomains_crtsh
    from reconcave.report_html import render_html_report
    from reconcave.utils import registrable_domain

log = logging.getLogger("reconcave")


def _configure_logging(verbose: bool = False, quiet: bool = False, log_file: str = None):
    """Sets up the "reconcave" logger's level and handlers. Called once,
    early in main() — every module shares this same logger name (see
    crawler.py, network.py, recon.py, diff.py), so configuring it here
    once covers the whole process, including every scan the interactive
    menu goes on to run.

    verbose wins if both --verbose and --quiet are passed (more
    information is the safer default when the two conflict).

    The console and the log file are filtered independently: --quiet only
    quiets the console. The file (if given) always captures full detail
    regardless of --quiet, since the common reason to combine "quiet
    console" with "--log-file" is wanting a clean terminal *and* a
    complete record to check later — not losing detail in both places."""
    console_level = logging.DEBUG if verbose else (logging.WARNING if quiet else logging.INFO)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    logger = logging.getLogger("reconcave")
    logger.setLevel(logging.DEBUG)  # let everything through to handlers; each handler filters itself
    logger.handlers.clear()
    logger.propagate = False

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(console_level)
    logger.addHandler(console)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(fmt)
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.error("Could not open log file %s (%s); logging to console only.", log_file, e)

# Single source of truth for the tool's display name. If you rename the
# project again, this is the one line in cli.py that needs to change for
# the banner/menu — the package name, entry point, User-Agent, and state
# dir live in pyproject.toml, network.py, and diff.py respectively.
APP_NAME = "ReconCave"

try:
    import colorama
    colorama.init(autoreset=True)
except ImportError:
    pass


# --------------------------------------------------------------------------
# Color handling — plain ANSI codes, no hard dependency. `colorama` (above)
# is optional and only needed to make ANSI work on legacy Windows cmd.exe;
# modern Windows Terminal / VS Code / most IDE terminals support ANSI
# natively. Respects --no-color and the NO_COLOR env var convention.
# --------------------------------------------------------------------------

_CODES = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "cyan": "\033[36m", "green": "\033[32m", "yellow": "\033[33m",
    "red": "\033[31m", "magenta": "\033[35m", "blue": "\033[34m",
}
_color_enabled = True


def set_color_enabled(enabled: bool):
    global _color_enabled
    _color_enabled = enabled


def c(text, *styles):
    if not _color_enabled:
        return text
    prefix = "".join(_CODES.get(s, "") for s in styles)
    return f"{prefix}{text}{_CODES['reset']}"


def _letter_spaced(text: str) -> str:
    """Renders text with a space between every letter (e.g. 'ReconCave' ->
    'R E C O N C A V E'), which reads visibly larger/bolder in a terminal.
    Deliberately plain ASCII only — an earlier version of this banner used
    Unicode fullwidth characters (e.g. 'Ｒ') for a similar effect, which
    rendered as '????' on a Windows console running a legacy codepage that
    doesn't cover that Unicode block. Plain ASCII letters and spaces exist
    in every codepage there is, so this can't have the same failure mode."""
    return " ".join(text.upper())


def print_banner():
    """Big, colorful, centered banner. Uses pyfiglet for true large ASCII
    art if installed (pure ASCII output — codepage-safe); otherwise falls
    back to a bold, colored box with letter-spaced text for a bigger look,
    with zero extra dependencies and zero exotic-Unicode risk."""
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns

    def centered(line):
        return line.center(term_width)

    def left_margin(content_width):
        return " " * max((term_width - content_width) // 2, 0)

    try:
        import pyfiglet
    except ImportError:
        pyfiglet = None

    art_lines = None
    if pyfiglet is not None:
        try:
            art_lines = pyfiglet.figlet_format(APP_NAME, font="big").rstrip("\n").split("\n")
        except Exception as e:
            # pyfiglet is a third-party dependency whose exact font
            # behavior isn't something this project controls or has
            # exhaustively verified across every install — if anything
            # about it goes wrong (missing font data, internal error,
            # whatever), fall back to the plain box banner below rather
            # than letting a banner-rendering problem take down the
            # whole menu. Only visible with --verbose.
            log.debug("pyfiglet banner failed (%s); using fallback banner.", e)
            art_lines = None

    if art_lines:
        # figlet lines share a common width; pad every line with the same
        # left margin rather than centering each independently, which
        # would stagger the letters instead of keeping the block aligned.
        art_width = max(len(line) for line in art_lines)
        pad = left_margin(art_width)
        for line in art_lines:
            print(c(pad + line, "cyan", "bold"))
    else:
        title = f"  {_letter_spaced(APP_NAME)}  "
        box_width = max(len(title), 44)
        border = "=" * box_width
        pad = left_margin(box_width)
        print(c(pad + border, "cyan"))
        print(c(pad + title.center(box_width), "cyan", "bold"))
        print(c(pad + border, "cyan"))

    print()
    print(c(centered(f"v{__version__} — Subdomain, IP, DNS & asset recon"), "yellow"))
    print(c(centered("Only scan domains you own or are authorized to assess."), "red", "bold"))
    print()


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Builds the argparse parser without parsing anything — shared by
    parse_args() (which parses real argv) and _print_full_help() (which
    just wants the help text, without argparse's --help calling
    sys.exit() on us mid-menu)."""
    p = argparse.ArgumentParser(
        prog="reconcave",
        description=(
            "ReconCave — subdomain, IP, DNS, TLS and asset recon for a domain. "
            "Combines a same-domain crawler with passive subdomain discovery "
            "(certificate transparency logs), DNS resolution, live HTTP "
            "probing, and optional ASN/TLS/email/takeover checks. "
            "Only run this against domains you own or are authorized to assess."
        ),
    )
    p.add_argument("target", nargs="?", help="Target URL or bare domain, e.g. example.com")
    p.add_argument("--depth", type=int, default=2, help="Max crawl depth (default: 2)")
    p.add_argument("--workers", type=int, default=8, help="Concurrent crawl workers (default: 8)")
    p.add_argument("--delay", type=float, default=0.2, help="Per-host crawl delay in seconds (default: 0.2)")
    p.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds (default: 10)")
    p.add_argument("--include-subdomains", action="store_true",
                    help="Also crawl discovered subdomains, not just the base host")
    p.add_argument("--no-robots", action="store_true", help="Ignore robots.txt (not recommended)")
    p.add_argument("--no-crawl", action="store_true", help="Skip crawling")
    p.add_argument("--no-recon", action="store_true", help="Skip passive subdomain discovery")
    p.add_argument("--no-probe", action="store_true", help="Skip live HTTP probing of discovered hosts")
    p.add_argument("--no-resolve", action="store_true", help="Skip DNS resolution entirely (hostnames only)")
    p.add_argument("--no-diff", action="store_true", help="Skip comparison against the previous saved scan")
    p.add_argument("--asn", action="store_true", help="Look up ASN/organization per IP (third-party API call)")
    p.add_argument("--dns-records", action="store_true", help="Fetch NS/MX/TXT records for the apex domain")
    p.add_argument("--tls", action="store_true", help="Fetch TLS certificate metadata for live HTTPS hosts")
    p.add_argument("--headers", action="store_true", help="Capture selected HTTP response headers during probing")
    p.add_argument("--cname-check", action="store_true",
                    help="Check for dangling CNAMEs (possible subdomain takeover) — requires dnspython")
    p.add_argument("--email", action="store_true",
                    help="Check SPF/DMARC/MX email security posture for the domain — requires dnspython")
    p.add_argument("--max-pages", type=int, default=None, help="Stop crawl after this many pages")
    p.add_argument("--format", choices=["json", "csv", "txt", "html"], default="json",
                    help="Output format (default: json)")
    p.add_argument("--output", default=None, help="Output filename base (without extension)")
    p.add_argument("--filter", default=None,
                    help="Only include discovered hosts containing this substring (case-insensitive). "
                         "Does not affect scan-history diffing, which always tracks the full result.")
    p.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR),
                    help=f"Where scan history is stored for diffing (default: {DEFAULT_STATE_DIR})")
    p.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Custom User-Agent string")
    p.add_argument("--no-color", action="store_true", help="Disable colored output")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose output (DEBUG-level logging)")
    p.add_argument("-q", "--quiet", action="store_true", help="Quiet output (warnings/errors only)")
    p.add_argument("--log-file", default=None, help="Also write logs to this file, in addition to the console")
    p.add_argument("--config", default=None,
                    help=f"Path to a JSON config file (default: {DEFAULT_CONFIG_PATH} if it exists)")
    p.add_argument("--no-config", action="store_true", help="Ignore any config file, even if present")
    p.add_argument("--version", action="version", version=f"reconcave {__version__}")
    return p


DEFAULT_CONFIG_PATH = DEFAULT_STATE_DIR.parent / "config.json"


def _load_config(explicit_path) -> dict:
    """Loads a JSON config file, e.g.:

        {"depth": 3, "workers": 10, "format": "html", "asn": true}

    Keys match long-flag names with dashes turned into underscores
    (--dns-records -> "dns_records"). Returns {} on any problem (missing
    file, bad JSON, wrong shape) rather than failing the run — a broken
    config file should never be the reason a scan doesn't start."""
    path = Path(explicit_path) if explicit_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        if explicit_path:
            log.warning("Config file not found: %s", path)
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Could not read config file %s (%s); ignoring.", path, e)
        return {}
    if not isinstance(data, dict):
        log.warning("Config file %s must contain a JSON object; ignoring.", path)
        return {}
    return data


def parse_args(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    # Lightweight pre-scan just for --config/--no-config, so a config file
    # can be loaded and applied as parser *defaults* before the real
    # parse — that way the config file sets your baseline, and any flag
    # you actually typed for this run still overrides it, exactly like a
    # normal default would.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    pre.add_argument("--no-config", action="store_true")
    known, _ = pre.parse_known_args(argv)

    p = _build_parser()

    if not known.no_config:
        config = _load_config(known.config)
        if config:
            valid_dests = {a.dest for a in p._actions}
            unknown_keys = set(config) - valid_dests
            if unknown_keys:
                log.warning("Ignoring unrecognized config key(s): %s", ", ".join(sorted(unknown_keys)))
            clean_config = {k: v for k, v in config.items() if k in valid_dests}
            if clean_config:
                p.set_defaults(**clean_config)

    return p.parse_args(argv)


def _print_full_help():
    """Prints the same help text as `reconcave --help`, but without
    triggering argparse's sys.exit() — safe to call from inside the
    interactive menu."""
    print(_build_parser().format_help())
    print(c("Example custom flags:", "bold"))
    print("  --depth 3 --asn --format html")
    print("  --no-crawl --no-probe --tls --cname-check")
    print("  --filter staging --format csv")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def save_results(result: dict, filename_base: str, fmt: str) -> str:
    if not result.get("subdomains"):
        log.warning(
            "Zero hosts in this result — the report will look empty. This usually means "
            "--no-crawl and --no-recon were both set (nothing left to discover), or "
            "--filter didn't match anything. Check the flags/preset used for this run."
        )

    if fmt == "json":
        path = make_unique_path(filename_base, "json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)

    elif fmt == "html":
        path = make_unique_path(filename_base, "html")
        try:
            content = render_html_report(result, version=__version__, app_name=APP_NAME)
        except Exception as e:
            # Never silently write a blank/broken file — if rendering
            # itself fails for any reason, write a page that says so
            # instead of leaving you staring at an empty tab wondering why.
            log.error("HTML rendering failed (%s); writing a fallback error page instead.", e)
            content = (
                f"<!DOCTYPE html><html><body style='font-family:sans-serif;padding:2rem'>"
                f"<h1>ReconCave report generation failed</h1>"
                f"<p>Rendering the HTML report raised an error: <code>{e}</code></p>"
                f"<p>The raw JSON result is still available if you re-run with --format json.</p>"
                f"</body></html>"
            )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    elif fmt == "csv":
        path = make_unique_path(filename_base, "csv")
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "host", "ips", "resolves", "status_code", "title",
                "asn_org", "tls_issuer", "tls_not_after", "cname_target",
                "possible_takeover", "source",
            ])
            for sub in result.get("subdomains", []):
                tls = sub.get("tls") or {}
                cname = sub.get("cname") or {}
                writer.writerow([
                    sub["host"],
                    ";".join(sub["ips"]),
                    sub["resolves"],
                    sub["status_code"],
                    sub["title"] or "",
                    ";".join(sub.get("asn_org") or []),
                    tls.get("issuer") or "",
                    tls.get("not_after") or "",
                    cname.get("cname_target") or "",
                    cname.get("possible_takeover") if cname.get("checked") else "",
                    ";".join(sub.get("source") or []),
                ])

    elif fmt == "txt":
        path = make_unique_path(filename_base, "txt")
        with open(path, "w") as f:
            f.write(f"# Target: {result.get('target')}\n")
            f.write(f"# Subdomains found: {result.get('subdomain_count')}\n\n")
            for sub in result.get("subdomains", []):
                ip_str = ", ".join(sub["ips"]) if sub["ips"] else "unresolved"
                status = sub.get("status_code")
                status_str = f" [{status}]" if status else ""
                f.write(f"{sub['host']}{status_str}  ->  {ip_str}\n")
            if result.get("email_security"):
                f.write("\n# Email security\n")
                f.write(json.dumps(result["email_security"], indent=2) + "\n")
    else:
        raise ValueError(f"Unknown format: {fmt}")

    log.info("Saved report to %s", path)
    return path


def safe_filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = parsed.netloc.replace(":", "_")
    return "reconcave_" + name[:100]


# Reports are always written next to the tool itself (a `results/` folder
# sibling to the `reconcave` package), regardless of the current working
# directory the tool happens to be launched from — this matters because
# an IDE's "Run" button, `python -m reconcave`, and a plain terminal `cd`
# can all leave you in a different CWD, and "where did my report go"
# is a bad first experience.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = _PROJECT_ROOT / "results"


def resolve_output_path(filename_base: str) -> str:
    """Turns a bare filename base into a full path inside RESULTS_DIR,
    unless the caller already supplied a path (via --output with a
    directory in it, or an absolute path) — in which case that's
    respected exactly as given."""
    if os.path.isabs(filename_base) or os.sep in filename_base or (os.altsep and os.altsep in filename_base):
        return filename_base
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        return str(RESULTS_DIR / filename_base)
    except OSError as e:
        log.warning(
            "Could not create results directory %s (%s); saving to the current directory instead.",
            RESULTS_DIR, e,
        )
        return filename_base


def make_unique_path(base: str, ext: str) -> str:
    """Never overwrites an existing report. If `{base}.{ext}` already
    exists (e.g. you scanned the same target twice), appends _1, _2, etc.
    until it finds a filename that doesn't exist yet, so every run's
    results are kept side by side rather than silently replacing the
    previous one."""
    candidate = f"{base}.{ext}"
    if not os.path.exists(candidate):
        return candidate
    i = 1
    while True:
        candidate = f"{base}_{i}.{ext}"
        if not os.path.exists(candidate):
            return candidate
        i += 1


# --------------------------------------------------------------------------
# Core run
# --------------------------------------------------------------------------

def split_by_scope(crawl_urls: set, target_domain: str) -> tuple:
    """Splits every URL found during crawling into (in-scope netlocs,
    external netlocs), based on registrable domain — NOT on
    --include-subdomains. Those are two different questions:

    - --include-subdomains controls whether the crawler *recurses into*
      a subdomain's pages while crawling (a performance/scope choice).
    - This function decides whether a *discovered* host belongs to the
      same organization as the target at all, for recon-reporting
      purposes — e.g. blog.example.com is registrably the same domain
      as example.com and should always be reported as in-scope, even if
      you never chose to crawl further into it. An outbound link to an
      unrelated third-party domain must never be merged into the recon
      target list — that would mean DNS-resolving, TLS-checking, and
      HTTP-probing a party you have no relationship to just because the
      target site links to it, which is a real scope violation, not a
      cosmetic one.

    Conflating these two (an earlier version of this function did) caused
    a real bug: a genuine subdomain of the target was wrongly excluded as
    "external" whenever --include-subdomains wasn't passed, even though
    it's obviously the same organization's infrastructure."""
    in_scope = set()
    external = set()
    for u in crawl_urls:
        netloc = urlparse(u).netloc.lower()
        if not netloc:
            continue
        if registrable_domain(netloc) == target_domain:
            in_scope.add(netloc)
        else:
            external.add(netloc)
    return in_scope, external


def run_once(args):
    """Runs one full scan according to `args`. Returns the saved file path,
    or None if the user interrupted the run (Ctrl+C) before it completed.

    Ctrl+C is handled gracefully at the two expensive, long-running phases
    (crawling many pages; resolving/probing many hosts) — those return
    whatever partial results they'd gathered instead of crashing. A Ctrl+C
    during one of the single short network calls (crt.sh lookup, wildcard
    probe, ASN batch, email check) aborts the whole run cleanly instead,
    since those are quick enough that mid-call cancellation isn't worth
    the added complexity."""
    raw = args.target
    url = raw if raw.startswith(("http://", "https://")) else "https://" + raw

    base_netloc = urlparse(url).netloc.lower()
    target_domain = registrable_domain(base_netloc)
    session = build_session(args.user_agent)

    print(c(f"Scanning {target_domain}... (press Ctrl+C at any time to stop)", "dim"))

    try:
        crawl_urls = set()
        host_info = {}
        errors = {}
        discovered_hosts = {base_netloc}
        external_links = set()

        if not args.no_crawl:
            crawler = Crawler(
                start_url=url,
                max_depth=args.depth,
                workers=args.workers,
                delay=args.delay,
                include_subdomains=args.include_subdomains,
                timeout=args.timeout,
                user_agent=args.user_agent,
                respect_robots=not args.no_robots,
                max_pages=args.max_pages,
                session=session,
            )
            crawl_urls = crawler.crawl()
            host_info = crawler.host_info
            errors = crawler.errors

            # See split_by_scope()'s docstring: crawl_urls includes every
            # link found on every page, including outbound links to
            # entirely unrelated third parties — only in-scope hosts get
            # merged into discovered_hosts, which drives DNS/TLS/probing.
            in_scope_hosts, external_links = split_by_scope(crawl_urls, target_domain)
            discovered_hosts |= in_scope_hosts

        if not args.no_recon:
            discovered_hosts |= discover_subdomains_crtsh(target_domain, session)

        wildcard = detect_wildcard_dns(target_domain) if not args.no_resolve else False
        if wildcard:
            log.warning(
                "%s appears to have wildcard DNS — any hostname under it may "
                "falsely appear to 'resolve'. Treat unexpected resolving hosts with suspicion.",
                target_domain,
            )

        subdomain_report = build_subdomain_report(
            discovered_hosts,
            session=session,
            crawl_host_info=host_info,
            resolve_dns=not args.no_resolve,
            probe_live=not args.no_probe,
            lookup_asn=args.asn,
            check_tls=args.tls,
            capture_headers=args.headers,
            check_cname=args.cname_check,
        )

        diff_info = {}
        if not args.no_diff:
            state_dir = Path(args.state_dir)
            current_hosts = {s["host"] for s in subdomain_report}
            previous_hosts = load_previous_hosts(target_domain, state_dir)
            diff_info = compute_diff(current_hosts, previous_hosts)
            save_current_hosts(target_domain, current_hosts, state_dir)
            if diff_info["new"] and not diff_info["is_first_scan"]:
                log.info("%d new subdomain(s) since last scan: %s",
                          len(diff_info["new"]), ", ".join(diff_info["new"][:10]))

        result = {
            "target": target_domain,
            "start_url": url,
            "wildcard_dns": wildcard,
            "crawl": {
                "pages_visited": len(crawl_urls),
                "urls": sorted(crawl_urls),
                "errors": errors,
                "external_links_found": sorted(external_links),
            },
            "subdomains": subdomain_report,
            "subdomain_count": len(subdomain_report),
            "diff": diff_info,
        }

        if args.dns_records:
            result["dns_records"] = dns_records(target_domain)

        if args.email:
            result["email_security"] = email_security_info(target_domain)

        if args.filter:
            needle = args.filter.lower()
            filtered = [s for s in result["subdomains"] if needle in s["host"].lower()]
            log.info("Filter '%s' matched %d of %d discovered hosts",
                      args.filter, len(filtered), len(result["subdomains"]))
            result["subdomains"] = filtered
            result["subdomain_count"] = len(filtered)
            result["filter_applied"] = args.filter

        filename_base = resolve_output_path(args.output or safe_filename_from_url(url))
        return save_results(result, filename_base, args.format)

    except KeyboardInterrupt:
        print()
        log.warning("Stopped by user. This run was not saved.")
        return None


# --------------------------------------------------------------------------
# Interactive menu
# --------------------------------------------------------------------------

_PRESETS = {
    "1": {  # Fast search
        "label": "Fast search",
        "flags": ["--depth", "1", "--no-diff"],
    },
    "2": {  # Deep search — thorough infra/subdomain recon
        "label": "Deep search",
        "flags": ["--no-crawl", "--asn", "--dns-records", "--tls", "--cname-check"],
    },
    "3": {  # Related domains only
        "label": "Related domains only",
        "flags": ["--no-crawl", "--no-probe"],
    },
    "4": {  # Email info
        "label": "Email info",
        "flags": ["--no-crawl", "--no-recon", "--no-probe", "--no-diff", "--email"],
    },
    "5": {  # Website info
        "label": "Website info (this host only)",
        "flags": ["--no-recon", "--depth", "0", "--tls", "--headers"],
    },
    "6": {  # Everything
        "label": "Everything",
        "flags": ["--asn", "--dns-records", "--tls", "--headers", "--cname-check", "--email"],
    },
}


def _print_menu():
    print(c("  Choose a scan type:", "bold"))
    print(f"  {c('1', 'green')}) {c('Fast search', 'bold')}             — quick pass, shallow crawl, no extras")
    print(f"  {c('2', 'green')}) {c('Deep search', 'bold')}             — thorough infra recon: ASN, DNS, TLS, takeover check")
    print(f"  {c('3', 'green')}) {c('Related domains only', 'bold')}    — passive subdomains + IPs, no crawling/probing")
    print(f"  {c('4', 'green')}) {c('Email info', 'bold')}              — SPF / DMARC / MX for the domain")
    print(f"  {c('5', 'green')}) {c('Website info', 'bold')}            — just this site: homepage, TLS, headers")
    print(f"  {c('6', 'green')}) {c('Everything', 'bold')}              — full crawl + recon + all enrichments")
    print(f"  {c('7', 'green')}) {c('Custom', 'bold')}                  — enter your own reconcave flags")
    print(f"  {c('8', 'green')}) {c('Help', 'bold')}                    — show all available flags and what they do")
    print(f"  {c('9', 'green')}) {c('Exit', 'bold')}")
    print()
    print(c("  Press Ctrl+C at any time to stop a running scan and return here.", "dim"))
    print()


def interactive_menu():
    """Runs when reconcave is launched with no arguments at all. This is a
    convenience layer for humans exploring the tool — every option here
    maps onto the exact same run_once()/parse_args() path as the
    flag-driven CLI, nothing here is a separate code path. Scripted or
    automated usage should always use flags directly; this menu is not,
    and should never become, a required step. `python -m reconcave <flags>`
    or the installed `reconcave <flags>` command both skip this entirely."""
    print_banner()
    _print_menu()

    while True:
        try:
            choice = input(c("Choose an option [1-9]: ", "cyan")).strip()
        except KeyboardInterrupt:
            print()
            log.info("Exiting.")
            return

        if choice == "9" or choice.lower() in ("e", "exit", "q", "quit"):
            log.info("Exiting.")
            return

        if choice == "8" or choice.lower() in ("help", "h", "?"):
            print()
            _print_full_help()
            print()
            _print_menu()
            continue

        if choice not in _PRESETS and choice != "7":
            print(c("Please enter a number from 1 to 9.", "red"))
            continue

        try:
            target = input("Target domain (e.g. example.com): ").strip()
        except KeyboardInterrupt:
            print()
            continue
        if not target:
            print(c("A target is required.", "red"))
            continue

        if choice == "7":
            while True:
                try:
                    raw_flags = input(
                        "Enter flags (or 'help' to see all options, e.g. --depth 3 --asn --format html): "
                    ).strip()
                except KeyboardInterrupt:
                    print()
                    raw_flags = None
                    break
                if raw_flags.lower() in ("help", "h", "?"):
                    print()
                    _print_full_help()
                    print()
                    continue
                break
            if raw_flags is None:
                continue
            argv = [target] + raw_flags.split()
            # allow choosing format even in custom mode if not already specified
            if "--format" not in argv:
                fmt = _ask_format()
                if fmt:
                    argv += ["--format", fmt]
        else:
            preset = _PRESETS[choice]
            print(c(f"  Selected: {preset['label']}", "yellow"))
            fmt = _ask_format()
            argv = [target, "--format", fmt] + preset["flags"]

        try:
            args = parse_args(argv)
            set_color_enabled(not args.no_color)
            path = run_once(args)
            if path:
                print(c(f"Done. Report saved to: {path}", "green", "bold"))
        except SystemExit:
            # argparse calls sys.exit() on bad custom flags — catch it so
            # a typo in "Custom" mode returns to the menu instead of
            # killing the whole interactive session.
            print(c("Could not parse those flags — check them and try again.", "red"))
        except Exception as e:
            log.error("Run failed: %s", e)

        print()
        _print_menu()


def _ask_format() -> str:
    try:
        fmt = input("Output format — json or html? [json]: ").strip().lower() or "json"
    except KeyboardInterrupt:
        print()
        return "json"
    if fmt not in ("json", "html"):
        print(f"Unrecognized format '{fmt}', defaulting to json.")
        fmt = "json"
    return fmt


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)
    _configure_logging(verbose=args.verbose, quiet=args.quiet, log_file=args.log_file)
    set_color_enabled(not args.no_color and not os.environ.get("NO_COLOR"))

    if args.target:
        run_once(args)
        return

    try:
        interactive_menu()
    except KeyboardInterrupt:
        print()
        log.info("Exiting.")


if __name__ == "__main__":
    main()
