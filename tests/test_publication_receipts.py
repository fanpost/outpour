"""Recovery receipts must retain remote evidence without scheduling a new write."""

from datetime import datetime, timedelta, timezone

import pytest

from crier.platforms.base import Article, PublishResult, ThreadPublishResult
from crier.publication_receipts import PublicationReceipt, load_receipt, save_receipt


@pytest.mark.parametrize("thread", [False, True])
def test_receipt_roundtrip_retains_typed_remote_result(tmp_registry, thread):
    source = tmp_registry / "post.md"
    result = (
        ThreadPublishResult(True, "devto", root_id="a", post_ids=["a", "b"])
        if thread
        else PublishResult(True, "devto", article_id="a")
    )
    receipt = PublicationReceipt(
        str(source),
        "devto",
        datetime.now(timezone.utc).isoformat(),
        Article("Title", "Body", tags=["one"]),
        result,
        rewritten=True,
        posted_content="Adapted",
        rewrite_author="Alex",
    )
    save_receipt(receipt)
    loaded = load_receipt(source, "devto")
    assert loaded == receipt
    assert loaded.covers_failure(None)
    assert not loaded.covers_failure(
        (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    )
    assert load_receipt(source, "other") is None


def test_failed_atomic_replacement_keeps_previous_receipt(tmp_registry, monkeypatch):
    import crier.publication_receipts as receipts

    source = tmp_registry / "post.md"
    receipt = PublicationReceipt(
        str(source),
        "devto",
        datetime.now(timezone.utc).isoformat(),
        Article("Original", "Body"),
        PublishResult(True, "devto", "a"),
    )
    save_receipt(receipt)

    def broken(*args):
        raise OSError("write failed")

    monkeypatch.setattr(receipts.os, "replace", broken)
    receipt.article.title = "Changed"
    with pytest.raises(OSError, match="write failed"):
        save_receipt(receipt)
    assert load_receipt(source, "devto").article.title == "Original"
    assert not list(tmp_registry.glob(".*.recovery/.receipt-*"))


@pytest.mark.parametrize("text", ["{bad json", '"string"', "[]", "{}", '{"version": 2}'])
def test_unreadable_receipt_raises_typed_error(tmp_registry, text):
    from crier.publication_receipts import UnreadableReceipt, _path

    source = tmp_registry / "post.md"
    path = _path(source, "devto")
    path.parent.mkdir(parents=True)
    path.write_text(text)
    with pytest.raises(UnreadableReceipt):
        load_receipt(source, "devto")
