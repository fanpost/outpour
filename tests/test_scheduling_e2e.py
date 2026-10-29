"""Scheduling end-to-end test (Outpour queue item 7).

A test article scheduled a few seconds out must NOT fire early, must
fire unattended via `schedule run` once due, must land in the ledger,
and a failed platform must be reported as failed (exit code 2 for a
partial failure) without losing the successful platform's record.
The short wait is deliberate: it exercises the real time comparison
(scheduled_time <= now) instead of only a pre-dated post.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from crier.cli import cli
from crier.platforms.base import PublishResult
from crier.scheduler import (
    create_scheduled_post,
    get_due_posts,
    get_scheduled_post,
)


def _md(tmp_path, name, canonical):
    md = tmp_path / name
    md.write_text(
        f"---\ntitle: Scheduled E2E\ncanonical_url: {canonical}\n---\nBody."
    )
    return md


def test_schedule_run_fires_after_due_time_and_reports_partial_failure(
    tmp_registry, monkeypatch
):
    monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-devto-key")
    monkeypatch.setenv("CRIER_HASHNODE_API_KEY", "test-hashnode-key")

    md = _md(tmp_registry, "sched.md", "https://example.com/sched-e2e")
    due_in = datetime.now(timezone.utc) + timedelta(seconds=5)
    good = create_scheduled_post(str(md), "devto", due_in)
    bad = create_scheduled_post(str(md), "hashnode", due_in)

    assert get_due_posts() == []  # not due yet: must not fire early

    time.sleep(6)  # wait out the schedule, unattended
    assert {p.id for p in get_due_posts()} == {good.id, bad.id}

    with (
        patch(
            "crier.platforms.devto.DevTo.publish",
            return_value=PublishResult(True, "devto", "dev-1", "https://dev.to/1"),
        ),
        patch(
            "crier.platforms.hashnode.Hashnode.publish",
            return_value=PublishResult(False, "hashnode", error="boom 500"),
        ),
    ):
        result = CliRunner().invoke(cli, ["schedule", "run", "--json"])

    assert result.exit_code == 2, result.output  # partial failure
    assert '"failed": 1' in result.output
    assert '"succeeded": 1' in result.output

    # Ledger: the success landed, the failure is recorded honestly.
    from crier.registry import get_failures, get_publication_id

    assert get_publication_id("https://example.com/sched-e2e", "devto") == "dev-1"
    assert get_publication_id("https://example.com/sched-e2e", "hashnode") is None
    assert any(f["platform"] == "hashnode" and f["error"] == "boom 500" for f in get_failures())

    # Schedule statuses reflect the outcome, and a second run is a no-op.
    assert get_scheduled_post(good.id).status == "published"
    assert get_scheduled_post(bad.id).status == "failed"
    rerun = CliRunner().invoke(cli, ["schedule", "run", "--json"])
    assert rerun.exit_code == 0
    assert '"processed": 0' in rerun.output


def test_future_post_is_not_fired(tmp_registry, monkeypatch):
    monkeypatch.setenv("CRIER_DEVTO_API_KEY", "test-devto-key")
    md = _md(tmp_registry, "future.md", "https://example.com/sched-future")
    post = create_scheduled_post(
        str(md), "devto", datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    result = CliRunner().invoke(cli, ["schedule", "run", "--json"])
    assert result.exit_code == 0
    assert '"processed": 0' in result.output
    assert get_scheduled_post(post.id).status == "pending"
