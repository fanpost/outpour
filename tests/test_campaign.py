"""Tests for the campaign module (plan generation + resumable run)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

import crier.campaign as camp
from crier.campaign import (
    build_plan,
    load_manifest,
    plan_campaign,
    run_campaign,
    save_manifest,
)


@dataclass
class _Article:
    title: str
    canonical_url: str | None


@pytest.fixture
def site(tmp_path, monkeypatch):
    """Point the campaigns dir at a temp site root."""
    monkeypatch.setattr(camp, "get_site_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _default_is_published(monkeypatch):
    """Default: registry reports nothing published. Tests override as needed.

    run_campaign now consults is_published at runtime (resume/dup-safety), so
    every test needs a deterministic answer rather than hitting the real DB.
    """
    monkeypatch.setattr(camp, "is_published", lambda canonical, platform: False)


# --- planning ---------------------------------------------------------------


def test_build_plan_skips_published(monkeypatch):
    monkeypatch.setattr(
        camp, "parse_markdown_file",
        lambda f: _Article("Foo", "https://x/foo/"),
    )
    # devto already published; hashnode not.
    monkeypatch.setattr(
        camp, "is_published",
        lambda url, p: p == "devto",
    )
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)

    manifest = build_plan("c", ["foo.md"], ["devto", "hashnode"])
    assert len(manifest["posts"]) == 1
    targets = manifest["posts"][0]["targets"]
    assert "devto" not in targets
    assert "hashnode" in targets
    assert targets["hashnode"] == {"status": "pending"}


def test_build_plan_short_form_gets_rewrite_field(monkeypatch):
    monkeypatch.setattr(
        camp, "parse_markdown_file",
        lambda f: _Article("Foo", "https://x/foo/"),
    )
    monkeypatch.setattr(camp, "is_published", lambda url, p: False)
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: p == "bluesky")

    manifest = build_plan("c", ["foo.md"], ["devto", "bluesky"])
    targets = manifest["posts"][0]["targets"]
    assert "rewrite" not in targets["devto"]
    assert targets["bluesky"]["rewrite"] == ""


def test_build_plan_skips_post_with_no_missing_targets(monkeypatch):
    monkeypatch.setattr(
        camp, "parse_markdown_file",
        lambda f: _Article("Foo", "https://x/foo/"),
    )
    monkeypatch.setattr(camp, "is_published", lambda url, p: True)  # all published
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    manifest = build_plan("c", ["foo.md"], ["devto", "hashnode"])
    assert manifest["posts"] == []


def test_build_plan_skips_missing_canonical(monkeypatch):
    monkeypatch.setattr(
        camp, "parse_markdown_file", lambda f: _Article("Foo", None)
    )
    monkeypatch.setattr(camp, "is_published", lambda url, p: False)
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    manifest = build_plan("c", ["foo.md"], ["devto"])
    assert manifest["posts"] == []


def test_plan_campaign_writes_loadable_manifest(site, monkeypatch):
    monkeypatch.setattr(camp, "find_content_files", lambda path: ["foo.md"])
    monkeypatch.setattr(
        camp, "parse_markdown_file",
        lambda f: _Article("Foo", "https://x/foo/"),
    )
    monkeypatch.setattr(camp, "is_published", lambda url, p: False)
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)

    plan_campaign("spring", platforms=["devto"])
    assert camp.campaign_path("spring").exists()
    loaded = load_manifest("spring")
    assert loaded["campaign"] == "spring"
    assert loaded["posts"][0]["canonical_url"] == "https://x/foo/"


# --- running ----------------------------------------------------------------


def _manifest(targets):
    return {
        "campaign": "c",
        "created": "2026-06-06T00:00:00Z",
        "platforms": list(targets.keys()),
        "posts": [
            {
                "canonical_url": "https://x/foo/",
                "file": "foo.md",
                "title": "Foo",
                "targets": targets,
            }
        ],
    }


def _outcome(success=True, article_id="1", url="https://dev/1", error=None,
             rewritten=False, posted_content=None):
    from crier.platforms.base import PublishResult
    from crier.publishing import PublishOutcome

    return PublishOutcome(
        result=PublishResult(success=success, platform="devto",
                             article_id=article_id, url=url, error=error),
        article=None, rewritten=rewritten, posted_content=posted_content,
    )


def test_run_missing_manifest_errors(site):
    summary = run_campaign("does-not-exist")
    assert summary.error is not None
    assert "not found" in summary.error


def test_run_dry_run_makes_no_publish_or_writes(site, monkeypatch):
    save_manifest("c", _manifest({"devto": {"status": "pending"}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    with monkeypatch.context() as m:
        pub = _spy_publish_one(m)
        summary = run_campaign("c", apply=False)
    assert summary.pending == 1
    assert summary.published == 0
    assert pub["calls"] == 0
    # manifest unchanged on disk: cell still pending
    assert load_manifest("c")["posts"][0]["targets"]["devto"]["status"] == "pending"


def test_run_apply_publishes_records_and_writes(site, recording_platform):
    from crier.registry import get_publication_id
    md = site / 'foo.md'
    md.write_text('---\ntitle: Foo\ncanonical_url: https://x/foo/\n---\nBody.')
    manifest = _manifest({'test_platform': {'status': 'pending'}})
    manifest['posts'][0]['file'] = str(md)
    save_manifest('c', manifest)
    summary = run_campaign('c', apply=True)
    assert summary.published == 1
    assert get_publication_id('https://x/foo/', 'test_platform') == 'remote-1'
    assert load_manifest('c')['posts'][0]['targets']['test_platform']['status'] == 'published'


def test_run_resumes_skipping_published(site, monkeypatch):
    save_manifest("c", _manifest({"devto": {"status": "published", "url": "u"}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    with monkeypatch.context() as m:
        pub = _spy_publish_one(m)
        summary = run_campaign("c", apply=True)
    assert summary.skipped == 1
    assert summary.published == 0
    assert pub["calls"] == 0


def test_run_skips_registry_published_cell(site, monkeypatch):
    """A cell pending in the manifest but already published per the registry is
    skipped (no republish), and its status is updated to published on apply.

    This is the resume / duplicate-safety guard: registry is the source of
    truth, so an interrupted run or an out-of-band publish never double-posts.
    """
    save_manifest("c", _manifest({"devto": {"status": "pending"}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    monkeypatch.setattr(camp, "is_published", lambda canonical, platform: True)
    with monkeypatch.context() as m:
        pub = _spy_publish_one(m)
        summary = run_campaign("c", apply=True)
    assert summary.skipped == 1
    assert summary.published == 0
    assert pub["calls"] == 0
    assert load_manifest("c")["posts"][0]["targets"]["devto"]["status"] == "published"


def test_run_short_form_empty_rewrite_needs_rewrite(site, monkeypatch):
    save_manifest("c", _manifest({"bluesky": {"status": "pending", "rewrite": ""}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: True)
    with monkeypatch.context() as m:
        pub = _spy_publish_one(m)
        summary = run_campaign("c", apply=True)
    assert summary.needs_rewrite == 1
    assert summary.published == 0
    assert pub["calls"] == 0


def test_run_short_form_with_rewrite_publishes(site, monkeypatch):
    save_manifest(
        "c", _manifest({"bluesky": {"status": "pending", "rewrite": "short take"}})
    )
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: True)
    monkeypatch.setattr("crier.registry.record_publication", lambda **kw: None)
    seen = {}

    def fake_publish_one(request, **kw):
        seen["rewrite_content"] = request.rewrite.content
        return _outcome()

    monkeypatch.setattr("crier.publishing.publish_and_record", fake_publish_one)
    summary = run_campaign("c", apply=True)
    assert summary.published == 1
    assert seen["rewrite_content"] == "short take"


def test_run_records_failure(site, recording_platform):
    from crier.registry import get_failures
    recording_platform.failure = 'boom'
    md = site / 'foo.md'
    md.write_text('---\ntitle: Foo\ncanonical_url: https://x/foo/\n---\nBody.')
    manifest = _manifest({'test_platform': {'status': 'pending'}})
    manifest['posts'][0]['file'] = str(md)
    save_manifest('c', manifest)
    summary = run_campaign('c', apply=True)
    assert summary.failed == 1
    assert get_failures()[0]['error'] == 'boom'
    assert load_manifest('c')['posts'][0]['targets']['test_platform']['status'] == 'failed'


def test_run_dry_run_needs_rewrite_not_persisted(site, monkeypatch):
    """A dry-run sets needs_rewrite in memory but must NOT persist it.

    run_campaign mutates the cell status to needs_rewrite before the apply
    gate; save_manifest only runs under apply, so the on-disk status must
    stay 'pending' after a dry-run.
    """
    save_manifest("c", _manifest({"bluesky": {"status": "pending", "rewrite": ""}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: True)
    summary = run_campaign("c", apply=False)
    assert summary.needs_rewrite == 1
    on_disk = load_manifest("c")["posts"][0]["targets"]["bluesky"]["status"]
    assert on_disk == "pending"


def test_run_failed_cell_is_retried(site, monkeypatch):
    """A cell left in 'failed' status is re-attempted on the next run."""
    save_manifest("c", _manifest({"devto": {"status": "failed", "error": "old"}}))
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    monkeypatch.setattr("crier.registry.record_publication", lambda **kw: None)
    calls = {"n": 0}

    def fake_publish_one(request, **kw):
        calls["n"] += 1
        return _outcome()

    monkeypatch.setattr("crier.publishing.publish_and_record", fake_publish_one)
    summary = run_campaign("c", apply=True)
    assert calls["n"] == 1
    assert summary.published == 1
    assert load_manifest("c")["posts"][0]["targets"]["devto"]["status"] == "published"


def test_run_multi_cell_mixed_outcomes(site, monkeypatch):
    """One manifest with published/pending/needs_rewrite cells: all counters."""
    save_manifest(
        "c",
        _manifest(
            {
                "devto": {"status": "published", "url": "u"},          # skipped
                "hashnode": {"status": "pending"},                     # publishes
                "bluesky": {"status": "pending", "rewrite": ""},       # needs_rewrite
            }
        ),
    )
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: p == "bluesky")
    monkeypatch.setattr("crier.registry.record_publication", lambda **kw: None)
    monkeypatch.setattr("crier.publishing.publish_and_record", lambda request, **kw: _outcome())

    summary = run_campaign("c", apply=True)
    assert summary.skipped == 1
    assert summary.published == 1
    assert summary.needs_rewrite == 1
    assert summary.failed == 0


def test_run_max_cells_caps_publishes(site, monkeypatch):
    """--max N publishes at most N cells and leaves the rest pending."""
    manifest = {
        "campaign": "c", "created": "x", "platforms": ["devto"],
        "posts": [
            {"canonical_url": f"https://x/p{i}/", "file": f"p{i}.md",
             "title": f"P{i}", "targets": {"devto": {"status": "pending"}}}
            for i in range(3)
        ],
    }
    save_manifest("c", manifest)
    monkeypatch.setattr(camp, "is_short_form_platform", lambda p: False)
    monkeypatch.setattr("crier.registry.record_publication", lambda **kw: None)
    calls = {"n": 0}

    def fake_publish_one(request, **kw):
        calls["n"] += 1
        return _outcome()

    monkeypatch.setattr("crier.publishing.publish_and_record", fake_publish_one)
    summary = run_campaign("c", apply=True, max_cells=2)
    assert summary.published == 2
    assert calls["n"] == 2
    # third cell left pending and persisted for the next run
    saved = load_manifest("c")
    statuses = [p["targets"]["devto"]["status"] for p in saved["posts"]]
    assert statuses.count("published") == 2
    assert statuses.count("pending") == 1


def _spy_publish_one(monkeypatch_ctx):
    """Install a publish_one spy that must never be called; returns a counter."""
    state = {"calls": 0}

    def spy(request, **kw):
        state["calls"] += 1
        return _outcome()

    monkeypatch_ctx.setattr("crier.publishing.publish_and_record", spy)
    return state


def test_campaign_recording_error_is_terminal(site, recording_platform, monkeypatch):
    md = site / 'real.md'
    md.write_text('---\ntitle: Real\ncanonical_url: https://site/real\n---\nBody.')
    manifest = _manifest({'test_platform': {'status': 'pending'}})
    manifest['posts'][0].update(file=str(md), canonical_url='https://site/real', title='Real')
    save_manifest('c', manifest)
    def broken(**kw):
        raise RuntimeError('registry unavailable')
    monkeypatch.setattr('crier.registry.record_publication', broken)
    first = run_campaign('c', apply=True)
    assert first.failed == 1
    assert load_manifest('c')['posts'][0]['targets']['test_platform']['status'] == 'published_unrecorded'
    run_campaign('c', apply=True)
    assert len(recording_platform.articles) == 1
