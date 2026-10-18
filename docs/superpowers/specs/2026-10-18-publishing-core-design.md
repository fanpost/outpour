# Publishing Repairs and Shared Core

Status: implemented and verified on `fix/publishing-core`; see the implementation
plan for execution results.

## Outcome and scope

Repair the seven reproduced review findings, then make automated API publishing
use the same preparation, execution, and registry-recording rules from the CLI,
MCP, campaigns, audit/retry, and scheduled dispatch. Success means identical
inputs produce the same remote payload and persisted metadata through every
supported entry point.

Retain Python 3.10 support, existing command names, JSON fields, platform plugin
discovery, SQLite identities, and MCP token semantics. Keep manual/import prompts
in the CLI. This change does not introduce a queue, replace schedule YAML, add
platforms, redesign remote HTTP retries, or promise exactly-once remote writes.

## Current boundaries

`publishing.py` prepares and publishes API single posts, but callers separately
parse content, rewrite, dispatch threads, and record outcomes. `schedule run`
implements its own publishing flow. MCP prepares an article, then reparses the
file during execution. The same successful result can consequently be recorded
differently or omitted entirely.

The latest local-source baseline was 1,345 passing tests, four skipped tests,
and 79% coverage. High statement coverage did not catch identity collisions or
cancel-versus-dispatch interleavings. The collision test currently encodes the
incorrect merge behavior and must change with an explicit explanation.

## Phase 1: Repairs before consolidation

Each repair starts with a regression test that fails on the existing source and
ends with the relevant module and integration tests passing.

| Finding | Required behavior | Primary files |
| --- | --- | --- |
| Partial reconciliation | Absence from a limited or unsuccessful listing cannot establish deletion. Report uncertainty without changing publication state. | `reconcile.py`, `platforms/base.py`, MCP/CLI reconcile output |
| Title collisions | Distinct canonical URLs or source files cannot merge because their titles slugify identically. Preserve both records and allocate a unique slug. | `registry.py` |
| Cancellation race | Cancellation holds the same schedule lock as creation, claiming, and updating for its entire read/check/write operation. | `scheduler.py` |
| Relative scheduled paths | New schedules store absolute resolved source paths at creation. | `scheduler.py` |
| Missing canonical URL | Successful MCP publication is recorded using the registry's existing title/source identity support, including when canonical URL is absent. | `mcp_server.py` |
| Scheduled thread metadata | Record thread classification, root, reply IDs, and URLs through `record_thread_publication`. | `cli.py` |
| Python 3.10 TOML | Use `tomllib` on Python 3.11+ and `tomli` on Python 3.10, with a conditional runtime dependency. Remove the handwritten TOML parser. | `converters/markdown.py`, `pyproject.toml` |

### Reconciliation evidence

Add an optional structured listing method to `Platform`, with a concrete default
implementation that wraps `list_articles()` and marks completeness unknown.
Existing plugins remain usable without implementing another abstract method.
The result carries articles and an explicit completeness flag; a short page is
not automatically complete. Only an adapter that has exhausted its pagination
successfully can declare completeness. Failed retrieval must never look like an
authoritative empty listing.

The initial repair treats all legacy listings as incomplete. Unmatched registry
entries appear in an additive `unverified` report field; `gone_from_platform`
contains only entries absent from a known-complete listing. Apply may backfill
observed posts but cannot soft-delete unverified entries. Additive CLI/MCP output
explains when deletion checks were inconclusive. Adapter pagination expansion is
not required to ship the safety repair.

### Identity rules

Continue canonical URL lookup first and source-file lookup second, including
legitimate title changes. If neither matches and a title slug already belongs
to an article with conflicting supplied identity, allocate a suffix. Title-only
calls remain backward compatible when no conflicting identity was supplied.
Do not change existing slugs or attempt to reconstruct previously overwritten
records automatically. Preserve registry UPSERT behavior and dependent stats.

### Scheduling compatibility

Existing absolute paths remain valid. Legacy relative paths resolve against
configured `site_root`, with a clear error if the expected source is absent;
never guess among same-named files in arbitrary working directories. With no
configured site root, use the schedule file's project directory. The original
creation directory of an old relative path cannot be recovered automatically.

## Phase 2: Shared API publishing flow

Keep the core in `publishing.py`; splitting the entire CLI is outside this work.
Introduce typed request/options objects and evolve the existing plan/outcome
types rather than maintaining separate argument dictionaries per caller.

- `PublishRequest` identifies the resolved source file and platform and contains
  rewrite, draft, and thread options. Rewrite/thread options are dataclasses;
  thread style is a validated enum with existing CLI spellings at the boundary.
- `PublishPlan` contains the prepared article, resolved adapter/context, rewrite
  attribution, and any thread payload. Preparation reads the source once and
  may call the configured LLM. Its documentation explicitly describes those
  effects. Preparation never publishes or writes the registry.
- `PublishOutcome` retains the actual `PublishResult` or `ThreadPublishResult`,
  prepared article, source identity, rewrite attribution, and posted content.
  Do not convert threads into synthetic classes or lose partial-result IDs.
- `PublicationState` distinguishes remote failure, successful recorded publish,
  and remote success with a recording error. Callers must not mistake a local
  persistence error for permission to repeat a remote publish.

The service exposes these stages:

1. `prepare_request(request) -> PublishPlan`: resolve API mode/credentials,
   parse, apply draft/rewrite settings once, and prepare thread content. Requests
   fail explicitly when auto-rewrite is requested without a configured provider
   or threading is unsupported. Obtain capabilities from the adapter class.
2. `execute_plan(plan) -> PublishOutcome`: use the prepared article directly;
   do not reread the source or repeat rewriting. Call one adapter operation,
   retaining thread metadata. No registry writes or prompts.
3. `record_outcome(outcome) -> PublishOutcome`: record success or failure once,
   using canonical URL when available and title/source identity otherwise.
   Select the registry function from the structured result type. Preserve
   explicit author attribution and LLM attribution consistently.
4. `publish_and_record(request) -> PublishOutcome`: compose these stages for
   automated entry points. Retain `publish_one` as a compatibility wrapper with
   its existing no-recording contract while internal callers migrate.

Dry-run stops before execution and recording. Preserve the existing validation
policy and `--no-check`/`--strict` behavior during migration; moving policy into
the core must not silently add new rejection rules to campaigns or MCP.

Credentials remain internal and excluded from repr/preview/JSON. Resolve
default LLM settings at request preparation; scheduled overrides retain their
current run-time precedence. Never mutate the source article between platform
requests; copy it with `dataclasses.replace` and copy mutable fields as needed.

## Entry-point migration

Migrate MCP first, then campaigns and audit/retry, scheduled API dispatch, and
immediate CLI API publishing. Migrate one entry point at a time while retaining
the repaired behavior. Once a caller delegates recording, remove its redundant
registry writes rather than leaving two owners.

MCP confirmation step two continues to take every argument from its consumed
token. It prepares and executes one plan, avoiding the extra read currently in
`_execute_publish`. Binding confirmation to a content digest is a separate
feature; this change does not claim to provide it.

Scheduling owns claiming, cancellation, and terminal schedule state; the shared
service owns the publication result and registry recording. Update schedule
success only after recording is attempted. If remote publishing succeeded but
recording failed, retain terminal `published` schedule state with an error and
surface the recording failure for reconciliation, preventing automatic reposts.
Do not modify the manifest or registry on campaign previews.

Manual/import flows retain interactive confirmation and existing sentinel IDs.
Their confirmed outcomes can use the shared recording helper without routing
interactive behavior through the automated API executor. CLI formatting,
aggregate counters, exit codes, and MCP confirmation remain boundary concerns.

## Verification and acceptance

Add regressions for partial/unknown versus complete reconciliation; distinct
canonical/source identities with the same title; preserved stats; overlapping
cancellation/claim/creation; scheduling and dispatch from different directories;
noncanonical MCP success/failure; stored thread IDs; and TOML comments, quoted
commas, multiline strings, and booleans on Python 3.10.

Add shared-core tests proving preparation occurs once, dry-run has no publishing
or registry writes, auto-rewrite is invoked at most once, partial thread results
retain IDs, and recording errors are distinguishable from remote failure.
Parameterize integration tests over migrated callers to verify identical payload,
identity, thread metadata, rewrite text, author attribution, and single recording.
Retain token-substitution, campaign resume, schedule claim, and deletion-history
regressions. Mock network operations and isolate all configuration/database paths.

Run tests against local source with `PYTHONPATH=src python -m pytest`, then obtain
coverage with `--cov=crier --cov-report=term-missing`. Run Ruff on changed code,
check a wheel build, and verify conditional TOML dependencies in metadata. Use
an isolated development environment if required tools are absent. Do not install
over the user's existing global environment or publish real content for testing.

## Delivery order

1. Independently tested repairs, including corrected expectations for old bugs.
2. Typed core and shared recording with compatibility wrappers.
3. Caller migrations and cross-entry-point integration tests.
4. Full suite, coverage review, focused code review, and documentation updates.

Keep the pre-existing MCP dependency constraint and `AGENTS.md` content intact.
Do not introduce a registry schema migration, queue dependency, or unrelated CLI
reorganization in this iteration.

## Execution clarification: recovery receipts

Independent review reproduced an existing-failure audit retry that published
remotely twice after registry recording failed. Campaign/schedule terminal states
alone cannot protect that route. The service now saves an atomic typed recovery
receipt beside the database when a remote success cannot be recorded. Retry uses
that receipt only to repair local recording, even if the source is gone; malformed
receipts block remote retry, and older receipts cannot mask newer failures. This
adds no queue or database schema. Receipts contain article/result metadata without
credentials and are removed after recording succeeds. Pending manual confirmation
is explicitly distinct from remote success. Explicit attribution overrides LLM
attribution; configured defaults apply to supplied rewrite text.
