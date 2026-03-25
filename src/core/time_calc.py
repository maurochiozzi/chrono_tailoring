from datetime import datetime, timedelta, date
from typing import Set

# [Req: RF-09.1] — Module-level defaults overridden at runtime by values from project_config.json
WORKING_START_HOUR = 8
WORKING_END_HOUR = 16
HOURS_PER_DAY = WORKING_END_HOUR - WORKING_START_HOUR


# [Req: RF-09.4, RF-09.5] — Returns False for weekends (weekday>=5) and dates in the holidays set
def is_working_day(day: date, holidays: Set[date]) -> bool:
    """Checks if a given day is a working day, skipping weekends and holidays.

    Args:
        day (date): The date to check.
        holidays (Set[date]): A set containing all known holiday dates.

    Returns:
        bool: True if it is a working weekday, False otherwise.
    """
    if day.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if day in holidays:
        return False
    return True


# [Req: RF-09.1, RF-09.2, RF-09.3, RF-09.6, RF-09.7] — Core working-time advance function used by the scheduler
def get_next_working_time(
    current_time: datetime,
    duration_minutes: int,
    holidays: Set[date],
    working_start_hour: int = WORKING_START_HOUR,
    working_end_hour: int = WORKING_END_HOUR,
) -> datetime:
    """Calculates the end time by advancing current_time by duration_minutes,
    respecting working hours, skipping weekends and holidays.

    Args:
        current_time (datetime): The starting datetime.
        duration_minutes (int): How many working minutes to advance.
        holidays (Set[date]): Set of dates to skip.
        working_start_hour (int, optional): Start of the working day. Defaults to WORKING_START_HOUR.
        working_end_hour (int, optional): End of the working day. Defaults to WORKING_END_HOUR.

    Raises:
        ValueError: If `working_start_hour` >= `working_end_hour`.
        ValueError: If `duration_minutes` is negative.

    Returns:
        datetime: The resulting datetime after duration has accumulated.
    """
    if working_start_hour >= working_end_hour:
        raise ValueError(f"Invalid working hours: start ({working_start_hour}) must be before end ({working_end_hour}).")
    if duration_minutes < 0:
        raise ValueError(f"Duration cannot be negative (got {duration_minutes} minutes).")

    if duration_minutes == 0:  # [Req: RF-09.7] — Zero-duration tasks (milestones) return immediately
        return current_time

    # Fast-forward start to a valid working slot
    if current_time.hour < working_start_hour:  # [Req: RF-09.2] — Advance pre-shift time to shift start
        current_time = current_time.replace(
            hour=working_start_hour, minute=0, second=0, microsecond=0
        )
    elif current_time.hour >= working_end_hour:  # [Req: RF-09.3] — Roll over to next day if past end of shift
        current_time = (
            current_time.replace(
                hour=working_start_hour, minute=0, second=0, microsecond=0
            )
            + timedelta(days=1)
        )

    # [Req: RF-09.4, RF-09.5] — Skip weekends and holidays before starting the duration countdown
    while not is_working_day(current_time.date(), holidays):
        current_time += timedelta(days=1)
        current_time = current_time.replace(
            hour=working_start_hour, minute=0, second=0, microsecond=0
        )

    end_time = current_time
    # [Req: RF-09.6] — Distribute duration progressively: consume today's remaining minutes first, then full days
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
