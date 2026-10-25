"""Edit parsed URL destinations while retaining the original Markdown source.

Marko supplies CommonMark/GFM syntax and character spans. Tree-sitter's HTML
grammar supplies attribute spans inside HTML nodes. Neither document is
re-rendered, so code examples and unrelated formatting remain untouched.
"""

from dataclasses import dataclass
from html import escape, unescape
from typing import Iterator
from urllib.parse import quote, urljoin, urlsplit

from marko import Markdown, block, inline
from marko.element import Element
from marko.helpers import MarkoExtension
from marko.source import Source
from tree_sitter import Language, Node, Parser
import tree_sitter_html


class LinkRefDef(block.LinkRefDef):
    """Retain the reference destination range already identified by Marko."""

    override = True
    dest_span: tuple[int, int]

    @classmethod
    def parse(cls, source: Source) -> "LinkRefDef":
        destination = source.context.linkref_info.link_dest
        element = super().parse(source)
        element.dest_span = (destination.start, destination.end)
        return element


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: str


def _walk(element: Element) -> Iterator[Element]:
    pending = [element]
    while pending:
        current = pending.pop()
        yield current
        if isinstance(current.children, list):
            pending.extend(reversed(current.children))


def _normalize(body: str) -> tuple[str, list[int]]:
    """Map Marko's normalized character offsets back to the original input."""
    text, positions = [], [0]
    index = 0
    while index < len(body):
        char = body[index]
        index += 1
        if char == "\r":
            if index < len(body) and body[index] == "\n":
                index += 1
            char = "\n"
        text.append("\ufffd" if char == "\0" else char)
        positions.append(index)
    return "".join(text), positions


def _html_values(fragment: str) -> Iterator[tuple[int, int, str]]:
    """Yield href/src attribute values with character offsets in the fragment."""
    source = fragment.encode("utf-8")
    parser = Parser(Language(tree_sitter_html.language()))
    pending: list[Node] = [parser.parse(source).root_node]
    while pending:
        node = pending.pop()
        pending.extend(reversed(node.named_children))
        if node.type != "attribute" or node.has_error:
            continue
        name = next((c for c in node.named_children if c.type == "attribute_name"), None)
        if name is None or name.text.lower() not in (b"href", b"src"):
            continue
        value = next(
            (
                c
                for c in node.named_children
                if c.type in ("attribute_value", "quoted_attribute_value")
            ),
            None,
        )
        if value is not None and value.type == "quoted_attribute_value":
            value = next((c for c in value.named_children if c.type == "attribute_value"), None)
        if value is not None:
            start = len(source[: value.start_byte].decode("utf-8"))
            end = len(source[: value.end_byte].decode("utf-8"))
            # HTML URL attributes trim ASCII whitespace, unlike Markdown's
            # angle-bracketed destinations, where spaces belong to the URL.
            yield start, end, unescape(value.text.decode("utf-8")).strip(" \t\n\r\f")


def resolve_relative_links(body: str, base_url: str, page_url: str | None = None) -> str:
    """Resolve actual link/image destinations, references, and HTML href/src."""
    if not base_url:
        return body
    text, positions = _normalize(body)
    base = base_url.rstrip("/") + "/"
    edits: list[_Edit] = []

    def resolve(url: str) -> str:
        if not url or url.startswith(("#", "//")):
            return url
        try:
            if urlsplit(url).scheme:
                return url
            resolved = urljoin(base if url.startswith("/") else page_url or base, url)
        except ValueError:
            # Validation belongs to the checker; don't corrupt an unparseable URL.
            return url
        return quote(resolved, safe="/:?#[]@!$&'()*+,;=%~-._")

    markdown = Markdown(extensions=["gfm", MarkoExtension(elements=[LinkRefDef])])
    for element in _walk(markdown.parse(text)):
        if isinstance(element, (inline.Link, inline.Image, LinkRefDef)):
            if element.dest_span is None:  # Reference uses are edited at the definition.
                continue
            start, end = element.dest_span
            raw = text[start:end]
            bracketed = raw.startswith("<") and raw.endswith(">")
            if bracketed:
                raw = raw[1:-1]
                start, end = start + 1, end - 1
            url = unescape(inline.Literal.strip_backslash(raw))
            resolved = resolve(url)
            if resolved != url:
                if not bracketed:
                    resolved = resolved.replace("(", r"\(").replace(")", r"\)")
                edits.append(_Edit(start, end, escape(resolved, quote=False)))
        elif isinstance(element, (inline.InlineHTML, block.HTMLBlock)):
            start, end = element.source_span
            for value_start, value_end, url in _html_values(text[start:end]):
                resolved = resolve(url)
                if resolved != url:
                    edits.append(
                        _Edit(start + value_start, start + value_end, escape(resolved, quote=True))
                    )

    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        body = body[: positions[edit.start]] + edit.replacement + body[positions[edit.end] :]
    return body
