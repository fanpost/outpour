"""Verify the same payload and registry effects through public entry points."""

import json
from datetime import datetime, timedelta, timezone

import pytest
import yaml
from click.testing import CliRunner

from crier import registry
from crier.cli import cli


def invoke_entry(entry, md, *, rewrite=None, thread=False):
    """Drive real entry points; only the remote adapter is a test double."""
    runner = CliRunner()
    if entry == "mcp":
        from crier.mcp_server import crier_publish

        preview = crier_publish(str(md), "test_platform", rewrite_content=rewrite)
        result = crier_publish(
            str(md), "test_platform", confirmation_token=preview["confirmation_token"]
        )
        assert result.get("success"), result
    elif entry == "campaign":
        from crier.campaign import run_campaign, save_manifest

        save_manifest(
            "parity",
            {
                "posts": [
                    {
                        "canonical_url": "https://site/parity",
                        "title": "Parity",
                        "file": str(md),
                        "targets": {"test_platform": {"status": "pending", "rewrite": rewrite}},
                    }
                ]
            },
        )
        result = run_campaign("parity", apply=True)
        assert result.published == 1, result
    elif entry == "schedule":
        from crier.scheduler import create_scheduled_post

        create_scheduled_post(
            str(md),
            "test_platform",
            datetime.now(timezone.utc) - timedelta(minutes=1),
            rewrite=rewrite,
            thread=thread,
        )
        result = runner.invoke(cli, ["schedule", "run", "--json"])
        assert result.exit_code == 0, result.output
    elif entry == "retry":
        registry.record_failure(
            "https://site/parity", "test_platform", "old error", title="Parity", source_file=str(md)
        )
        result = runner.invoke(cli, ["audit", "--retry", "--json"])
        assert result.exit_code == 0, result.output
    elif entry == "audit":
        result = runner.invoke(
            cli, ["audit", str(md.parent), "--to", "test_platform", "--publish", "--batch"]
        )
        assert result.exit_code == 0, result.output
    else:
        args = ["publish", str(md), "--to", "test_platform", "--batch", "--no-check"]
        if rewrite:
            args += ["--rewrite", rewrite]
        if thread:
            args += ["--thread"]
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output


@pytest.fixture
def parity_source(recording_platform, tmp_path):
    from crier.config import get_config_path

    config_file = get_config_path()
    config = yaml.safe_load(config_file.read_text())
    config.update(rewrite_author="Alex", content_paths=["posts"])
    config_file.write_text(yaml.safe_dump(config))
    posts = tmp_path / "posts"
    posts.mkdir()
    md = posts / "parity.md"
    md.write_text(
        "---\ntitle: Parity\ncanonical_url: https://site/parity\ntags: [one, two]\n---\nBody."
    )
    return md


@pytest.mark.parametrize("entry", ["cli", "mcp", "campaign", "audit", "retry", "schedule"])
def test_public_entry_points_share_payload_and_record_once(
    entry, parity_source, recording_platform, monkeypatch
):
    calls = []
    original = registry.record_publication

    def record(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(registry, "record_publication", record)
    invoke_entry(entry, parity_source)
    article = recording_platform.articles[0]
    assert (article.title, article.body, article.tags, article.published) == (
        "Parity",
        "Body.",
        ["one", "two"],
        True,
    )
    row = registry.get_connection().execute("SELECT * FROM publications").fetchone()
    assert row["platform_id"] == "remote-1"
    assert row["rewritten"] == 0
    assert row["rewrite_author"] is None
    assert row["last_error"] is None
    assert len(calls) == len(recording_platform.articles) == 1


@pytest.mark.parametrize("entry", ["cli", "mcp", "campaign", "schedule"])
def test_explicit_rewrite_parity(entry, parity_source, recording_platform):
    invoke_entry(entry, parity_source, rewrite="Rewritten body.")
    assert recording_platform.articles[0].body == "Rewritten body."
    assert recording_platform.articles[0].is_rewrite
    row = registry.get_connection().execute("SELECT * FROM publications").fetchone()
    assert row["posted_content"] == "Rewritten body."
    assert row["rewrite_author"] == "Alex"
    assert row["rewritten"] == 1


@pytest.mark.parametrize("entry", ["cli", "schedule"])
def test_thread_metadata_parity(entry, parity_source, recording_platform):
    parity_source.write_text(parity_source.read_text() + " Long sentence." * 40)
    invoke_entry(entry, parity_source, thread=True)
    assert len(recording_platform.threads) == 1
    row = registry.get_connection().execute("SELECT * FROM publications").fetchone()
    assert row["is_thread"] == 1
    assert json.loads(row["thread_ids"]) == ["thread-1", "thread-2"]
    assert json.loads(row["thread_urls"]) == ["https://remote/t1", "https://remote/t2"]


def test_publish_one_compatibility_does_not_record(parity_source, recording_platform):
    from crier.publishing import publish_one

    result = publish_one(parity_source, "test_platform")
    assert result.remote_success
    assert len(recording_platform.articles) == 1
    assert registry.get_all_articles() == {}


def test_multiple_platforms_do_not_share_rewritten_articles(
    parity_source, recording_platform, monkeypatch
):
    from unittest.mock import MagicMock

    from crier.llm.provider import RewriteResult
    from crier.platforms import PLATFORMS

    class LongPlatform(recording_platform):
        name = "long_platform"
        max_content_length = 10000

    monkeypatch.setitem(PLATFORMS, LongPlatform.name, LongPlatform)
    monkeypatch.setenv("CRIER_LONG_PLATFORM_API_KEY", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    provider = MagicMock()
    provider.model = "unit"
    provider.rewrite.return_value = RewriteResult("Short body.", "unit")
    monkeypatch.setattr("crier.llm.get_provider", lambda *a, **kw: provider)
    original = "Original body. " * 40
    parity_source.write_text(parity_source.read_text().replace("Body.", original))
    result = CliRunner().invoke(
        cli,
        [
            "publish",
            str(parity_source),
            "--to",
            "test_platform",
            "--to",
            "long_platform",
            "--auto-rewrite",
            "--batch",
            "--no-check",
        ],
    )
    assert result.exit_code == 0, result.output
    assert [a.body for a in recording_platform.articles] == ["Short body.", original.strip()]
    assert all(a.tags == ["one", "two"] for a in recording_platform.articles)
    assert provider.rewrite.call_count == 1
    rows = {
        row["platform"]: dict(row)
        for row in registry.get_connection().execute("SELECT * FROM publications")
    }
    assert rows["test_platform"]["rewritten"] == 1
    assert rows["long_platform"]["rewritten"] == 0
    assert rows["long_platform"]["rewrite_author"] is None


@pytest.mark.parametrize("entry", ["cli", "mcp", "audit", "retry", "schedule"])
def test_recording_errors_report_remote_identity(
    entry, parity_source, recording_platform, monkeypatch
):
    def unavailable(**kwargs):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(registry, "record_publication", unavailable)
    runner = CliRunner()
    if entry == "mcp":
        from crier.mcp_server import crier_publish

        token = crier_publish(str(parity_source), "test_platform")["confirmation_token"]
        data = crier_publish(str(parity_source), "test_platform", confirmation_token=token)
    elif entry == "schedule":
        from crier.scheduler import create_scheduled_post

        create_scheduled_post(
            str(parity_source), "test_platform", datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        data = json.loads(runner.invoke(cli, ["schedule", "run", "--json"]).output)["results"][0]
    elif entry == "retry":
        registry.record_failure(
            "https://site/parity",
            "test_platform",
            "old error",
            title="Parity",
            source_file=str(parity_source),
        )
        data = json.loads(runner.invoke(cli, ["audit", "--retry", "--json"]).output)["results"][0]
    elif entry == "audit":
        data = json.loads(
            runner.invoke(
                cli,
                [
                    "audit",
                    str(parity_source.parent),
                    "--to",
                    "test_platform",
                    "--publish",
                    "--batch",
                ],
            ).output
        )["results"][0]
    else:
        data = json.loads(
            runner.invoke(
                cli,
                ["publish", str(parity_source), "--to", "test_platform", "--batch", "--no-check"],
            ).output
        )["results"][0]
    assert data.get("success") is not True
    assert data["remote_published"] is True
    assert data["article_id"] == "remote-1"
    assert data["url"] == "https://remote/1"
    assert "registry unavailable" in data["error"]
    assert len(recording_platform.articles) == 1


def test_audit_no_pending_cells_still_returns_json(parity_source, recording_platform):
    invoke_entry("audit", parity_source)
    result = CliRunner().invoke(
        cli, ["audit", str(parity_source.parent), "--to", "test_platform", "--publish", "--batch"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["results"] == []
    assert data["summary"]["failed"] == 0
    assert len(recording_platform.articles) == 1
