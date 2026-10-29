"""Idempotency and ledger tests (Outpour queue item 6).

Re-running publish_and_record for the same article/platform must
update instead of duplicating, must record per-platform status and
URL/event id for every run, and must report partial failures honestly
without discarding the prior successful record.
"""

from __future__ import annotations

import pytest

from crier.platforms import PLATFORMS
from crier.platforms.base import Platform, PublishResult
from crier.publishing import PublishRequest, publish_and_record


class CountingPlatform(Platform):
    """Fake remote: publish creates, update replaces, both counted."""

    name = "idem_platform"
    publishes: list = []
    updates: list = []
    update_result = None  # None = success; PublishResult = forced outcome

    def publish(self, article):
        self.publishes.append(article.title)
        return PublishResult(True, self.name, "remote-1", "https://remote/1")

    def update(self, article_id, article):
        self.updates.append((article_id, article.title))
        if self.update_result is not None:
            return self.update_result
        return PublishResult(True, self.name, "remote-1", "https://remote/1-updated")

    def list_articles(self, limit=10):
        return []

    def get_article(self, article_id):
        return None


@pytest.fixture
def idem_platform(tmp_registry, monkeypatch):
    CountingPlatform.publishes = []
    CountingPlatform.updates = []
    CountingPlatform.update_result = None
    monkeypatch.setitem(PLATFORMS, CountingPlatform.name, CountingPlatform)
    monkeypatch.setenv("CRIER_IDEM_PLATFORM_API_KEY", "test-secret")
    return CountingPlatform


def _md(tmp_path, title="Idem Post"):
    md = tmp_path / "post.md"
    md.write_text(
        f"---\ntitle: {title}\ncanonical_url: https://example.com/idem-post\n---\nBody v1."
    )
    return md


def test_first_publish_creates_and_records(idem_platform, tmp_path):
    from crier.registry import get_publication_id, get_publication_info

    md = _md(tmp_path)
    outcome = publish_and_record(PublishRequest(md, "idem_platform"))
    assert outcome.state.value == "recorded"
    assert idem_platform.publishes == ["Idem Post"]
    assert idem_platform.updates == []
    assert get_publication_id("https://example.com/idem-post", "idem_platform") == "remote-1"
    info = get_publication_info("https://example.com/idem-post", "idem_platform")
    assert info["url"] == "https://remote/1"


def test_republish_updates_instead_of_duplicating(idem_platform, tmp_path):
    from crier.registry import get_publication_info

    md = _md(tmp_path)
    publish_and_record(PublishRequest(md, "idem_platform"))
    md.write_text(
        "---\ntitle: Idem Post\ncanonical_url: https://example.com/idem-post\n---\nBody v2."
    )
    outcome = publish_and_record(PublishRequest(md, "idem_platform"))
    assert outcome.state.value == "recorded"
    assert len(idem_platform.publishes) == 1  # no second create
    assert idem_platform.updates == [("remote-1", "Idem Post")]
    info = get_publication_info("https://example.com/idem-post", "idem_platform")
    assert info["url"] == "https://remote/1-updated"  # ledger follows the update
    assert info["article_id"] == "remote-1"


def test_failed_update_is_reported_and_prior_record_survives(idem_platform, tmp_path):
    from crier.registry import get_failures, get_publication_info

    md = _md(tmp_path)
    publish_and_record(PublishRequest(md, "idem_platform"))
    idem_platform.update_result = PublishResult(
        False, "idem_platform", error="Platform does not support updating posts"
    )
    outcome = publish_and_record(PublishRequest(md, "idem_platform"))
    assert outcome.state.value == "failure_recorded"
    assert "does not support updating" in (outcome.result.error or "")
    assert len(idem_platform.publishes) == 1  # never fell back to a duplicate create
    info = get_publication_info("https://example.com/idem-post", "idem_platform")
    assert info["article_id"] == "remote-1"  # prior success is NOT wiped
    assert info["url"] == "https://remote/1"
    failures = get_failures()
    assert any(
        f["platform"] == "idem_platform" and "does not support updating" in f["error"]
        for f in failures
    )


def test_failed_first_publish_records_failure_not_success(idem_platform, tmp_path, monkeypatch):
    from crier.registry import get_failures, get_publication_id

    monkeypatch.setattr(
        CountingPlatform, "publish",
        lambda self, article: PublishResult(False, self.name, error="boom 500"),
    )
    md = _md(tmp_path)
    outcome = publish_and_record(PublishRequest(md, "idem_platform"))
    assert outcome.state.value == "failure_recorded"
    assert get_publication_id("https://example.com/idem-post", "idem_platform") is None
    assert any(f["error"] == "boom 500" for f in get_failures())
