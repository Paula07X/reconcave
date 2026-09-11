# Security Policy

## Scope of this policy

This document covers security issues **in ReconCave's own code** — bugs
that could make the tool itself unsafe to run (e.g. a vulnerability that
lets a malicious target server compromise the machine running ReconCave,
or a flaw that causes ReconCave to scan hosts outside the intended
target's scope).

This document does **not** cover vulnerabilities you discover *using*
ReconCave against a third-party target. That's between you and whoever
owns that target, through their own disclosure process.

## Responsible use

ReconCave performs reconnaissance: passive subdomain discovery,
DNS resolution, and live HTTP/TLS probing. It does not exploit, attack,
or attempt unauthorized access to anything. Even so, running it against a
domain you don't own or don't have explicit authorization to assess may
violate that target's terms of service or the law in your jurisdiction.
**Only scan domains you own or are authorized to test.** This applies
regardless of how harmless a given flag or scan mode seems.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No — please upgrade before reporting |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.
Instead:

1. Open a private security advisory via GitHub's "Report a vulnerability"
   feature on this repository, or email the maintainer directly (see
   `pyproject.toml` for the current contact).
2. Include what you found, how to reproduce it, and — if you have one —
   what you think the impact is.
3. You should get an acknowledgment within a few days. This is a small,
   community-maintained project, not a company with an SLA — please be
   patient, and feel free to follow up if you haven't heard back.

## What counts as a security issue here

Some concrete examples specific to this codebase:

- A bug that causes `split_by_scope()` (see `docs/architecture.md`) to
  misclassify an out-of-scope host as in-scope, so ReconCave ends up
  DNS-resolving, TLS-checking, or HTTP-probing a host it shouldn't. (This
  has happened before during development — see `CHANGELOG.md` — and is
  taken seriously precisely because of that history.)
- Anything that would let a malicious page served by a scanned target
  execute code on the machine running ReconCave (e.g. via the HTML
  parsing, the report rendering, or the crt.sh response handling).
- Credential or secret leakage (there shouldn't be any secrets in this
  tool at all, which is itself worth flagging if you find one).

Bug reports about missing features, false positives in the
subdomain-takeover check, or general reliability issues are welcome too —
just as regular GitHub issues, not security reports.
