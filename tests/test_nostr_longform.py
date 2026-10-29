"""Tests for the NIP-23 long-form Nostr platform (kind 30023).

Pure tag-mapping tests run without the [nostr] extra; signing tests
importorskip pynostr and exercise real BIP340 signatures with the
relay broadcast mocked out (no network).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from crier.platforms.base import Article
from crier.platforms.nostr import DEFAULT_RELAYS
from crier.platforms.nostr_longform import (
    NostrLongform,
    build_tags,
    derive_d_tag,
)


def _article(**kw):
    base = dict(
        title="Hello World",
        body="# Hello\n\nFull article body.",
        description="A short summary",
        tags=["ai", "tools"],
        canonical_url="https://example.com/posts/hello-world/",
        cover_image="https://example.com/cover.png",
    )
    base.update(kw)
    return Article(**base)


# --- d-tag derivation -----------------------------------------------------


def test_d_tag_from_canonical_url():
    assert derive_d_tag(_article()) == "hello-world"


def test_d_tag_from_title_when_no_canonical():
    assert derive_d_tag(_article(canonical_url=None)) == "hello-world"


def test_d_tag_fallback_never_empty():
    assert derive_d_tag(Article(title="", body="x")) == "article"


# --- tag mapping (pure) ---------------------------------------------------


def test_build_tags_full_mapping():
    tags = build_tags(_article(), published_at=1700000000)
    d = {t[0]: t[1] for t in tags if len(t) == 2}
    assert d["d"] == "hello-world"
    assert d["title"] == "Hello World"
    assert d["summary"] == "A short summary"
    assert d["published_at"] == "1700000000"
    assert d["image"] == "https://example.com/cover.png"
    assert [t[1] for t in tags if t[0] == "t"] == ["ai", "tools"]


def test_build_tags_omits_empty_optionals():
    tags = build_tags(
        Article(title="T", body="b", description=None, tags=None, cover_image=None),
        published_at=1700000000,
    )
    kinds = [t[0] for t in tags]
    assert kinds == ["d", "title", "published_at"]


# --- construction ---------------------------------------------------------


def test_properties_and_default_relays():
    n = NostrLongform("nsec1abc")
    assert n.name == "nostr-longform"
    assert n.is_short_form is False
    assert n.max_content_length is None
    assert n.relays == DEFAULT_RELAYS


def test_custom_relays_via_pipe():
    n = NostrLongform("nsec1abc|wss://relay.one,wss://relay.two")
    assert n.secret == "nsec1abc"
    assert n.relays == ["wss://relay.one", "wss://relay.two"]


def test_list_and_get_unsupported():
    n = NostrLongform("nsec1abc")
    assert n.list_articles() == []
    assert n.get_article("x") is None


# --- signing / publish (needs the [nostr] extra) --------------------------


def test_publish_signs_kind_30023_with_full_tags():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    captured = {}
    n = NostrLongform(PrivateKey().hex())
    with patch.object(
        NostrLongform, "_publish_event", lambda self, e: captured.update(event=e)
    ):
        res = n.publish(_article())
    assert res.success is True
    ev = captured["event"]
    assert ev.kind == 30023
    assert ev.verify() is True
    assert ev.content == "# Hello\n\nFull article body."
    tagdict = {t[0]: t[1] for t in ev.tags if len(t) == 2}
    assert tagdict["d"] == "hello-world"
    assert tagdict["title"] == "Hello World"
    assert tagdict["summary"] == "A short summary"
    assert tagdict["image"] == "https://example.com/cover.png"
    assert [t[1] for t in ev.tags if t[0] == "t"] == ["ai", "tools"]
    assert res.url.startswith("https://njump.me/")


def test_update_republishes_same_d_tag():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    seen = []
    n = NostrLongform(PrivateKey().hex())
    with patch.object(
        NostrLongform, "_publish_event", lambda self, e: seen.append(e)
    ):
        res = n.update("old-id", _article())
    assert res.success is True
    assert seen[0].kind == 30023
    assert ["d", "hello-world"] in seen[0].tags


def test_delete_builds_kind5_with_a_tag():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    captured = {}
    n = NostrLongform(PrivateKey().hex())
    with patch.object(
        NostrLongform, "_publish_event", lambda self, e: captured.update(event=e)
    ):
        res = n.delete("deadbeefpubkey:hello-world")
    assert res.success is True
    assert captured["event"].kind == 5
    assert ["a", "30023:deadbeefpubkey:hello-world"] in captured["event"].tags
