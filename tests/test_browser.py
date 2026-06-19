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
