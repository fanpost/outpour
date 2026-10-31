"""FastAPI web UI for Outpour (Phase 2).

Server-rendered pages plus vanilla JS. No new publishing logic lives
here: every action calls the service layer, which calls the existing
publishing and scheduler code paths. The server binds 127.0.0.1 only
(see the `outpour serve` command), so this UI is for the machine it
runs on; it has no login of its own and must not be exposed publicly.
"""

from __future__ import annotations

import html
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .service import UIService

CSS = """
body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}
nav a{margin-right:1rem} table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:.4rem;text-align:left;vertical-align:top}
.ok{color:#067647}.bad{color:#b42318}.dim{color:#666}
label{display:block;margin:.6rem 0 .2rem} input[type=text],textarea{width:100%;padding:.4rem}
textarea{height:22rem;font-family:monospace} button{padding:.4rem 1rem;margin-top:.8rem}
fieldset{margin:1rem 0} .card{border:1px solid #ccc;padding:1rem;margin:1rem 0}
button.primary{background:#0b5cab;color:#fff;border:1px solid #0b5cab}
.hosted{color:#444;font-size:.95rem}
"""

WAITLIST_URL = (
    "https://docs.google.com/forms/d/e/1FAIpQLSe3qMXj-"
    "idw8vcJe9swefxvUgUjifLGqTiIwkvAi188b6Nc2g/viewform"
)

HOSTED_STRIP = (
    "<hr><p class='hosted'>Running Outpour on your own machine. Prefer not to? "
    "A hosted version is in the works: we run it, you just write. "
    f"<a href='{WAITLIST_URL}' target='_blank' rel='noopener'>"
    "Join the hosted waitlist</a></p>"
)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _page(title: str, body: str) -> str:
    nav = (
        '<nav><a href="/articles">Articles</a><a href="/editor/new">New article</a>'
        '<a href="/schedule">Schedule</a><a href="/platforms">Platforms</a></nav><hr>'
    )
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_esc(title)} - Outpour</title><style>{CSS}</style>"
        f"<script src='/static/app.js' defer></script></head><body>"
        f"<h1>Outpour</h1>{nav}<h2>{_esc(title)}</h2>{body}{HOSTED_STRIP}</body></html>"
    )


def _platform_checkboxes(service: Any, selected: set[str] | None = None, disabled: bool = False) -> str:
    parts = ["<fieldset><legend>Platforms</legend>"]
    off = " disabled" if disabled else ""
    for platform in service.list_platforms():
        name = platform["name"]
        # Default path (no explicit selection): only configured platforms
        # are checked, so one click publishes to everything that can work
        # and an unconfigured platform is never silently included.
        if selected is None:
            checked = " checked" if platform.get("configured") else ""
        else:
            checked = " checked" if name in selected else ""
        hint = "" if platform["configured"] else " (not configured)"
        parts.append(
            f"<label><input type='checkbox' name='platforms' value='{_esc(name)}'{checked}{off}> "
            f"{_esc(name)}{_esc(hint)}</label>"
        )
    parts.append("</fieldset>")
    return "".join(parts)


def _editor_form(service: Any, article: dict[str, Any] | None, saved: bool, error: str = "") -> str:
    # An article dict with no path (e.g. rebuilt from a failed save) is
    # treated as new, so its filename field stays visible and its
    # submitted values are preserved instead of discarded with the error.
    is_new = article is None or not article.get("path")
    path = "" if is_new else article["path"]
    tags = ", ".join(article["tags"]) if article and article.get("tags") else ""
    if error:
        notice = f"<p class='bad'>{_esc(error)}</p>"
    elif saved:
        notice = "<p class='ok'>Saved.</p>"
    else:
        notice = ""
    filename_value = _esc(article.get("filename", "")) if article else ""
    filename_field = (
        "<label>Filename (under the first content path, .md added if missing)</label>"
        f"<input type='text' name='filename' placeholder='my-article' value='{filename_value}'>"
        if is_new
        else ""
    )
    return (
        f"{notice}<form method='post' action='/editor'>"
        f"<input type='hidden' name='path' value='{_esc(path)}'>"
        f"{filename_field}"
        "<label>Title</label>"
        f"<input type='text' name='title' value='{_esc(article['title']) if article else ''}'>"
        "<label>Description</label>"
        f"<input type='text' name='description' value='{_esc(article['description']) if article else ''}'>"
        "<label>Tags (comma separated)</label>"
        f"<input type='text' name='tags' value='{_esc(tags)}'>"
        "<label>Canonical URL</label>"
        f"<input type='text' name='canonical_url' value='{_esc(article['canonical_url']) if article else ''}'>"
        "<label>Cover image URL</label>"
        f"<input type='text' name='cover_image' value='{_esc(article['cover_image']) if article else ''}'>"
        "<label>Body (markdown)</label>"
        f"<textarea name='body'>{_esc(article['body']) if article else ''}</textarea>"
        "<button type='submit' class='primary'>Save article</button></form>"
        + _action_forms(service, path, enabled=not is_new)
    )


def _action_forms(service: Any, path: str, enabled: bool = True) -> str:
    boxes = _platform_checkboxes(service, disabled=not enabled)
    off = "" if enabled else " disabled"
    note = "" if enabled else "<p class='dim'>Save the article first to publish or schedule it.</p>"
    return (
        "<div class='card'><h3>Publish now</h3>" + note +
        "<form method='post' action='/publish' data-confirm='Publish now to the selected platforms?' data-progress='Publishing...'>"
        f"<input type='hidden' name='path' value='{_esc(path)}'>{boxes}"
        f"<label><input type='checkbox' name='draft' value='1'{off}> Draft (where the platform supports it)</label>"
        f"<button type='submit'{off}>Publish now</button></form></div>"
        "<div class='card'><h3>Schedule for later</h3>" + note +
        "<form method='post' action='/schedule' data-confirm='Schedule for the selected platforms?' data-progress='Scheduling...'>"
        f"<input type='hidden' name='path' value='{_esc(path)}'>{boxes}"
        "<label>When (for example: 2026-11-02 09:00, tomorrow 9am, in 2 hours)</label>"
        f"<input type='text' name='when' required{off}>"
        f"<label><input type='checkbox' name='draft' value='1'{off}> Draft (where the platform supports it)</label>"
        f"<button type='submit'{off}>Schedule</button></form></div>"
    )


def _results_rows(results: list[dict[str, Any]], kind: str) -> str:
    rows = []
    for item in results:
        if item.get("success"):
            if kind == "publish":
                detail = item.get("url") or item.get("article_id") or "published"
                rows.append(
                    f"<tr><td>{_esc(item['platform'])}</td>"
                    f"<td class='ok'>Published</td><td>{_esc(detail)}</td></tr>"
                )
            else:
                rows.append(
                    f"<tr><td>{_esc(item['platform'])}</td>"
                    f"<td class='ok'>Scheduled</td>"
                    f"<td>{_esc(item.get('scheduled_time'))} (id {_esc(item.get('post_id'))})</td></tr>"
                )
        else:
            rows.append(
                f"<tr><td>{_esc(item['platform'])}</td>"
                f"<td class='bad'>Failed</td><td>{_esc(item.get('error'))}</td></tr>"
            )
    return "".join(rows)


def create_app(service: Any = None) -> FastAPI:
    """Build the FastAPI app. Pass a fake service in tests."""
    svc = service or UIService()
    app = FastAPI(title="Outpour")

    @app.get("/", include_in_schema=False)
    async def index() -> RedirectResponse:
        return RedirectResponse("/articles", status_code=303)

    @app.get("/articles", response_class=HTMLResponse)
    async def articles() -> str:
        rows = []
        for article in svc.list_articles():
            published = []
            failed = []
            for name, info in (article.get("status") or {}).items():
                if info["state"] == "published":
                    label = f"<a href='{_esc(info['url'])}'>{_esc(name)}</a>" if info.get("url") else _esc(name)
                    published.append(label)
                elif info["state"] == "failed":
                    failed.append(f"{_esc(name)}: {_esc(info.get('error'))}")
            rows.append(
                "<tr><td>"
                f"<a href='/editor?path={_esc(article['path'])}'>{_esc(article['title'])}</a>"
                f"<div class='dim'>{_esc(article['name'])}</div></td>"
                f"<td>{', '.join(published) if published else '<span class=dim>not published</span>'}</td>"
                f"<td>{'<br>'.join(failed) if failed else ''}</td></tr>"
            )
        body = (
            "<table><tr><th>Article</th><th>Published</th><th>Failed</th></tr>"
            + "".join(rows)
            + "</table>"
            if rows
            else "<p class='dim'>No articles found. Set content paths with "
            "<code>outpour content add &lt;dir&gt;</code>, then write one from New article.</p>"
        )
        return _page("Articles", body)

    @app.get("/editor", response_class=HTMLResponse)
    async def editor(request: Request) -> str:
        raw = request.query_params.get("path", "")
        saved = request.query_params.get("saved") == "1"
        article = svc.get_article(raw) if raw else None
        if raw and article is None:
            return _page("Editor", "<p class='bad'>Article not found.</p>")
        return _page("Editor", _editor_form(svc, article, saved))

    @app.get("/editor/new", response_class=HTMLResponse)
    async def editor_new() -> str:
        return _page("New article", _editor_form(svc, None, False))

    @app.post("/editor")
    async def editor_save(request: Request) -> RedirectResponse:
        form = await request.form()
        path = (form.get("path") or "").strip() or None
        fields = {
            "title": form.get("title") or "",
            "description": form.get("description") or "",
            "tags": form.get("tags") or "",
            "canonical_url": form.get("canonical_url") or "",
            "cover_image": form.get("cover_image") or "",
        }
        try:
            saved = svc.save_article(path, fields, form.get("body") or "", form.get("filename") or None)
        except ValueError as exc:
            # Preserve everything the user typed: rebuild the form from
            # the submitted fields instead of returning a bare error page.
            draft = {
                "path": path or "",
                "title": fields["title"],
                "description": fields["description"],
                "tags": [tag.strip() for tag in fields["tags"].split(",") if tag.strip()],
                "canonical_url": fields["canonical_url"],
                "cover_image": fields["cover_image"],
                "body": form.get("body") or "",
                "filename": form.get("filename") or "",
            }
            return HTMLResponse(
                _page("Editor", _editor_form(svc, draft, False, error=str(exc))),
                status_code=400,
            )
        return RedirectResponse(f"/editor?path={_esc(str(saved))}&saved=1", status_code=303)

    @app.post("/publish", response_class=HTMLResponse)
    async def publish_now(request: Request) -> str:
        form = await request.form()
        path = form.get("path") or ""
        platforms = form.getlist("platforms")
        draft = bool(form.get("draft"))
        if not platforms:
            return _page("Publish results", "<p class='bad'>No platforms selected.</p>")
        try:
            results = svc.publish_article(path, platforms, draft)
        except ValueError as exc:
            return _page("Publish results", f"<p class='bad'>{_esc(exc)}</p>")
        body = (
            f"<p>Article: {_esc(Path(path).name)}</p>"
            "<table><tr><th>Platform</th><th>Result</th><th>Detail</th></tr>"
            + _results_rows(results, "publish")
            + "</table><p><a href='/articles'>Back to articles</a></p>"
        )
        return _page("Publish results", body)

    @app.get("/schedule", response_class=HTMLResponse)
    async def schedule_page() -> str:
        rows = []
        for post in svc.list_scheduled():
            cancel = ""
            if post.get("status") == "pending":
                cancel = (
                    "<form method='post' action='/schedule/cancel' "
                    "data-confirm='Cancel this scheduled post?'>"
                    f"<input type='hidden' name='post_id' value='{_esc(post['id'])}'>"
                    "<button type='submit'>Cancel</button></form>"
                )
            rows.append(
                f"<tr><td>{_esc(post['id'])}</td><td>{_esc(post.get('file_name'))}</td>"
                f"<td>{_esc(post.get('platform') or post.get('profile'))}</td>"
                f"<td>{_esc(post.get('scheduled_time'))}</td><td>{_esc(post.get('status'))}</td>"
                f"<td>{_esc(post.get('error')) if post.get('error') else ''}{cancel}</td></tr>"
            )
        body = (
            "<table><tr><th>ID</th><th>File</th><th>Platform</th><th>When</th>"
            "<th>Status</th><th>Error / action</th></tr>" + "".join(rows) + "</table>"
            if rows
            else "<p class='dim'>Nothing scheduled.</p>"
        )
        return _page("Schedule", body)

    @app.post("/schedule", response_class=HTMLResponse)
    async def schedule_for_later(request: Request) -> str:
        form = await request.form()
        path = form.get("path") or ""
        platforms = form.getlist("platforms")
        when = form.get("when") or ""
        draft = bool(form.get("draft"))
        if not platforms:
            return _page("Schedule results", "<p class='bad'>No platforms selected.</p>")
        try:
            results = svc.schedule_article(path, platforms, when, draft)
        except ValueError as exc:
            return _page("Schedule results", f"<p class='bad'>{_esc(exc)}</p>")
        body = (
            f"<p>Article: {_esc(Path(path).name)}; when: {_esc(when)}</p>"
            "<table><tr><th>Platform</th><th>Result</th><th>Detail</th></tr>"
            + _results_rows(results, "schedule")
            + "</table><p><a href='/schedule'>View schedule</a></p>"
        )
        return _page("Schedule results", body)

    @app.post("/schedule/cancel")
    async def schedule_cancel(request: Request) -> RedirectResponse:
        form = await request.form()
        svc.cancel_scheduled(form.get("post_id") or "")
        return RedirectResponse("/schedule", status_code=303)

    @app.get("/platforms", response_class=HTMLResponse)
    async def platforms_page() -> str:
        rows = []
        for platform in svc.list_platforms():
            configured = "yes" if platform["configured"] else "no"
            source = platform.get("source") or "-"
            rows.append(
                f"<tr><td>{_esc(platform['name'])}</td><td>{_esc(platform['description'])}</td>"
                f"<td>{configured}</td><td>{_esc(platform['mode'])}</td><td>{_esc(source)}</td></tr>"
            )
        body = (
            "<p>Outpour sends each article to the platforms you tick in the editor. "
            "Full articles go to the long-form platforms; announcement platforms post "
            "a short version with a link back. A platform marked as not configured "
            "needs its key added before it can publish.</p>"
            "<p class='dim'>Key values are never shown here. Configure keys with "
            "<code>outpour config set platforms.&lt;name&gt;.api_key &lt;key&gt;</code> "
            "or the matching CRIER_&lt;PLATFORM&gt;_API_KEY environment variable.</p>"
            "<table><tr><th>Platform</th><th>Description</th><th>Configured</th>"
            "<th>Mode</th><th>Key source</th></tr>" + "".join(rows) + "</table>"
        )
        return _page("Platforms", body)

    @app.get("/static/app.js", include_in_schema=False)
    async def static_js() -> Response:
        try:
            data = (resources.files("crier.ui") / "static" / "app.js").read_bytes()
        except (FileNotFoundError, ModuleNotFoundError, AttributeError):
            fallback = Path(__file__).parent / "static" / "app.js"
            data = fallback.read_bytes() if fallback.exists() else b""
        return Response(content=data, media_type="application/javascript")

    return app
