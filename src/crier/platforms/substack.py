"""Substack Notes via browser automation.

Substack has no public write API, so notes are posted by driving the web
composer with a captured session (see `crier login substack`). Short-form by
convention; Substack imposes no small length cap on notes.

The Notes composer lives on the home feed (substack.com/; /notes redirects
there). Posting is: click the "on your mind" opener button, type into the
TipTap/ProseMirror contenteditable, then click Post (which enables once the
note has text). Selectors confirmed by live inspection on 2026-06-19; if
Substack changes its markup, update them here (a failed post saves a screenshot
to ~/.config/crier/browser/substack/last-error.png).
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
        # The composer lives on the home feed; /notes redirects here.
        page.goto("https://substack.com/", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        # Open the composer via the "on your mind" prompt button.
        page.locator('button:has-text("on your mind")').first.click()
        page.wait_for_timeout(1500)
        # Type into the TipTap/ProseMirror contenteditable. insert_text keeps
        # newlines literal (no Enter key events that could submit early).
        editor = page.locator("div.tiptap.ProseMirror").first
        editor.click()
        page.keyboard.insert_text(text)
        page.wait_for_timeout(800)
        # The Post button enables once the note has text.
        post_btn = page.get_by_role("button", name="Post", exact=True).first
        if not post_btn.is_enabled():
            raise RuntimeError("Substack Post button never enabled (empty note?)")
        post_btn.click()
        # A successful post closes the composer (the Cancel button disappears).
        # If it stays open, the note did NOT post (e.g. Substack returns HTTP
        # 429 rate-limit on note creation); surface that as a failure rather
        # than a false success.
        try:
            page.wait_for_function(
                "() => ![...document.querySelectorAll('button')]"
                ".some(b => (b.innerText || '').trim() === 'Cancel')",
                timeout=12000,
            )
        except Exception as e:
            raise RuntimeError(
                "Substack note did not post: composer stayed open after Post "
                "(possible rate limit or markup change)"
            ) from e
        page.wait_for_timeout(1000)
        return page.url
