"""Service layer for the Outpour web UI.

This module is the only place the UI touches publishing, scheduling,
configuration, and the ledger. The FastAPI routes in app.py are thin:
they render what these functions return and pass form input straight
through. Tests inject a fake object with the same method names, so
endpoint tests never touch a real platform.

Key values are never returned by any function here: list_platforms
reports configured/mode/source only, never the key itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .. import config, registry, scheduler
from ..converters import parse_front_matter
from ..platforms import PLATFORMS
from ..publishing import PublishRequest, publish_and_record


def _content_roots() -> list[Path]:
    """Configured content directories, resolved against the project root."""
    project_root = config.get_project_root() or Path.cwd()
    roots = []
    for raw in config.get_content_paths():
        path = Path(raw)
        if not path.is_absolute():
            path = project_root / path
        roots.append(path.resolve())
    return roots


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_article_path(raw: str) -> Path:
    """Resolve a UI-supplied path, refusing anything outside content roots.

    When content paths are configured, the file must live under one of
    them. When none are configured, it must live under the working
    directory. This keeps a path form field from becoming a file reader
    for arbitrary locations.
    """
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        roots = _content_roots()
        base = roots[0] if roots else Path.cwd()
        candidate = base / candidate
    resolved = candidate.resolve()
    roots = _content_roots()
    if roots:
        if not any(_is_within(resolved, root) for root in roots):
            raise ValueError("Article path is outside the configured content paths")
    elif not _is_within(resolved, Path.cwd().resolve()):
        raise ValueError("Article path is outside the working directory")
    return resolved


def _ledger_status(path: Path) -> dict[str, dict[str, Any]]:
    """Per-platform ledger status for one file, best effort.

    Returns a mapping platform -> {state, url, error} where state is
    one of published, failed, or blank (no ledger row). A missing or
    unreadable registry degrades to an empty mapping rather than
    breaking the articles page.
    """
    try:
        found = registry.get_article_by_file(path)
    except Exception:  # noqa: BLE001 - ledger is advisory on this page
        return {}
    if not found:
        return {}
    _slug, data = found
    status: dict[str, dict[str, Any]] = {}
    for platform, pub in (data.get("platforms") or {}).items():
        if pub.get("deleted_at"):
            continue
        if pub.get("id"):
            status[platform] = {"state": "published", "url": pub.get("url"), "error": None}
        elif pub.get("last_error"):
            status[platform] = {
                "state": "failed",
                "url": None,
                "error": pub.get("last_error"),
            }
    return status


def list_articles() -> list[dict[str, Any]]:
    """All markdown articles under the configured content paths."""
    extensions = config.get_file_extensions() or [".md"]
    wanted = {ext.lower() for ext in extensions}
    articles: list[dict[str, Any]] = []
    for root in _content_roots():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in wanted:
                continue
            if any(part.startswith(".") for part in path.relative_to(root).parts[:-1]):
                continue
            try:
                frontmatter, _body = parse_front_matter(path.read_text())
            except OSError:
                continue
            articles.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "title": frontmatter.get("title") or path.stem,
                    "description": frontmatter.get("description") or "",
                    "tags": frontmatter.get("tags") or [],
                    "status": _ledger_status(path),
                }
            )
    return articles


def get_article(path: str) -> dict[str, Any] | None:
    """One article's editable fields, or None when the file is missing."""
    resolved = resolve_article_path(path)
    if not resolved.is_file():
        return None
    frontmatter, body = parse_front_matter(resolved.read_text())
    return {
        "path": str(resolved),
        "name": resolved.name,
        "title": frontmatter.get("title") or "",
        "description": frontmatter.get("description") or "",
        "tags": frontmatter.get("tags") or [],
        "canonical_url": frontmatter.get("canonical_url") or "",
        "cover_image": frontmatter.get("cover_image") or frontmatter.get("image") or "",
        "body": body,
        "frontmatter": frontmatter,
    }


def save_article(
    path: str | None,
    fields: dict[str, Any],
    body: str,
    filename: str | None = None,
) -> Path:
    """Write an article, preserving frontmatter keys the editor hides.

    With path=None a new file is created under the first content path
    (or the working directory when none is configured). The filename
    comes from the explicit filename field, else a slug of the title.
    """
    if path:
        resolved = resolve_article_path(path)
        frontmatter, _old = parse_front_matter(resolved.read_text()) if resolved.exists() else ({}, "")
    else:
        roots = _content_roots()
        base = roots[0] if roots else Path.cwd().resolve()
        base.mkdir(parents=True, exist_ok=True)
        stem = (filename or "").strip()
        if not stem:
            from slugify import slugify

            stem = slugify(fields.get("title") or "untitled") or "untitled"
        stem = Path(stem).name
        if not stem.endswith(".md"):
            stem += ".md"
        resolved = (base / stem).resolve()
        if roots and not any(_is_within(resolved, root) for root in roots):
            raise ValueError("Article path is outside the configured content paths")
        frontmatter = {}
    for key in ("title", "description", "canonical_url", "cover_image"):
        value = (fields.get(key) or "").strip() if isinstance(fields.get(key), str) else fields.get(key)
        if value:
            frontmatter[key] = value
        else:
            frontmatter.pop(key, None)
    tags = fields.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    if tags:
        frontmatter["tags"] = tags
    else:
        frontmatter.pop("tags", None)
    text = "---\n" + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True) + "---\n\n" + body.strip() + "\n"
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text)
    return resolved


def list_platforms() -> list[dict[str, Any]]:
    """Every known platform with configured/mode/source only.

    Key values are never included: the page shows whether a platform
    is configured and where its key came from, not the key itself.
    """
    platforms = []
    for name in sorted(PLATFORMS):
        cls = PLATFORMS[name]
        platforms.append(
            {
                "name": name,
                "description": getattr(cls, "description", "") or "",
                "configured": config.is_platform_configured(name),
                "mode": config.get_platform_mode(name),
                "source": config.get_api_key_source(name),
            }
        )
    return platforms


def publish_article(path: str, platforms: list[str], draft: bool) -> list[dict[str, Any]]:
    """Publish now, via the existing publish_and_record code path.

    One platform's failure never blocks the others, and every result
    (including the error text) is returned for the results page.
    Idempotency comes from publish_and_record: a re-publish updates
    the existing ledger entry instead of duplicating it.
    """
    resolved = resolve_article_path(path)
    results: list[dict[str, Any]] = []
    for platform in platforms:
        try:
            outcome = publish_and_record(
                PublishRequest(resolved, platform, draft=draft),
                silent=True,
            )
            result = outcome.result
            results.append(
                {
                    "platform": platform,
                    "success": bool(result.success),
                    "url": result.url,
                    "article_id": result.article_id,
                    "error": result.error,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report honestly, keep going
            results.append(
                {
                    "platform": platform,
                    "success": False,
                    "url": None,
                    "article_id": None,
                    "error": str(exc),
                }
            )
    return results


def schedule_article(
    path: str, platforms: list[str], when: str, draft: bool
) -> list[dict[str, Any]]:
    """Schedule for later, via the existing scheduler code path."""
    resolved = resolve_article_path(path)
    scheduled_dt = scheduler.parse_schedule_time(when)
    if scheduled_dt is None:
        return [
            {
                "platform": platform,
                "success": False,
                "post_id": None,
                "scheduled_time": None,
                "error": f"Could not parse schedule time: {when}",
            }
            for platform in platforms
        ]
    results: list[dict[str, Any]] = []
    for platform in platforms:
        try:
            post = scheduler.create_scheduled_post(
                str(resolved),
                platform,
                scheduled_dt,
                draft=draft,
            )
            results.append(
                {
                    "platform": platform,
                    "success": True,
                    "post_id": post.id,
                    "scheduled_time": post.scheduled_time.isoformat(),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - report honestly, keep going
            results.append(
                {
                    "platform": platform,
                    "success": False,
                    "post_id": None,
                    "scheduled_time": None,
                    "error": str(exc),
                }
            )
    return results


def list_scheduled() -> list[dict[str, Any]]:
    """The schedule queue, newest schedule state first by time."""
    posts = []
    for post in scheduler.list_scheduled_posts():
        data = post.to_dict()
        data["file_name"] = Path(post.file_path).name
        posts.append(data)
    return posts


def cancel_scheduled(post_id: str) -> bool:
    """Cancel a pending scheduled post; False when not pending/found."""
    return scheduler.cancel_scheduled_post(post_id)


class UIService:
    """Default service object: thin bound methods over the functions above."""

    def list_articles(self) -> list[dict[str, Any]]:
        return list_articles()

    def get_article(self, path: str) -> dict[str, Any] | None:
        return get_article(path)

    def save_article(
        self, path: str | None, fields: dict[str, Any], body: str, filename: str | None = None
    ) -> Path:
        return save_article(path, fields, body, filename)

    def list_platforms(self) -> list[dict[str, Any]]:
        return list_platforms()

    def publish_article(self, path: str, platforms: list[str], draft: bool) -> list[dict[str, Any]]:
        return publish_article(path, platforms, draft)

    def schedule_article(
        self, path: str, platforms: list[str], when: str, draft: bool
    ) -> list[dict[str, Any]]:
        return schedule_article(path, platforms, when, draft)

    def list_scheduled(self) -> list[dict[str, Any]]:
        return list_scheduled()

    def cancel_scheduled(self, post_id: str) -> bool:
        return cancel_scheduled(post_id)
