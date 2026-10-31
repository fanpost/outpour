"""Tests for the front-matter bootstrap helper (dogfood follow-up).

A draft with no front matter is found by audit (its title falls back to
the filename stem), but it then publishes under that stem with no
explicit metadata. Bootstrap gives such drafts a real title from their
first heading, without ever touching body text.
"""

from click.testing import CliRunner

from crier.cli import cli
from crier.converters import bootstrap_front_matter, parse_front_matter


def test_no_front_matter_takes_title_from_first_heading():
    content = "# How To Follow Up\n\nBody text.\n"
    new_content, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is True
    assert detail == "How To Follow Up"
    frontmatter, body = parse_front_matter(new_content)
    assert frontmatter["title"] == "How To Follow Up"
    # The heading stays in the body: bootstrap never alters body text.
    assert body == "# How To Follow Up\n\nBody text."


def test_no_front_matter_without_heading_falls_back_to_filename():
    content = "Just paragraphs, no heading.\n"
    new_content, changed, detail = bootstrap_front_matter(
        content, "ai-lead-follow-up"
    )
    assert changed is True
    assert detail == "Ai Lead Follow Up"
    frontmatter, _body = parse_front_matter(new_content)
    assert frontmatter["title"] == "Ai Lead Follow Up"


def test_heading_link_yields_link_text():
    content = "# [Hello World](https://example.com)\n\nBody.\n"
    _new, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is True
    assert detail == "Hello World"


def test_file_with_title_is_untouched():
    content = "---\ntitle: Existing\n---\n\nBody.\n"
    new_content, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is False
    assert detail == "already has a title"
    assert new_content == content


def test_front_matter_without_title_gains_only_a_title_line():
    content = "---\ntags: [ai]\n---\n\nBody.\n"
    new_content, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is True
    assert detail == "Draft"
    frontmatter, body = parse_front_matter(new_content)
    assert frontmatter["title"] == "Draft"
    assert frontmatter["tags"] == ["ai"]
    assert body == "Body."


def test_toml_front_matter_without_title_gains_title():
    content = "+++\ntags = [\"ai\"]\n+++\n\nBody.\n"
    new_content, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is True
    assert detail == "Draft"
    frontmatter, body = parse_front_matter(new_content)
    assert frontmatter["title"] == "Draft"
    assert body == "Body."


def test_title_with_colon_round_trips_through_yaml():
    content = "# Lead follow-up: what actually works\n\nBody.\n"
    new_content, changed, _detail = bootstrap_front_matter(content, "draft")
    assert changed is True
    frontmatter, _body = parse_front_matter(new_content)
    assert frontmatter["title"] == "Lead follow-up: what actually works"


def test_unparseable_front_matter_is_untouched():
    content = "---\ntitle: [broken\n---\n\nBody.\n"
    new_content, changed, detail = bootstrap_front_matter(content, "draft")
    assert changed is False
    assert detail == "unparseable front matter"
    assert new_content == content


def test_cli_bootstraps_file_and_leaves_body_intact(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "crier.config.get_exclude_patterns", lambda: ["_index.md"]
    )
    target = tmp_path / "my-draft.md"
    target.write_text("# Real Title\n\nBody stays exactly.\n")
    titled = tmp_path / "titled.md"
    titled.write_text("---\ntitle: Kept\n---\n\nBody.\n")
    index = tmp_path / "_index.md"
    index.write_text("# Index\n\nBody.\n")

    result = CliRunner().invoke(cli, ["bootstrap", str(tmp_path)])
    assert result.exit_code == 0, result.output
    # Excluded names never enter the file list, so only the titled file
    # counts as skipped; the index file is simply left alone.
    assert "1 added, 1 skipped" in result.output
    frontmatter, body = parse_front_matter(target.read_text())
    assert frontmatter["title"] == "Real Title"
    # Heading stays in the body: bootstrap never alters body text.
    assert body == "# Real Title\n\nBody stays exactly."
    assert titled.read_text().startswith("---\ntitle: Kept")
    assert index.read_text() == "# Index\n\nBody.\n"


def test_cli_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("crier.config.get_exclude_patterns", lambda: [])
    target = tmp_path / "draft.md"
    original = "# Dry Title\n\nBody.\n"
    target.write_text(original)

    result = CliRunner().invoke(
        cli, ["bootstrap", "--dry-run", str(target)]
    )
    assert result.exit_code == 0, result.output
    assert "1 would be added" in result.output
    assert target.read_text() == original
