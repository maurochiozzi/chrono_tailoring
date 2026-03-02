from datetime import datetime, timedelta, date
from typing import Set

# Module-level defaults — overridden at runtime by values from project_requirements.txt
WORKING_START_HOUR = 8
WORKING_END_HOUR = 16
HOURS_PER_DAY = WORKING_END_HOUR - WORKING_START_HOUR


def is_working_day(day: date, holidays: Set[date]) -> bool:
    """Checks if a given day is a weekday and not a holiday."""
    if day.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if day in holidays:
        return False
    return True


def get_next_working_time(
    current_time: datetime,
    duration_minutes: int,
    holidays: Set[date],
    working_start_hour: int = WORKING_START_HOUR,
    working_end_hour: int = WORKING_END_HOUR,
) -> datetime:
    """
    Calculates the end time by advancing current_time by duration_minutes,
    respecting working hours, skipping weekends and holidays.

    Args:
        current_time: The starting datetime.
        duration_minutes: How many working minutes to advance.
        holidays: Set of dates to skip.
        working_start_hour: Start of the working day (default 8).
        working_end_hour: End of the working day (default 16).
    """
    if duration_minutes == 0:
        return current_time

    # Fast-forward start to a valid working slot
    if current_time.hour < working_start_hour:
        current_time = current_time.replace(
            hour=working_start_hour, minute=0, second=0, microsecond=0
        )
    elif current_time.hour >= working_end_hour:
        current_time = (
            current_time.replace(
                hour=working_start_hour, minute=0, second=0, microsecond=0
            )
            + timedelta(days=1)
        )

    while not is_working_day(current_time.date(), holidays):
        current_time += timedelta(days=1)
        current_time = current_time.replace(
            hour=working_start_hour, minute=0, second=0, microsecond=0
        )

    end_time = current_time
    working_minutes_per_day = (working_end_hour - working_start_hour) * 60
    minutes_to_end_of_day = (working_end_hour - end_time.hour) * 60 - end_time.minute

    if duration_minutes <= minutes_to_end_of_day:
        end_time += timedelta(minutes=duration_minutes)
    else:
        duration_minutes -= minutes_to_end_of_day
        end_time = (
            end_time.replace(
                hour=working_start_hour, minute=0, second=0, microsecond=0
            )
            + timedelta(days=1)
        )

        full_days = int(duration_minutes // working_minutes_per_day)
        remaining_mins = int(duration_minutes % working_minutes_per_day)

        # When remaining is exactly 0, we still owe one complete working day
        # (ending at working_end_hour), so convert it accordingly.
        if remaining_mins == 0 and full_days > 0:
            full_days -= 1
            remaining_mins = working_minutes_per_day

        days_consumed = 0
        while days_consumed < full_days:
            while not is_working_day(end_time.date(), holidays):
                end_time += timedelta(days=1)
            days_consumed += 1
            end_time += timedelta(days=1)

        while not is_working_day(end_time.date(), holidays):
            end_time += timedelta(days=1)

        end_time += timedelta(minutes=remaining_mins)

    return end_time
