"""Unit tests for HTML escaping utility."""
from pdf_epub.utils import escape_html


def test_escapes_ampersand() -> None:
    assert escape_html("a & b") == "a &amp; b"


def test_escapes_less_than() -> None:
    assert escape_html("<tag>") == "&lt;tag&gt;"


def test_escapes_greater_than() -> None:
    assert escape_html("x > y") == "x &gt; y"


def test_escapes_double_quote() -> None:
    assert escape_html('"quoted"') == "&quot;quoted&quot;"


def test_escapes_single_quote() -> None:
    assert escape_html("it's") == "it&#x27;s"


def test_all_special_chars_together() -> None:
    assert escape_html("&<>\"'") == "&amp;&lt;&gt;&quot;&#x27;"


def test_plain_text_unchanged() -> None:
    assert escape_html("hello world 123") == "hello world 123"


def test_empty_string() -> None:
    assert escape_html("") == ""
