"""Guards for the changelog.

The changelog stopped at the upstream Crier 2.1.1 entry while the
repo had already shipped Outpour 0.1.0, 0.2.0, and 0.2.1. These
tests pin the Outpour release entries so a later edit cannot
silently drop the release history again.
"""

from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def _text():
    return CHANGELOG.read_text(encoding="utf-8")


def test_changelog_covers_all_outpour_releases():
    text = _text()
    assert "## 0.1.0" in text
    assert "## 0.2.0" in text
    assert "## 0.2.1" in text
    assert "## Unreleased" in text


def test_changelog_names_the_headline_features():
    text = _text()
    assert "NIP-23" in text
    assert "Idempotent" in text
    assert "web UI" in text
    assert "wheel build" in text


def test_changelog_has_no_em_dash():
    assert "\u2014" not in _text()
