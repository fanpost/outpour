"""Tests for Nostr relay OK acknowledgement (NIP-01).

Before this change, the Nostr platforms reported publish success
fire-and-forget: RelayManager.publish_event queues the event and
run_sync connects, but nobody ever checked whether any relay sent
an OK. A publish to unreachable relays still returned success.
broadcast_event now collects the OKs and publish() fails honestly
when no relay acknowledged the event.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from crier.platforms.base import Article
from crier.platforms.nostr import Nostr, broadcast_event
from crier.platforms.nostr_longform import NostrLongform


def _article(**kw):
    base = dict(title="T", body="hello world", canonical_url="https://x/p/")
    base.update(kw)
    return Article(**base)


class _FakePool:
    """Stands in for pynostr's MessagePool; get_all_ok drains like the real one."""

    def __init__(self, oks):
        self._oks = list(oks)

    def get_all_ok(self):
        oks, self._oks = self._oks, []
        return oks


class _FakeRelayManager:
    """Stands in for pynostr's RelayManager; records relays, never touches a socket."""

    def __init__(self, oks):
        self.added = []
        self.published = None
        self.closed = False
        self.message_pool = _FakePool(oks)

    def add_relay(self, url):
        self.added.append(url)

    def publish_event(self, event):
        self.published = event

    def run_sync(self):
        pass

    def close_all_relay_connections(self):
        self.closed = True


def _ok(event_id, ok, message, url):
    return SimpleNamespace(event_id=event_id, ok=ok, message=message, url=url)


def _run_broadcast(oks, relays):
    """Run broadcast_event with a fake RelayManager; returns (results, manager)."""
    mgr = _FakeRelayManager(oks)
    with patch("pynostr.relay_manager.RelayManager", lambda: mgr):
        results = broadcast_event(relays, SimpleNamespace(id="ev1"))
    return results, mgr


# --- broadcast_event -----------------------------------------------------


def test_broadcast_collects_accepted_rejected_and_silent():
    relays = ["wss://a", "wss://b", "wss://c"]
    oks = [
        _ok("ev1", True, "", "wss://a"),
        _ok("ev1", False, "duplicate:", "wss://b"),
    ]
    results, mgr = _run_broadcast(oks, relays)
    assert results == {
        "wss://a": "accepted",
        "wss://b": "rejected: duplicate:",
        "wss://c": "no acknowledgement",
    }
    assert mgr.added == relays
    assert mgr.published.id == "ev1"
    assert mgr.closed is True


def test_broadcast_string_true_counts_as_accepted():
    # pynostr types OKMessage.ok as str; a relay sending "true" must count.
    results, _ = _run_broadcast(
        [_ok("ev1", "true", "", "wss://a")], ["wss://a"]
    )
    assert results == {"wss://a": "accepted"}


def test_broadcast_string_false_is_not_accepted():
    # bool("false") is True in Python, so a naive truthiness check would lie.
    results, _ = _run_broadcast(
        [_ok("ev1", "false", "pow:", "wss://a")], ["wss://a"]
    )
    assert results == {"wss://a": "rejected: pow:"}


def test_broadcast_ignores_oks_for_other_events():
    results, _ = _run_broadcast(
        [_ok("other-event", True, "", "wss://a")], ["wss://a"]
    )
    assert results == {"wss://a": "no acknowledgement"}


# --- publish() honesty ---------------------------------------------------


def test_kind1_publish_fails_when_no_relay_acknowledges():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    n = Nostr(PrivateKey().hex())
    with patch.object(
        Nostr, "_publish_event",
        lambda self, e: {"wss://a": "no acknowledgement"},
    ):
        res = n.publish(_article(is_rewrite=True))
    assert res.success is False
    assert "No relay acknowledged" in res.error
    assert "wss://a: no acknowledgement" in res.error
    assert "duplicates" in res.error  # kind-1 caution: re-posting duplicates


def test_kind1_publish_succeeds_when_one_relay_accepts():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    n = Nostr(PrivateKey().hex())
    with patch.object(
        Nostr, "_publish_event",
        lambda self, e: {
            "wss://a": "accepted",
            "wss://b": "rejected: duplicate:",
            "wss://c": "no acknowledgement",
        },
    ):
        res = n.publish(_article(is_rewrite=True))
    assert res.success is True
    assert res.url.startswith("https://njump.me/note1")


def test_longform_publish_fails_when_no_relay_acknowledges():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    n = NostrLongform(PrivateKey().hex())
    with patch.object(
        NostrLongform, "_publish_event",
        lambda self, e: {"wss://a": "rejected: blocked:"},
    ):
        res = n.publish(_article())
    assert res.success is False
    assert "No relay acknowledged" in res.error
    assert "replaces the previous version" in res.error  # safe to re-publish


def test_longform_publish_succeeds_when_one_relay_accepts():
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    n = NostrLongform(PrivateKey().hex())
    with patch.object(
        NostrLongform, "_publish_event",
        lambda self, e: {"wss://a": "accepted"},
    ):
        res = n.publish(_article())
    assert res.success is True
