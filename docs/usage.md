# Usage

ReconCave has two interfaces to the exact same code — pick whichever fits
the moment. Neither is the "real" one; both call the identical functions.

## Flag-driven (scriptable)

This is the interface to use in scripts, CI, or anywhere you want
predictable, pipeable output.

```bash
reconcave example.com                          # crawl + full recon, JSON output
reconcave example.com --no-crawl               # pure subdomain/IP recon, fast
reconcave example.com --format html            # local, offline HTML report
reconcave example.com --asn --tls --cname-check --dns-records --email
reconcave example.com --filter staging         # only hosts containing "staging"
reconcave example.com --include-subdomains --depth 3
```

Run `reconcave --help` for the full flag reference at any time.

### Common flags

| Flag | What it does |
|---|---|
| `--depth N` | Max crawl depth (default 2) |
| `--no-crawl` | Skip crawling entirely |
| `--no-recon` | Skip passive subdomain discovery (crt.sh) |
| `--no-probe` | Skip live HTTP probing of discovered hosts |
| `--no-resolve` | Skip DNS resolution entirely (hostnames only, fastest) |
| `--include-subdomains` | Let the crawler *recurse into* discovered subdomains, not just the base host |
| `--asn` | Attribute IPs to their hosting org (third-party API call) |
| `--tls` | Fetch TLS certificate metadata for live HTTPS hosts |
| `--headers` | Capture selected HTTP response headers during probing |
| `--cname-check` | Flag dangling CNAMEs (possible subdomain takeover) — needs `dnspython` |
| `--email` | SPF/DMARC/MX check for the domain — needs `dnspython` |
| `--dns-records` | NS/MX/TXT records for the apex domain — needs `dnspython` |
| `--filter TEXT` | Only include hosts containing this substring |
| `--format {json,csv,txt,html}` | Output format (default `json`) |
| `--output PATH` | Custom output path/filename base |
| `--no-diff` | Skip comparison against the previous saved scan |
| `--no-color` | Disable colored output |
| `-v`, `--verbose` | DEBUG-level logging |
| `-q`, `--quiet` | Warnings/errors only on console |
| `--log-file PATH` | Also write full-detail logs to a file, independent of console verbosity |
| `--config PATH` | Load default flag values from a JSON config file |
| `--no-config` | Ignore any config file, even if present |

### Config file

Any repeated combination of flags can be saved as defaults instead of
retyped every time. Create `~/.reconcave/config.json` (or point
`--config` at any path):

```json
{
  "depth": 3,
  "format": "html",
  "asn": true,
  "tls": true
}
```

Keys match long-flag names with dashes turned into underscores
(`--dns-records` → `"dns_records"`). Any flag you actually type on the
command line still overrides the config file for that one run — the
config file only sets the baseline. Unrecognized keys are ignored with a
warning rather than causing an error, so a typo in the config file never
blocks a scan.

**Important distinction:** `--include-subdomains` controls whether the
crawler *follows links into* a subdomain's pages. It does **not** control
whether a discovered subdomain gets reported — any host that's registrably
part of the target domain (e.g. `blog.example.com` under `example.com`)
is always reported, resolved, and probed, whether or not you crawled into
it. See [architecture.md](architecture.md#scope-boundary) for why this
distinction matters — it was a real bug earlier in this project's history
(see [CHANGELOG.md](../CHANGELOG.md)).

## Interactive menu

Run with no arguments:

```bash
reconcave
```

You'll see a banner and a menu with named scan types:

1. **Fast search** — quick pass, shallow crawl, no extras
2. **Deep search** — thorough infra recon: ASN, DNS, TLS, takeover check
3. **Related domains only** — passive subdomains + IPs, no crawling/probing
4. **Email info** — SPF/DMARC/MX for the domain
5. **Website info** — just this site: homepage, TLS, headers
6. **Everything** — full crawl + recon + all enrichments
7. **Custom** — enter your own flags (type `help` here to see them all)
8. **Help** — full flag reference, without leaving the menu
9. **Exit**

Every option prompts for your target and preferred output format
(JSON or HTML) before running. **Ctrl+C stops the current scan at any
time** and returns you to the menu instead of leaving it stuck.

## Entry points

Three ways to launch ReconCave, all running the identical code:

```bash
reconcave example.com              # after `pip install -e .` — the intended way
python -m reconcave example.com    # no install needed, run from the project root
python reconcave/cli.py example.com  # direct script execution (see note below)
```

The third form exists specifically because some IDEs (Visual Studio's
"Open Folder" mode is the one that prompted this) run whichever `.py` file
is active as a bare script, not as part of a package. `cli.py` detects
that case and patches its own imports so it still works either way — see
[modules.md](modules.md#clipy) for how.

## Output

Reports are always written to a `results/` folder next to the installed
tool — not wherever your terminal's current directory happens to be —
unless you pass `--output` with an explicit path. Re-running against the
same target never overwrites a previous report:
`example.com.json`, `example.com_1.json`, `example.com_2.json`, and so on.

Every scan is also compared against your last scan of the same target
(state saved under `~/.reconcave/state/`), so `diff.new` in the JSON
output tells you what's changed since last time. Disable with `--no-diff`.
