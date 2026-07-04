"""Content scheduling for crier.

This module provides scheduling functionality for delayed publishing:
- ScheduledPost dataclass to represent scheduled posts
- schedule.yaml storage for persistence
- Time parsing with natural language support (via dateparser)
- Cron-friendly run command for processing due schedules
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import os
import tempfile
import uuid
import yaml

# A runner crash can leave posts stuck in "publishing"; claims older than
# this are considered abandoned and become claimable again.
STALE_CLAIM_MINUTES = 30


def _ensure_aware(dt: datetime) -> datetime:
    """Coerce a naive datetime to UTC (stored times are always UTC).

    schedule.yaml is human-editable; a hand-edited naive timestamp must
    not crash every aware comparison in the scheduler.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class ScheduledPost:
    """Represents a scheduled publish operation."""

    id: str
    file_path: str
    platform: str
    scheduled_time: datetime
    created_at: datetime
    status: str  # pending, publishing, published, failed, cancelled
    error: str | None = None
    rewrite: str | None = None
    auto_rewrite: bool = False
    profile: str | None = None  # Profile to use instead of single platform
    rewrite_author: str | None = None  # Who authored the rewrite text
    claimed_at: datetime | None = None  # When a runner claimed this post

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "platform": self.platform,
            "scheduled_time": self.scheduled_time.isoformat(),
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "error": self.error,
            "rewrite": self.rewrite,
            "auto_rewrite": self.auto_rewrite,
            "profile": self.profile,
            "rewrite_author": self.rewrite_author,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScheduledPost":
        """Create from dictionary."""
        claimed_at = data.get("claimed_at")
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            platform=data["platform"],
            scheduled_time=_ensure_aware(
                datetime.fromisoformat(data["scheduled_time"])
            ),
            created_at=_ensure_aware(
                datetime.fromisoformat(data["created_at"])
            ),
            status=data["status"],
            error=data.get("error"),
            rewrite=data.get("rewrite"),
            auto_rewrite=data.get("auto_rewrite", False),
            profile=data.get("profile"),
            rewrite_author=data.get("rewrite_author"),
            claimed_at=(
                _ensure_aware(datetime.fromisoformat(claimed_at))
                if claimed_at else None
            ),
        )


def get_schedule_path() -> Path:
    """Get the schedule.yaml file path."""
    from .config import get_site_root

    root = get_site_root() or Path.cwd()
    return root / ".crier" / "schedule.yaml"


def load_schedule() -> dict[str, Any]:
    """Load the schedule from disk."""
    schedule_file = get_schedule_path()

    if not schedule_file.exists():
        return {"version": 1, "scheduled_posts": []}

    with open(schedule_file) as f:
        data = yaml.safe_load(f) or {}

    return data


def save_schedule(schedule: dict[str, Any]) -> None:
    """Save the schedule to disk atomically.

    Writes to a temp file in the same directory and os.replace()s it into
    place, so a crash mid-write can never truncate schedule.yaml.
    """
    schedule_file = get_schedule_path()
    schedule_file.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=schedule_file.parent, prefix=".schedule-", suffix=".yaml"
    )
    try:
        with os.fdopen(fd, "w") as f:
            yaml.safe_dump(schedule, f, default_flow_style=False, sort_keys=False)
        os.replace(tmp_path, schedule_file)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@contextmanager
def _schedule_lock():
    """Serialize read-modify-write cycles on schedule.yaml.

    An hourly cron runner and a manual `crier publish --schedule` can
    overlap; without a lock one write clobbers the other. Uses flock on
    POSIX; degrades to no locking where fcntl is unavailable (Windows),
    matching the previous behavior there.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return

    lock_path = get_schedule_path().with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def create_scheduled_post(
    file_path: str,
    platform: str,
    scheduled_time: datetime,
    rewrite: str | None = None,
    auto_rewrite: bool = False,
    profile: str | None = None,
    rewrite_author: str | None = None,
) -> ScheduledPost:
    """Create and save a new scheduled post.

    Args:
        file_path: Path to the markdown file
        platform: Platform name (or empty string if using profile)
        scheduled_time: When to publish (should be UTC)
        rewrite: Optional custom rewrite content
        auto_rewrite: Whether to use LLM auto-rewrite
        profile: Optional profile name to use instead of platform
        rewrite_author: Label for who wrote the rewrite content

    Returns:
        The created ScheduledPost
    """
    # Ensure scheduled_time is in UTC
    if scheduled_time.tzinfo is None:
        scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)

    post = ScheduledPost(
        id=str(uuid.uuid4())[:8],
        file_path=str(file_path),
        platform=platform,
        scheduled_time=scheduled_time,
        created_at=datetime.now(timezone.utc),
        status="pending",
        rewrite=rewrite,
        auto_rewrite=auto_rewrite,
        profile=profile,
        rewrite_author=rewrite_author,
    )

    with _schedule_lock():
        schedule = load_schedule()
        schedule["scheduled_posts"].append(post.to_dict())
        save_schedule(schedule)

    return post


def get_scheduled_post(post_id: str) -> ScheduledPost | None:
    """Get a scheduled post by ID."""
    schedule = load_schedule()

    for post_data in schedule.get("scheduled_posts", []):
        if post_data["id"] == post_id or post_data["id"].startswith(post_id):
            return ScheduledPost.from_dict(post_data)

    return None


def list_scheduled_posts(
    status: str | None = None,
) -> list[ScheduledPost]:
    """List scheduled posts, optionally filtered by status.

    Args:
        status: Filter by status (pending, published, failed, cancelled)

    Returns:
        List of ScheduledPost objects
    """
    schedule = load_schedule()
    posts = []

    for post_data in schedule.get("scheduled_posts", []):
        if status is None or post_data["status"] == status:
            posts.append(ScheduledPost.from_dict(post_data))

    # Sort by scheduled_time
    posts.sort(key=lambda p: p.scheduled_time)
    return posts


def get_due_posts() -> list[ScheduledPost]:
    """Get all pending posts that are due for publishing.

    Returns posts where:
    - status == "pending"
    - scheduled_time <= now

    Returns:
        List of due ScheduledPost objects
    """
    now = datetime.now(timezone.utc)
    posts = list_scheduled_posts(status="pending")

    return [p for p in posts if p.scheduled_time <= now]


def claim_due_posts(
    stale_after_minutes: int = STALE_CLAIM_MINUTES,
) -> list[ScheduledPost]:
    """Atomically claim all due posts for publishing.

    Under the schedule lock, marks every claimable post "publishing" and
    stamps claimed_at, so an overlapping runner (cron + manual) claims
    nothing and cannot double-publish. Claimable posts are:
    - pending with scheduled_time <= now
    - stuck in "publishing" with a claim older than stale_after_minutes
      (a previous runner crashed mid-publish)

    Returns:
        The claimed ScheduledPost objects (status already "publishing").
    """
    now = datetime.now(timezone.utc)
    claimed: list[ScheduledPost] = []

    with _schedule_lock():
        schedule = load_schedule()

        for post_data in schedule.get("scheduled_posts", []):
            status = post_data.get("status")
            if status == "pending":
                due = _ensure_aware(
                    datetime.fromisoformat(post_data["scheduled_time"])
                ) <= now
            elif status == "publishing":
                claimed_at = post_data.get("claimed_at")
                due = claimed_at is None or (
                    now - _ensure_aware(datetime.fromisoformat(claimed_at))
                    > timedelta(minutes=stale_after_minutes)
                )
            else:
                due = False

            if due:
                post_data["status"] = "publishing"
                post_data["claimed_at"] = now.isoformat()
                claimed.append(ScheduledPost.from_dict(post_data))

        if claimed:
            save_schedule(schedule)

    return claimed


def update_scheduled_post(
    post_id: str,
    status: str | None = None,
    error: str | None = None,
) -> bool:
    """Update a scheduled post's status.

    Args:
        post_id: Post ID (or prefix)
        status: New status
        error: Error message (for failed status)

    Returns:
        True if updated, False if not found
    """
    with _schedule_lock():
        schedule = load_schedule()

        for post_data in schedule.get("scheduled_posts", []):
            if post_data["id"] == post_id or post_data["id"].startswith(post_id):
                if status:
                    post_data["status"] = status
                if error is not None:
                    post_data["error"] = error
                save_schedule(schedule)
                return True

    return False


def cancel_scheduled_post(post_id: str) -> bool:
    """Cancel a scheduled post.

    Args:
        post_id: Post ID (or prefix)

    Returns:
        True if cancelled, False if not found or not pending
    """
    schedule = load_schedule()

    for post_data in schedule.get("scheduled_posts", []):
        if post_data["id"] == post_id or post_data["id"].startswith(post_id):
            if post_data["status"] != "pending":
                return False
            post_data["status"] = "cancelled"
            save_schedule(schedule)
            return True

    return False


def delete_scheduled_post(post_id: str) -> bool:
    """Delete a scheduled post from the schedule.

    Args:
        post_id: Post ID (or prefix)

    Returns:
        True if deleted, False if not found
    """
    with _schedule_lock():
        schedule = load_schedule()
        original_count = len(schedule.get("scheduled_posts", []))

        schedule["scheduled_posts"] = [
            p for p in schedule.get("scheduled_posts", [])
            if not (p["id"] == post_id or p["id"].startswith(post_id))
        ]

        if len(schedule["scheduled_posts"]) < original_count:
            save_schedule(schedule)
            return True

    return False


def parse_schedule_time(time_str: str) -> datetime | None:
    """Parse a schedule time string into a datetime.

    Supports:
    - ISO format: "2025-01-24 09:00" or "2025-01-24T09:00:00"
    - Natural language: "tomorrow 9am", "in 2 hours", "next monday 10am"

    The dateparser library is used for natural language parsing.
    Naive input (no explicit timezone) is interpreted as LOCAL wall-clock
    time; explicit offsets in the input are honored. The result is always
    converted to UTC for storage.

    Args:
        time_str: Time string to parse

    Returns:
        datetime in UTC, or None if parsing failed
    """
    try:
        import dateparser
    except ImportError:
        # Fall back to basic ISO parsing if dateparser not installed
        try:
            dt = datetime.fromisoformat(time_str)
            # Naive input means local time; astimezone() on a naive
            # datetime attaches the local zone before converting.
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    # Use dateparser for natural language
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
        # Naive input is the user's local wall-clock time; convert to
        # UTC for storage. TIMEZONE only applies when the input itself
        # carries no timezone, so explicit offsets are still honored.
        "TIMEZONE": "local",
        "TO_TIMEZONE": "UTC",
    }

    parsed = dateparser.parse(time_str, settings=settings)

    if parsed:
        # Ensure UTC
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)

    return parsed


def cleanup_old_posts(days: int = 30) -> int:
    """Remove old completed/cancelled posts from schedule.

    Args:
        days: Remove posts older than this many days

    Returns:
        Number of posts removed
    """
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)

    with _schedule_lock():
        schedule = load_schedule()
        original_count = len(schedule.get("scheduled_posts", []))

        schedule["scheduled_posts"] = [
            p for p in schedule.get("scheduled_posts", [])
            if p["status"] == "pending" or
            _ensure_aware(
                datetime.fromisoformat(p["scheduled_time"])
            ).timestamp() > cutoff
        ]

        removed = original_count - len(schedule["scheduled_posts"])
        if removed > 0:
            save_schedule(schedule)

    return removed
