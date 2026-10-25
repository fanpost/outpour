# Changelog

## 2.1.1 — 2026-10-25

- Restrict MCP SQL queries through a separate read-only SQLite connection and an authorizer that blocks writes, attachments, extension loading, and connection changes.
- Recover existing remote publications from receipts across publishing entry points instead of reposting after a registry failure. Corrupt receipts block publication.
- Bind MCP confirmation to prepared articles and campaign posts. Changed campaign manifests require a new preview.
- Exclude failure-only records from publication listings and reconciliation.
- Honor Hugo `slug` and `url` front matter when inferring canonical URLs and resolve bundle assets against the page URL.
- Resolve relative links even with explicit canonical URLs. Rewrite parsed Markdown destinations, reference definitions, and HTML attributes while preserving code examples and surrounding source formatting.
- Share YAML/TOML metadata parsing for date and tag filters, and offer all discovered platform adapters in setup.
- Add Marko, Tree-sitter, and the Tree-sitter HTML grammar as runtime dependencies. Python 3.10 and newer remain supported.

Validation: 1,490 tests passed with 83% line coverage; lint and distribution builds passed. Python 3.10 was checked with the minimum parser dependency versions. Independent code review was completed, and its HTML URL whitespace finding was corrected.
