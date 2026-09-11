# Contributing to ReconCave

Thanks for considering it. This is a small project; the bar for
contributing is low, but a few things keep it maintainable.

## Setup

```bash
git clone https://github.com/paula07x/reconcave.git
cd reconcave
pip install -e ".[dev]"
pytest
```

`[dev]` installs `pytest`, `pytest-cov`, and `ruff`. `[full]` (separately)
installs the optional enrichment libraries — see
[docs/installation.md](docs/installation.md) if you want those too while
developing.

## Before opening a PR

- **Add a test.** Every bug fix in this project's history has shipped
  with a regression test built from the real data that exposed the bug
  (see `tests/test_cli.py` for examples) — that pattern is the standard
  here, not an exception.
- **Run the full suite**: `pytest` (or `python -m unittest discover -s
  tests` if you don't have pytest installed). All tests offline — no
  network access required to run them; anything that touches the network
  should be mocked, the same way `test_recon.py` mocks `requests`.
- **`ruff check reconcave tests`** should pass clean.
- Keep the optional-dependency pattern (see
  [docs/architecture.md](docs/architecture.md#optional-dependency-pattern))
  for anything that needs a library outside the core `requirements` in
  `pyproject.toml`. A new feature should never hard-fail just because
  someone installed the core package without `[full]`.

## Where things go

See [docs/modules.md](docs/modules.md) for what each file is responsible
for. The short version: network-touching helpers go in `network.py`,
anything crawling-specific stays in `crawler.py`, passive-discovery and
per-host enrichment go in `recon.py`, and all user-facing surface (flags,
menu, output writing) lives in `cli.py`.

## Scope boundary — read this before adding a new discovery source

If you're adding a new way to discover hosts (a new passive data source,
a new crawl heuristic, anything), it **must** be run through
`split_by_scope()` in `cli.py` before those hosts reach
`build_subdomain_report()`. This isn't a style preference — merging an
unfiltered host list into the recon target set is exactly the bug class
documented in `CHANGELOG.md`, and it means the tool ends up scanning
third parties it has no authorization to test, purely because the target
site happens to link to them. See
[docs/architecture.md](docs/architecture.md#scope-boundary) for the full
explanation.

## What this project won't add

In line with [SECURITY.md](SECURITY.md): PRs that turn ReconCave from a
passive/authorized-recon tool into an active exploitation tool (port
scanners bundled in by default, vulnerability exploitation, credential
brute-forcing, anything that actively attacks rather than passively
observes) are out of scope for this project, regardless of how useful
they might be. If in doubt, open an issue to discuss before writing the
code.

## Commit / PR style

No strict convention enforced, but a PR that does one thing, with a
description of *why* (not just *what*), reviews much faster than a
sprawling one. If your change fixes a bug found via real-world usage,
say so and include the data that exposed it if you can share it — that's
directly how most of this project's test suite came to exist.
