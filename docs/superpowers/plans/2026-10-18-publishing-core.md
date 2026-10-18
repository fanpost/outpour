# Publishing Repairs and Shared Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the seven verified bugs, then give automated publishing one preparation, execution, and recording flow.

**Architecture:** First repair current entry points with regression tests. Extend the existing core with typed requests and outcomes, then migrate callers one at a time while retaining compatibility wrappers and presentation at the boundaries.

**Tech Stack:** Python 3.10+, dataclasses, enums, Click, FastMCP, SQLite, PyYAML, tomllib/tomli, pytest, Ruff, Hatchling.

**Spec:** [Approved design](../specs/2026-10-18-publishing-core-design.md).

## Global Constraints

- Retain Python 3.10 support, existing command names, JSON fields, platform plugin discovery, SQLite identities, and MCP token semantics.
- Keep manual/import prompts in the CLI.
- No queue, schedule-storage replacement, registry schema migration, new platforms, remote HTTP retry redesign, or unrelated CLI reorganization.
- Retain `publish_one` with its existing no-recording contract.
- Keep the pre-existing MCP dependency constraint and `AGENTS.md` content intact.
- Never publish real content or overwrite the user's global Python environment during verification.
- Every bug repair must have a regression observed failing before its implementation; retain UPSERT/stat-history and token-substitution regressions.

## Review Focus

- A successful remote write followed by a local recording error must never become an automatic retry: Tasks 8, 10, and 11.
- Canonical URL and source-file lookups can disagree or supply only partial identity; preserve lookup precedence and avoid title-based merges: Task 1.
- Empty and short remote pages cannot prove completeness; legacy plugins must remain instantiable: Task 2.
- Default versus explicit LLM settings, including zero retries and false truncation, must retain precedence without duplicate rewrites: Tasks 8, 11, and 12.
- Preparation for a second platform must not mutate the first platform's article, tags, or rewrite attribution: Tasks 8 and 12.

## File Responsibilities and Sequence

Tasks 1–7 repair existing behavior. Task 8 defines the core interfaces consumed by Tasks 9–12. Task 13 validates the completed migration.

`registry.py` owns identity and persistence primitives; `platforms/base.py` owns adapter contracts; `reconcile.py` owns evidence-based comparison; `scheduler.py` owns schedule storage/claims and source-path resolution. `publishing.py` owns typed API preparation, execution, and recording. CLI, MCP, and campaign modules own presentation, confirmation, claims, and progress. Tests use temporary config/DB paths and fake adapters at the network boundary.

## Task 1: Preserve distinct article identities

**Files:** `src/crier/registry.py`; `tests/test_registry.py`.

**Interfaces:** Preserve `get_or_create_slug(title, canonical_url=None, source_file=None, conn=None) -> str` and public registry signatures.

- [x] Write failing regressions for equal titles with different canonical URLs and files; assert `slug_a != slug_b`, both original URLs resolve, and both platform IDs survive. Correct `TestSlug.test_get_or_create_slug_unique_collision` to expect distinct slugs. Include canonical-match/source-match title changes, source-only collisions, title-only reuse, and preserved stats.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_registry.py -q`; confirm failures identify unintended identity reuse.
- [x] Inspect the existing slug row's canonical/source fields before title fallback. Reuse a canonical or source match in the existing order. Allocate `_ensure_unique_slug` when supplied canonical/source identity conflicts with the slug owner. Preserve old identities and UPSERT semantics.
- [x] Repeat the module tests, then commit only this task's files as `fix(registry): preserve distinct articles with matching title slugs`.

## Task 2: Require completeness evidence for reconciliation deletion

**Files:** `src/crier/platforms/base.py`, `src/crier/reconcile.py`, `src/crier/cli.py`, `src/crier/mcp_server.py`; `tests/test_reconcile.py`, `tests/test_mcp.py`, `tests/test_cli.py`, `tests/test_plugin_discovery.py`.

**Interfaces:** Add `ArticleListing(articles: list[dict[str, Any]], complete: bool = False, error: str | None = None)` and concrete `Platform.list_articles_snapshot(limit: int = 10) -> ArticleListing`. Add `ReconcileReport.unverified: list[ReconcileEntry]`; retain existing fields.

- [x] Add partial-list, empty-unknown, empty-complete, complete-missing, and retrieval-error tests. Assert partial apply leaves `is_published(old_key, platform)` true; a complete missing result makes it false; errors write nothing. Change old deletion tests to explicitly supply complete snapshots. Check legacy plugin discovery and additive CLI/MCP `unverified` output.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_reconcile.py tests/test_mcp.py tests/test_cli.py tests/test_plugin_discovery.py -q`; verify the new evidence cases fail first.
- [x] Implement the default snapshot wrapper with `complete=False`. Reconciliation consumes it, checks errors before writes, and classifies unmatched rows as unverified unless completeness is explicit. A complete empty result may establish deletion; an unknown empty result cannot. Keep backfill and dry-run behavior.
- [x] Rerun these tests and commit as `fix(reconcile): require complete listings before recording deletions`.

## Task 3: Serialize schedule cancellation

**Files:** `src/crier/scheduler.py`; `tests/test_scheduler.py`.

**Interfaces:** Preserve `cancel_scheduled_post(post_id: str) -> bool`; use existing `_schedule_lock()`.

- [x] Add cancel-versus-claim and cancel-versus-create tests with controlled subprocess synchronization. Block cancellation after it reads pending A/B, start the competing operation, then release it. Assert B is claimed once and concurrently created C survives; use events/pipes and bounded timeouts rather than sleeps.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_scheduler.py -q`; confirm the old unlocked implementation loses state.
- [x] Lock the entire cancellation load/check/update/save operation, matching other mutators; retain prefix and terminal-state behavior.
- [x] Rerun the module tests and commit as `fix(schedule): lock cancellation across its full transaction`.

## Task 4: Resolve scheduled sources consistently

**Files:** `src/crier/scheduler.py`, scheduled dispatch in `src/crier/cli.py`; `tests/test_scheduler.py`, `tests/test_cli.py`.

**Interfaces:** Add `resolve_scheduled_source(file_path: str | Path) -> Path`; absolute paths pass through, legacy relative paths resolve against `get_site_root() or get_schedule_path().parent.parent`.

- [x] Test scheduling from a subdirectory and dispatching from another directory; assert the intended article reaches the adapter. Assert new `ScheduledPost.file_path == str(source.resolve())`. Test legacy site-relative paths, missing legacy sources, and misleading same-name files in the runner's CWD. Update exact relative-path assertions in old creation tests.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_scheduler.py tests/test_cli.py -k 'Schedule or schedule' -q`; observe the path regressions fail.
- [x] Resolve new source paths at creation and call the shared resolver for legacy dispatch; do not search arbitrary directories.
- [x] Rerun focused tests and commit as `fix(schedule): persist absolute source paths and resolve legacy entries`.

## Task 5: Record noncanonical MCP publications

**Files:** `src/crier/mcp_server.py`; `tests/test_mcp.py`.

**Interfaces:** Preserve `crier_publish` and `_execute_publish` signatures during this repair.

- [x] Add real-registry success and failure tests with no canonical URL and no configured base URL. Assert recorded lookup by source/slug contains the remote ID or recorded error. Keep token-supplied file/platform/rewrite/author override tests.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_mcp.py -q`; confirm absent records cause the intended failure.
- [x] Remove canonical-URL gating from publication/failure recording when parsed article identity is available. Pass optional canonical URL, title, and resolved source path to registry functions.
- [x] Rerun MCP tests and commit as `fix(mcp): track publications without canonical URLs`.

## Task 6: Preserve scheduled thread results

**Files:** scheduled dispatch in `src/crier/cli.py`; `tests/test_cli.py`.

**Interfaces:** Retain actual `ThreadPublishResult`; use existing `record_thread_publication`.

- [x] Extend `TestScheduleRunFullOptions.test_run_publishes_thread_when_requested` with `assert is_thread(key, platform)` and `assert get_thread_ids(key, platform) == ['t-1', 't-2']`; query stored URLs too. Add single-post fallback and unsuccessful/partial thread cases: expose returned IDs in additive `thread_ids` output while keeping the failure status and not recording complete success.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_cli.py -k ScheduleRun -q`; confirm successful thread metadata is missing before the fix.
- [x] Remove the synthetic result class in this path; branch on the actual result type for recording. Single posts still use `record_publication`; unsuccessful threads do not become successful publications.
- [x] Rerun focused tests and commit as `fix(schedule): retain published thread metadata`.

## Task 7: Parse TOML with supported libraries

**Files:** `src/crier/converters/markdown.py`, `pyproject.toml`; `tests/test_converters.py`.

**Interfaces:** Preserve `_parse_toml(toml_str: str) -> dict[str, Any]` and `parse_front_matter` return types. Add dependency `tomli>=2.0; python_version < '3.11'` without changing the existing MCP constraint.

- [x] Add Python 3.10 regressions for inline comments, quoted commas, multiline strings, and false booleans: `assert parsed['published'] is False`; `assert parsed['tags'] == ['one, two', 'three']`. Exercise both library-import branches with valid input; retain existing malformed-front-matter behavior.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_converters.py -q` on Python 3.10 and observe the handwritten-parser failures.
- [x] Replace the fallback with `tomli.loads`, using `tomllib.loads` when available, and add the conditional dependency.
- [x] Rerun converter tests on 3.10 and an available 3.11+ interpreter; commit as `fix(converters): use a compliant TOML parser on Python 3.10`.

## Task 8: Introduce the typed publishing service

**Files:** `src/crier/publishing.py`; `tests/test_publishing.py`, shared fixtures in `tests/conftest.py`.

**Interfaces:** Define the following in `publishing.py`; retain existing `prepare_publish`/`publish_one` signatures as adapters.

```text
# Dataclasses; options/requests are frozen. Defaults use default_factory.
RewriteOptions(content: str | None = None, author: str | None = None,
               auto: bool = False, provider: LLMProvider | None = None,
               retry_count: int | None = None, truncate: bool | None = None,
               temperature: float | None = None, model: str | None = None)
ThreadStyle: str, Enum  # NUMBERED='numbered', SIMPLE='simple', EMOJI='emoji'
ThreadOptions(enabled: bool = False, style: ThreadStyle = ThreadStyle.NUMBERED)
PublishRequest(source_file: Path, platform: str,
               rewrite: RewriteOptions = ..., draft: bool = False,
               thread: ThreadOptions = ...)
prepare_request(request: PublishRequest) -> PublishPlan
execute_plan(plan: PublishPlan) -> PublishOutcome
record_outcome(outcome: PublishOutcome) -> PublishOutcome
publish_and_record(request: PublishRequest, *, dry_run: bool = False) -> PublishOutcome
```

`PublishPlan` retains its existing fields, adds request, resolved adapter, and thread payload, and excludes credentials/adapter/provider from repr. An error plan may lack an article or adapter. `PublishOutcome.result` retains `PublishResult | ThreadPublishResult` and adds request, `recording_error`, and `state`. `PublicationState` values are `preview`, `remote_failed`, `remote_succeeded`, `recorded`, and `recording_failed`. For compatibility with existing direct outcome construction, omitted state is inferred from the actual result. Add outcome properties `remote_success`, `article_id`, and `url`, derived from result type. Preserve existing rewrite bookkeeping fields. Do not serialize whole plans with `asdict`.

- [x] Add behavior tests using a fake `Platform` and real temporary registry: preparation once; unchanged prepared payload after a source edit; one rewrite; dry-run with zero remote/DB writes; single/thread success; unsupported threading; missing provider; exceptions; no canonical URL; explicit author versus `llm:<model>`; partial thread IDs; recording error preserving remote success. Also assert request reuse does not mutate articles/tags and secret strings are absent from repr and preview output.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_publishing.py -q`; confirm the new service tests fail before implementation.
- [x] Implement the interfaces and route compatibility wrappers through preparation/execution only. Resolve request source paths with `expanduser().resolve()`, copy parsed article/tags, resolve LLM defaults only when needed using existing config/get_provider functions, and retain explicit zero/false overrides. Recording uses actual result type and the prepared source identity. Never treat a dry-run synthetic result as a recordable remote success; repeated recording of an already-recorded outcome is a no-op.
- [x] Rerun core/registry/rewrite/threading tests; commit as `refactor(publishing): add typed preparation execution and recording`.

## Task 9: Migrate MCP to prepared execution

**Files:** `src/crier/mcp_server.py`; `tests/test_mcp.py`.

**Interfaces:** Consume Task 8's service. `_prepare_publish` returns a `PublishPlan` or existing error dict; `_execute_publish(plan: PublishPlan) -> dict` executes and records that plan.

- [x] Replace the old delegation-only test with a real file/registry integration test: spy on parsing while executing confirmed step two and assert one parse, the actual adapter payload, and one stored publication. Assert caller arguments cannot override consumed-token details, dry-run writes nothing, and recording failure returns additive `remote_published=True` with an error rather than publish failure.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_mcp.py -q`; confirm the extra parse/state regressions fail.
- [x] Build requests from token details, execute the prepared plan, and remove local duplicate recording. Keep existing success/error response fields and lazy imports. Do not bind content hashes or credentials into user-visible tokens.
- [x] Rerun MCP/core tests and commit as `refactor(mcp): execute and record prepared publishing plans`.

## Task 10: Migrate campaigns and audit/retry

**Files:** `src/crier/campaign.py`, audit/retry paths in `src/crier/cli.py`; `tests/test_campaign.py`, `tests/test_cli.py`.

**Interfaces:** Consume `PublishRequest`, `RewriteOptions`, and `publish_and_record`; add terminal campaign cell status `published_unrecorded` for remote success with recording failure.

- [x] Add integration tests proving canonical/source identity and rewrite text come from the executed outcome, success/failure recording occurs once, and campaign dry-run changes no manifest/DB. On remote success plus recording error, assert the cell persists `published_unrecorded`, exposes the error, increments the failure count, and a second run never republishes that cell. Audit/retry reports the same distinction and does not create a new remote-failure row for successful remote writes.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_campaign.py tests/test_cli.py -k 'campaign or Campaign or Audit or audit' -q`; confirm missing service/error behavior fails.
- [x] Replace API publishing and duplicate writes with Task 8's service. Keep campaign registry-based resume/max-cell accounting and audit filters/exit codes; skip both terminal published statuses. Preserve the dormant update branch separately without claiming it has been consolidated.
- [x] Rerun campaign/CLI/core tests and commit as `refactor(publishing): share campaign and audit execution`.

## Task 11: Migrate scheduled API dispatch

**Files:** schedule dispatch in `src/crier/cli.py`, `src/crier/scheduler.py` only if needed for conversion; `tests/test_cli.py`, `tests/test_scheduler.py`.

**Interfaces:** Convert `ScheduledPost` fields into Task 8's request/options. Scheduling continues to own claim and terminal-state updates.

- [x] Add integration tests with explicit zero retries, false truncation, temperature/model overrides, default resolution, manual rewrite priority, thread metadata, and per-post failure isolation. Force registry failure after successful remote publishing; assert schedule `status == 'published'`, a visible error/nonzero exit, and zero publications on a second run.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_cli.py tests/test_scheduler.py -k 'Schedule or schedule' -q`; verify new recording-error expectations fail.
- [x] Replace duplicate parse/rewrite/API/registry logic with one service call per claimed post. Resolve legacy paths using Task 4. Apply terminal state after recording: recorded success is published; remote failure is failed; recording failure after remote success is published with error. Preserve option guards, JSON fields, claims, and counters.
- [x] Rerun scheduler/CLI/core tests and commit as `refactor(schedule): dispatch through the shared publishing service`.

## Task 12: Migrate immediate CLI API publishing

**Files:** immediate publishing in `src/crier/cli.py`; `tests/test_cli.py`.

**Interfaces:** Consume Task 8's typed service for API mode. Manual/import confirmation remains outside the automated executor.

- [x] Add payload/DB integration tests for draft, explicit rewrite, auto-rewrite attribution, threading, and multiple platforms. Assert original tags/content remain independent, unsupported threading is explicit, each request rewrites at most once, and the original JSON fields/exit codes remain. Retain manual/import confirmation and batch-skip tests; verify previews have no remote/registry effects.
- [x] Run `PYTHONPATH=src python -m pytest tests/test_cli.py -q`; confirm new core/recording invariants fail before migration.
- [x] Replace API-only duplicate rewriting, synthetic thread results, and registry writes with typed requests/outcomes. Keep `--no-check`/`--strict` policy and interactive/manual/import behavior. If manual/import recording adopts `record_outcome`, call it only after explicit confirmation and preserve existing sentinel IDs.
- [x] Rerun CLI/MCP/campaign/core tests and commit as `refactor(cli): unify API publishing and outcome recording`.

## Task 13: Verify parity, packaging, and documentation

**Files:** new `tests/test_publishing_integration.py`; `tests/conftest.py`, `README.md`, `CLAUDE.md`, approved spec status if needed. Do not edit `AGENTS.md`.

- [x] Parameterize equivalent supported inputs across immediate CLI, MCP, campaign, audit/retry, and schedule entry points using a shared fake adapter and isolated real registries. Assert identical captured `Article`, remote IDs, rewrite attribution, one publication row, and one recording attempt. Parameterize thread cases only over entry points exposing threads. Test old `publish_one` still leaves the DB untouched. Commit tests with any parity corrections after red/green verification.
- [x] Create an isolated development venv outside the repository if dependencies are missing; install editable `.[dev,mcp,nostr]` and `build`. Run `PYTHONPATH=src python -m pytest --cov=crier --cov-report=term-missing`. Require zero failures, inspect skipped tests and missed core/error branches, and avoid reducing existing coverage. Run Python 3.10 and an available 3.11+ environment; report unavailable matrix entries explicitly.
- [x] Run Ruff on touched source/tests and fix introduced diagnostics. Compare any pre-existing diagnostics against baseline rather than reformatting the entire CLI. Run `python -m build --outdir /tmp/crier-core-dist`; inspect wheel/sdist contents and conditional TOML dependency metadata, install the wheel in a clean venv, and run `crier --help`. Run `git diff --check` and review the diff against all seven repairs and the spec.
- [x] Update README/CLAUDE guidance for incomplete reconciliation, scheduled path compatibility, shared publishing stages, and remote-success/recording-error behavior. Remove obsolete claims about caller-owned recording and manual platform registration. Perform a focused code review of changed files, address findings with regressions, rerun affected/full checks, and commit documentation as `docs: describe shared publishing and reconciliation safety`.

## Execution Handoff

Review this plan before source changes. Recommended method: **Native**, implementing sequentially in this session with one independent whole-change review at the end. The caller migrations depend on a common interface, making sequential execution straightforward. **Subagent-driven** execution is also available, with an independent implementation/review cycle for each task.

Neither method permits live publishing during tests. Preserve the user's existing work; stage/commit only task-owned changes, especially when adding the conditional TOML dependency beside the pre-existing MCP dependency edit.

## Execution Results

Implemented on `fix/publishing-core`. The final independent review identified
three safety/parity gaps: retry after recording failure, pending manual
confirmation, and default LLM attribution. Each was reproduced by a failing test
and addressed in the native fix pass. Recovery receipts preserve remote results
for local recording repair without another remote write; corrupt receipts block
retry and successful repair works even after source removal.

Final verification: 1,408 tests passed on Python 3.10 and 1,408 on Python 3.11;
coverage is 82% (baseline 79%). Wheel and source-distribution builds passed; a
clean Python 3.10 wheel installation verified CLI startup, packaged skill,
receipt module, lifecycle enum, TOML parsing, and conditional dependencies.
Ruff introduced no diagnostics relative to the baseline; new receipt code/tests
pass lint directly. `git diff --check` passed. Network calls were mocked or
blocked during verification. Existing MCP dependency edits and AGENTS.md were
preserved.
