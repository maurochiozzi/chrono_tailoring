from datetime import datetime, timedelta, date
from typing import Set

WORKING_START_HOUR = 8
WORKING_END_HOUR = 16 # 8 hours total (16-8)
HOURS_PER_DAY = 8 # (16-8)

def is_working_day(day: date, holidays: Set[date]) -> bool:
    """Checks if a given day is a weekday and not a holiday."""
    # Monday is 0, Sunday is 6
    if day.weekday() >= 5: # Weekend
        return False
    if day in holidays: # Holiday
        return False
    return True

def get_next_working_time(current_time: datetime, duration_minutes: int, holidays: Set[date]) -> datetime:
    """
    Calculates the end time by advancing current_time by duration_minutes,
    respecting working hours (8 AM to 4 PM), skipping weekends and holidays.
    """
    if duration_minutes == 0:
        return current_time # 0-duration tasks finish immediately

    # Fast forward start time to a valid working slot
    if current_time.hour < WORKING_START_HOUR:
        current_time = current_time.replace(hour=WORKING_START_HOUR, minute=0, second=0, microsecond=0)
    elif current_time.hour >= WORKING_END_HOUR:
        current_time = current_time.replace(hour=WORKING_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    while not is_working_day(current_time.date(), holidays):
        current_time += timedelta(days=1)
        current_time = current_time.replace(hour=WORKING_START_HOUR, minute=0, second=0, microsecond=0)

    end_time = current_time
    working_minutes_per_day = (WORKING_END_HOUR - WORKING_START_HOUR) * 60

    minutes_to_end_of_working_day = (WORKING_END_HOUR - end_time.hour) * 60 - end_time.minute
    
    if duration_minutes <= minutes_to_end_of_working_day:
        end_time += timedelta(minutes=duration_minutes)
    else:
        duration_minutes -= minutes_to_end_of_working_day
        end_time = end_time.replace(hour=WORKING_START_HOUR, minute=0, second=0, microsecond=0) + timedelta(days=1)

        # Advance through full working days, skipping weekends/holidays
        # Each "full day" is one complete working day (8:00 → 16:00).
        # We track by number of working days consumed; remaining_mins go
        # on top of the last consumed day starting at 8:00.
        full_days = int(duration_minutes // working_minutes_per_day)
        remaining_mins = int(duration_minutes % working_minutes_per_day)

        # When the remainder is 0, we still owe one full day (ending at 16:00),
        # so treat the last day as a full-day remainder instead of N+1 days.
        if remaining_mins == 0 and full_days > 0:
            full_days -= 1
            remaining_mins = working_minutes_per_day

        days_consumed = 0
        while days_consumed < full_days:
            while not is_working_day(end_time.date(), holidays):
                end_time += timedelta(days=1)
            days_consumed += 1
            end_time += timedelta(days=1)

        # Land on a working day, then add remaining minutes from 8:00
        while not is_working_day(end_time.date(), holidays):
            end_time += timedelta(days=1)

        end_time += timedelta(minutes=remaining_mins)

    return end_time
