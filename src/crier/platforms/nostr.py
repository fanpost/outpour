"""Nostr platform: signed kind-1 notes broadcast to relays (NIP-01).

Nostr is a protocol, not a service: a note is a secp256k1/Schnorr-signed event
(BIP340) broadcast to relays over websockets. Signing needs the optional
[nostr] extra (pynostr, which pulls coincurve); the heavy import is deferred to
publish/delete so the platform stays importable and constructible without it.

api_key formats:
  - "nsec1..."                    bech32 private key, default relays
  - "<64-hex>"                    hex private key, default relays
  - "nsec1...|wss://r1,wss://r2"  key plus a custom relay list (pipe-separated)

Nostr has no authoritative cross-relay listing (a relay only holds what it has
seen), so list_articles/get_article are intentionally not implemented (empty/
None) and reconcile/stats do not apply. Notes are immutable, so update is not
supported. Deletion is best-effort via a NIP-09 (kind 5) event; relays may or
may not honor it.
"""

from __future__ import annotations

from typing import Any

from .base import Article, DeleteResult, Platform, PublishResult

DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://nos.lol",
    "wss://relay.nostr.band",
    "wss://relay.primal.net",
]

_IMPORT_HINT = "Nostr requires the 'nostr' extra: pip install 'outpour[nostr]'"


def broadcast_event(relays: list[str], event) -> dict[str, str]:
    """Broadcast a signed event and collect per-relay NIP-01 OK acks.

    Returns ``{relay_url: outcome}`` where outcome is ``"accepted"``,
    ``"rejected: <relay message>"``, or ``"no acknowledgement"`` (the
    relay never answered within its connect window). Callers must
    treat "no acknowledgement" as unproven, never as success: earlier
    versions of this helper reported success fire-and-forget, which
    claimed publishes that no relay had confirmed.

    Raises ImportError with the install hint when the [nostr] extra
    is missing. Each relay gets pynostr's default ~2s connect window,
    so a full broadcast to the default set takes at most ~8s.
    """
    try:
        from pynostr.relay_manager import RelayManager
    except ImportError as e:  # pragma: no cover
        raise ImportError(_IMPORT_HINT) from e
    rm = RelayManager()
    for url in relays:
        rm.add_relay(url)
    try:
        rm.publish_event(event)
        rm.run_sync()
        acks = {}
        for ok in rm.message_pool.get_all_ok():
            if ok.event_id == event.id:
                acks[ok.url] = ok
        results = {}
        for url in relays:
            if url in acks:
                ok = acks[url]
                if ok.ok is True or ok.ok == "true":
                    results[url] = "accepted"
                else:
                    results[url] = f"rejected: {ok.message}"
            else:
                results[url] = "no acknowledgement"
        return results
    finally:
        try:
            rm.close_all_relay_connections()
        except Exception:
            pass


class Nostr(Platform):
    """Publish short notes to the Nostr network.

    Configure with a private key: ``outpour config set platforms.nostr.api_key
    nsec1...`` (optionally ``nsec1...|wss://relay.a,wss://relay.b`` for custom
    relays). Short-form by convention (microblogging), though Nostr imposes no
    length limit.
    """

    name = "nostr"
    description = "Signed short notes on the Nostr protocol (relays)"
    max_content_length = None  # Nostr imposes no protocol length limit
    is_short_form = True
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

    def _compose(self, article: Article) -> str:
        if article.is_rewrite:
            return self._append_canonical_url(article.body, article)
        parts = [article.title]
        if article.description:
            parts.append(article.description)
        if article.canonical_url:
            parts.append(article.canonical_url)
        if article.tags:
            parts.append(" ".join(f"#{t.replace('-', '')}" for t in article.tags[:5]))
        return "\n\n".join(parts)

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

    def _publish_event(self, event) -> dict[str, str]:
        """Broadcast a signed event, returning per-relay OK outcomes.

        See broadcast_event for the outcome vocabulary. A relay that
        never answers reports "no acknowledgement", which publish()
        treats as failure, not success.
        """
        return broadcast_event(self.relays, event)

    # --- Platform interface ---------------------------------------------

    def publish(self, article: Article) -> PublishResult:
        text = self._compose(article)
        if error := self._check_content_length(text):
            return PublishResult(success=False, platform=self.name, error=error)
        try:
            event = self._signed_event(text, kind=1)
            results = self._publish_event(event)
        except Exception as e:
            return PublishResult(success=False, platform=self.name, error=str(e))
        accepted = [u for u, o in results.items() if o == "accepted"]
        if not accepted:
            detail = "; ".join(f"{u}: {o}" for u, o in results.items())
            return PublishResult(
                success=False,
                platform=self.name,
                error=(
                    f"No relay acknowledged event {event.id} ({detail}). "
                    "The event may still have been stored by a relay that "
                    "stayed silent; check njump before re-posting, since "
                    "kind-1 notes are immutable and a re-post duplicates."
                ),
            )
        return PublishResult(
            success=True,
            platform=self.name,
            article_id=event.id,
            url=f"https://njump.me/{event.bech32()}",
        )

    def update(self, article_id: str, article: Article) -> PublishResult:
        return PublishResult(
            success=False,
            platform=self.name,
            error="Nostr notes are immutable; cannot update (post a new note).",
        )

    def list_articles(self, limit: int = 10) -> list[dict[str, Any]]:
        # Nostr has no authoritative listing across relays; not supported.
        return []

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        return None

    def delete(self, article_id: str) -> DeleteResult:
        """Best-effort NIP-09 deletion: publish a kind-5 event referencing the note."""
        try:
            event = self._signed_event("", kind=5, tags=[["e", article_id]])
            self._publish_event(event)
        except Exception as e:
            return DeleteResult(success=False, platform=self.name, error=str(e))
        return DeleteResult(success=True, platform=self.name)
