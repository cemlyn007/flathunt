import datetime


def get_next_datetime(arrival_time: datetime.time) -> datetime.datetime:
    if arrival_time.tzinfo is None:
        raise ValueError("arrival_time must be timezone-aware")
    next_day = datetime.datetime.now(
        tz=arrival_time.tzinfo
    ).date() + datetime.timedelta(days=1)
    while next_day.weekday() > 4:
        next_day = next_day + datetime.timedelta(days=1)
    return datetime.datetime(
        next_day.year,
        next_day.month,
        next_day.day,
        hour=arrival_time.hour,
        minute=arrival_time.minute,
        second=arrival_time.second,
        microsecond=arrival_time.microsecond,
        tzinfo=arrival_time.tzinfo,
    )
