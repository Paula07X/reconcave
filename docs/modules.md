# Module reference

One-paragraph summary of every file in `reconcave/`, in rough pipeline
order. See [architecture.md](architecture.md) for how they connect.

## `utils.py`

URL/hostname/domain helpers with no network calls: `normalize_url()`
(strips fragments, trailing slashes), `is_valid_hostname()` (rejects
email addresses and other junk that crt.sh's data sometimes contains —
see the `TestCrtshDiscovery` regression test in `test_recon.py` for the
exact real-world case this catches), `registrable_domain()` (reduces
`a.b.example.co.uk` to `example.co.uk`, using `tldextract` if installed
or a small hardcoded TLD list otherwise), and `same_domain()` (used by
the crawler to decide what to recurse into — see the "Scope boundary"
note in architecture.md for why this is *not* the same thing as scope
classification).

## `network.py`

Everything that touches the network except crawling and crt.sh:
`build_session()` (requests session with retry/backoff), `RobotsCache`
(fetches and caches `robots.txt` per host), `RateLimiter` (per-host
delay), `resolve_ips()` (plain DNS), `detect_wildcard_dns()` (probes a
random nonexistent subdomain to catch wildcard DNS zones before they
produce false positives), `get_tls_info()` / `get_cname()` /
`check_dangling_cname()` / `email_security_info()` /
`lookup_asn_batch()` — the optional enrichment functions, each following
the optional-dependency pattern described in architecture.md.

## `crawler.py`

`Crawler`: a same-domain, depth-limited, concurrent page crawler. Follows
links up to `--depth`, respects `robots.txt` and a per-host delay,
extracts every `<a href>` on every page into `all_urls` — **including
outbound links to other domains**, which it does not follow further but
does still report. (This is *why* `split_by_scope()` exists in `cli.py` —
the crawler's job is just to find links, not to judge whether they're
in-scope.)

## `recon.py`

`discover_subdomains_crtsh()`: passive subdomain discovery via certificate
transparency logs, with `is_valid_hostname()` filtering applied.
`probe_host()`: tries HTTPS then HTTP, extracts a cheap `<title>` and
optionally response headers. `build_subdomain_report()`: the fan-out step
that resolves IPs and optionally probes/TLS-checks/CNAME-checks every
in-scope host concurrently, merging in anything the crawler already
learned about a host so it isn't re-fetched.

## `diff.py`

Saves the current scan's host set to `~/.reconcave/state/<target>.json`
and compares against whatever was saved there last time. Pure local file
I/O, no network calls.

## `report_html.py`

Renders the self-contained, offline HTML report — a single `.format()`
call against a template string, with sortable columns and a client-side
filter box (vanilla JS, no CDN dependency, so it works with no internet
connection when opened).

## `cli.py`

Everything user-facing: argument parsing (`parse_args()` /
`_build_parser()`), the banner (`print_banner()`), the interactive menu
(`interactive_menu()`, `_PRESETS`), `split_by_scope()` (see architecture.md),
`run_once()` (orchestrates the whole pipeline for one scan), and
`save_results()` / `make_unique_path()` (output writing, never overwrites
a previous report).

This file has a self-healing import block at the top: it tries a normal
relative import (`from . import __version__`), and falls back to
patching `sys.path` and re-importing absolutely (`from reconcave import
__version__`) if that fails. The fallback exists specifically because
some IDEs (Visual Studio's "Open Folder" mode, in particular) run
whichever `.py` file is active as a bare script rather than as part of a
package, which breaks relative imports. `__main__.py` has the identical
fallback for the same reason, since `python -m reconcave` and directly
running `__main__.py` are both plausible IDE behaviors.

## `__main__.py`

A two-line shim so `python -m reconcave ...` works: imports and calls
`cli.main()`. Has the same self-healing import fallback as `cli.py`.

## `__init__.py`

Just `__version__`.
