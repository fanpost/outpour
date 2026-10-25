"""Tests for crier.converters module."""
import pytest

from crier.converters import parse_markdown_file, parse_front_matter
from crier.converters.markdown import resolve_relative_links


class TestParseFrontMatter:
    """Tests for parse_front_matter()."""

    def test_parse_valid_front_matter(self):
        content = """\
---
title: My Title
description: A description
---

Body content here.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["title"] == "My Title"
        assert front_matter["description"] == "A description"
        assert body == "Body content here."

    def test_parse_with_tags_list(self):
        content = """\
---
title: Tagged Article
tags: [python, testing, crier]
---

Body.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["tags"] == ["python", "testing", "crier"]

    def test_parse_without_front_matter(self):
        content = "Just plain content without front matter."
        front_matter, body = parse_front_matter(content)
        assert front_matter == {}
        assert body == content

    def test_parse_empty_front_matter(self):
        # Empty front matter requires a newline between the markers
        content = """\
---

---

Body only.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter == {}
        assert body == "Body only."

    def test_parse_malformed_yaml(self):
        content = """\
---
title: [unclosed bracket
invalid: yaml: here
---

Body.
"""
        front_matter, body = parse_front_matter(content)
        # Should return empty dict on YAML error
        assert front_matter == {}

    def test_multiline_body(self):
        content = """\
---
title: Test
---

Paragraph one.

Paragraph two.

Paragraph three.
"""
        front_matter, body = parse_front_matter(content)
        assert "Paragraph one." in body
        assert "Paragraph two." in body
        assert "Paragraph three." in body


    def test_parse_toml_front_matter(self):
        content = """\
+++
title = "My TOML Title"
description = "A TOML description"
draft = false
+++

Body content here.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["title"] == "My TOML Title"
        assert front_matter["description"] == "A TOML description"
        assert front_matter["draft"] is False
        assert body == "Body content here."

    def test_parse_toml_with_arrays(self):
        content = """\
+++
title = "Tagged TOML"
tags = ['python', 'testing', 'crier']
+++

Body.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["title"] == "Tagged TOML"
        assert front_matter["tags"] == ["python", "testing", "crier"]

    def test_parse_toml_hugo_style(self):
        """Test TOML front matter as used by Hugo sites."""
        content = """\
+++
title = 'CTK: Conversation Archive'
date = 2025-12-18T11:11:23-06:00
draft = true
tags = ['ctk', 'long-echo', 'python']
categories = ['tools', 'personal']
description = 'A tool for exporting AI conversations.'
+++

Following the Long Echo philosophy, I built CTK.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter["title"] == "CTK: Conversation Archive"
        assert front_matter["description"] == "A tool for exporting AI conversations."
        assert front_matter["draft"] is True
        assert "tags" in front_matter
        assert "Following the Long Echo philosophy" in body

    def test_parse_empty_toml_front_matter(self):
        content = """\
+++

+++

Body only.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter == {}
        assert body == "Body only."

    def test_parse_malformed_toml(self):
        content = """\
+++
this is not valid toml [[[
+++

Body.
"""
        front_matter, body = parse_front_matter(content)
        assert front_matter == {} or isinstance(front_matter, dict)


class TestParseMarkdownFile:
    """Tests for parse_markdown_file()."""

    def test_parse_complete_file(self, sample_markdown_file):
        article = parse_markdown_file(sample_markdown_file)
        assert article.title == "Test Article Title"
        assert article.description == "A brief description"
        assert article.tags == ["python", "testing"]
        assert article.canonical_url == "https://example.com/test-article"
        assert article.published is True
        assert "body of the test article" in article.body

    def test_parse_minimal_file(self, tmp_path):
        md_file = tmp_path / "minimal.md"
        md_file.write_text("""\
---
title: Just a Title
---

Content.
""")
        article = parse_markdown_file(md_file)
        assert article.title == "Just a Title"
        assert article.description is None
        assert article.tags == []
        assert article.canonical_url is None
        assert article.published is True  # Default

    def test_parse_file_without_front_matter(self, tmp_path):
        md_file = tmp_path / "no_front_matter.md"
        md_file.write_text("Just plain markdown content.")

        article = parse_markdown_file(md_file)
        # Title defaults to filename stem
        assert article.title == "no_front_matter"
        assert article.body == "Just plain markdown content."

    def test_parse_with_comma_separated_tags(self, tmp_path):
        md_file = tmp_path / "comma_tags.md"
        md_file.write_text("""\
---
title: Comma Tags
tags: python, testing, crier
---

Body.
""")
        article = parse_markdown_file(md_file)
        assert article.tags == ["python", "testing", "crier"]

    def test_parse_with_published_false(self, tmp_path):
        md_file = tmp_path / "draft.md"
        md_file.write_text("""\
---
title: Draft Article
published: false
---

Draft content.
""")
        article = parse_markdown_file(md_file)
        assert article.published is False

    def test_parse_with_cover_image(self, tmp_path):
        md_file = tmp_path / "with_cover.md"
        md_file.write_text("""\
---
title: Article with Cover
cover_image: https://example.com/image.png
---

Content.
""")
        article = parse_markdown_file(md_file)
        # cover_image is not currently extracted by parse_markdown_file
        # but the article is still created successfully
        assert article.title == "Article with Cover"

    def test_parse_accepts_path_string(self, sample_markdown_file):
        # Should work with string path as well as Path object
        article = parse_markdown_file(str(sample_markdown_file))
        assert article.title == "Test Article Title"

    def test_parse_resolves_relative_links(self, tmp_path, monkeypatch):
        """Test that relative links are resolved when base_url is available."""

        md_file = tmp_path / "with_links.md"
        md_file.write_text("""\
---
title: Article with Links
---

Check out [another post](/posts/other-article/).

Here's an image: ![alt](/images/photo.png)
""")
        # Provide base_url directly
        article = parse_markdown_file(md_file, base_url="https://example.com")
        assert "https://example.com/posts/other-article/" in article.body
        assert "https://example.com/images/photo.png" in article.body

    def test_parse_infers_canonical_url_from_config_regardless_of_cwd(self, tmp_path, monkeypatch):
        """canonical_url inference must work regardless of the caller's CWD.

        Regression test: parse_markdown_file used to call Path(cp).resolve() on
        relative content_paths, which resolved against CWD instead of site_root.
        This meant running crier from a different directory would silently fail
        to infer canonical URLs, causing audit to skip everything.
        """
        import os
        import yaml

        # Build a fake Hugo site at tmp_path with a relative content_path
        site = tmp_path / "my-blog"
        (site / "content" / "post" / "my-article").mkdir(parents=True)
        md = site / "content" / "post" / "my-article" / "index.md"
        md.write_text("""\
---
title: My Article
---

Body.
""")

        # Point global config at the fake site with a RELATIVE content_path
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(yaml.dump({
            "site_root": str(site),
            "site_base_url": "https://example.com",
            "content_paths": ["content/post"],  # Relative!
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))

        # Run from a directory that is NOT the site_root
        other_dir = tmp_path / "elsewhere"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)
        assert os.getcwd() == str(other_dir)

        # Should still infer canonical_url correctly
        article = parse_markdown_file(str(md))
        assert article.canonical_url == "https://example.com/post/my-article/"

    def test_parse_infers_canonical_url_from_front_matter_slug(self, tmp_path, monkeypatch):
        """A dated bundle directory with a slug is served at the slug.

        Regression: inference used the directory name, so a cross-post of
        content/post/2026-10-18-x/index.md with slug: x linked to
        /post/2026-10-18-x/, which Hugo never builds.
        """
        import yaml

        site = tmp_path / "blog"
        bundle = site / "content" / "post" / "2026-10-18-finding-things"
        bundle.mkdir(parents=True)
        md = bundle / "index.md"
        md.write_text("---\ntitle: Finding Things\nslug: finding-things\n---\n\nBody.\n")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "site_root": str(site),
            "site_base_url": "https://example.com",
            "content_paths": ["content/post"],
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))

        article = parse_markdown_file(str(md))
        assert article.canonical_url == "https://example.com/post/finding-things/"

    def test_parse_resolves_bundle_resources_against_the_canonical_page(self, tmp_path, monkeypatch):
        """A figure stored beside index.md is served under the page's URL."""
        import yaml

        site = tmp_path / "blog"
        bundle = site / "content" / "post" / "2026-10-18-finding-things"
        bundle.mkdir(parents=True)
        md = bundle / "index.md"
        md.write_text("---\ntitle: Finding Things\nslug: finding-things\n---\n\n![A graph](graph.svg)\n")
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "site_root": str(site),
            "site_base_url": "https://example.com",
            "content_paths": ["content/post"],
        }))
        monkeypatch.setenv("CRIER_CONFIG", str(config_file))

        article = parse_markdown_file(str(md))
        assert "![A graph](https://example.com/post/finding-things/graph.svg)" in article.body


class TestResolveRelativeLinks:
    """Tests for resolve_relative_links()."""

    @pytest.mark.parametrize("body", [
        '```md\n[example](relative.md)\n<img src="figure.svg">\n```',
        '~~~html\n<a href="relative.md">example</a>\n~~~',
        '    [example](relative.md)\n    <img src="figure.svg">',
        '`[example](relative.md)` and `<img src="figure.svg">`',
        '<!-- <img src="figure.svg"> -->',
        '<script>const example = \'<img src="figure.svg">\';</script>',
        r'\[example](relative.md)',
        '[invalid URL](https://[bad)',
    ])
    def test_literal_examples_are_preserved(self, body):
        assert resolve_relative_links(body, "https://example.com") == body

    @pytest.mark.parametrize(("body", "expected"), [
        ('[graph][g]\n\n[g]: figure.svg "A title"',
         '[graph][g]\n\n[g]: https://example.com/post/figure.svg "A title"'),
        ('![graph][]\n\n[graph]: <figure.svg>',
         '![graph][]\n\n[graph]: <https://example.com/post/figure.svg>'),
        ('[a [nested] label](figure.svg "Title")',
         '[a [nested] label](https://example.com/post/figure.svg "Title")'),
        ('[![image](figure.svg)](details/)',
         '[![image](https://example.com/post/figure.svg)](https://example.com/post/details/)'),
        ('[graph](<figure one.svg> "Title")',
         '[graph](<https://example.com/post/figure%20one.svg> "Title")'),
        ('<a HREF = \'details/?x=1&amp;y=2\'>link</a>',
         '<a HREF = \'https://example.com/post/details/?x=1&amp;y=2\'>link</a>'),
        ('<img src=figure.svg>', '<img src=https://example.com/post/figure.svg>'),
        ('> [link](figure.svg)\n> continued',
         '> [link](https://example.com/post/figure.svg)\n> continued'),
        ('| link |\n| --- |\n| [graph](figure.svg) |',
         '| link |\n| --- |\n| [graph](https://example.com/post/figure.svg) |'),
        ('é 🐈 [graph](figure.svg)', 'é 🐈 [graph](https://example.com/post/figure.svg)'),
        ('[root](/about/)', '[root](https://example.com/about/)'),
        ('[graph](a(b).svg)', '[graph](https://example.com/post/a\\(b\\).svg)'),
        (r'[graph](a\)b.svg)', r'[graph](https://example.com/post/a\)b.svg)'),
        ('> [graph][g]\n>\n> [g]: a.svg',
         '> [graph][g]\n>\n> [g]: https://example.com/post/a.svg'),
        ('[graph](a&amp;b.svg)', '[graph](https://example.com/post/a&amp;b.svg)'),
        ('<svg viewBox="0 0 1 1"><a href="a.svg">é</a></svg>',
         '<svg viewBox="0 0 1 1"><a href="https://example.com/post/a.svg">é</a></svg>'),
    ])
    def test_structured_destinations_preserve_surrounding_source(self, body, expected):
        assert resolve_relative_links(body, "https://example.com/blog", "https://example.com/post/") == expected

    def test_real_link_changes_without_changing_code_or_layout(self):
        body = '# Title\r\n\r\n```md\r\n[x](x.md)\r\n```\r\n\r\n  [real](x.md)\r\n'
        expected = body.replace('  [real](x.md)', '  [real](https://example.com/x.md)')
        assert resolve_relative_links(body, "https://example.com") == expected

    @pytest.mark.parametrize(("body", "expected"), [
        ('<img src=" image.png ">', '<img src="https://example.com/image.png">'),
        ('<a href="\t other.html \r\n">link</a>', '<a href="https://example.com/other.html">link</a>'),
        ('<img src="&#32;image.png&#32;">', '<img src="https://example.com/image.png">'),
        ('<img src="\u00a0image.png\u00a0">', '<img src="https://example.com/%C2%A0image.png%C2%A0">'),
    ])
    def test_html_url_whitespace_matches_browser_resolution(self, body, expected):
        assert resolve_relative_links(body, "https://example.com") == expected

    def test_resolve_markdown_link_absolute_path(self):
        """Resolve markdown links with absolute paths."""
        body = "Check out [this post](/posts/other/)."
        result = resolve_relative_links(body, "https://example.com")
        assert result == "Check out [this post](https://example.com/posts/other/)."

    def test_resolve_markdown_link_relative_path(self):
        """Resolve markdown links with relative paths."""
        body = "See [related](related-post/)."
        result = resolve_relative_links(body, "https://example.com")
        assert result == "See [related](https://example.com/related-post/)."

    def test_path_relative_links_resolve_against_the_page(self):
        """A page-bundle resource lives under the page, as a browser would resolve it."""
        body = "![figure](figure.svg) and [root](/about/)"
        result = resolve_relative_links(body, "https://example.com",
                                        page_url="https://example.com/post/my-slug/")
        assert result == ("![figure](https://example.com/post/my-slug/figure.svg) "
                          "and [root](https://example.com/about/)")

    def test_resolve_markdown_image(self):
        """Resolve markdown images."""
        body = "![photo](/images/pic.png)"
        result = resolve_relative_links(body, "https://example.com")
        assert result == "![photo](https://example.com/images/pic.png)"

    def test_preserve_absolute_urls(self):
        """Don't modify already-absolute URLs."""
        body = "Check [external](https://other.com/page)."
        result = resolve_relative_links(body, "https://example.com")
        assert result == "Check [external](https://other.com/page)."

    def test_preserve_anchors(self):
        """Don't modify anchor links."""
        body = "See [section](#heading)."
        result = resolve_relative_links(body, "https://example.com")
        assert result == "See [section](#heading)."

    def test_preserve_mailto(self):
        """Don't modify mailto: links."""
        body = "Email [me](mailto:test@example.com)."
        result = resolve_relative_links(body, "https://example.com")
        assert result == "Email [me](mailto:test@example.com)."

    def test_resolve_html_href(self):
        """Resolve HTML href attributes."""
        body = '<a href="/about">About</a>'
        result = resolve_relative_links(body, "https://example.com")
        assert result == '<a href="https://example.com/about">About</a>'

    def test_resolve_html_src(self):
        """Resolve HTML src attributes."""
        body = '<img src="/images/logo.png" alt="logo">'
        result = resolve_relative_links(body, "https://example.com")
        assert result == '<img src="https://example.com/images/logo.png" alt="logo">'

    def test_multiple_links(self):
        """Resolve multiple links in same content."""
        body = """
Here's [link one](/page1) and [link two](/page2).

And an image: ![img](/img.png)
"""
        result = resolve_relative_links(body, "https://example.com")
        assert "https://example.com/page1" in result
        assert "https://example.com/page2" in result
        assert "https://example.com/img.png" in result

    def test_no_base_url_returns_unchanged(self):
        """Without base_url, content is unchanged."""
        body = "Link to [page](/page)."
        result = resolve_relative_links(body, "")
        assert result == body
        result = resolve_relative_links(body, None)
        assert result == body

    def test_base_url_trailing_slash_normalized(self):
        """Trailing slash on base_url shouldn't cause double slashes."""
        body = "[link](/path)"
        result = resolve_relative_links(body, "https://example.com/")
        assert result == "[link](https://example.com/path)"

    def test_preserve_protocol_relative(self):
        """Don't modify protocol-relative URLs."""
        body = "[link](//cdn.example.com/file.js)"
        result = resolve_relative_links(body, "https://example.com")
        assert result == "[link](//cdn.example.com/file.js)"

    def test_preserve_data_urls(self):
        """Don't modify data: URLs."""
        body = "![img](data:image/png;base64,abc123)"
        result = resolve_relative_links(body, "https://example.com")
        assert result == "![img](data:image/png;base64,abc123)"


def test_toml_preserves_comments_commas_and_multiline_strings():
    from crier.converters.markdown import _parse_toml
    parsed = _parse_toml('''published = false # keep draft
tags = ["one, two", "three"]
description = """first
second"""
''')
    assert parsed['published'] is False
    assert parsed['tags'] == ['one, two', 'three']
    assert parsed['description'] == 'first\nsecond'


def test_explicit_canonical_still_resolves_bundle_links(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text("site_base_url: https://example.com\n")
    monkeypatch.setenv("CRIER_CONFIG", str(config))
    md = tmp_path / "post.md"
    md.write_text('---\ntitle: Post\ncanonical_url: https://example.com/post/\n---\n![chart](chart.svg)')
    assert parse_markdown_file(md).body == '![chart](https://example.com/post/chart.svg)'


def test_content_root_accepts_documented_string_path(tmp_path):
    md = tmp_path / "content" / "post.md"
    md.parent.mkdir()
    md.write_text('---\ntitle: Post\n---\nBody')
    article = parse_markdown_file(md, content_root=str(md.parent), base_url="https://example.com")
    assert article.canonical_url == "https://example.com/post/"
