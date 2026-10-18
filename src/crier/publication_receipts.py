"""Durable receipts for remote writes whose registry recording failed.

These are recovery records, not pending work: consumers may retry the local
recording, but must not repeat the remote write represented by a receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import get_db_path
from .platforms.base import Article, PublishResult, ThreadPublishResult


class UnreadableReceipt(ValueError):
    """A receipt exists but cannot be trusted; callers must not repeat the remote write."""


@dataclass
class PublicationReceipt:
    source_file: str
    platform: str
    created_at: str
    article: Article
    result: PublishResult | ThreadPublishResult
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None

    def covers_failure(self, failed_at: str | None) -> bool:
        """An older receipt must not suppress a later, distinct failed attempt."""
        if failed_at is None:
            return True
        failure = datetime.fromisoformat(failed_at.replace("Z", "+00:00"))
        if failure.tzinfo is None:
            failure = failure.replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(self.created_at) >= failure


def _path(source_file: str | Path, platform: str) -> Path:
    identity = json.dumps([str(Path(source_file).expanduser().resolve()), platform])
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    database = get_db_path()
    return database.parent / f".{database.name}.recovery" / f"{key}.json"


def save_receipt(receipt: PublicationReceipt) -> None:
    """Atomically preserve the remote result without persisting credentials."""
    path = _path(receipt.source_file, receipt.platform)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = asdict(receipt)
    payload["version"] = 1
    payload["kind"] = "thread" if isinstance(receipt.result, ThreadPublishResult) else "single"
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".receipt-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_receipt(source_file: str | Path, platform: str) -> PublicationReceipt | None:
    """Load an exact source/platform receipt; corrupt receipts must block retry."""
    path = _path(source_file, platform)
    if not path.exists():
        return None
    try:
        receipt = _parse(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise UnreadableReceipt(str(exc)) from exc
    if (
        receipt.source_file != str(Path(source_file).expanduser().resolve())
        or receipt.platform != platform
        or receipt.result.success is not True
        or getattr(receipt.result, "requires_confirmation", False)
    ):
        raise UnreadableReceipt("Invalid publication recovery receipt identity or result")
    return receipt


def _parse(text: str) -> PublicationReceipt:
    payload = json.loads(text)
    if payload.pop("version") != 1:
        raise ValueError("Unsupported publication recovery receipt version")
    kind = payload.pop("kind")
    if kind not in ("single", "thread"):
        raise ValueError("Unknown publication recovery receipt kind")
    result_type = ThreadPublishResult if kind == "thread" else PublishResult
    payload["result"] = result_type(**payload["result"])
    payload["article"] = Article(**payload["article"])
    return PublicationReceipt(**payload)


def remove_receipt(source_file: str | Path, platform: str) -> None:
    _path(source_file, platform).unlink(missing_ok=True)
