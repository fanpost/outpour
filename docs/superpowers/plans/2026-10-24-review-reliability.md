# Review Reliability Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task, with regression tests before each fix.

**Goal:** Resolve the six reviewed correctness/safety issues and the directly related metadata and adapter-discovery inconsistencies.

**Architecture:** Keep the existing prepare/execute/record core. Make receipt-aware execution the common boundary, bind MCP confirmation to the reviewed operation, and use structured parsers and discovered adapter metadata rather than duplicate parsing or registration lists.

**Tech Stack:** Python 3.10+, SQLite, Click, FastMCP, pytest; structured Markdown parsing for link edits.

**Spec:** The code review in this conversation and the user's instruction to address its issues in an appropriate order and manner.

## Global Constraints

- Preserve token-as-source-of-truth, recovery receipts, and registry history.
- No live publishing in tests; isolate configuration and databases.
- Preserve Markdown semantics, including code, references, titles, and embedded HTML.
- Preserve the untracked AGENTS.md. Work on a fix branch in the existing checkout.
- Keep broad CLI restructuring and speculative product features separate from these repairs.

## Review Focus

- SQL attachment, connection pragmas, write CTEs, and extension loading must not escape read-only access.
- Corrupt receipts and recovery after source/config changes must never cause a duplicate remote write.
- Changed campaign manifests and source files must not silently change a confirmed operation.
- Markdown code examples, reference links, nested links/images, and HTML attributes must retain their semantics.
- Failure-only rows and TOML metadata must behave consistently across CLI, MCP, and reconciliation.

## Tasks

Each task follows: add regression tests; run and observe the expected failures; implement; run the focused tests. Final verification runs the entire suite with coverage, lint, formatting on changed code, and a wheel build. A fresh reviewer examines the final diff.

- [x] **1. SQL boundary.** Update `crier_sql` and registry connection helpers. Use a dedicated read-only connection and SQLite authorizer; tests in `test_mcp.py` prove writes/ATTACH/unsafe functions are denied, normal SELECT/CTE queries work, and the normal registry connection remains writable.
- [x] **2. Publication recovery.** Route `publish_and_record` through `execute_or_recover`. Tests in `test_publishing_integration.py` prove repeats repair the registry without another remote write, corrupt receipts block posting, and campaign/schedule callers retain typed outcomes.
- [x] **3. Confirmation binding.** Retain prepared publish snapshots; bind campaign confirmation to its manifest and source contents and reject changes. Tests in `test_mcp.py` mutate source and manifest between steps, preserve caller-argument override behavior, and prove no changed operation reaches a remote adapter.
- [x] **4. Registry filtering.** Exclude NULL platform IDs from `get_platform_publications`; regression tests cover failure-only and subsequently successful records, CLI/MCP listings, and reconciliation.
- [x] **5. Content parsing.** Resolve links with explicit canonical URLs, normalize path inputs, replace whole-document regex rewriting with structured Markdown/HTML handling, and share YAML/TOML metadata parsing in `utils.py`. Tests cover literal code, reference links, titles, nested destinations, explicit canonical URLs, and TOML search filters.
- [x] **6. Adapter setup.** Derive setup choices from `PLATFORMS` and descriptions; retain existing specialized credential prompts. Tests prove every discovered adapter, including a user plugin, is selectable.
- [x] **7. Documentation and verification.** Update README/CLAUDE invariants, run unit/integration tests with coverage, lint and wheel build; review the complete diff and address substantive findings.

## Execution notes

- Baseline review: 1,431 tests passed; 82% line coverage; lint clean. Repository-wide formatting already differs in 23 files.
- User authorized implementing the reviewed remedies; no new design approval is needed for these bug fixes.

- SQL regressions: 6 failures observed before the fix; 128 SQL/registry tests passed afterward.
- Recovery regressions: 5 failures observed before the fix; 155 focused service/integration tests passed afterward.
- Confirmation regressions: all 5 failed before the fix; 146 MCP/campaign/integration tests passed afterward.
- Registry regressions: 3 failed before filtering; 231 registry/MCP/reconciliation tests passed afterward.
- Content regressions: 20 failed before parser fixes. Marko was selected after a Tree-sitter Markdown prototype missed valid nested labels; HTML alone uses Tree-sitter. 223 focused tests passed after content/setup fixes.
- Whole suite: 1,484 passed; 83% coverage; link-edit module 100% line coverage. Lint and wheel build passed.
- Python 3.10 with minimum Marko/Tree-sitter/HTML versions: 257 focused tests passed.
- Two supplemental tests cover newer failure timestamps and corrupt campaign receipts; both passed.
- Independent review found one important HTML URL whitespace regression. Three new cases failed before trimming decoded HTML ASCII whitespace; all pass after the fix. Nonbreaking spaces remain part of the URL.
- Final verification: 1,490 tests passed (497 warnings), 83% overall line coverage. Lint and wheel build passed; new parser file passes formatting. Repository-wide format checking still reports the same 23 pre-existing files.
- Final Python 3.10/minimum-dependency converter run: 68 passed.
- No remaining important review findings. New product features and broad CLI module splitting remain outside this repair scope.

## Reproduce verification

```bash
uv run --no-project --with-editable '.[dev,mcp,nostr]' pytest --cov=crier --cov-report=term-missing -q
uv run --no-project --with-editable '.[dev,mcp,nostr]' ruff check src/ tests/
uv build --wheel
```

## Parser and SQL references

- [SQLite authorizer](https://www.sqlite.org/c3ref/set_authorizer.html)
- [Marko source positions](https://marko-py.readthedocs.io/en/latest/usage.html#source-positions)
- [Tree-sitter HTML grammar](https://github.com/tree-sitter/tree-sitter-html)

