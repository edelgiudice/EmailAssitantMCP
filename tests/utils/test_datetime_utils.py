"""Tests for datetime_utils module."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from email_assistant_mcp.utils.datetime_utils import (
    parse_iso8601_to_datetime,
    parse_iso8601_to_epoch,
    utc_now,
)


class TestParseISO8601ToDatetime:
    """Tests for parse_iso8601_to_datetime function."""

    def test_valid_iso8601_with_z_suffix(self):
        """Test parsing valid ISO 8601 with 'Z' suffix."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00Z")
        expected = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result == expected
        assert result.tzinfo == timezone.utc

    def test_valid_iso8601_with_positive_timezone(self):
        """Test parsing valid ISO 8601 with positive timezone offset."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00+05:00")
        # Should preserve the timezone
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 0
        assert result.utcoffset() == timedelta(hours=5)

    def test_valid_iso8601_with_negative_timezone(self):
        """Test parsing valid ISO 8601 with negative timezone offset."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00-05:00")
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.second == 0
        assert result.utcoffset() == timedelta(hours=-5)

    def test_valid_iso8601_naive_defaults_to_utc(self):
        """Test parsing naive ISO 8601 string defaults to UTC."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00")
        expected = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result == expected
        assert result.tzinfo == timezone.utc

    def test_normalize_to_utc_true_with_timezone(self):
        """Test normalize_to_utc=True converts to UTC."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00+05:00", normalize_to_utc=True)
        # 10:30 +05:00 should become 05:30 UTC
        expected = datetime(2024, 1, 15, 5, 30, 0, tzinfo=timezone.utc)
        assert result == expected
        assert result.tzinfo == timezone.utc

    def test_normalize_to_utc_true_with_z_suffix(self):
        """Test normalize_to_utc=True with Z suffix (already UTC)."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00Z", normalize_to_utc=True)
        expected = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result == expected
        assert result.tzinfo == timezone.utc

    def test_normalize_to_utc_false_preserves_timezone(self):
        """Test normalize_to_utc=False preserves original timezone."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00+05:00", normalize_to_utc=False)
        # Should keep the original timezone offset
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30
        assert result.utcoffset() == timedelta(hours=5)

    @pytest.mark.parametrize("invalid_input", [
        "not-a-date",
        "2024-13-01T10:30:00Z",  # Invalid month
        "2024-01-32T10:30:00Z",  # Invalid day
        "2024-01-15 10:30:00",   # Space instead of T
        "2024/01/15T10:30:00Z",  # Slashes instead of dashes
        "15-01-2024T10:30:00Z",  # Wrong order
        "",                       # Empty string
    ])
    def test_invalid_format_raises_value_error(self, invalid_input):
        """Test invalid ISO 8601 format raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            parse_iso8601_to_datetime(invalid_input)
        assert "Invalid ISO 8601" in str(exc_info.value)

    def test_fractional_seconds(self):
        """Test parsing ISO 8601 with fractional seconds."""
        result = parse_iso8601_to_datetime("2024-01-15T10:30:00.123456Z")
        expected = datetime(2024, 1, 15, 10, 30, 0, 123456, tzinfo=timezone.utc)
        assert result == expected

    def test_extreme_past_date(self):
        """Test parsing extreme past date."""
        result = parse_iso8601_to_datetime("1900-01-01T00:00:00Z")
        expected = datetime(1900, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert result == expected

    def test_extreme_future_date(self):
        """Test parsing extreme future date."""
        result = parse_iso8601_to_datetime("2999-12-31T23:59:59Z")
        expected = datetime(2999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        assert result == expected

    def test_whitespace_trimming(self):
        """Test that leading/trailing whitespace is trimmed."""
        result = parse_iso8601_to_datetime("  2024-01-15T10:30:00Z  ")
        expected = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert result == expected


class TestParseISO8601ToEpoch:
    """Tests for parse_iso8601_to_epoch function."""

    def test_epoch_conversion_accuracy(self):
        """Test epoch conversion produces correct Unix timestamp."""
        # January 1, 1970 00:00:00 UTC is epoch 0
        result = parse_iso8601_to_epoch("1970-01-01T00:00:00Z")
        assert result == 0

        # Known timestamp: 2024-01-15T10:30:00Z
        result = parse_iso8601_to_epoch("2024-01-15T10:30:00Z")
        # Verify it's a positive integer for a date after 1970
        assert isinstance(result, int)
        assert result > 0

        # Verify the timestamp is correct by converting back
        dt = datetime.fromtimestamp(result, tz=timezone.utc)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30

    def test_different_timezones_same_instant(self):
        """Test different timezones convert to same epoch for same instant."""
        # Same instant in time, different timezone representations
        utc_time = "2024-01-15T10:30:00Z"
        plus_five = "2024-01-15T15:30:00+05:00"  # 5 hours ahead
        minus_five = "2024-01-15T05:30:00-05:00"  # 5 hours behind

        epoch_utc = parse_iso8601_to_epoch(utc_time)
        epoch_plus = parse_iso8601_to_epoch(plus_five)
        epoch_minus = parse_iso8601_to_epoch(minus_five)

        assert epoch_utc == epoch_plus
        assert epoch_utc == epoch_minus

    def test_invalid_input_raises_value_error(self):
        """Test invalid input raises ValueError."""
        with pytest.raises(ValueError):
            parse_iso8601_to_epoch("not-a-date")

        with pytest.raises(ValueError):
            parse_iso8601_to_epoch("2024-13-01T10:30:00Z")

    def test_fractional_seconds_truncated(self):
        """Test fractional seconds are truncated in epoch conversion."""
        # Epoch is in whole seconds, microseconds should be truncated
        result1 = parse_iso8601_to_epoch("2024-01-15T10:30:00.999999Z")
        result2 = parse_iso8601_to_epoch("2024-01-15T10:30:00Z")
        # Both should produce the same epoch (seconds)
        assert result1 == result2

    def test_returns_integer(self):
        """Test that function returns an integer, not float."""
        result = parse_iso8601_to_epoch("2024-01-15T10:30:00Z")
        assert isinstance(result, int)


class TestUtcNow:
    """Tests for utc_now function."""

    def test_returns_timezone_aware_datetime(self):
        """Test that utc_now returns a timezone-aware datetime."""
        result = utc_now()
        assert result.tzinfo is not None
        assert isinstance(result, datetime)

    def test_timezone_is_utc(self):
        """Test that timezone is UTC."""
        result = utc_now()
        assert result.tzinfo == timezone.utc

    def test_returns_current_time(self):
        """Test that utc_now returns current time (reasonable range check)."""
        before = datetime.now(timezone.utc)
        result = utc_now()
        after = datetime.now(timezone.utc)

        # Result should be between before and after (within a few seconds)
        assert result >= before - timedelta(seconds=1)
        assert result <= after + timedelta(seconds=1)

    def test_multiple_calls_advance_in_time(self):
        """Test that multiple calls show time progression."""
        first = utc_now()
        # Small delay to ensure different timestamps
        time.sleep(0.01)
        second = utc_now()

        assert second >= first
