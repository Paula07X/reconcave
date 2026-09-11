# Installation

## Requirements

- Python 3.9 or newer
- No system-level dependencies — everything installable is pure Python

## Basic install

```bash
git clone https://github.com/paula07x/reconcave.git
cd reconcave
pip install -e .
```

This installs the core tool: crawler, passive subdomain discovery (crt.sh),
DNS resolution, live HTTP probing, and the JSON/CSV/TXT/HTML report writers.
No optional dependencies are required for any of that.

## Full install (recommended)

```bash
pip install -e ".[full]"
```

This adds:

| Package | Unlocks |
|---|---|
| `dnspython` | NS/MX/TXT lookups, dangling-CNAME/takeover detection, SPF/DMARC email checks |
| `tldextract` | Accurate registrable-domain splitting (public suffix list) for unusual TLDs like `.co.uk` |
| `pyfiglet` | Large ASCII-art banner in the interactive menu |
| `colorama` | Colored terminal output on legacy Windows consoles (`cmd.exe`) |

Every one of these degrades gracefully if missing — the relevant flag
(`--dns-records`, `--cname-check`, `--email`, etc.) just returns an
"unavailable" note instead of failing the whole scan. There's no wrong way
to install this; `[full]` just means fewer "not available" notes.

## Verifying the install

```bash
reconcave --version
```

If that command isn't found after `pip install -e .`, your Python
Scripts/bin directory likely isn't on `PATH`. Two ways around that without
touching `PATH`:

```bash
python -m reconcave --version
```

or, from inside the project folder:

```bash
python reconcave/cli.py --version
```

All three run the identical code — see
[the note on entry points in usage.md](usage.md#entry-points) for when
you'd use which.

## Development install

```bash
pip install -e ".[dev]"
pytest
```

`[dev]` adds `pytest`, `pytest-cov`, and `ruff` — everything the test suite
and CI need. See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full
workflow.
