"""Dry-run honesty: the preview must show what publish will really do.

Covers the three open dogfood gaps from MVP-TEST-REPORT.md:
1. Dev.to silently sanitizes tags; the dry-run preview must show the
   tags as they will be sent.
2. The pre-publish check printed only a warning count; it must itemize
   each warning.
3. The dry run did not validate the Nostr key format, so a bad key
   only failed at real publish time.
"""

import pytest
import yaml
from click.testing import CliRunner

from crier.cli import cli
from crier.platforms.base import Platform
from crier.platforms.devto import DevTo, sanitize_tags
from crier.platforms.nostr import Nostr
from crier.platforms.nostr_longform import NostrLongform


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config_and_registry(tmp_path, monkeypatch):
    """Mock config and SQLite registry, as in test_cli.py."""
    from crier.registry import init_db, reset_connection

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config = {
        "platforms": {
            "devto": {"api_key": "test_devto_key"},
            "nostr-longform": {"api_key": "not-a-real-key"},
            "nostr": {"api_key": "also-not-a-real-key"},
        },
        "content_paths": [str(tmp_path / "posts")],
    }
    config_file.write_text(yaml.dump(config))
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.delenv("CRIER_CONFIG", raising=False)

    db_path = tmp_path / "crier.db"
    monkeypatch.setenv("CRIER_DB", str(db_path))
    reset_connection()
    init_db(db_path)

    monkeypatch.chdir(tmp_path)

    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()

    yield {
        "config_file": config_file,
        "db_path": db_path,
        "posts_dir": posts_dir,
        "tmp_path": tmp_path,
    }

    reset_connection()


def _article(path, tags):
    path.write_text(f"""\
---
title: Test Article
description: A test description
tags: [{", ".join(tags)}]
canonical_url: https://example.com/test
---

Content here, short.
""")


class TestPreviewTags:
    def test_devto_sanitizes_hyphenated_tags(self):
        assert sanitize_tags(["ai-lead-follow-up", "python"]) == [
            "aileadfollowup",
            "python",
        ]

    def test_devto_caps_at_four_tags(self):
        assert sanitize_tags(["a", "b", "c", "d", "e"]) == ["a", "b", "c", "d"]

    def test_devto_preview_tags_matches_sanitize(self):
        assert DevTo("key").preview_tags(["ai-lead-follow-up", "python"]) == [
            "aileadfollowup",
            "python",
        ]

    def test_base_preview_tags_unchanged(self):
        class Plain(Platform):
            name = "plain"

            def publish(self, article):
                raise NotImplementedError

            def update(self, article_id, article):
                raise NotImplementedError

            def list_articles(self, limit=10):
                return []

            def get_article(self, article_id):
                return None

        assert Plain("key").preview_tags(["ai-lead-follow-up"]) == [
            "ai-lead-follow-up"
        ]


class TestValidateCredentials:
    @pytest.mark.parametrize("cls", [Nostr, NostrLongform])
    def test_bad_key_returns_error(self, cls):
        err = cls("not-a-real-key").validate_credentials()
        assert err, "a malformed key must report an error"

    @pytest.mark.parametrize("cls", [Nostr, NostrLongform])
    def test_valid_hex_key_ok(self, cls):
        from pynostr.key import PrivateKey

        assert cls(PrivateKey().hex()).validate_credentials() is None

    @pytest.mark.parametrize("cls", [Nostr, NostrLongform])
    def test_valid_nsec_key_ok(self, cls):
        from pynostr.key import PrivateKey

        assert cls(PrivateKey().bech32()).validate_credentials() is None

    @pytest.mark.parametrize("cls", [Nostr, NostrLongform])
    def test_key_with_relay_suffix_ok(self, cls):
        from pynostr.key import PrivateKey

        key = PrivateKey().hex()
        assert cls(f"{key}|wss://relay.damus.io").validate_credentials() is None

    def test_base_validate_credentials_ok(self):
        class Plain(Platform):
            name = "plain"

            def publish(self, article):
                raise NotImplementedError

            def update(self, article_id, article):
                raise NotImplementedError

            def list_articles(self, limit=10):
                return []

            def get_article(self, article_id):
                return None

        assert Plain("anything").validate_credentials() is None


class TestDryRunPreview:
    def test_dry_run_shows_devto_tags_as_sent(
        self, runner, mock_config_and_registry, monkeypatch
    ):
        # Wide terminal so the Rich table does not wrap the note.
        monkeypatch.setenv("COLUMNS", "200")
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        _article(
            test_file,
            ["ai-lead-follow-up", "python", "testing", "extra-tag", "fifth-tag"],
        )

        result = runner.invoke(
            cli, ["publish", str(test_file), "--to", "devto", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        # Hyphens stripped, fifth tag dropped by the 4-tag cap.
        assert "Tags as sent: aileadfollowup, python, testing, extratag" in result.output

    def test_dry_run_no_tag_note_when_tags_unchanged(
        self, runner, mock_config_and_registry
    ):
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        _article(test_file, ["python", "testing"])

        result = runner.invoke(
            cli, ["publish", str(test_file), "--to", "devto", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Tags as sent" not in result.output
        assert "Would publish" in result.output

    def test_dry_run_flags_bad_nostr_key(
        self, runner, mock_config_and_registry
    ):
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        _article(test_file, ["python"])

        result = runner.invoke(
            cli,
            ["publish", str(test_file), "--to", "devto", "--to", "nostr-longform", "--dry-run"],
        )
        assert result.exit_code == 0, result.output
        assert "Bad credentials" in result.output
        assert "nostr-longform" in result.output
        # The bad-key platform is not shown as Ready; devto still is.
        assert result.output.count("Ready") == 1

    def test_dry_run_valid_nostr_key_is_ready(
        self, runner, mock_config_and_registry
    ):
        from pynostr.key import PrivateKey

        import yaml as _yaml

        config_file = mock_config_and_registry["config_file"]
        config = _yaml.safe_load(config_file.read_text())
        config["platforms"]["nostr-longform"]["api_key"] = PrivateKey().hex()
        config_file.write_text(_yaml.dump(config))

        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        _article(test_file, ["python"])

        result = runner.invoke(
            cli, ["publish", str(test_file), "--to", "nostr-longform", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Bad credentials" not in result.output
        assert "Ready" in result.output

    def test_dry_run_itemizes_prepublish_warnings(
        self, runner, mock_config_and_registry
    ):
        # No 'date' in front matter and a 3-word body both warn.
        test_file = mock_config_and_registry["posts_dir"] / "test.md"
        _article(test_file, ["python"])

        result = runner.invoke(
            cli, ["publish", str(test_file), "--to", "devto", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        assert "Pre-publish check: 2 warnings" in result.output
        assert "missing-date" in result.output
        assert "short-body" in result.output
