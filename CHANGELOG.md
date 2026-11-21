# Changelog

## Unreleased

- Web UI polish: typewriter font and dark mode, editor status line and focus mode, Markdown import, publish progress with per-platform streaming, grouped platform checkboxes, datetime picker for scheduling, one primary color plus grays, 12-column grid, and a verified GitHub star count in the waitlist strip. UX checklist score 100/100.
- `outpour bootstrap` adds title front matter to existing drafts from the first heading or filename, without touching body text.
- Dry-run honesty: Dev.to tag sanitizing is shown as sent, pre-publish warnings are itemized, and malformed Nostr keys are caught before publish.
- Nostr publishing now reads relay OK replies and fails honestly when no relay acknowledges.
- Every user-facing command hint now reads `outpour`, not `crier`. The `crier` command still works.
- GitHub Actions workflows now use actions/checkout@v5 and actions/setup-python@v6, which run on Node 24 natively; the scheduled runs no longer carry the Node 20 deprecation warning.
- README guards: tests pin the intro sentence, the quick-start link target, and no em dash in the README.

## 0.2.1 - 2026-10-29

- Fixed the wheel build: the web UI static file was packaged twice, which broke every install from the 0.2.0 tag. Installs from this tag work.
- README rewritten as a landing page, with a hosted waitlist section (expected $19/month, founding-price lock).

## 0.2.0 - 2026-10-29

- Local web UI (optional `[ui]` extra): Articles, Editor, Schedule, and Platforms screens on 127.0.0.1 only, reusing the CLI publishing, scheduler, and ledger code. Publish now and schedule for later from the browser; per-platform results and errors shown honestly.
- UI tests: 11 endpoint tests with mocked platforms.

Validation: 1,518 tests passed.

## 0.1.0 - 2026-10-29

- First Outpour release, forked from Crier 2.1.1 and rebranded (package and CLI are `outpour`; upstream attribution and MIT license kept).
- Nostr long-form publishing (NIP-23, kind 30023) with d-tag derived from the article slug, so re-publishing updates instead of duplicating.
- Idempotent re-publishing: re-running a publish updates the existing post instead of creating a second one, and the ledger records per-platform status, URL, and event id, including partial failures.
- Scheduling end-to-end, dogfood dry run on a real Rankplan draft, `.env.example` listing every key the MVP needs, and a README setup section.

Validation: 1,507 tests passed. Live Nostr test article published and fetched back from public relays; Dev.to, Medium, and Hashnode live tests recorded separately in the build log.

## 2.1.1 - 2026-10-25

- Restrict MCP SQL queries through a separate read-only SQLite connection and an authorizer that blocks writes, attachments, extension loading, and connection changes.
- Recover existing remote publications from receipts across publishing entry points instead of reposting after a registry failure. Corrupt receipts block publication.
- Bind MCP confirmation to prepared articles and campaign posts. Changed campaign manifests require a new preview.
- Exclude failure-only records from publication listings and reconciliation.
- Honor Hugo `slug` and `url` front matter when inferring canonical URLs and resolve bundle assets against the page URL.
- Resolve relative links even with explicit canonical URLs. Rewrite parsed Markdown destinations, reference definitions, and HTML attributes while preserving code examples and surrounding source formatting.
- Share YAML/TOML metadata parsing for date and tag filters, and offer all discovered platform adapters in setup.
- Add Marko, Tree-sitter, and the Tree-sitter HTML grammar as runtime dependencies. Python 3.10 and newer remain supported.

Validation: 1,490 tests passed with 83% line coverage; lint and distribution builds passed. Python 3.10 was checked with the minimum parser dependency versions. Independent code review was completed, and its HTML URL whitespace finding was corrected.
