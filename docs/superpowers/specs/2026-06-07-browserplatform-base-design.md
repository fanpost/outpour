# BrowserPlatform Base Design

**Status:** approved (design), pending spec review
**Date:** 2026-06-07
**Author:** Alex Towell (with Claude Code)

## Goal

Add a reusable `BrowserPlatform` base that lets crier publish to platforms with
no usable API by driving a real browser (Playwright), plus a first concrete
subclass (Substack Notes) that validates the base end to end.

## Background

Crier publishes to 15 platforms today. Three classes of target have no viable
API path: community aggregators (Hacker News, Lobsters), Substack (no public
write API), and X/Twitter (copy-paste only). Hashnode also lost its free API on
2026-05-13 (Pro plan now required). The shared need is the same: log in once as
a human, then post programmatically by driving the site's own editor.

This mirrors the `_fediverse.py` win: one runtime captured as a base class, with
each new platform reduced to a thin subclass. The base is the high-value unit;
Substack Notes is the first subclass and the validator.

User constraint (standing): no copy-paste-only platforms. Browser automation is
an accepted mechanism; an API is preferred when one exists.

## Architecture

New module `src/crier/platforms/_browser.py` defining `BrowserPlatform(Platform)`.
The leading underscore keeps it out of platform auto-discovery (the same
mechanism that hides `_fediverse.py`); only concrete subclasses register.

- **Sync Playwright.** The `Platform` ABC is synchronous (`publish`, `update`,
  etc.), so the base uses Playwright's sync API (`sync_playwright`). No async
  leaks into the platform contract.
- **Optional `[browser]` extra.** `pyproject.toml` gains `browser = ["playwright>=1.40"]`.
  The Playwright import is deferred to publish/login time (lazy import in a
  helper), so the module stays importable and discoverable without the extra,
  matching the Nostr pattern. Chromium itself is installed once by the user with
  `playwright install chromium`; missing-browser errors are surfaced as failures
  with that hint.
- **Session storage.** Cookies are stored per platform at
  `~/.config/crier/browser/<name>/state.json` (Playwright `storage_state`).
  A helper `_session_path(name)` returns this path; the directory is created on
  login.

## Base contract

The base owns the entire lifecycle so subclasses stay tiny.

`BrowserPlatform.publish(article) -> PublishResult`:
1. If the `[browser]` extra is missing, return a failure with the install hint.
2. If `state.json` is missing, return a failure: `"No browser session for
   <name>; run: crier login <name>"`.
3. Lazy-launch headless Chromium, open a context with the stored `storage_state`,
   open a page.
4. Call the subclass hook `_post(page, article) -> str` (returns the posted URL).
5. Return `PublishResult(success=True, platform=name, url=posted_url)`.
6. On ANY exception: save a screenshot to
   `~/.config/crier/browser/<name>/last-error.png` (best effort), and return
   `PublishResult(success=False, platform=name, error=str(e))`.
7. ALWAYS close the context and browser in a `finally` block.

Subclasses implement only:

- Class attributes: `name`, `description`, `login_url`, `is_short_form`,
  `max_content_length`.
- `_post(self, page, article) -> str`: the site choreography (navigate to the
  composer, fill the text from `self._compose(article)`, submit, return the
  resulting post URL). `_compose` reuses the base `_append_canonical_url` and
  the rewrite/metadata composition already used by other short-form platforms.

Unsupported-by-default operations (overridable later):

- `update(article_id, article)`: returns a failure ("not supported for browser
  platforms in v1").
- `list_articles(limit)`: returns `[]` (no listing). The reconcile
  empty-listing guard already refuses to mark rows gone when a listing is empty
  but the registry has rows, so this is safe.
- `get_article(article_id)`: returns `None`.
- `delete`: `supports_delete = False` in v1.
- `get_stats`: `supports_stats = False` in v1.

## crier login command

New CLI command `crier login <platform>`:
1. Resolve the platform from `PLATFORMS`; error if it is not a
   `BrowserPlatform` subclass.
2. Lazy-import Playwright (error with the `[browser]` install hint if missing).
3. Launch a HEADED Chromium, navigate to the subclass `login_url`.
4. Print: `Log in to <platform> in the browser window, then press Enter here.`
5. Block on stdin (`click.pause` or `input()`).
6. Save `context.storage_state(path=_session_path(name))` (create the directory
   first).
7. Close the browser and confirm the saved path.

Cookies only, never passwords. Magic-link, OAuth, and 2FA all work because the
human completes them in the real browser window. There is no `--headless`
variant of login (capture requires a human).

## First subclass: Substack Notes

`src/crier/platforms/substack.py` defining `Substack(BrowserPlatform)`:

- `name = "substack"`, `description = "Short notes on Substack (browser)"`,
  `login_url = "https://substack.com/"`, `is_short_form = True`,
  `max_content_length = None` (Notes have no small hard cap).
- `_post(page, article)`: navigate to the Notes composer, fill the composer with
  `self._compose(article)`, click Post, and return the new note's URL (falling
  back to the profile URL if a per-note URL cannot be scraped).

The exact DOM selectors are NOT guessed in this spec. They will be derived at
build time by inspecting the live Substack Notes composer with the Playwright
MCP tools, after a session has been captured with `crier login substack`. The
build task records the selectors it found and why.

Long-form Substack Posts are a deliberate follow-up subclass, not part of v1.

## Configuration

No API key is stored for browser platforms; the session file is the credential.
`crier doctor` reports a browser platform as healthy if its `state.json` exists,
and as needing `crier login` otherwise (doctor calls `list_articles`, which
returns `[]`; doctor logic gets a small branch: for `BrowserPlatform`
subclasses, health is "session file present").

## Error handling

- Missing `[browser]` extra: failure result with `pip install 'crier[browser]'`
  and `playwright install chromium` hints.
- Missing session: failure result with the `crier login <name>` hint.
- Selector-not-found / navigation timeout: best-effort screenshot to
  `last-error.png`, failure result carrying the exception text.
- The browser context and browser are always closed in `finally`, including on
  exceptions, so a failed publish never leaks a process.

## Testing

- `tests/test_browser.py`: unit tests with the Playwright launch chain mocked
  (patch `sync_playwright` to yield a fake browser/context/page). Assert:
  - missing-extra path returns a failure with the install hint;
  - missing-session path returns a failure with the login hint;
  - happy path opens a context with `storage_state` set to the session file,
    calls `_post`, and returns its URL in the `PublishResult`;
  - the browser is closed on success AND when `_post` raises;
  - a raising `_post` produces a failure result (no exception escapes).
  A tiny in-test `_DummyBrowser(BrowserPlatform)` subclass exercises the base
  without a real site.
- `tests/test_substack.py`: unit-test `Substack._compose` (rewrite vs metadata,
  canonical appended) and class attributes. `_post` is DOM-dependent, so it is
  validated manually, not unit-tested against a live site.
- Discovery test: `_browser.py` excluded (underscore), `substack` registered;
  built-in count 15 -> 16; add `substack` to the expected-names set.
- `crier login` CLI test: mock Playwright; assert it errors for a non-browser
  platform and writes the session file for a browser platform.
- Full suite stays green; `ruff` clean.

## Scope

In scope (v1):
- `BrowserPlatform` base in `_browser.py`.
- `Substack` (Notes) subclass.
- `crier login <platform>` command.
- `[browser]` optional extra.
- Tests and docs (README API-key section note, CLAUDE.md platform list +
  "Adding a Browser-Automation Platform" subsection).

Not in scope (follow-ups the base supports later):
- Shared-session reuse across a run (Approach B).
- Long-form Substack Posts.
- Hacker News, Lobsters, and upgrading Twitter off copy-paste.
- `delete` / `list_articles` / `get_stats` for browser platforms.
- A headless toggle or a `--headed` publish mode for debugging.

## Open questions

None. Notes-first and Approach A (per-publish launch) are decided.
