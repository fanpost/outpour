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
