"""Shared test fixtures for crier tests."""


import pytest
import yaml

from crier.platforms.base import Article


@pytest.fixture
def sample_article():
    """Create a sample Article for testing."""
    return Article(
        title="Test Article Title",
        body="This is the body of the test article.\n\nIt has multiple paragraphs.",
        description="A brief description of the test article",
        tags=["python", "testing", "crier"],
        canonical_url="https://example.com/test-article",
        published=True,
    )


@pytest.fixture
def sample_markdown_file(tmp_path):
    """Create a sample markdown file with front matter."""
    content = """\
---
title: "Test Article Title"
description: "A brief description"
tags: [python, testing]
canonical_url: https://example.com/test-article
published: true
---

This is the body of the test article.

It has multiple paragraphs.
"""
    md_file = tmp_path / "test_article.md"
    md_file.write_text(content)
    return md_file


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    """Create a temporary global config file and patch the config path.

    All config is global-only now — no local .crier/config.yaml.
    The .crier/ directory is only for the registry.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"

    # Patch the config path
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_FILE", config_file)
    monkeypatch.setattr("crier.config.DEFAULT_CONFIG_DIR", config_dir)

    # Clear any cached config
    monkeypatch.delenv("CRIER_CONFIG", raising=False)

    # Change to tmp_path so registry can find .crier/ here if needed
    monkeypatch.chdir(tmp_path)

    return config_file


@pytest.fixture
def tmp_registry(tmp_path, monkeypatch):
    """Create a temporary SQLite registry with isolated config."""
    from crier.registry import init_db, reset_connection

    db_path = tmp_path / "crier.db"

    # Point CRIER_DB to the temp database
    monkeypatch.setenv("CRIER_DB", str(db_path))

    # Set up isolated config with site_root pointing to tmp_path
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.yaml"
    config_file.write_text(yaml.dump({"site_root": str(tmp_path)}))
    monkeypatch.setenv("CRIER_CONFIG", str(config_file))
    monkeypatch.chdir(tmp_path)

    # Reset any cached connection and initialize fresh DB
    reset_connection()
    init_db(db_path)

    yield tmp_path

    # Clean up connection
    reset_connection()


@pytest.fixture
def mock_env_api_key(monkeypatch):
    """Factory fixture to set environment API keys."""
    def _set_key(platform: str, value: str):
        monkeypatch.setenv(f"CRIER_{platform.upper()}_API_KEY", value)
    return _set_key


@pytest.fixture
def configured_platforms(tmp_config):
    """Create a config with some platforms configured."""
    config = {
        "platforms": {
            "devto": {"api_key": "devto_test_key"},
            "bluesky": {"api_key": "handle.bsky.social:app-password"},
            "twitter": {"api_key": "manual"},
            "linkedin": {"api_key": ""},
        },
        "profiles": {
            "blogs": ["devto", "hashnode"],
            "social": ["bluesky", "mastodon"],
            "all": ["blogs", "social"],
        },
        "content_paths": ["posts", "articles"],
    }
    tmp_config.write_text(yaml.dump(config))
    return tmp_config


@pytest.fixture(autouse=True)
def prevent_live_http(monkeypatch):
    """Tests must supply remote responses rather than contact publishing services."""
    import requests

    def blocked_request(*args, **kwargs):
        raise AssertionError('Unmocked HTTP request blocked during tests')

    monkeypatch.setattr(requests.sessions.Session, 'request', blocked_request)


@pytest.fixture
def recording_platform(tmp_registry, monkeypatch):
    """A real adapter contract with an in-memory remote, isolated from the registry."""
    from crier.platforms import PLATFORMS
    from crier.platforms.base import Platform, PublishResult, ThreadPublishResult
    from dataclasses import replace

    class RecordingPlatform(Platform):
        name = 'test_platform'
        supports_threads = True
        max_content_length = 100
        articles = []
        threads = []
        failure = None

        def publish(self, article):
            self.articles.append(replace(article, tags=list(article.tags or [])))
            if self.failure:
                raise RuntimeError(self.failure)
            return PublishResult(True, self.name, 'remote-1', 'https://remote/1')

        def publish_thread(self, posts):
            self.threads.append(list(posts))
            return ThreadPublishResult(True, self.name, 'thread-1', 'https://remote/t1',
                                       ['thread-1', 'thread-2'],
                                       ['https://remote/t1', 'https://remote/t2'])

        def update(self, article_id, article):
            return self.publish(article)

        def list_articles(self, limit=10):
            return []

        def get_article(self, article_id):
            return None

    monkeypatch.setitem(PLATFORMS, RecordingPlatform.name, RecordingPlatform)
    monkeypatch.setenv('CRIER_TEST_PLATFORM_API_KEY', 'test-secret')
    return RecordingPlatform
