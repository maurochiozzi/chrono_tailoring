"""
Unit tests for src/core/time_calc.py
Tests working day logic and time advancement calculations.
"""
import pytest
from datetime import datetime, date
from src.core.time_calc import is_working_day, get_next_working_time

NO_HOLIDAYS: set = set()

# A fixed holiday for testing
FIXED_HOLIDAY = date(2026, 2, 9)  # Monday
HOLIDAYS_WITH_ONE = {FIXED_HOLIDAY}


class TestIsWorkingDay:
    def test_monday_is_working(self):
        assert is_working_day(date(2026, 2, 9), NO_HOLIDAYS) is True

    def test_saturday_not_working(self):
        assert is_working_day(date(2026, 2, 7), NO_HOLIDAYS) is False

    def test_sunday_not_working(self):
        assert is_working_day(date(2026, 2, 8), NO_HOLIDAYS) is False

    def test_holiday_not_working(self):
        assert is_working_day(FIXED_HOLIDAY, HOLIDAYS_WITH_ONE) is False

    def test_non_holiday_monday_is_working(self):
        assert is_working_day(date(2026, 2, 16), HOLIDAYS_WITH_ONE) is True


class TestGetNextWorkingTime:
    def test_zero_duration_returns_same_time(self):
        t = datetime(2026, 2, 9, 8, 0)  # Monday 8:00
        result = get_next_working_time(t, 0, NO_HOLIDAYS)
        assert result == t

    def test_short_duration_within_same_day(self):
        start = datetime(2026, 2, 9, 8, 0)  # Monday 8:00
        result = get_next_working_time(start, 60, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 9, 9, 0)

    def test_duration_exactly_fills_day(self):
        # 8 hours = 480 minutes = full day from 8:00
        start = datetime(2026, 2, 9, 8, 0)
        result = get_next_working_time(start, 480, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 9, 16, 0)

    def test_duration_spills_into_next_day(self):
        # Start at 15:00, 120 min duration → 60 min today, 60 min next day from 8:00 → 9:00
        start = datetime(2026, 2, 9, 15, 0)  # Monday
        result = get_next_working_time(start, 120, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 10, 9, 0)  # Tuesday 9:00

    def test_skips_weekend(self):
        # Friday 15:30 + 60 min → 30 min today (16:00), remainder on Monday
        start = datetime(2026, 2, 13, 15, 30)  # Friday
        result = get_next_working_time(start, 60, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 16, 8, 30)  # Monday 8:30

    def test_start_before_working_hours_advances_to_8am(self):
        start = datetime(2026, 2, 9, 6, 0)  # Before 8am
        result = get_next_working_time(start, 60, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 9, 9, 0)

    def test_start_after_working_hours_moves_to_next_day(self):
        start = datetime(2026, 2, 9, 17, 0)  # After 4pm Monday
        result = get_next_working_time(start, 60, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 10, 9, 0)  # Tuesday

    def test_skips_holiday(self):
        # Monday is a holiday → task starts Tuesday
        start = datetime(2026, 2, 9, 8, 0)  # Holiday
        result = get_next_working_time(start, 60, HOLIDAYS_WITH_ONE)
        assert result == datetime(2026, 2, 10, 9, 0)  # Tuesday 9:00

    def test_multi_day_duration(self):
        # 480 * 2 = 960 minutes = 2 full working days from 8:00 Monday
        # Day 1: Mon 8:00 → 16:00 (480 min)
        # Day 2: Tue 8:00 → 16:00 (480 min)
        # Result: Tuesday 16:00
        start = datetime(2026, 2, 9, 8, 0)  # Monday
        result = get_next_working_time(start, 480 * 2, NO_HOLIDAYS)
        assert result == datetime(2026, 2, 10, 16, 0)  # Tuesday end of day
