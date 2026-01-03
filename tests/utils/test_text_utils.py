"""Unit tests for text_utils module."""

from __future__ import annotations

import pytest

from email_assistant_mcp.utils.text_utils import strip_html, truncate_text


class TestTruncateText:
    """Test suite for truncate_text() function."""

    # Basic Functionality Tests
    def test_no_truncation_when_under_limit(self):
        """Test that text under the limit is not truncated."""
        result, truncated = truncate_text("Hello", 10)
        assert result == "Hello"
        assert truncated is False

    def test_truncation_with_ellipsis(self):
        """Test that text exceeding limit is truncated with ellipsis."""
        result, truncated = truncate_text("Hello world", 8)
        assert result == "Hello..."
        assert truncated is True

    def test_very_short_limit_no_ellipsis(self):
        """Test that very short limits (≤3) truncate without ellipsis."""
        result, truncated = truncate_text("Hello", 2)
        assert result == "He"
        assert truncated is True

    def test_exact_limit_boundary(self):
        """Test text length exactly equal to limit."""
        result, truncated = truncate_text("Hello", 5)
        assert result == "Hello"
        assert truncated is False

    def test_negative_limit_raises_error(self):
        with pytest.raises(ValueError, match="limit must be non-negative"):
            truncate_text("Hello", -1)

    # Edge Cases - None and Empty Strings
    def test_none_value_handling(self):
        """Test that None input returns empty string."""
        result, truncated = truncate_text(None, 10)
        assert result == ""
        assert truncated is False

    def test_empty_string_handling(self):
        """Test that empty string input returns empty string."""
        result, truncated = truncate_text("", 10)
        assert result == ""
        assert truncated is False

    def test_whitespace_only_strings(self):
        """Test handling of whitespace-only strings without strip."""
        result, truncated = truncate_text("   ", 10)
        assert result == "   "
        assert truncated is False

    def test_very_long_strings(self):
        """Test handling of very long strings (10000+ characters)."""
        long_text = "a" * 10000
        result, truncated = truncate_text(long_text, 100)
        assert len(result) == 100
        assert result == ("a" * 97) + "..."
        assert truncated is True

    # strip Parameter Tests
    def test_strip_true_removes_whitespace(self):
        """Test that strip=True removes leading/trailing whitespace."""
        result, truncated = truncate_text("  Hello  ", 10, strip=True)
        assert result == "Hello"
        assert truncated is False

    def test_strip_false_preserves_whitespace(self):
        """Test that strip=False preserves whitespace (default)."""
        result, truncated = truncate_text("  Hello  ", 10, strip=False)
        assert result == "  Hello  "
        assert truncated is False

    def test_strip_default_preserves_whitespace(self):
        """Test that default behavior preserves whitespace."""
        result, truncated = truncate_text("  Hello  ", 10)
        assert result == "  Hello  "
        assert truncated is False

    def test_strip_with_truncation(self):
        """Test that strip=True works correctly with truncation."""
        result, truncated = truncate_text("  Hello world  ", 8, strip=True)
        assert result == "Hello..."
        assert truncated is True

    def test_strip_brings_text_under_limit(self):
        """Test that stripping brings text under limit, avoiding truncation."""
        result, truncated = truncate_text("  Hello  ", 5, strip=True)
        assert result == "Hello"
        assert truncated is False

    def test_strip_whitespace_only_string(self):
        """Test strip=True with whitespace-only string."""
        result, truncated = truncate_text("   ", 10, strip=True)
        assert result == ""
        assert truncated is False

    # Return Tuple Validation
    def test_returns_tuple(self):
        """Test that function returns a tuple."""
        result = truncate_text("Hello", 10)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_tuple_first_element_is_string(self):
        """Test that first tuple element is a string."""
        result, truncated = truncate_text("Hello", 10)
        assert isinstance(result, str)

    def test_tuple_second_element_is_bool(self):
        """Test that second tuple element is a boolean."""
        result, truncated = truncate_text("Hello", 10)
        assert isinstance(truncated, bool)

    def test_truncated_false_when_not_truncated(self):
        """Test that truncated flag is False when text is not shortened."""
        result, truncated = truncate_text("Short", 10)
        assert truncated is False

    def test_truncated_true_when_truncated(self):
        """Test that truncated flag is True when text is shortened."""
        result, truncated = truncate_text("Very long text", 5)
        assert truncated is True

    # Boundary Cases with Ellipsis
    def test_limit_of_three_no_ellipsis(self):
        """Test that limit of exactly 3 truncates without ellipsis."""
        result, truncated = truncate_text("Hello", 3)
        assert result == "Hel"
        assert truncated is True

    def test_limit_of_four_with_ellipsis(self):
        """Test that limit of 4 truncates with ellipsis."""
        result, truncated = truncate_text("Hello world", 4)
        assert result == "H..."
        assert truncated is True

    def test_limit_of_one(self):
        """Test handling of limit of 1."""
        result, truncated = truncate_text("Hello", 1)
        assert result == "H"
        assert truncated is True

    def test_limit_of_zero(self):
        """Test handling of limit of 0."""
        result, truncated = truncate_text("Hello", 0)
        assert result == ""
        assert truncated is True

    # Complex Real-World Scenarios
    def test_email_subject_truncation(self):
        """Test realistic email subject truncation."""
        subject = "Re: Important meeting about Q4 project deliverables"
        result, truncated = truncate_text(subject, 30)
        assert result == "Re: Important meeting about..."
        assert truncated is True
        assert len(result) == 30

    def test_multiline_text_truncation(self):
        """Test truncation of text with newlines."""
        text = "Line 1\nLine 2\nLine 3"
        result, truncated = truncate_text(text, 10)
        assert result == "Line 1\n..."
        assert truncated is True

    def test_unicode_text_truncation(self):
        """Test truncation with Unicode characters."""
        text = "Hello 世界 🌍"
        result, truncated = truncate_text(text, 10)
        assert truncated is False
        assert result == text

    def test_unicode_text_truncation_with_limit(self):
        """Test truncation with Unicode characters exceeding limit."""
        text = "Hello 世界 🌍 extra text"
        result, truncated = truncate_text(text, 12)
        assert result == "Hello 世界 ..."
        assert truncated is True

    
class TestStripHtml:
    """Test suite for strip_html() function."""

    # Basic Functionality Tests
    def test_simple_html_tag_stripping(self):
        """Test that simple HTML tags are replaced with spaces."""
        result = strip_html("<p>Hello</p>")
        assert result == " Hello "

    def test_multiple_tags(self):
        """Test that multiple HTML tags are all replaced with spaces."""
        result = strip_html("<b>Bold</b> and <i>italic</i>")
        assert result == " Bold  and  italic "

    def test_tags_replaced_with_spaces(self):
        """Verify tags are replaced with spaces, not removed entirely."""
        result = strip_html("<span>A</span><span>B</span>")
        # Each tag becomes a space, so we get " A  B "
        assert result == " A  B "

    def test_text_without_html(self):
        """Test that plain text without HTML passes through unchanged."""
        result = strip_html("Plain text")
        assert result == "Plain text"

    # Edge Cases - None and Empty Strings
    def test_none_value_handling(self):
        """Test that None input returns empty string."""
        result = strip_html(None)
        assert result == ""

    def test_empty_string(self):
        """Test that empty string input returns empty string."""
        result = strip_html("")
        assert result == ""

    def test_whitespace_only_strings(self):
        """Test that whitespace-only strings are preserved by default."""
        result = strip_html("   ")
        assert result == "   "

    def test_whitespace_only_with_strip(self):
        """Test that whitespace-only strings return empty with strip_whitespace=True."""
        result = strip_html("   ", strip_whitespace=True)
        assert result == ""

    # Nested Tags
    def test_nested_tags(self):
        """Test that nested HTML tags are properly removed."""
        result = strip_html("<div><p>Text</p></div>")
        assert result == "  Text  "

    def test_deeply_nested_tags(self):
        """Test deeply nested tags."""
        result = strip_html("<div><span><b><i>Deep</i></b></span></div>")
        assert result == "    Deep    "

    # Malformed HTML
    def test_malformed_html_unclosed_tag(self):
        """Test that unclosed tags are still stripped."""
        result = strip_html("<p>Unclosed tag")
        assert "<p>" not in result
        assert "Unclosed tag" in result

    def test_empty_tag(self):
        """Test empty angle brackets."""
        result = strip_html("<>Empty tag</>")
        # <> doesn't match the pattern (requires at least 1 char), </> does match
        assert result == "<>Empty tag "

    def test_double_angle_brackets(self):
        """Test double angle brackets."""
        result = strip_html("<<double")
        # First < starts a tag that ends at the second <, leaving "double"
        assert "double" in result

    # Self-Closing Tags
    def test_self_closing_br_tag(self):
        """Test self-closing br tag."""
        result = strip_html("Line1<br/>Line2")
        assert result == "Line1 Line2"

    def test_self_closing_img_tag(self):
        """Test self-closing img tag with attributes."""
        result = strip_html('<img src="image.jpg"/>Text')
        assert result == " Text"

    # Tags with Attributes
    def test_tags_with_attributes(self):
        """Test that tags with attributes are properly stripped."""
        result = strip_html('<a href="url">Link</a>')
        assert result == " Link "

    def test_tags_with_multiple_attributes(self):
        """Test tags with multiple attributes."""
        result = strip_html('<div class="container" id="main" data-value="123">Content</div>')
        assert result == " Content "

    def test_tags_with_quoted_attributes(self):
        """Test tags with various quote styles in attributes."""
        result = strip_html("<span data-value='test' class=\"active\">Text</span>")
        assert result == " Text "

    # strip_whitespace Parameter Tests
    def test_strip_whitespace_false_default(self):
        """Test that strip_whitespace defaults to False and preserves whitespace."""
        result = strip_html("  <p>Hello</p>  ")
        assert result == "   Hello   "

    def test_strip_whitespace_true_removes_leading_trailing(self):
        """Test that strip_whitespace=True removes leading/trailing whitespace."""
        result = strip_html("  <p>Hello</p>  ", strip_whitespace=True)
        assert result == " Hello "

    def test_strip_whitespace_true_with_only_tags(self):
        """Test strip_whitespace=True when input is only whitespace and tags."""
        result = strip_html("  <br/>  ", strip_whitespace=True)
        # After stripping whitespace, we have "<br/>", which becomes " "
        assert result == " "

    def test_strip_whitespace_preserves_internal_spacing(self):
        """Test that strip_whitespace only affects leading/trailing, not internal."""
        result = strip_html("  <p>Hello  World</p>  ", strip_whitespace=True)
        assert result == " Hello  World "

    # Complex Real-World Scenarios
    def test_email_html_snippet(self):
        """Test realistic email HTML snippet."""
        html = '<div class="email"><p>Hello,</p><p>Thanks for your message.</p></div>'
        result = strip_html(html)
        assert "Hello," in result
        assert "Thanks for your message." in result
        assert "<" not in result
        assert ">" not in result

    def test_mixed_content(self):
        """Test mixed HTML and plain text content."""
        result = strip_html("Plain text <b>bold</b> more plain <i>italic</i> end")
        assert result == "Plain text  bold  more plain  italic  end"

    def test_consecutive_tags(self):
        """Test multiple consecutive tags without text between them."""
        result = strip_html("<p></p><div></div><span></span>Text")
        assert result == "      Text"

    def test_tag_with_newlines(self):
        """Test tags spanning multiple lines."""
        html = """<div
            class="test"
            id="main">Content</div>"""
        result = strip_html(html)
        assert "Content" in result
        assert "<div" not in result

    # Verify No Security/Sanitization Claims
    def test_script_tag_content_not_sanitized(self):
        """Verify that script content is only tag-stripped, not sanitized."""
        # This test documents that strip_html is NOT a security sanitizer
        result = strip_html("<script>alert('xss')</script>")
        # The tags are removed, but the content remains
        assert result == " alert('xss') "
        assert "script" not in result.lower()

    def test_style_tag_content_preserved(self):
        """Verify that style tag content is preserved (minus tags)."""
        result = strip_html("<style>body { color: red; }</style>")
        assert result == " body { color: red; } "
