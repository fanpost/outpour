"""Guards for the README landing copy.

The intro paragraph was mangled by a main-chat edit on 2026-11-19
(a comma splice with no subject: "Paste into different editors, ...
tags, Outpour removes that tax"). These tests pin the repaired
copy and the Try now link so a later edit cannot silently
reintroduce the breakage.
"""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def _text():
    return README.read_text(encoding="utf-8")


def test_intro_sentence_has_a_subject():
    text = _text()
    assert "You paste it into four different editors" in text
    assert "tags, Outpour removes that tax" not in text


def test_try_now_link_points_at_quick_start():
    text = _text()
    assert (
        "https://github.com/fanpost/outpour/blob/master/README.md#quick-start"
        in text
    )
    assert "## Quick start" in text


def test_readme_has_no_em_dash():
    assert "\u2014" not in _text()
