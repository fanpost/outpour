"""Tests for the Outpour web UI (Phase 2, queue items 10-13).

Endpoint tests run against a fake service so no real platform is ever
touched. The service layer itself is tested against a temporary
content directory for article discovery and saving.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crier.ui import create_app
from crier.ui import service as ui_service
from crier.ui.app import CSS


class FakeService:
    """In-memory stand-in for UIService, with a secret it must never leak."""

    _secret = "sk-live-sentinel-123"

    def __init__(self):
        self.cancelled: list[str] = []
        self.saved: list[dict] = []
        self.imported: list[dict] = []

    def list_articles(self):
        return [
            {
                "path": "/content/first.md",
                "name": "first.md",
                "title": "First Article",
                "description": "A first article",
                "tags": ["ai"],
                "status": {
                    "devto": {"state": "published", "url": "https://dev.to/x/first", "error": None},
                    "medium": {"state": "failed", "url": None, "error": "manual mode"},
                },
            },
            {
                "path": "/content/second.md",
                "name": "second.md",
                "title": "Second Article",
                "description": "",
                "tags": [],
                "status": {},
            },
        ]

    def get_article(self, path):
        for article in self.list_articles():
            if article["path"] == path:
                return {
                    **article,
                    "canonical_url": "https://example.com/first",
                    "cover_image": "",
                    "body": "# Hello\n\nBody text.",
                    "frontmatter": {"title": article["title"]},
                }
        return None

    def save_article(self, path, fields, body, filename=None):
        if not (fields.get("title") or "").strip():
            raise ValueError("Give the article a title before saving.")
        if body == "trigger-error":
            raise ValueError("Cannot save: bad path")
        self.saved.append({"path": path, "fields": fields, "body": body, "filename": filename})
        return Path(path or f"/content/{filename or 'new'}.md")

    def import_markdown(self, filename, text):
        if not text.strip():
            raise ValueError("That file is empty, so there is nothing to import.")
        if not filename.lower().endswith((".md", ".markdown")):
            raise ValueError("Only Markdown files (.md) can be imported.")
        self.imported.append({"filename": filename, "text": text})
        return Path(f"/content/{Path(filename).stem}.md")

    def list_platforms(self):
        return [
            {"name": "devto", "description": "Dev.to", "configured": True, "mode": "api", "source": "env"},
            {"name": "medium", "description": "Medium", "configured": True, "mode": "manual", "source": None},
            {"name": "hashnode", "description": "Hashnode", "configured": False, "mode": "unconfigured", "source": None},
        ]

    def publish_article(self, path, platforms, draft):
        return [
            {
                "platform": "devto",
                "success": True,
                "url": "https://dev.to/x/first",
                "article_id": "123",
                "error": None,
            },
            {
                "platform": "medium",
                "success": False,
                "url": None,
                "article_id": None,
                "error": "medium is in manual mode (not API)",
            },
        ]

    def schedule_article(self, path, platforms, when, draft):
        if when == "raise-bad-time":
            raise ValueError("Could not parse schedule time: raise-bad-time")
        if when == "not a time at all !!!":
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
        return [
            {
                "platform": platform,
                "success": True,
                "post_id": "abc123",
                "scheduled_time": "2026-11-02T09:00:00+00:00",
                "error": None,
            }
            for platform in platforms
        ]

    def list_scheduled(self):
        return [
            {
                "id": "abc123",
                "file_path": "/content/first.md",
                "file_name": "first.md",
                "platform": "devto",
                "profile": None,
                "scheduled_time": "2026-11-02T09:00:00+00:00",
                "created_at": "2026-10-29T00:00:00+00:00",
                "status": "pending",
                "error": None,
            }
        ]

    def cancel_scheduled(self, post_id):
        self.cancelled.append(post_id)
        return post_id == "abc123"


@pytest.fixture()
def client():
    return TestClient(create_app(service=FakeService()))


def test_articles_page_lists_titles_and_ledger_status(client):
    response = client.get("/articles")
    assert response.status_code == 200
    assert "First Article" in response.text
    assert "Second Article" in response.text
    assert "devto" in response.text
    assert "manual mode" in response.text


def test_articles_empty_state_names_a_real_command():
    class EmptyService(FakeService):
        def list_articles(self):
            return []

    response = TestClient(create_app(service=EmptyService())).get("/articles")
    assert response.status_code == 200
    assert "No articles found" in response.text
    assert "outpour config content add" in response.text
    assert "outpour content add" not in response.text


def test_editor_page_has_fields_platform_checkboxes_and_draft_toggle(client):
    response = client.get("/editor", params={"path": "/content/first.md"})
    assert response.status_code == 200
    assert "First Article" in response.text
    assert "Body text." in response.text
    assert "name='platforms'" in response.text
    assert "name='draft'" in response.text


def test_editor_new_page_has_platform_checkboxes(client):
    response = client.get("/editor/new")
    assert response.status_code == 200
    assert "name='platforms'" in response.text
    assert "Save the article first" in response.text


def test_editor_defaults_to_configured_platforms_only(client):
    import re

    response = client.get("/editor/new")
    assert response.status_code == 200
    assert re.search(r"value='devto'[^>]*checked", response.text)
    assert re.search(r"value='medium'[^>]*checked", response.text)
    assert not re.search(r"value='hashnode'[^>]*checked", response.text)


def test_editor_collapses_advanced_metadata_and_requires_title(client):
    response = client.get("/editor", params={"path": "/content/first.md"})
    assert response.status_code == 200
    assert "<details><summary>Advanced metadata</summary>" in response.text
    assert "name='title' required" in response.text
    details_start = response.text.index("<details>")
    assert "name='canonical_url'" in response.text[details_start:]
    assert "name='cover_image'" in response.text[details_start:]


def test_save_blank_title_rejected_with_input_preserved(client):
    response = client.post(
        "/editor",
        data={
            "path": "/content/first.md",
            "title": "   ",
            "description": "",
            "tags": "ai",
            "canonical_url": "",
            "cover_image": "",
            "body": "kept body",
        },
    )
    assert response.status_code == 400
    assert "Give the article a title before saving." in response.text
    assert "kept body" in response.text


def test_publish_no_platforms_links_back_to_editor(client):
    response = client.post("/publish", data={"path": "/content/first.md"})
    assert response.status_code == 200
    assert "No platforms selected." in response.text
    assert "Edit this article" in response.text
    assert "/editor?path=/content/first.md" in response.text


def test_schedule_error_keeps_time_and_edit_link(client):
    response = client.post(
        "/schedule",
        data={"path": "/content/first.md", "platforms": ["devto"], "when": "raise-bad-time"},
    )
    assert response.status_code == 200
    assert "Could not parse schedule time" in response.text
    assert "When you entered: raise-bad-time" in response.text
    assert "Edit this article" in response.text
    assert "/editor?path=/content/first.md&amp;when=raise-bad-time" in response.text


def test_platform_choice_is_asked_once_not_twice(client):
    import re

    response = client.get("/editor", params={"path": "/content/first.md"})
    assert response.status_code == 200
    # One checkbox set for three platforms, shared by both actions.
    assert response.text.count("name='platforms'") == 3
    assert "formaction='/publish'" in response.text
    assert "formaction='/schedule'" in response.text
    assert "Publish now" in response.text
    assert "Schedule publish" in response.text
    # The draft toggle is shared too.
    assert response.text.count("name='draft'") == 1


def test_editor_reopens_with_the_schedule_time_prefilled(client):
    response = client.get(
        "/editor", params={"path": "/content/first.md", "when": "tomorrow 9am"}
    )
    assert response.status_code == 200
    assert "name='when' value='tomorrow 9am'" in response.text


def test_editor_save_error_preserves_input(client):
    response = client.post(
        "/editor",
        data={
            "path": "/content/first.md",
            "title": "Kept Title",
            "description": "",
            "tags": "ai",
            "canonical_url": "",
            "cover_image": "",
            "body": "trigger-error",
        },
    )
    assert response.status_code == 400
    assert "Cannot save: bad path" in response.text
    assert "Kept Title" in response.text
    assert "trigger-error" in response.text


def test_publish_results_show_success_and_failure_honestly(client):
    response = client.post(
        "/publish",
        data={"path": "/content/first.md", "platforms": ["devto", "medium"], "draft": "1"},
    )
    assert response.status_code == 200
    assert "Published" in response.text
    assert "https://dev.to/x/first" in response.text
    assert "manual mode (not API)" in response.text


def test_publish_results_link_live_url_and_offer_next_steps(client):
    response = client.post(
        "/publish",
        data={"path": "/content/first.md", "platforms": ["devto", "medium"], "draft": "1"},
    )
    assert response.status_code == 200
    assert "<a href='https://dev.to/x/first'>https://dev.to/x/first</a>" in response.text
    assert "Back to articles" in response.text
    assert "Edit this article" in response.text
    assert "/editor?path=/content/first.md" in response.text


def test_schedule_results_offer_next_steps(client):
    response = client.post(
        "/schedule",
        data={"path": "/content/first.md", "platforms": ["devto"], "when": "2026-11-02 09:00"},
    )
    assert response.status_code == 200
    assert "View schedule" in response.text
    assert "Back to articles" in response.text


def test_static_js_confirm_names_selected_platforms(client):
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "input[name='platforms']:checked" in response.text
    assert "the selected platforms" in response.text
    assert "chosen.join" in response.text


def test_schedule_results_and_unparseable_time(client):
    ok = client.post(
        "/schedule",
        data={"path": "/content/first.md", "platforms": ["devto"], "when": "2026-11-02 09:00"},
    )
    assert ok.status_code == 200
    assert "Scheduled" in ok.text
    assert "abc123" in ok.text

    bad = client.post(
        "/schedule",
        data={"path": "/content/first.md", "platforms": ["devto"], "when": "not a time at all !!!"},
    )
    assert bad.status_code == 200
    assert "Could not parse schedule time" in bad.text


def test_schedule_page_and_cancel(client):
    page = client.get("/schedule")
    assert page.status_code == 200
    assert "abc123" in page.text
    assert "first.md" in page.text
    cancelled = client.post("/schedule/cancel", data={"post_id": "abc123"}, follow_redirects=False)
    assert cancelled.status_code == 303
    assert cancelled.headers["location"] == "/schedule"


def test_platforms_page_never_shows_key_values(client):
    response = client.get("/platforms")
    assert response.status_code == 200
    assert "devto" in response.text
    assert "unconfigured" in response.text
    assert FakeService._secret not in response.text


def test_pages_carry_hosted_waitlist_strip(client):
    for route in ("/articles", "/platforms", "/schedule"):
        response = client.get(route)
        assert response.status_code == 200
        assert "Join the hosted waitlist" in response.text
        assert "docs.google.com/forms" in response.text


def test_hosted_strip_names_price_and_founding_lock(client):
    response = client.get("/articles")
    assert response.status_code == 200
    assert "Expected $19 a month" in response.text
    assert "founding price" in response.text


def test_platforms_page_states_keys_stay_local(client):
    response = client.get("/platforms")
    assert response.status_code == 200
    assert "Your keys live in your local config file" in response.text
    assert "free and open source" in response.text


def test_css_type_scale_has_at_most_five_sizes():
    # The checklist caps a page at 5 text sizes. The UI keeps four:
    # 1.75rem (h1), 1.25rem (h2), 1rem (body and h3) and .85rem
    # (small print). Body has no font-size rule, so it is the 1rem base.
    sizes = {float(value) for value in re.findall(r"font-size:\s*([\d.]+)rem", CSS)}
    assert sizes <= {1.75, 1.25, 1.0, 0.85}
    assert len(sizes) <= 5


def test_css_spacing_uses_one_scale():
    # One spacing scale: every margin, padding and gap value is 0, auto,
    # or a multiple of .25rem up to 2rem, so sections share one rhythm.
    allowed = {0.0, 0.25, 0.5, 1.0, 2.0}
    for declaration in re.findall(r"(?:margin|padding|gap)[^:]*:([^;}]+)[;}]", CSS):
        for token in declaration.replace(",", " ").split():
            if token.endswith("rem"):
                assert float(token[:-3]) in allowed, token
            else:
                assert token in {"0", "auto"}, token


def test_pages_have_dark_mode_toggle_and_theme_script(client):
    response = client.get("/articles")
    assert response.status_code == 200
    assert "id='theme-toggle'" in response.text
    assert "outpour-theme" in response.text
    js = client.get("/static/app.js")
    assert "outpour-theme" in js.text
    assert "Courier" in response.text  # typewriter font stack ships in the CSS


def test_publish_and_schedule_forms_carry_progress_state(client):
    response = client.get("/editor", params={"path": "/content/first.md"})
    assert response.status_code == 200
    assert "data-progress='Publishing...'" in response.text
    assert "data-progress='Scheduling...'" in response.text


def test_editor_new_page_has_import_form(client):
    response = client.get("/editor/new")
    assert response.status_code == 200
    assert "action='/editor/import'" in response.text
    assert "type='file'" in response.text


def test_import_markdown_redirects_into_editor(client):
    response = client.post(
        "/editor/import",
        files={"file": ("note.md", "---\ntitle: Imported\n---\n\nBody.\n", "text/markdown")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/editor?path=/content/note.md")


def test_import_rejects_non_markdown_and_empty_files(client):
    bad = client.post("/editor/import", files={"file": ("note.txt", "hello", "text/plain")})
    assert bad.status_code == 400
    assert "Only Markdown files" in bad.text
    empty = client.post("/editor/import", files={"file": ("note.md", "", "text/markdown")})
    assert empty.status_code == 400
    assert "empty" in empty.text


def test_editor_has_status_line_and_focus_toggle(client):
    response = client.get("/editor", params={"path": "/content/first.md"})
    assert response.status_code == 200
    assert "id='editor-status'" in response.text
    assert "4 words" in response.text  # the fake article body is 4 words
    assert "id='focus-toggle'" in response.text
    js = client.get("/static/app.js")
    assert "editor-status" in js.text
    assert "focus-toggle" in js.text


def test_service_import_markdown_keeps_content_and_renames_on_collision(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setattr(ui_service.config, "get_content_paths", lambda: [str(content)])
    monkeypatch.setattr(ui_service.config, "get_project_root", lambda: tmp_path)
    text = "---\ntitle: Kept\nslug: custom-key\n---\n\nBody.\n"
    first = ui_service.import_markdown("post.markdown", text)
    assert first.name == "post.md"
    assert first.read_text() == text
    second = ui_service.import_markdown("post.md", text)
    assert second.name == "post-2.md"


def test_static_js_served(client):
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "confirm" in response.text


def test_static_js_handles_progress_state(client):
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "data-progress" in response.text
    assert "disabled" in response.text
    assert "defaultPrevented" in response.text


def test_static_js_reads_confirm_and_progress_from_the_clicked_button(client):
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "event.submitter" in response.text
    assert 'getAttribute("data-confirm")' in response.text
    assert 'getAttribute("data-progress")' in response.text
    # The schedule button makes "when" required; publish now does not.
    assert "data-require-when" in response.text
    assert "when.required" in response.text


def test_service_discovers_articles_in_content_dir(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    (content / "with-frontmatter.md").write_text(
        "---\ntitle: Hello World\ntags: [ai, seo]\n---\n\nBody here.\n"
    )
    (content / "plain.md").write_text("# No frontmatter\n")
    monkeypatch.setattr(ui_service.config, "get_content_paths", lambda: [str(content)])
    monkeypatch.setattr(ui_service.config, "get_file_extensions", lambda: [".md"])
    monkeypatch.setattr(ui_service.config, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(ui_service.registry, "get_article_by_file", lambda path: None)
    articles = ui_service.list_articles()
    assert [a["title"] for a in articles] == ["plain", "Hello World"] or {
        a["title"] for a in articles
    } == {"plain", "Hello World"}
    by_name = {a["name"]: a for a in articles}
    assert by_name["with-frontmatter.md"]["tags"] == ["ai", "seo"]
    assert by_name["plain.md"]["title"] == "plain"


def test_service_save_blank_title_rejected(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setattr(ui_service.config, "get_content_paths", lambda: [str(content)])
    monkeypatch.setattr(ui_service.config, "get_project_root", lambda: tmp_path)
    with pytest.raises(ValueError, match="title before saving"):
        ui_service.save_article(
            None,
            {"title": "   ", "description": "", "tags": "", "canonical_url": "", "cover_image": ""},
            "# Body\n",
            filename="no-title",
        )
    assert not (content / "no-title.md").exists()


def test_service_save_round_trip(tmp_path, monkeypatch):
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setattr(ui_service.config, "get_content_paths", lambda: [str(content)])
    monkeypatch.setattr(ui_service.config, "get_project_root", lambda: tmp_path)
    saved = ui_service.save_article(
        None,
        {"title": "Saved Article", "description": "Desc", "tags": "ai, seo", "canonical_url": "", "cover_image": ""},
        "# Body\n",
        filename="saved-article",
    )
    assert saved.name == "saved-article.md"
    assert "title: Saved Article" in saved.read_text()
    loaded = ui_service.get_article(str(saved))
    assert loaded["title"] == "Saved Article"
    assert loaded["tags"] == ["ai", "seo"]
    assert loaded["body"].startswith("# Body")


def test_serve_command_binds_localhost_only(monkeypatch):
    import sys
    import types

    from click.testing import CliRunner

    from crier.cli import cli

    calls: dict = {}

    stub = types.ModuleType("uvicorn")

    def fake_run(app, host=None, port=None, **kwargs):
        calls["host"] = host
        calls["port"] = port

    stub.run = fake_run
    monkeypatch.setitem(sys.modules, "uvicorn", stub)
    result = CliRunner().invoke(cli, ["serve", "--port", "8123"])
    assert result.exit_code == 0, result.output
    assert calls == {"host": "127.0.0.1", "port": 8123}
