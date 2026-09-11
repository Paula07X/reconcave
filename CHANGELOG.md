# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — first named release as ReconCave

Project renamed twice during development before settling here (first
`Subterra`, then briefly `XyRecon`) due to naming conflicts discovered at
each step — see the naming rationale in `README.md` if curious.

### Added
- `--verbose`/`-v` and `--quiet`/`-q` flags for logging level control.
- `--log-file PATH` — writes a full-detail log to a file independently of
  console verbosity, so `--quiet --log-file scan.log` gives a clean
  terminal while still keeping a complete record.
- Config file support: `~/.reconcave/config.json` (or `--config PATH`) sets
  default flag values for every run, which any flag you actually type
  still overrides for that run. `--no-config` skips it entirely.

### Fixed
- **Banner rendering (`????` on Windows).** An earlier banner used Unicode
  fullwidth characters to make the app name render bigger. This broke on
  Windows consoles running a legacy codepage that doesn't cover that
  Unicode block — every letter showed as `?`. Replaced with plain-ASCII
  letter-spacing (`R E C O N C A V E`), which exists in every codepage
  there is and can't have this failure mode.
- Leftover copyright holder name in `LICENSE` from the project's original
  name, missed by the automated rename since it only covered `.py`/
  `.toml`/`.md`/`.yml` files.

### Changed
- Banner and interactive menu re-centered against actual detected
  terminal width instead of a fixed assumption.

## [0.3.0] — scope-boundary fixes

Both bugs in this release were found via a real scan against a live
target submitted during testing, not by inspection — both are now locked
in with regression tests built from that scenario (`tests/test_cli.py`).

### Fixed
- **Out-of-scope hosts scanned as if in-scope.** The crawler correctly
  never *followed* outbound links to third parties (e.g. a homepage's
  link to its own social media accounts), but those links were still
  being merged into the recon target list — meaning unrelated external
  domains got DNS-resolved, TLS-checked, and HTTP-probed purely because
  the target site linked to them. Introduced `split_by_scope()` to
  separate "found while crawling" from "in-scope for recon."
- **Real subdomains wrongly excluded.** The first fix above over-corrected:
  it used `--include-subdomains` (a crawl-recursion setting) to decide
  scope, which wrongly excluded a genuine subdomain of the target as
  "external" whenever that flag wasn't passed. Scope is now decided
  purely by registrable-domain comparison, fully decoupled from the
  crawl-recursion flag.

## [0.2.0] — feature expansion

### Added
- TLS certificate metadata for live HTTPS hosts (`--tls`)
- HTTP response header capture during probing (`--headers`)
- Dangling-CNAME / subdomain-takeover detection (`--cname-check`)
- Email security posture: SPF/DMARC/MX (`--email`)
- Interactive menu with named scan presets (Fast/Deep/Related-domains-only/
  Email/Website-info/Everything/Custom), replacing a bare `input()` loop
- In-menu `help` (full flag reference without leaving the menu)
- Ctrl+C now stops an in-progress scan gracefully (partial results kept)
  instead of crashing or hanging
- Reports never overwrite each other — automatic `_1`, `_2`, ... suffixing
- Reports always save to a `results/` folder next to the tool, regardless
  of the working directory the tool was launched from
- `--filter` for substring-filtering discovered hosts

### Fixed
- HTML report output hardened: a rendering failure now produces a
  readable fallback error page instead of a silently blank file, and a
  zero-result scan now logs a clear warning explaining why before
  writing an empty-looking report.
- `cli.py` (and `__main__.py`) made self-healing against "attempted
  relative import with no known parent package" — the error you get when
  an IDE runs the file as a bare script instead of as part of the
  package. Both now detect that case and patch their own imports.

## [0.1.0] — initial version

Single-file scraper, extended into a same-domain crawler with
concurrency, robots.txt handling, and retry/backoff — then extended again
into a full recon tool: passive subdomain discovery via crt.sh, DNS
resolution, wildcard-DNS detection, live HTTP probing, optional ASN/org
lookup, JSON/CSV/TXT/HTML output, and scan-over-scan diffing.

### Fixed
- crt.sh's `name_value` field occasionally contains email addresses mixed
  in with real hostnames (e.g. `admin@example.com`), found via a real
  scan during testing. Added `is_valid_hostname()` filtering, with a
  regression test built from the exact bad entries that exposed it.
