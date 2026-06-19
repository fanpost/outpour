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
