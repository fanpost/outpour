# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Crier cross-posts Markdown content (YAML or TOML front matter) to platform APIs and tracks every publication in a SQLite registry. Two front ends share one core: a Click CLI (`crier ...`) and an MCP server (`crier mcp`) that Claude Code drives through the companion crier plugin.

User-facing usage (every command, flag, config key, and API-key format) lives in README.md and `crier <command> --help`. This file covers the architecture and the invariants that no single file makes obvious.

## Development Commands

```bash
pip install -e ".[dev,mcp,nostr]"   # mcp is required: tests/test_mcp.py imports the server
pytest                              # full suite; live HTTP is blocked by a fixture
pytest tests/test_publishing.py::test_name -v
pytest -k reconcile -v
pytest --cov=crier --cov-report=term-missing
ruff check src/ tests/              # rule set pinned in pyproject [tool.ruff.lint]
pip wheel . --no-deps -w dist/      # Hatchling build; src/crier/SKILL.md is force-included
```

Python >= 3.10 (`tomli` backfills `tomllib` on 3.10). Ruff line length is 100. `ruff format` has never been applied repo-wide, so `ruff format --check` reports many files; it is not an enforced gate, and running it would reformat unrelated code. Commit messages follow `feat(scope): ...`, `fix(scope): ...`, `refactor(scope): ...`.

## Architecture

```
  cli.py (Click)          mcp_server.py (FastMCP: 20 tools, 3 resources)
          \                    /
       publishing.py: prepare -> execute -> record
        /             |                \
  platforms/      registry.py        rewrite.py + llm/
  (adapters)      (SQLite)           (manual and LLM rewrites)
```

Supporting modules: `campaign.py` (manifest-driven bulk publish), `reconcile.py` (live vs registry diff), `scheduler.py` (deferred publish), `checker.py` (pre-publish validation: pure `check_article`, I/O `check_file`), `threading.py` (thread splitting and formatting), `feed.py` (RSS/Atom via feedgen), `converters/markdown.py` (front matter parsing; rewrites relative links to absolute using `site_base_url`), `publication_receipts.py` (recovery receipts), `config.py`, `utils.py`. `cli.py` is a single ~5300-line file.

### Publishing core (`publishing.py`)

All automated API publishing runs through one pipeline with typed inputs (`PublishRequest`, `RewriteOptions`, `ThreadOptions`):

1. `prepare_request(request, source_article=None)` resolves mode and API key, parses the source (or uses a supplied snapshot), applies a supplied rewrite or calls the LLM, and splits threads. It never publishes or records; problems come back on `PublishPlan.error`.
2. `execute_plan(plan)` sends exactly the prepared article or thread and converts adapter exceptions into a failed result.
3. `record_outcome(outcome)` owns every registry effect (success, thread, or failure row) and is a no-op on terminal states, so an outcome is recorded at most once.

`publish_and_record` composes the three; CLI publish, audit publish and retry, scheduled dispatch, and campaigns all call it. The MCP server calls the stages separately so step 1 of its two-step confirmation can preview a prepared plan; its step 2 executes through `execute_or_recover(plan)`. `prepare_publish`/`publish_one` are compatibility wrappers; `publish_one` executes WITHOUT recording and has no internal callers.

`PublishOutcome.state` is a `PublicationState` enum. Distinguish `remote_success` (the platform accepted the write) from `success` (remote write AND recording both succeeded). Do not convert outcomes into ad-hoc result classes, and do not record them again in a caller.

- **Recording failure after a remote success** writes a recovery receipt (`publication_receipts.py`, a JSON file under `.<db name>.recovery/` beside the registry DB; no credentials). `audit --retry` replays it to repair the registry without reposting. A corrupt receipt raises `UnreadableReceipt` (a `ValueError`) and blocks remote retry; a receipt older than a newer failure is ignored. MCP is fenced the same way: step 1 reports any receipt as `preview.unrecorded_publication`, and `execute_or_recover` records from it (`PublishOutcome.recovered`) instead of publishing again. MCP has no failure row to compare, so any receipt counts there. Campaign cells become `published_unrecorded` (skipped by later runs); schedules stay terminal `published` with the error attached.
- **`awaiting_confirmation`** (manual/import platforms) is not a successful write. Only the interactive CLI performs manual confirmation; automated callers report the required manual action.
- **Rewrite attribution precedence:** explicit author, then `llm:<model>` for an actual LLM rewrite, then the configured default for supplied rewrite text. A supplied rewrite over the platform limit is rejected at preparation.

### Platforms (`platforms/`)

- `base.py` defines the abstract `Platform` (`publish`, `update`, `list_articles`, `get_article`; optional `delete`, `get_stats`, `publish_thread`), the result dataclasses, capability attributes (`is_short_form`, `max_content_length`, `supports_delete`, `supports_stats`, `supports_threads`, `thread_max_posts`), and `retry_request()` (exponential backoff, `Retry-After`, retryable vs non-retryable status codes). HTTP adapters use `self.retry_request()`, never `requests.*` directly.
- Discovery: `_discover_package_platforms()` scans the package and `_discover_user_platforms()` loads `~/.config/crier/platforms/*.py` (user plugins override built-ins; broken plugins warn instead of crashing). Files starting with `_` are skipped, which is how shared bases stay unregistered. `PLATFORMS` maps name to class; there is no hardcoded registration list.
- `_fediverse.py`: `FediversePlatform` implements the Mastodon-compatible REST API; `mastodon.py` and `pleroma.py` are ~30-line subclasses. Akkoma or GoToSocial would be the same shape.
- `nostr.py`: Schnorr-signed kind-1 notes over websockets via the optional `[nostr]` extra (import deferred to publish/delete). No listing or update; delete is best-effort NIP-09. It does not use `retry_request`.
- `bluesky.py`: AT Protocol. `detect_facets` emits link and hashtag facets as non-overlapping UTF-8 byte ranges; `list_articles` paginates `getAuthorFeed` (100 per page cap) and skips reposts.
- Mode comes from the configured key, not the class: `get_platform_mode()` returns `api`, `manual` (`api_key: manual`, copy-paste), `import` (`api_key: import`, e.g. Medium), or `unconfigured`.

crier is API-only by design. A Playwright browser-automation base (Substack) was built and removed on 2026-06-21: Substack rejects automated note writes with HTTP 403, and the other candidates (X, Hacker News, Lobsters) are equally hardened or inappropriate for automated posting. The spec and plan remain in `docs/superpowers/` as a record; do not reintroduce browser automation without revisiting that finding.

### Registry (`registry.py`)

Global SQLite DB at `~/.config/crier/crier.db` (WAL mode, foreign keys on; tables `articles`, `publications`, `stats`, `schema_version`). Articles are keyed by a title-derived slug (python-slugify) that stays stable if the title changes; `canonical_url` is optional, uniquely indexed metadata, so posts without one are still tracked. There are no content hashes. `get_or_create_slug()` runs wherever a publication is recorded; `update_article_metadata()` is the public metadata editor (do not import the private `_update_article_metadata`). `migrate_yaml_to_sqlite()` upgrades old YAML registries.

### Reconcile and campaigns

- `reconcile.py` diffs a platform's live listing against the registry into `in_both`, `untracked_live` (backfilled on `--apply`), `gone_from_platform`, and `unverified`. A registry row is only soft-deleted when the adapter's `list_articles_snapshot()` returns `ArticleListing(complete=True)`. The base implementation wraps `list_articles()` as incomplete and **no adapter currently overrides it**, so in practice `--apply` backfills but never deletes; unmatched rows are reported as `unverified`. A listing error, or an empty listing while the registry has rows, produces an error report rather than mass deletion. Raising `--limit` does not establish completeness.
- `campaign.py`: `plan_campaign` writes a YAML manifest of missing (post, platform) cells to `<site_root>/.crier/campaigns/<name>.yaml`; short-form cells carry an empty `rewrite` to fill in, so the manifest doubles as the rewrite cache. `run_campaign` publishes pending cells via `publish_and_record`, checks the registry per cell (an interrupted run never reposts), and supports `--max N` to drip a backlog over several runs.

### MCP server (`mcp_server.py`)

20 tools across registry queries, content search and check, actions (publish, delete, archive, campaign plan and run), and platform operations (remote list, doctor, stats), plus 3 resources (`crier://schema`, `crier://config` sanitized, `crier://platforms`). Tools return dicts (`{"error": ...}` on validation failure) and import their dependencies lazily so tool listing stays fast; keep top-level imports minimal.

### Config (`config.py`)

One global file, `~/.config/crier/config.yaml` (override the path with `CRIER_CONFIG`); there is no per-project config and no merge logic. Precedence: config file < environment (`CRIER_<PLATFORM>_API_KEY`, `CRIER_DB`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`) < CLI args. `site_root` locates the content project; `content_paths` resolve against `site_root` (never CWD), while the registry path is global. Profiles can reference other profiles. Schedules live in `<site_root>/.crier/schedule.yaml` and store absolute source paths (legacy relative paths resolve from `site_root`).

## Non-Obvious Conventions

Violating these causes regressions that are not visible from any single file.

- **Token-as-source-of-truth for MCP destructive ops.** `crier_publish`, `crier_delete`, and `crier_campaign_run` are two-step: step 1 returns a preview plus a token (5-minute TTL); step 2 executes with every parameter read from the consumed token, ignoring caller args. This blocks a token-substitution bypass. A new step-1 parameter must go into the token `details` and be read back in step 2 (see `_create_token`/`_consume_token` and the `test_*_step2_token_overrides_caller_args` tests).
- **`crier_sql` is sandboxed** in `SAVEPOINT crier_sql_guard`, always rolled back, on top of its `SELECT`-prefix check.
- **Dual-key registry API.** Public registry functions whose key parameter is named `canonical_url` accept a slug or a canonical URL, dispatched by `_resolve_slug(conn, key)` (slug lookup first). Treat the key as opaque.
- **Failure rows live in `publications`** with `platform_id IS NULL`. Queries for real publications must filter `WHERE platform_id IS NOT NULL AND deleted_at IS NULL`, or failed attempts count as successes.
- **UPSERT, never `INSERT OR REPLACE`,** in `record_publication`, `record_thread_publication`, `save_stats`, and `record_failure`. `INSERT OR REPLACE` cascade-deletes stats and silently resets unlisted columns; the UPSERTs explicitly reset `deleted_at`, `last_error`, `is_thread`, `thread_ids`, and `posted_content` so re-publishing resurrects a soft-deleted row cleanly. Locked in by `TestDeletionPreservesHistory`.
- **Rewrites go through `rewrite.apply_rewrite()`**, a `dataclasses.replace` that sets `body` and `is_rewrite=True`. Never rebuild an `Article(...)` by hand; it silently drops fields when `Article` grows.
- **Short-form is a class attribute.** `is_short_form_platform(name)` reads `PLATFORMS[name].is_short_form`; the `--long-form` filter and campaign rewrite cells derive from it. Never add a hardcoded platform set.
- **Derive behavior from structure.** Discovery, short-form detection, and modes all read capability attributes or config structure. Prefer that over parallel lookup tables or string parsing when extending crier.

## Adding a Platform

1. Create `platforms/<name>.py` subclassing `Platform`, or `FediversePlatform` for a Mastodon-compatible server (override only `name`, `description`, `max_content_length`, `default_instance`).
2. Set the capability attributes and implement `publish`, `update`, `list_articles`, `get_article`, plus any of `delete`, `get_stats`, `publish_thread`.
3. Use `self.retry_request()` for HTTP and return result objects.
4. Override `list_articles_snapshot()` to return `complete=True` only if the adapter genuinely exhausted pagination; that is what enables reconcile deletions for it.
5. Add the API-key format to README.md and update the expected count and name set in `tests/test_plugin_discovery.py`. No registration code is needed.

## Testing

- The autouse `prevent_live_http` fixture replaces `requests.sessions.Session.request` with a failure, so every remote call must be mocked. Platform tests patch `crier.platforms.base.requests.<method>` (the module `retry_request` calls through) and set `platform.max_retries = 0` when asserting on error responses.
- `recording_platform` registers an in-memory `test_platform` adapter (thread-capable) with its API-key env var, for driving the real publishing pipeline end to end.
- Anything touching the registry must isolate it: set `CRIER_DB` to a temp path, call `reset_connection()` (the module caches its connection), then `init_db()`. The `tmp_registry` fixture does this; `test_stats.py` and `test_threading.py` define local variants. `tmp_config` isolates the config file, `configured_platforms` provides devto, bluesky, manual-mode twitter, and profiles, and `mock_env_api_key` sets per-platform env keys.
- Nostr signing tests `importorskip("pynostr")`; the rest of `tests/test_nostr.py` runs without the extra.

## Related

The user-facing Claude Code integration (skill, `/crier` command, cross-poster and auditor agents, `.mcp.json`) lives in a separate repo at `~/github/alex-claude-plugins/crier/`. The in-repo `crier skill` command and `src/crier/SKILL.md` are deprecated in its favor.
