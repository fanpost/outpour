"""Nostr long-form platform: NIP-23 kind-30023 articles (Outpour).

A kind-30023 event is a parameterized replaceable event: the ``d`` tag is
its address, so re-publishing the same article (same ``d`` tag, same
author) replaces the previous version instead of duplicating it. That
property is what makes Nostr a scheduler-friendly destination: a
re-publish is an update, not a second post.

Frontmatter mapping (from the Article fields Crier already carries):
  - ``d`` tag: slug derived from the canonical URL's last path segment
    when present, otherwise a slugified title (max 80 chars, same
    helper style as the registry's slugify).
  - ``title`` tag: article title.
  - ``summary`` tag: article description, when present.
  - ``published_at`` tag: current UTC unix time at publish (Article
    carries no source date, so publish time is the honest value).
  - ``image`` tag: cover_image URL, when present.
  - ``t`` tags: article tags, one per tag.
  - content: the full markdown body (NIP-23 content is markdown).

api_key formats (same as the kind-1 Nostr platform):
  - "nsec1..."                    bech32 private key, default relays
  - "<64-hex>"                    hex private key, default relays
  - "nsec1...|wss://r1,wss://r2"  key plus a custom relay list

Signing needs the optional [nostr] extra (pynostr); the import is
deferred to publish/delete so the platform stays constructible
without it. Like kind-1, there is no authoritative cross-relay
listing, so list_articles/get_article are intentionally empty/None
and stats do not apply. Deletion is best-effort NIP-09 (kind 5) with
an ``a`` tag addressing the 30023 event; relays may or may not honor
it.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from slugify import slugify

from .base import Article, DeleteResult, Platform, PublishResult
from .nostr import DEFAULT_RELAYS

_IMPORT_HINT = "Nostr requires the 'nostr' extra: pip install 'outpour[nostr]'"


def derive_d_tag(article: Article) -> str:
    """Derive the NIP-23 ``d`` tag for an article.

    Canonical URL wins (its last non-empty path segment, e.g.
    https://example.com/posts/my-article/ -> "my-article"); otherwise
    the title is slugified. Falls back to "article" if neither yields
    anything, so the tag is never empty.
    """
    if article.canonical_url:
        path = urlparse(article.canonical_url).path.strip("/")
        if path:
            return path.rsplit("/", 1)[-1]
    slug = slugify(article.title or "", max_length=80)
    return slug or "article"


def build_tags(article: Article, published_at: int | None = None) -> list[list[str]]:
    """Build the NIP-23 tag list for an article (pure, no signing)."""
    tags: list[list[str]] = [["d", derive_d_tag(article)]]
    if article.title:
        tags.append(["title", article.title])
    if article.description:
        tags.append(["summary", article.description])
    tags.append(["published_at", str(published_at if published_at is not None else int(time.time()))])
    if article.cover_image:
        tags.append(["image", article.cover_image])
    for tag in article.tags or []:
        if tag:
            tags.append(["t", tag])
    return tags


class NostrLongform(Platform):
    """Publish long-form articles to Nostr as NIP-23 kind-30023 events."""

    name = "nostr-longform"
    description = "Long-form articles on Nostr (NIP-23, kind 30023)"
    max_content_length = None  # Nostr imposes no protocol length limit
    is_short_form = False
    supports_delete = True
    supports_stats = False
    api_key_url = "https://nostr.com/"

    def __init__(self, api_key: str, relays: list[str] | None = None):
        super().__init__(api_key)
        raw = api_key or ""
        if "|" in raw:
            key_part, relays_part = raw.split("|", 1)
            parsed = [r.strip() for r in relays_part.split(",") if r.strip()]
        else:
            key_part, parsed = raw, None
        self.secret = key_part.strip()
        self.relays = relays or parsed or list(DEFAULT_RELAYS)

    # --- helpers ---------------------------------------------------------

    def _load_key(self):
        """Build the pynostr PrivateKey (lazy import; raises if extra missing)."""
        try:
            from pynostr.key import PrivateKey
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_HINT) from e
        if self.secret.startswith("nsec"):
            return PrivateKey.from_nsec(self.secret)
        return PrivateKey.from_hex(self.secret)

    def _signed_event(self, content: str, kind: int, tags: list | None = None):
        """Build and sign a Nostr event (lazy import; raises if extra missing)."""
        try:
            from pynostr.event import Event
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_HINT) from e
        priv = self._load_key()
        event = Event(
            content=content, kind=kind, pubkey=priv.public_key.hex(), tags=tags or []
        )
        event.sign(priv.hex())
        return event

    def _publish_event(self, event) -> None:
        """Broadcast a signed event to all configured relays."""
        try:
            from pynostr.relay_manager import RelayManager
        except ImportError as e:  # pragma: no cover
            raise ImportError(_IMPORT_HINT) from e
        rm = RelayManager(timeout=self.timeout)
        for url in self.relays:
            rm.add_relay(url)
        try:
            rm.publish_event(event)
            rm.run_sync()
        finally:
            try:
                rm.close_all_relay_connections()
            except Exception:
                pass

    # --- Platform interface ----------------------------------------------

    def publish(self, article: Article) -> PublishResult:
        try:
            event = self._signed_event(
                article.body, kind=30023, tags=build_tags(article)
            )
            self._publish_event(event)
        except Exception as e:
            return PublishResult(success=False, platform=self.name, error=str(e))
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=event.id,
            url=f"https://njump.me/{event.bech32()}",
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        """Re-publish: kind 30023 is replaceable, so the same d-tag
        replaces the previous version instead of duplicating it."""
        return self.publish(article)

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        # Nostr has no authoritative listing across relays; not supported.
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Best-effort NIP-09 deletion via a kind-5 event.

        article_id is expected to be "pubkey:d-tag" when the caller
        knows it; a bare event id falls back to an ``e`` tag.
        """
        try:
            priv = self._load_key()
            if ":" in article_id:
                tags = [["a", f"30023:{article_id}"]]
            else:
                tags = [["e", article_id]]
            event = self._signed_event("", kind=5, tags=tags)
            self._publish_event(event)
        except Exception as e:
            return DeleteResult(success=False, platform=self.name, error=str(e))
        return DeleteResult(success=True, platform=self.name)
