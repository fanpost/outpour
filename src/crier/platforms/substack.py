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

from ._browser import BrowserPlatform
from .base import Article


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
