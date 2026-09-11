# Architecture

## Pipeline overview

A single scan (`run_once()` in `cli.py`) moves through these stages in
order. Every stage is optional (skippable via flags) except the first
two lines of bookkeeping:

```
target URL/domain
      |
      v
+-------------------+   same-domain, depth-limited,     +--------------+
|  Crawler.crawl()   |-->  concurrent page fetching ---->| crawl_urls   |
+-------------------+   (crawler.py)                     | + host_info  |
      |                                                  +------+-------+
      |                                                         |
      v                                                         v
+------------------------+                        +---------------------------+
| discover_subdomains_    |  crt.sh certificate    |    split_by_scope()       |
| crtsh() (recon.py)      |  transparency lookup   |    (cli.py)               |
+------------+------------+                        +-------------+-------------+
             |                                                    |
             +--------------------------+-------------------------+
                                         v
                            discovered_hosts (in-scope only --
                            see "Scope boundary" below)
                                         |
                                         v
                          +--------------------------------+
                          |  build_subdomain_report()       |  DNS resolve, live
                          |  (recon.py)                     |  HTTP probe, optional
                          |                                  |  TLS / headers / ASN
                          +---------------+------------------+  / CNAME check
                                          |
                                          v
                               +---------------------+
                               |  compute_diff()      |  vs. last saved scan
                               |  (diff.py)            |  of this target
                               +----------+------------+
                                          |
                                          v
                             result dict -> save_results()
                             (json / csv / txt / html)
```

## Scope boundary

This is the single most important design decision in the codebase, and
it exists because of a real bug found during testing (documented in
[CHANGELOG.md](../CHANGELOG.md)): a crawled page can freely link to
completely unrelated third parties (a "follow us on Twitter" link), and
without a deliberate boundary, those links would get merged into the
recon target list and end up DNS-resolved, TLS-checked, and HTTP-probed —
meaning the tool would silently scan companies you have no relationship
to, just because the target site links to them.

`split_by_scope()` in `cli.py` draws that boundary using **registrable
domain** comparison (`blog.example.com` and `example.com` share a
registrable domain; an unrelated third-party domain does not), and this
is deliberately **independent** of the `--include-subdomains` flag. That flag controls a
completely different question — whether the crawler *recurses into* a
subdomain's own pages — and an earlier version of this code conflated the
two, which caused a second real bug (a genuine subdomain got wrongly
excluded as "external" whenever `--include-subdomains` wasn't passed).

If you're extending this codebase: any new source of discovered hosts
(a new passive data source, a new crawl strategy) must go through
`split_by_scope()` before reaching `build_subdomain_report()`. Never
merge a raw crawled URL's netloc directly into the recon target set.

## Optional-dependency pattern

`network.py`, `utils.py`, and `cli.py` follow one consistent pattern for
every optional enrichment library (`dnspython`, `tldextract`, `pyfiglet`,
`colorama`): a top-level `try: import X; _HAS_X = True` /
`except ImportError: _HAS_X = False`, and every function that needs it
checks the flag and returns a `{"available": False}`-shaped stub (or a
graceful fallback behavior) rather than raising. No code path should ever
hard-crash because an optional package isn't installed — see any of
`dns_records()`, `get_cname()`, `email_security_info()`, or
`registrable_domain()` in `network.py`/`utils.py` for the pattern to copy.

## Concurrency and interruption

`Crawler.crawl()` and `build_subdomain_report()` both use
`concurrent.futures.ThreadPoolExecutor` and both wrap their main loop in
a `try/except KeyboardInterrupt` that calls `pool.shutdown(wait=False,
cancel_futures=True)` and returns whatever partial results had already
completed, rather than raising. This is what makes Ctrl+C "just work" from
either the flag-driven CLI or the interactive menu. A Ctrl+C during one of
the single, short, non-threaded network calls (the crt.sh lookup, the
wildcard-DNS probe, the ASN batch call) is not specially handled — those
calls are quick enough that mid-call cancellation wasn't worth the added
complexity, and `run_once()`'s outer `try/except KeyboardInterrupt`
catches it there instead, aborting that run cleanly without saving a
partial file.

## Module responsibilities

See [modules.md](modules.md) for a file-by-file breakdown.
