"""Shared preparation, execution, and recording for API publishing.

Preparation reads content/configuration and may call an LLM. Execution sends the
prepared snapshot; recording owns registry effects. Compatibility publish_one()
intentionally executes without recording.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from .config import get_api_key, get_platform_mode
from .converters import parse_markdown_file
from .llm.provider import LLMProvider
from .platforms import get_platform
from .platforms.base import Article, Platform, PublishResult, ThreadPublishResult
from .rewrite import apply_rewrite, auto_rewrite_for_platform

logger = logging.getLogger(__name__)


class ThreadStyle(str, Enum):
    NUMBERED = "numbered"
    SIMPLE = "simple"
    EMOJI = "emoji"


class PublicationState(str, Enum):
    PREVIEW = "preview"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    REMOTE_FAILED = "remote_failed"
    FAILURE_RECORDED = "failure_recorded"
    REMOTE_SUCCEEDED = "remote_succeeded"
    RECORDED = "recorded"
    RECORDING_FAILED = "recording_failed"


@dataclass(frozen=True)
class RewriteOptions:
    content: str | None = None
    author: str | None = None
    auto: bool = False
    provider: LLMProvider | None = field(default=None, repr=False)
    retry_count: int | None = None
    truncate: bool | None = None
    temperature: float | None = None
    model: str | None = None


@dataclass(frozen=True)
class ThreadOptions:
    enabled: bool = False
    style: ThreadStyle = ThreadStyle.NUMBERED

    def __post_init__(self):
        object.__setattr__(self, "style", ThreadStyle(self.style))


@dataclass(frozen=True)
class PublishRequest:
    source_file: Path
    platform: str
    rewrite: RewriteOptions = field(default_factory=RewriteOptions)
    draft: bool = False
    thread: ThreadOptions = field(default_factory=ThreadOptions)


@dataclass
class PublishPlan:
    platform: str
    mode: str
    api_key: str | None = field(repr=False)
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None
    error: str | None = None
    request: PublishRequest | None = None
    adapter: Platform | None = field(default=None, repr=False)
    thread_posts: list[str] | None = None


@dataclass
class PublishOutcome:
    result: PublishResult | ThreadPublishResult
    article: Article | None
    rewritten: bool = False
    posted_content: str | None = None
    rewrite_author: str | None = None
    request: PublishRequest | None = None
    recording_error: str | None = None
    state: PublicationState | None = None
    # True when the outcome replays a recovery receipt instead of a new remote write.
    recovered: bool = False

    def __post_init__(self):
        if self.state is None and self.requires_confirmation:
            self.state = PublicationState.AWAITING_CONFIRMATION
        if self.state is None:
            self.state = (
                PublicationState.REMOTE_SUCCEEDED
                if self.result.success
                else PublicationState.REMOTE_FAILED
            )

    @property
    def remote_success(self) -> bool:
        return (
            self.result.success
            and not self.requires_confirmation
            and self.state != PublicationState.PREVIEW
        )

    @property
    def article_id(self) -> str | None:
        if isinstance(self.result, ThreadPublishResult):
            return self.result.root_id
        return self.result.article_id

    @property
    def url(self) -> str | None:
        if isinstance(self.result, ThreadPublishResult):
            return self.result.root_url
        return self.result.url

    @property
    def thread_ids(self) -> list[str] | None:
        return self.result.post_ids if isinstance(self.result, ThreadPublishResult) else None

    @property
    def thread_urls(self) -> list[str] | None:
        return self.result.post_urls if isinstance(self.result, ThreadPublishResult) else None

    @property
    def is_thread(self) -> bool:
        return isinstance(self.result, ThreadPublishResult)

    @property
    def success(self) -> bool:
        return (
            self.result.success and not self.requires_confirmation and self.recording_error is None
        )

    @property
    def error(self) -> str | None:
        return (
            self.recording_error
            or self.result.error
            or ("Manual confirmation required; use the CLI" if self.requires_confirmation else None)
        )

    @property
    def requires_confirmation(self) -> bool:
        return isinstance(self.result, PublishResult) and self.result.requires_confirmation

    @property
    def manual_content(self) -> str | None:
        return self.result.manual_content if isinstance(self.result, PublishResult) else None

    @property
    def compose_url(self) -> str | None:
        return self.result.compose_url if isinstance(self.result, PublishResult) else None


def prepare_request(
    request: PublishRequest,
    *,
    source_article: Article | None = None,
    silent: bool = True,
    console=None,
) -> PublishPlan:
    """Read source/config and optionally rewrite; never publish or record."""
    request = replace(request, source_file=Path(request.source_file).expanduser().resolve())
    mode = get_platform_mode(request.platform)
    plan = PublishPlan(request.platform, mode, None, None, request=request)
    if mode != "api":
        plan.error = f"{request.platform} is in {mode} mode (not API)"
        return plan
    plan.api_key = get_api_key(request.platform)
    if not plan.api_key:
        plan.error = f"No API key configured for {request.platform}"
        return plan
    try:
        article = (
            source_article
            if source_article is not None
            else parse_markdown_file(str(request.source_file))
        )
        article = replace(article, tags=list(article.tags) if article.tags is not None else None)
        plan.article = article
        if not article.title:
            plan.error = "Article has no title"
            return plan
        if request.draft:
            article.published = False
        plan.adapter = get_platform(request.platform)(plan.api_key)
        if request.thread.enabled and not plan.adapter.supports_threads:
            plan.error = f"{request.platform} does not support thread posting"
            return plan
        rewrite = request.rewrite
        plan.rewrite_author = rewrite.author
        if rewrite.content:
            plan.article = apply_rewrite(article, rewrite.content)
            plan.rewritten = True
            plan.posted_content = rewrite.content
            if plan.rewrite_author is None:
                from .config import get_rewrite_author

                plan.rewrite_author = get_rewrite_author()
        elif rewrite.auto:
            from .config import (
                get_llm_config,
                get_llm_retry_count,
                get_llm_truncate_fallback,
                is_llm_configured,
            )

            provider = rewrite.provider
            if provider is None and is_llm_configured():
                from .llm import get_provider

                provider = get_provider(
                    get_llm_config(), temperature=rewrite.temperature, model=rewrite.model
                )
            if provider is None:
                plan.error = "auto_rewrite requested but no LLM is configured or provider available"
                return plan
            max_len = plan.adapter.max_content_length
            if max_len and len(article.body) > max_len:
                rw = auto_rewrite_for_platform(
                    article,
                    request.platform,
                    max_len,
                    provider,
                    retry_count=(
                        rewrite.retry_count
                        if rewrite.retry_count is not None
                        else get_llm_retry_count()
                    ),
                    truncate_fallback=(
                        rewrite.truncate
                        if rewrite.truncate is not None
                        else get_llm_truncate_fallback()
                    ),
                    silent=silent,
                    console=console,
                )
                if not rw.success:
                    plan.error = rw.error or "auto-rewrite failed"
                    return plan
                plan.article = rw.article
                plan.rewritten = True
                plan.posted_content = rw.rewrite_text
                if plan.rewrite_author is None:
                    plan.rewrite_author = f"llm:{provider.model}"
        if not plan.rewritten:
            plan.rewrite_author = None
        if (
            rewrite.content
            and not request.thread.enabled
            and not rewrite.auto
            and plan.adapter.max_content_length
            and len(plan.article.body) > plan.adapter.max_content_length
        ):
            plan.error = (
                f"Rewrite content too long: {len(plan.article.body)} chars "
                f"(limit: {plan.adapter.max_content_length})"
            )
            return plan
        if request.thread.enabled:
            from .threading import split_into_thread

            plan.thread_posts = split_into_thread(
                plan.article.body,
                max_length=plan.adapter.max_content_length or 300,
                style=request.thread.style.value,
                max_posts=plan.adapter.thread_max_posts,
            )
    except Exception as exc:  # noqa: BLE001 — isolate adapter and recording failures
        plan.error = str(exc)
    return plan


def _outcome(
    plan: PublishPlan,
    result: PublishResult | ThreadPublishResult,
    *,
    state: PublicationState | None = None,
) -> PublishOutcome:
    return PublishOutcome(
        result,
        plan.article,
        rewritten=plan.rewritten,
        posted_content=plan.posted_content,
        rewrite_author=plan.rewrite_author,
        request=plan.request,
        state=state,
    )


def execute_plan(plan: PublishPlan) -> PublishOutcome:
    """Publish exactly the prepared article, retaining the actual adapter result."""
    if plan.error or plan.article is None or plan.adapter is None:
        return _outcome(
            plan, PublishResult(False, plan.platform, error=plan.error or "Incomplete publish plan")
        )
    try:
        if plan.thread_posts and len(plan.thread_posts) > 1:
            result = plan.adapter.publish_thread(plan.thread_posts)
        else:
            result = plan.adapter.publish(plan.article)
    except Exception as exc:  # noqa: BLE001 — isolate adapter and recording failures
        result = PublishResult(False, plan.platform, error=str(exc))
    return _outcome(plan, result)


def record_outcome(outcome: PublishOutcome) -> PublishOutcome:
    """Record once; distinguish persistence failure from a successful remote write."""
    if outcome.state in (
        PublicationState.PREVIEW,
        PublicationState.RECORDED,
        PublicationState.RECORDING_FAILED,
        PublicationState.FAILURE_RECORDED,
    ):
        return outcome
    if outcome.article is None:
        return outcome
    if outcome.requires_confirmation:
        return outcome
    from .registry import record_failure, record_publication, record_thread_publication

    article = outcome.article
    source = str(outcome.request.source_file) if outcome.request else None
    platform = outcome.request.platform if outcome.request else outcome.result.platform
    identity = {
        "canonical_url": article.canonical_url,
        "platform": platform,
        "title": article.title,
        "source_file": source,
    }
    try:
        if not outcome.result.success:
            record_failure(**identity, error_msg=outcome.result.error or "Unknown publish error")
            outcome.state = PublicationState.FAILURE_RECORDED
        elif isinstance(outcome.result, ThreadPublishResult):
            record_thread_publication(
                **identity,
                root_id=outcome.result.root_id,
                root_url=outcome.result.root_url,
                thread_ids=outcome.result.post_ids or [],
                thread_urls=outcome.result.post_urls,
                rewritten=outcome.rewritten,
                rewrite_author=outcome.rewrite_author,
                posted_content=outcome.posted_content,
            )
            outcome.state = PublicationState.RECORDED
        else:
            record_publication(
                **identity,
                article_id=outcome.article_id,
                url=outcome.url,
                rewritten=outcome.rewritten,
                rewrite_author=outcome.rewrite_author,
                posted_content=outcome.posted_content,
            )
            outcome.state = PublicationState.RECORDED
    except Exception as exc:  # noqa: BLE001 — isolate adapter and recording failures
        outcome.recording_error = str(exc)
        outcome.state = PublicationState.RECORDING_FAILED
        if outcome.remote_success and outcome.request is not None:
            from datetime import datetime, timezone

            from .publication_receipts import PublicationReceipt, save_receipt

            try:
                save_receipt(
                    PublicationReceipt(
                        source_file=str(outcome.request.source_file),
                        platform=platform,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        article=article,
                        result=outcome.result,
                        rewritten=outcome.rewritten,
                        posted_content=outcome.posted_content,
                        rewrite_author=outcome.rewrite_author,
                    )
                )
            except Exception as receipt_error:  # noqa: BLE001 — preserve the known remote result
                outcome.recording_error += f"; could not save recovery receipt: {receipt_error}"
    else:
        if outcome.state == PublicationState.RECORDED and outcome.request is not None:
            from .publication_receipts import remove_receipt

            try:
                remove_receipt(outcome.request.source_file, platform)
            except Exception:  # noqa: BLE001 — cleanup cannot invalidate a committed publication
                logger.debug("Could not remove stale publication recovery receipt")
    return outcome


def recover_unrecorded(
    request: PublishRequest, *, failed_at: str | None = None, dry_run: bool = False
) -> PublishOutcome | None:
    """Retry only local persistence of an earlier remote success, never publish."""
    from .publication_receipts import load_receipt

    receipt = load_receipt(request.source_file, request.platform)
    if receipt is None or not receipt.covers_failure(failed_at):
        return None
    outcome = PublishOutcome(
        receipt.result,
        receipt.article,
        rewritten=receipt.rewritten,
        posted_content=receipt.posted_content,
        rewrite_author=receipt.rewrite_author,
        request=replace(request, source_file=Path(receipt.source_file)),
        state=PublicationState.PREVIEW if dry_run else PublicationState.REMOTE_SUCCEEDED,
        recovered=True,
    )
    return outcome if dry_run else record_outcome(outcome)


def execute_or_recover(plan: PublishPlan) -> PublishOutcome:
    """Execute and record a prepared plan unless a receipt shows it is already live.

    A confirmed publish has no failure row to compare against, so any receipt for
    the source/platform counts (``failed_at=None``): it is evidence of a remote
    write that must not be repeated. Unreadable receipts raise ``UnreadableReceipt``
    and therefore also block the remote write.
    """
    if plan.request is not None:
        recovered = recover_unrecorded(plan.request)
        if recovered is not None:
            return recovered
    return record_outcome(execute_plan(plan))


def publish_and_record(
    request: PublishRequest,
    *,
    dry_run: bool = False,
    source_article: Article | None = None,
    silent: bool = True,
    console=None,
) -> PublishOutcome:
    plan = prepare_request(request, source_article=source_article, silent=silent, console=console)
    if dry_run and not plan.error:
        return _outcome(plan, PublishResult(True, plan.platform), state=PublicationState.PREVIEW)
    if dry_run:
        return _outcome(
            plan,
            PublishResult(False, plan.platform, error=plan.error),
            state=PublicationState.PREVIEW,
        )
    return record_outcome(execute_plan(plan))


def prepare_publish(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    silent: bool = True,
    console=None,
) -> PublishPlan:
    """Compatibility adapter: preparation only, with no registry writes."""
    request = PublishRequest(
        Path(file_path),
        platform,
        draft=draft,
        rewrite=RewriteOptions(
            content=rewrite_content,
            author=rewrite_author,
            auto=auto_rewrite,
            provider=llm_provider,
            retry_count=auto_rewrite_retry,
            truncate=auto_rewrite_truncate,
        ),
    )
    return prepare_request(request, silent=silent, console=console)


def publish_one(
    file_path: str | Path,
    platform: str,
    *,
    rewrite_content: str | None = None,
    rewrite_author: str | None = None,
    auto_rewrite: bool = False,
    llm_provider=None,
    auto_rewrite_retry: int = 0,
    auto_rewrite_truncate: bool = False,
    draft: bool = False,
    dry_run: bool = False,
    silent: bool = True,
    console=None,
) -> PublishOutcome:
    """Compatibility API: publish a single post, deliberately without recording."""
    plan = prepare_publish(
        file_path,
        platform,
        rewrite_content=rewrite_content,
        rewrite_author=rewrite_author,
        auto_rewrite=auto_rewrite,
        llm_provider=llm_provider,
        auto_rewrite_retry=auto_rewrite_retry,
        auto_rewrite_truncate=auto_rewrite_truncate,
        draft=draft,
        silent=silent,
        console=console,
    )
    if dry_run:
        return _outcome(
            plan,
            PublishResult(not bool(plan.error), platform, error=plan.error),
            state=PublicationState.PREVIEW,
        )
    return execute_plan(plan)
