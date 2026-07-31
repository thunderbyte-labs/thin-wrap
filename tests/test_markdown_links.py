#!/usr/bin/env python3
"""Tests for visible-URL handling of markdown links in UI rendering."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ui import make_links_visible, UI


def test_labeled_link_gets_visible_url():
    """[label](url) must render with the URL visible right after the label."""
    result = make_links_visible("[AP News](https://apnews.com/hub/donald-trump)")
    assert result == (
        "[AP News](https://apnews.com/hub/donald-trump) "
        "(https://apnews.com/hub/donald-trump)"
    )


def test_link_with_long_url_query():
    """URLs with query strings must be handled."""
    url = "https://apnews.com/live/trump-iran-news-updates-07-30-2026"
    result = make_links_visible(f"[AP News: Trump says]({url})")
    assert result == f"[AP News: Trump says]({url}) ({url})"


def test_multiple_links_on_one_line():
    """Every inline link on the same line must be transformed."""
    result = make_links_visible(
        "[Reuters](https://www.reuters.com/) and "
        "[AP News](https://apnews.com/hub/donald-trump)"
    )
    assert result == (
        "[Reuters](https://www.reuters.com/) (https://www.reuters.com/) and "
        "[AP News](https://apnews.com/hub/donald-trump) "
        "(https://apnews.com/hub/donald-trump)"
    )


def test_image_not_transformed():
    """Image syntax ![alt](src) must be left untouched."""
    src = "![alt text](https://example.com/img.png)"
    assert make_links_visible(src) == src


def test_bare_url_untouched():
    """Plain URLs must be left untouched (already visible as text)."""
    text = "Check https://apnews.com/hub/donald-trump for more."
    assert make_links_visible(text) == text


def test_autolink_untouched():
    """Autolink syntax <https://...> must be left untouched."""
    text = "See <https://example.com/page> now."
    assert make_links_visible(text) == text


def test_text_without_links_unchanged():
    """Text with no inline links must be returned unchanged."""
    text = "Hello **bold** world with a /command and 42."
    assert make_links_visible(text) == text


def test_render_markdown_includes_visible_url(capsys):
    """UI.render_markdown must output the URL as visible text."""
    UI.render_markdown(
        "[AP News](https://apnews.com/hub/donald-trump)"
    )
    out = capsys.readouterr().out
    assert "https://apnews.com/hub/donald-trump" in out
