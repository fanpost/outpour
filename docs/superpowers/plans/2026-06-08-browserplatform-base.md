# BrowserPlatform Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable `BrowserPlatform` base that publishes by driving a real browser (Playwright), plus a first Substack Notes subclass that validates it.

**Architecture:** A `platforms/_browser.py` base (leading underscore keeps it out of auto-discovery, like `_fediverse.py`) owns the full Playwright lifecycle synchronously: launch headless Chromium with a stored `storage_state`, call a subclass `_post` hook, scrape the URL, always close. Sessions are captured by a new headed `crier login <platform>` command and stored at `~/.config/crier/browser/<name>/state.json`. Concrete subclasses (Substack first) set class attributes and implement `_post`.

**Tech Stack:** Python, Playwright (sync API) as an optional `[browser]` extra, Click CLI, pytest with the Playwright chain mocked.

## Global Constraints

- Playwright is an OPTIONAL extra: `browser = ["playwright>=1.40"]`. The import MUST be deferred to publish/login time so the module stays importable and discoverable without the extra (same pattern as `nostr.py`).
- The base file is `src/crier/platforms/_browser.py`; the leading underscore excludes it from `_discover_package_platforms()`. Only concrete subclasses register.
- Every platform method returns a result object and never raises out of `publish`/`update`/`delete` (same contract as all platforms in `base.py`).
- Tests MUST NOT launch a real browser. Mock the Playwright launch chain.
- Soul hook on file writes: no em-dash characters, no the-word-spelled-l-e-v-e-r-a-g-e, no emoji in markdown headers. Use commas/colons/periods.
- Session/credential is the `state.json` file, not an api_key. Browser platforms are constructed as `cls("")` (empty api_key).
- `ruff check src/ tests/` stays clean; full `pytest` stays green.

---

### Task 1: BrowserPlatform base + [browser] extra

**Files:**
- Create: `src/crier/platforms/_browser.py`
- Modify: `pyproject.toml` (add the `[browser]` optional extra)
- Test: `tests/test_browser.py`

**Interfaces:**
- Consumes: `crier.platforms.base.Platform`, `Article`, `PublishResult`, `DeleteResult`; `crier.config.DEFAULT_CONFIG_DIR` (a `pathlib.Path` = `~/.config/crier`).
- Produces:
  - `BrowserPlatform(Platform)` with class attrs `supports_delete = False`, `supports_stats = False`, `headless = True`, `login_url: str | None = None`.
  - `BrowserPlatform._session_path(self) -> pathlib.Path` returning `DEFAULT_CONFIG_DIR / "browser" / self.name / "state.json"`.
  - `BrowserPlatform._import_sync_playwright(self)` returning the `sync_playwright` callable or raising `ImportError` with the install hint.
  - `BrowserPlatform._compose(self, article) -> str`.
  - `BrowserPlatform.publish(self, article) -> PublishResult` (full lifecycle).
  - Abstract-by-convention hook `BrowserPlatform._post(self, page, article, text) -> str` (returns posted URL; raises `NotImplementedError` in the base).
  - `BROWSER_IMPORT_HINT: str` module constant.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_browser.py`:

```python
"""Tests for the BrowserPlatform base (Playwright chain mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from crier.platforms._browser import BROWSER_IMPORT_HINT, BrowserPlatform
from crier.platforms.base import Article


class _DummyBrowser(BrowserPlatform):
    name = "dummy"
    login_url = "https://example.com/login"

    def _post(self, page, article, text):
        page.goto("https://example.com/compose")
        page.fill("#editor", text)
        page.click("#submit")
        return "https://example.com/post/1"


def _fake_playwright():
    """Return (sync_playwright_callable, pw, browser, context, page) MagicMocks."""
    page = MagicMock(name="page")
    context = MagicMock(name="context")
    context.new_page.return_value = page
    context.pages = [page]
    browser = MagicMock(name="browser")
    browser.new_context.return_value = context
    pw = MagicMock(name="pw")
    pw.chromium.launch.return_value = browser
    starter = MagicMock(name="starter")
    starter.start.return_value = pw
    sync_playwright = MagicMock(name="sync_playwright", return_value=starter)
    return sync_playwright, pw, browser, context, page


def _article(**kw):
    base = dict(title="T", body="hello", canonical_url="https://x/p/")
    base.update(kw)
    return Article(**base)


def _with_session(platform, tmp_path, monkeypatch):
    """Point the platform's session path at an existing temp state file."""
    session = tmp_path / "state.json"
    session.write_text("{}")
    monkeypatch.setattr(platform, "_session_path", lambda: session)
    return session


def test_missing_session_returns_failure(tmp_path, monkeypatch):
    p = _DummyBrowser("")
    monkeypatch.setattr(p, "_session_path", lambda: tmp_path / "absent.json")
    res = p.publish(_article(body="x", is_rewrite=True))
    assert res.success is False
    assert "crier login dummy" in res.error


def test_missing_extra_returns_failure(tmp_path, monkeypatch):
    p = _DummyBrowser("")
    _with_session(p, tmp_path, monkeypatch)

    def boom():
        raise ImportError(BROWSER_IMPORT_HINT)

    monkeypatch.setattr(p, "_import_sync_playwright", boom)
    res = p.publish(_article(body="x", is_rewrite=True))
    assert res.success is False
    assert "browser" in res.error.lower()


def test_publish_happy_path_uses_storage_state_and_returns_url(tmp_path, monkeypatch):
    p = _DummyBrowser("")
    session = _with_session(p, tmp_path, monkeypatch)
    sync_playwright, pw, browser, context, page = _fake_playwright()
    monkeypatch.setattr(p, "_import_sync_playwright", lambda: sync_playwright)

    res = p.publish(_article(body="my note", is_rewrite=True))

    assert res.success is True
    assert res.url == "https://example.com/post/1"
    # context opened with the stored session
    browser.new_context.assert_called_once_with(storage_state=str(session))
    # launched headless
    pw.chromium.launch.assert_called_once_with(headless=True)
    # text was the rewrite with canonical appended
    page.fill.assert_called_once()
    filled_text = page.fill.call_args.args[1]
    assert "my note" in filled_text and "https://x/p/" in filled_text
    # everything closed
    context.close.assert_called_once()
    browser.close.assert_called_once()
    pw.stop.assert_called_once()


def test_publish_closes_browser_when_post_raises(tmp_path, monkeypatch):
    class _Boom(_DummyBrowser):
        def _post(self, page, article, text):
            raise RuntimeError("selector not found")

    p = _Boom("")
    _with_session(p, tmp_path, monkeypatch)
    sync_playwright, pw, browser, context, page = _fake_playwright()
    monkeypatch.setattr(p, "_import_sync_playwright", lambda: sync_playwright)

    res = p.publish(_article(body="x", is_rewrite=True))

    assert res.success is False
    assert "selector not found" in res.error
    # closed despite the exception
    context.close.assert_called_once()
    browser.close.assert_called_once()
    pw.stop.assert_called_once()
    # best-effort error screenshot attempted on the open page
    page.screenshot.assert_called_once()


def test_base_post_not_implemented():
    class _Bare(BrowserPlatform):
        name = "bare"

    with pytest.raises(NotImplementedError):
        _Bare("")._post(MagicMock(), _article(), "t")


def test_update_list_get_defaults():
    p = _DummyBrowser("")
    assert p.update("id", _article()).success is False
    assert p.list_articles() == []
    assert p.get_article("x") is None
    assert p.supports_delete is False
    assert p.supports_stats is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_browser.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'crier.platforms._browser'`.

- [ ] **Step 3: Implement the base**

Create `src/crier/platforms/_browser.py`:

```python
"""Base class for platforms published by driving a real browser (Playwright).

A note is posted by launching headless Chromium with a previously captured
session (cookies in storage_state), navigating the site's own editor, filling
it, and submitting. Playwright is an optional [browser] extra; the import is
deferred to publish/login time so this module stays importable and discoverable
without it (the leading underscore in the filename also keeps the base out of
platform auto-discovery, the same trick used by _fediverse.py).

Subclasses set class attributes (name, description, login_url, is_short_form,
max_content_length) and implement _post(page, article, text) -> posted_url.
Sessions are captured by the `crier login <platform>` command.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import DEFAULT_CONFIG_DIR
from .base import Article, DeleteResult, Platform, PublishResult

BROWSER_IMPORT_HINT = (
    "Browser platforms need the 'browser' extra: "
    "pip install 'crier[browser]' && playwright install chromium"
)


class BrowserPlatform(Platform):
    """Publish by driving a real browser session.

    Construct with an empty api_key (`cls("")`); the credential is the captured
    session file at ~/.config/crier/browser/<name>/state.json, written by
    `crier login <name>`.
    """

    name = "browser"
    description = "Browser-automation platform"
    login_url: str | None = None
    headless: bool = True
    supports_delete = False
    supports_stats = False

    def _session_path(self) -> Path:
        """Location of this platform's captured Playwright storage_state."""
        return DEFAULT_CONFIG_DIR / "browser" / self.name / "state.json"

    def _import_sync_playwright(self):
        """Return Playwright's sync_playwright callable (lazy; raises if absent)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover
            raise ImportError(BROWSER_IMPORT_HINT) from e
        return sync_playwright

    def _compose(self, article: Article) -> str:
        """Build the post text. Rewrites get the canonical URL appended."""
        if article.is_rewrite:
            return self._append_canonical_url(article.body, article)
        parts = [p for p in (article.title, article.body) if p]
        return "\n\n".join(parts)

    def _post(self, page, article: Article, text: str) -> str:
        """Drive the site editor and return the posted URL. Override in subclasses."""
        raise NotImplementedError(f"{self.name}._post() not implemented")

    def _save_error_screenshot(self, context) -> None:
        """Best-effort screenshot of the open page for debugging a failed post."""
        try:
            path = self._session_path().parent / "last-error.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            pages = getattr(context, "pages", None) or []
            if pages:
                pages[0].screenshot(path=str(path))
        except Exception:
            pass

    def publish(self, article: Article) -> PublishResult:
        session = self._session_path()
        if not session.exists():
            return PublishResult(
                success=False,
                platform=self.name,
                error=f"No browser session for {self.name}; run: crier login {self.name}",
            )
        try:
            sync_playwright = self._import_sync_playwright()
        except ImportError as e:
            return PublishResult(success=False, platform=self.name, error=str(e))

        text = self._compose(article)
        if error := self._check_content_length(text):
            return PublishResult(success=False, platform=self.name, error=error)

        pw = browser = context = None
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(storage_state=str(session))
            page = context.new_page()
            url = self._post(page, article, text)
            return PublishResult(success=True, platform=self.name, url=url)
        except Exception as e:
            if context is not None:
                self._save_error_screenshot(context)
            return PublishResult(success=False, platform=self.name, error=str(e))
        finally:
            for closer in (
                getattr(context, "close", None),
                getattr(browser, "close", None),
                getattr(pw, "stop", None),
            ):
                if closer is not None:
                    try:
                        closer()
                    except Exception:
                        pass

    def update(self, article_id: str, article: Article) -> PublishResult:
        return PublishResult(
            success=False,
            platform=self.name,
            error=f"{self.name}: update is not supported for browser platforms",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        return None

    def delete(self, article_id: str) -> DeleteResult:
        return DeleteResult(
            success=False,
            platform=self.name,
            error=f"{self.name} does not support deletion",
        )
```

- [ ] **Step 4: Add the `[browser]` extra to pyproject.toml**

In `pyproject.toml`, under `[project.optional-dependencies]`, add (next to the existing `nostr` extra):

```toml
browser = [
    "playwright>=1.40",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_browser.py -q`
Expected: PASS (8 tests).

- [ ] **Step 6: Lint**

Run: `ruff check src/crier/platforms/_browser.py tests/test_browser.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/crier/platforms/_browser.py tests/test_browser.py pyproject.toml
git commit -m "feat(platforms): BrowserPlatform base (Playwright, session-driven publish)"
```

---

### Task 2: crier login command + doctor health branch

**Files:**
- Modify: `src/crier/cli.py` (add the `login` command; add a `BrowserPlatform` branch in `doctor`)
- Test: `tests/test_cli.py` (append login tests)

**Interfaces:**
- Consumes: `BrowserPlatform` and `_session_path` from Task 1; `get_platform`, `PLATFORMS` (already imported in `cli.py`); the module `console` object in `cli.py`.
- Produces: a Click command `login` registered on the `cli` group, invoked as `crier login <platform>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_login_rejects_unknown_platform():
    from click.testing import CliRunner

    from crier.cli import cli

    result = CliRunner().invoke(cli, ["login", "nope-not-real"])
    assert result.exit_code != 0
    assert "Unknown platform" in result.output


def test_login_rejects_non_browser_platform():
    from click.testing import CliRunner

    from crier.cli import cli

    # devto is a normal API platform, not a BrowserPlatform
    result = CliRunner().invoke(cli, ["login", "devto"])
    assert result.exit_code != 0
    assert "not a browser" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -k login -q`
Expected: FAIL (no `login` command; `Usage` error or wrong message).

- [ ] **Step 3: Implement the login command + doctor branch**

In `src/crier/cli.py`, add the command (place it near the `doctor` command). Use the existing module-level `console`, `PLATFORMS`, and `get_platform`:

```python
@cli.command()
@click.argument("platform")
def login(platform):
    """Capture a browser session for a browser-automation platform.

    Opens a real browser window so you can log in once; the session cookies are
    saved and reused for headless publishing. Needs: pip install 'crier[browser]'
    and 'playwright install chromium'.
    """
    from .platforms._browser import BrowserPlatform

    if platform not in PLATFORMS:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        raise SystemExit(1)

    platform_cls = get_platform(platform)
    if not issubclass(platform_cls, BrowserPlatform):
        console.print(f"[red]{platform} is not a browser-automation platform[/red]")
        raise SystemExit(1)

    instance = platform_cls("")
    try:
        sync_playwright = instance._import_sync_playwright()
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    session_path = instance._session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        if instance.login_url:
            page.goto(instance.login_url)
        click.echo(
            f"Log in to {platform} in the browser window, then press Enter here."
        )
        click.pause(info="")
        context.storage_state(path=str(session_path))
        browser.close()

    console.print(f"[green]Saved {platform} session to {session_path}[/green]")
```

Then update the `doctor` command so browser platforms report on their session file instead of calling `list_articles`. In `doctor`, inside the `for name in PLATFORMS:` loop, immediately after the line `api_key = get_api_key(name)` (around `cli.py:1630`), insert:

```python
        # Browser platforms have no api_key; health is "session captured"
        from .platforms._browser import BrowserPlatform
        platform_cls_early = get_platform(name)
        if issubclass(platform_cls_early, BrowserPlatform):
            instance = platform_cls_early("")
            if instance._session_path().exists():
                table.add_row(name, "[green]✓ Healthy[/green]", "Browser session captured")
                json_platforms.append({"name": name, "status": "healthy", "details": "Browser session captured"})
                healthy += 1
            else:
                table.add_row(name, "[yellow]○ No session[/yellow]", f"Run: crier login {name}")
                json_platforms.append({"name": name, "status": "not_configured", "details": f"Run: crier login {name}"})
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -k login -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the doctor test subset to confirm no regression**

Run: `python -m pytest tests/test_cli.py -k doctor -q`
Expected: PASS (existing doctor tests still green).

- [ ] **Step 6: Lint**

Run: `ruff check src/crier/cli.py`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/crier/cli.py tests/test_cli.py
git commit -m "feat(cli): crier login (browser session capture) + doctor browser branch"
```

---

### Task 3: Substack Notes subclass + discovery, docs

**Files:**
- Create: `src/crier/platforms/substack.py`
- Test: `tests/test_substack.py`
- Modify: `tests/test_plugin_discovery.py` (count 15 to 16; add `substack`)
- Modify: `CLAUDE.md` (platform count 15 to 16; add a browser-platform note)

**Interfaces:**
- Consumes: `BrowserPlatform` from Task 1.
- Produces: `Substack(BrowserPlatform)` registered under name `substack`, with `is_short_form = True`, `max_content_length = None`, `login_url = "https://substack.com/"`, and `_post` implementing the Notes choreography.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_substack.py`:

```python
"""Tests for the Substack (Notes) browser platform.

Only the composition and class attributes are unit-tested. _post drives the
live Substack DOM, so it is validated manually (crier login substack, then a
real publish), not against a mocked page here.
"""

from __future__ import annotations

from crier.platforms.base import Article
from crier.platforms.substack import Substack


def _article(**kw):
    base = dict(title="My Post", body="full body here",
                canonical_url="https://metafunctor.com/post/x/")
    base.update(kw)
    return Article(**base)


def test_properties():
    s = Substack("")
    assert s.name == "substack"
    assert s.is_short_form is True
    assert s.max_content_length is None
    assert s.supports_delete is False
    assert s.login_url == "https://substack.com/"


def test_compose_rewrite_appends_canonical():
    s = Substack("")
    text = s._compose(_article(body="short take", is_rewrite=True))
    assert "short take" in text
    assert "https://metafunctor.com/post/x/" in text


def test_compose_non_rewrite_uses_title_and_body():
    s = Substack("")
    text = s._compose(_article(is_rewrite=False))
    assert "My Post" in text
    assert "full body here" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_substack.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'crier.platforms.substack'`.

- [ ] **Step 3: Implement the Substack subclass**

Create `src/crier/platforms/substack.py`. The selectors below are the starting
point; confirm and adjust them during live validation (Step 7) by inspecting the
real Notes composer. Keep the structure (navigate, open composer, type, submit,
read URL):

```python
"""Substack Notes via browser automation.

Substack has no public write API, so notes are posted by driving the web
composer with a captured session (see `crier login substack`). Short-form by
convention; Substack imposes no small length cap on notes.

The DOM selectors in _post target the Notes composer at substack.com/notes.
They are confirmed during live validation; if Substack changes its markup,
update them here (a failed post saves a screenshot to
~/.config/crier/browser/substack/last-error.png).
"""

from __future__ import annotations

from .base import Article
from ._browser import BrowserPlatform


class Substack(BrowserPlatform):
    name = "substack"
    description = "Short notes on Substack (browser automation)"
    login_url = "https://substack.com/"
    is_short_form = True
    max_content_length = None

    def _post(self, page, article: Article, text: str) -> str:
        # Open the Notes composer.
        page.goto("https://substack.com/notes", wait_until="domcontentloaded")
        # The composer is a contenteditable; click it, then type.
        composer = page.get_by_role("textbox").first
        composer.click()
        composer.fill(text)
        # Submit the note.
        page.get_by_role("button", name="Post").first.click()
        # Give the post request time to settle, then return the current URL.
        page.wait_for_timeout(2000)
        return page.url
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_substack.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Update the discovery test**

In `tests/test_plugin_discovery.py`, in `test_discovers_all_builtins`, change the
count assertion and docstring from 15 to 16:

```python
        result = _discover_package_platforms()
        assert len(result) == 16
```

In `test_expected_platform_names`, add `"substack"` to the expected set:

```python
        expected = {
            "devto", "bluesky", "mastodon", "hashnode", "medium",
            "linkedin", "ghost", "buttondown", "telegram", "discord",
            "threads", "wordpress", "twitter", "pleroma", "nostr",
            "substack",
        }
```

- [ ] **Step 6: Update CLAUDE.md and README**

In `CLAUDE.md`, change `**Platform Categories** (15 total):` to `(16 total):`,
add `substack` to a new Browser line under the categories, and add a short note.
Apply this edit to the categories block:

```markdown
**Platform Categories** (16 total):
- Blog: devto, hashnode, medium, ghost, wordpress
- Newsletter: buttondown
- Social: bluesky, mastodon, pleroma, nostr, linkedin, threads, twitter (copy-paste mode)
- Announcement: telegram, discord
- Browser-automation: substack (Notes)
```

Then add this paragraph immediately after the existing Nostr paragraph:

```markdown
Substack (`platforms/substack.py`) posts Notes by driving the web composer with
Playwright, via the optional `[browser]` extra. It subclasses `BrowserPlatform`
(`platforms/_browser.py`), a leading-underscore base excluded from discovery
that owns the launch/post/scrape/close lifecycle. Sessions are captured once
with `crier login substack` (headed browser, cookies saved to
`~/.config/crier/browser/substack/state.json`) and reused headless. Browser
platforms have no api_key, do not support update/list/delete in v1, and a failed
post saves a screenshot to `~/.config/crier/browser/<name>/last-error.png`.
Adding another browser platform (Hacker News, Lobsters) is a thin subclass that
sets `login_url` and implements `_post(page, article, text) -> url`.
```

Also add a Substack row to the README platform table. In `README.md`, in the
`## Supported Platforms` table, add a row after the Twitter/X row:

```markdown
| **Substack** | none (browser session) | Notes via browser automation; run `crier login substack` |
```

And after the "Announcement Channels" note paragraph in `### Platform Notes`, add:

```markdown
**Browser-automation Platforms** (Substack):
- No API key. Run `crier login substack` once to capture a session.
- Posts Notes by driving the web composer headlessly.
```

- [ ] **Step 7: Live validation (manual, not a unit test)**

This step needs the `[browser]` extra and a Substack account. It is performed by
the human or with the Playwright MCP tools, not by a headless test:

```bash
pip install 'crier[browser]'
playwright install chromium
crier login substack          # log in by hand, press Enter
crier config set profiles.notes.platforms '[substack]'   # optional
# dry validation: confirm a real note posts and returns a URL
crier publish <a-recent-post>.md --to substack --rewrite "test note from crier"
```

If the composer selectors in `_post` do not match the live DOM, inspect the page
(Playwright MCP `browser_snapshot`), correct the selectors in
`src/crier/platforms/substack.py`, and re-run. Record the confirmed selectors in
the commit message.

- [ ] **Step 8: Run the full suite + lint**

Run: `python -m pytest -q`
Expected: PASS (existing total + 3 substack + browser tests; discovery green at 16).

Run: `ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 9: Commit**

```bash
git add src/crier/platforms/substack.py tests/test_substack.py \
        tests/test_plugin_discovery.py CLAUDE.md
git commit -m "feat(platforms): add Substack Notes (browser automation)"
```

---

## Notes for the implementer

- The Substack `_post` selectors are a best-effort starting point. The base saves
  a screenshot on failure to make selector debugging fast. Treat live validation
  (Task 3, Step 7) as the real acceptance test for `_post`; the unit tests only
  cover composition and attributes.
- Do not make the base or subclass import Playwright at module top level. The
  lazy import is what keeps discovery and the rest of the test suite working
  without the extra installed.
- `crier login` is interactive by design (it waits on stdin). Its happy path is
  not unit-tested; the tests cover the guard rails (unknown platform, non-browser
  platform).
