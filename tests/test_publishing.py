from unittest.mock import MagicMock, patch

from crier.platforms.base import Article, PublishResult
from crier.publishing import PublishOutcome, prepare_publish, publish_one
from crier.rewrite import AutoRewriteResult


def _article(body_len=50):
    return Article(
        title="Hello World",
        body="A" * body_len,
        description="desc",
        tags=["python"],
        canonical_url="https://example.com/post/hello/",
    )


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_api_mode_no_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "devto")
    assert plan.error is None
    assert plan.mode == "api"
    assert plan.api_key == "real-key"
    assert plan.article.title == "Hello World"
    assert plan.rewritten is False
    assert plan.posted_content is None


@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_prepare_publish_rejects_non_api_mode(mode):
    plan = prepare_publish("post.md", "twitter")
    assert plan.error is not None
    assert "manual" in plan.error
    assert plan.article is None


@patch("crier.publishing.get_api_key", return_value=None)
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_missing_key(mode, key):
    plan = prepare_publish("post.md", "devto")
    assert plan.error is not None
    assert "No API key" in plan.error


@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_explicit_rewrite(mode, key, parse):
    parse.return_value = _article()
    plan = prepare_publish("post.md", "bluesky", rewrite_content="short take")
    assert plan.rewritten is True
    assert plan.posted_content == "short take"
    assert plan.article.body == "short take"
    assert plan.article.is_rewrite is True


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_success(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    inst.publish.return_value = PublishResult(
        success=True, platform="devto", article_id="123",
        url="https://dev.to/x/123",
    )
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto")
    assert outcome.result.success is True
    assert outcome.result.article_id == "123"
    assert outcome.article.title == "Hello World"
    assert outcome.rewritten is False


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_dry_run_does_not_call_publish(mode, key, parse, get_plat):
    parse.return_value = _article()
    inst = MagicMock()
    get_plat.return_value = lambda _key: inst
    outcome = publish_one("post.md", "devto", dry_run=True)
    assert outcome.result.success is True
    assert outcome.article is not None
    inst.publish.assert_not_called()


@patch("crier.publishing.get_platform_mode", return_value="manual")
def test_publish_one_propagates_prepare_error(mode):
    outcome = publish_one("post.md", "twitter")
    assert outcome.result.success is False
    assert "manual" in outcome.result.error


@patch("crier.publishing.auto_rewrite_for_platform")
@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_prepare_publish_auto_rewrite_success(mode, key, parse, get_plat, auto_rw):
    """Auto-rewrite success path: body exceeds max_content_length, LLM rewrites it."""
    long_article = _article(body_len=500)
    parse.return_value = long_article

    rewritten_article = Article(
        title="Hello World",
        body="short",
        description="desc",
        tags=["python"],
        canonical_url="https://example.com/post/hello/",
        is_rewrite=True,
    )
    auto_rw.return_value = AutoRewriteResult(
        success=True,
        article=rewritten_article,
        rewrite_text="short",
    )

    inst = MagicMock()
    inst.max_content_length = 300
    get_plat.return_value = lambda _k: inst

    llm_provider = MagicMock()
    llm_provider.model = "gpt-4o-mini"

    plan = prepare_publish(
        "post.md", "bluesky",
        auto_rewrite=True, llm_provider=llm_provider,
    )

    assert plan.error is None
    assert plan.rewritten is True
    assert plan.posted_content == "short"
    assert plan.rewrite_author == "llm:gpt-4o-mini"
    assert plan.article.body == "short"


@patch("crier.publishing.auto_rewrite_for_platform")
@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_auto_rewrite_failure(mode, key, parse, get_plat, auto_rw):
    """Auto-rewrite failure path: LLM can't fit content; publish is not called."""
    parse.return_value = _article(body_len=500)

    auto_rw.return_value = AutoRewriteResult(
        success=False,
        error="too long after retries",
    )

    inst = MagicMock()
    inst.max_content_length = 300
    get_plat.return_value = lambda _k: inst

    llm_provider = MagicMock()
    llm_provider.model = "gpt-4o-mini"

    outcome = publish_one(
        "post.md", "bluesky",
        auto_rewrite=True, llm_provider=llm_provider,
    )

    assert outcome.result.success is False
    assert "too long" in outcome.result.error
    assert isinstance(outcome, PublishOutcome)
    inst.publish.assert_not_called()


@patch("crier.publishing.get_platform")
@patch("crier.publishing.parse_markdown_file")
@patch("crier.publishing.get_api_key", return_value="real-key")
@patch("crier.publishing.get_platform_mode", return_value="api")
def test_publish_one_platform_exception_wrapped(mode, key, parse, get_plat):
    """Platform exceptions are caught and wrapped in a failed PublishResult."""
    parse.return_value = _article()

    inst = MagicMock()
    inst.publish.side_effect = RuntimeError("boom")
    get_plat.return_value = lambda _k: inst

    outcome = publish_one("post.md", "devto")

    assert outcome.result.success is False
    assert "boom" in outcome.result.error
    assert isinstance(outcome, PublishOutcome)


def test_prepared_plan_executes_snapshot_and_records_once(recording_platform, tmp_path, monkeypatch):
    from crier.publishing import PublishRequest, execute_plan, prepare_request, record_outcome
    from crier.registry import get_all_articles, get_connection
    md = tmp_path / 'post.md'
    md.write_text('---\ntitle: Snapshot\ntags: [original]\n---\nOriginal body.')
    plan = prepare_request(PublishRequest(md, 'test_platform'))
    md.write_text('---\ntitle: Changed\n---\nChanged body.')
    outcome = record_outcome(execute_plan(plan))
    record_outcome(outcome)
    assert recording_platform.articles[0].title == 'Snapshot'
    assert recording_platform.articles[0].body == 'Original body.'
    assert outcome.state.value == 'recorded'
    assert len(get_all_articles()) == 1
    assert get_connection().execute('SELECT count(*) FROM publications').fetchone()[0] == 1
    assert 'test-secret' not in repr(plan)


def test_service_dry_run_has_no_remote_or_registry_effects(recording_platform, tmp_path):
    from crier.publishing import PublishRequest, publish_and_record, record_outcome
    from crier.registry import get_all_articles
    md = tmp_path / 'preview.md'
    md.write_text('---\ntitle: Preview\n---\nBody.')
    outcome = publish_and_record(PublishRequest(md, 'test_platform'), dry_run=True)
    record_outcome(outcome)
    assert outcome.state.value == 'preview'
    assert not recording_platform.articles
    assert get_all_articles() == {}


def test_recording_failure_retains_remote_success(recording_platform, tmp_path, monkeypatch):
    from crier.publishing import PublishRequest, publish_and_record
    md = tmp_path / 'post.md'
    md.write_text('---\ntitle: Remote success\n---\nBody.')
    def fail(**kw):
        raise RuntimeError('database unavailable')
    monkeypatch.setattr('crier.registry.record_publication', fail)
    outcome = publish_and_record(PublishRequest(md, 'test_platform'))
    assert outcome.remote_success
    assert outcome.state.value == 'recording_failed'
    assert outcome.recording_error == 'database unavailable'
    receipt = next(tmp_path.glob('.*.recovery/*.json'))
    assert 'test-secret' not in receipt.read_text()
    assert len(recording_platform.articles) == 1


def test_service_preserves_thread_ids_and_rewrite_author(recording_platform, tmp_path):
    from crier.publishing import PublishRequest, RewriteOptions, ThreadOptions, publish_and_record
    from crier.registry import get_connection, get_thread_ids
    md = tmp_path / 'thread.md'
    md.write_text('---\ntitle: Thread\n---\nBody.')
    outcome = publish_and_record(PublishRequest(md, 'test_platform',
        rewrite=RewriteOptions(content='First. ' * 30, author='Alex'),
        thread=ThreadOptions(enabled=True)))
    assert outcome.state.value == 'recorded'
    assert get_thread_ids('thread', 'test_platform') == ['thread-1', 'thread-2']
    row = get_connection().execute('SELECT rewrite_author,posted_content FROM publications').fetchone()
    assert row[0] == 'Alex'
    assert row[1] == 'First. ' * 30


def test_partial_thread_retains_remote_ids(recording_platform, tmp_path, monkeypatch):
    from crier.platforms.base import ThreadPublishResult
    from crier.publishing import PublishRequest, ThreadOptions, publish_and_record
    md = tmp_path / 'partial.md'
    md.write_text('---\ntitle: Partial\n---\n' + 'First sentence. ' * 40)
    monkeypatch.setattr(recording_platform, 'publish_thread', lambda self, posts:
        ThreadPublishResult(False, self.name, root_id='partial-1',
                            post_ids=['partial-1'], error='second post failed'))
    outcome = publish_and_record(PublishRequest(md, 'test_platform', thread=ThreadOptions(True)))
    assert not outcome.success
    assert outcome.thread_ids == ['partial-1']
    assert outcome.error == 'second post failed'


def test_auto_rewrite_runs_once_and_preserves_explicit_attribution(recording_platform, tmp_path):
    from crier.llm.provider import RewriteResult
    from crier.publishing import PublishRequest, RewriteOptions, publish_and_record
    md = tmp_path / 'auto.md'
    md.write_text('---\ntitle: Auto\n---\n' + 'Long body. ' * 100)
    provider = MagicMock()
    provider.model = 'unit-model'
    provider.rewrite.return_value = RewriteResult('Short text.', 'unit-model')
    outcome = publish_and_record(PublishRequest(md, 'test_platform', rewrite=RewriteOptions(
        auto=True, provider=provider, author='Alex', retry_count=0, truncate=False)))
    assert outcome.success
    assert recording_platform.articles[0].body == 'Short text.'
    assert outcome.rewrite_author == 'Alex'
    assert provider.rewrite.call_count == 1


def test_explicit_zero_retry_and_false_truncate_override_defaults(recording_platform, tmp_path, monkeypatch):
    from crier.llm.provider import RewriteResult
    from crier.publishing import PublishRequest, RewriteOptions, publish_and_record
    monkeypatch.setattr('crier.config.get_llm_retry_count', lambda: 3)
    monkeypatch.setattr('crier.config.get_llm_truncate_fallback', lambda: True)
    md = tmp_path / 'overrides.md'
    md.write_text('---\ntitle: Overrides\n---\n' + 'Long. ' * 100)
    provider = MagicMock()
    provider.model = 'unit'
    provider.rewrite.return_value = RewriteResult('x' * 150, 'unit')
    outcome = publish_and_record(PublishRequest(md, 'test_platform', rewrite=RewriteOptions(
        auto=True, provider=provider, retry_count=0, truncate=False)))
    assert not outcome.success
    assert 'too long' in outcome.error
    assert provider.rewrite.call_count == 1
    assert not recording_platform.articles


def test_auto_rewrite_without_provider_fails_before_publishing(recording_platform, tmp_path, monkeypatch):
    from crier.publishing import PublishRequest, RewriteOptions, publish_and_record
    monkeypatch.setattr('crier.config.is_llm_configured', lambda: False)
    md = tmp_path / 'missing-provider.md'
    md.write_text('---\ntitle: Provider\n---\nBody.')
    outcome = publish_and_record(PublishRequest(md, 'test_platform', rewrite=RewriteOptions(auto=True)))
    assert not outcome.success
    assert 'no LLM' in outcome.error
    assert not recording_platform.articles


def test_failed_outcome_is_recorded_only_once(recording_platform, tmp_path, monkeypatch):
    from crier import registry
    from crier.publishing import PublishRequest, execute_plan, prepare_request, record_outcome
    recording_platform.failure = 'remote failed'
    md = tmp_path / 'failure.md'
    md.write_text('---\ntitle: Failure\n---\nBody.')
    calls = []
    original = registry.record_failure
    def record(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(registry, 'record_failure', record)
    outcome = execute_plan(prepare_request(PublishRequest(md, 'test_platform')))
    record_outcome(outcome)
    record_outcome(outcome)
    assert not outcome.success
    assert registry.get_failures()[0]['error'] == 'remote failed'
    assert len(calls) == 1


def test_manual_confirmation_is_not_remote_success(recording_platform, tmp_path, monkeypatch):
    from crier.publishing import PublishRequest, publish_and_record
    from crier.registry import get_all_articles
    md = tmp_path / 'manual.md'
    md.write_text('---\ntitle: Manual\n---\nBody.')
    monkeypatch.setattr(recording_platform, 'publish', lambda self, article: PublishResult(
        True, self.name, requires_confirmation=True, manual_content='Manual body.',
        compose_url='https://remote/compose'))
    outcome = publish_and_record(PublishRequest(md, 'test_platform'))
    assert outcome.requires_confirmation
    assert not outcome.remote_success
    assert not outcome.success
    assert outcome.state.value == 'awaiting_confirmation'
    assert outcome.error
    assert get_all_articles() == {}


def test_recovery_metadata_error_never_hides_remote_success(recording_platform, tmp_path, monkeypatch):
    import yaml

    from crier.publishing import PublishRequest, publish_and_record
    md = tmp_path / 'recovery-error.md'
    md.write_text('---\ntitle: Recovery error\n---\nBody.')
    def broken_record(**kwargs):
        raise RuntimeError('registry unavailable')
    def broken_receipt(*args):
        raise yaml.YAMLError('configuration unreadable')
    monkeypatch.setattr('crier.registry.record_publication', broken_record)
    monkeypatch.setattr('crier.publication_receipts.save_receipt', broken_receipt)
    outcome = publish_and_record(PublishRequest(md, 'test_platform'))
    assert outcome.remote_success
    assert outcome.article_id == 'remote-1'
    assert 'registry unavailable' in outcome.error
    assert 'configuration unreadable' in outcome.error


def test_execute_or_recover_replays_receipt_without_remote_write(
    recording_platform, tmp_path, monkeypatch
):
    from crier.publishing import (
        PublicationState,
        PublishRequest,
        execute_or_recover,
        prepare_request,
        publish_and_record,
    )
    from crier.registry import get_publication_id
    md = tmp_path / 'live.md'
    md.write_text('---\ntitle: Live\n---\nBody.')
    def unavailable(**kwargs):
        raise RuntimeError('db down')
    with monkeypatch.context() as patcher:
        patcher.setattr('crier.registry.record_publication', unavailable)
        assert publish_and_record(PublishRequest(md, 'test_platform')).remote_success
    outcome = execute_or_recover(prepare_request(PublishRequest(md, 'test_platform')))
    assert outcome.recovered is True
    assert outcome.state == PublicationState.RECORDED
    assert outcome.url == 'https://remote/1'
    assert len(recording_platform.articles) == 1
    assert get_publication_id('live', 'test_platform') == 'remote-1'


def test_execute_or_recover_without_receipt_publishes(recording_platform, tmp_path):
    from crier.publishing import PublishRequest, execute_or_recover, prepare_request
    md = tmp_path / 'fresh.md'
    md.write_text('---\ntitle: Fresh\n---\nBody.')
    outcome = execute_or_recover(prepare_request(PublishRequest(md, 'test_platform')))
    assert outcome.success and outcome.recovered is False
    assert len(recording_platform.articles) == 1
