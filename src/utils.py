"""Utility functions for date partitioning and other helpers."""


from datetime import date, timedelta
from typing import Iterable, Union, Literal, cast


PartitionInterval = Union[
    Literal["daily", "weekly", "monthly"],
    int,
]


def partition(
    start: date,
    end: date,
    interval: PartitionInterval = "monthly",
) -> Iterable[date]:
    """Generate partition start dates between two dates.

    The function yields deterministic partition boundaries that can be used
    for time-windowed scraping or data ingestion. Partitions are inclusive of
    the start month/day and inclusive of the end month/day at the partition
    level.

    Supported intervals:
      - "daily": one partition per day
      - "weekly": one partition per 7 days
      - "monthly": one partition per calendar month
      - int: custom partition size in days (must be > 0)

    Args:
        start: Start date of the overall range.
        end: End date of the overall range.
        interval (Optional): Partition interval. Either a string
            ("daily", "weekly", "monthly") or an integer
            specifying the partition size in days.

    Yields:
        The start date of each partition.

    Raises:
        ValueError: If interval is invalid or end < start.

    Examples:
        >>> list(partition(date(2024, 1, 15), date(2024, 3, 20), "monthly"))
        [date(2024, 1, 1), date(2024, 2, 1), date(2024, 3, 1)]

        >>> list(partition(date(2024, 1, 1), date(2024, 1, 10), "daily"))
        [date(2024, 1, 1), ..., date(2024, 1, 10)]

        >>> list(partition(date(2024, 1, 1), date(2024, 1, 15), 5))
        [date(2024, 1, 1), date(2024, 1, 6), date(2024, 1, 11)]
    """
    if end < start:
        raise ValueError("end must be greater than or equal to start")

    # Normalize string intervals
    if isinstance(interval, str):
        interval_lower = interval.lower()

        if interval_lower == "daily":
            step = timedelta(days=1)

        elif interval_lower == "weekly":
            step = timedelta(days=7)

        elif interval_lower == "monthly":
            cur = date(start.year, start.month, 1)
            stop = date(end.year, end.month, 1)

            while cur <= stop:
                yield cur

                year = cur.year + (cur.month // 12)
                month = (cur.month % 12) + 1
                cur = date(year, month, 1)
            return

        else:
            raise ValueError(
                "interval must be 'daily', 'weekly', 'monthly', or a positive int"
            )

    elif isinstance(interval, int):
        if interval <= 0:
            raise ValueError("integer interval must be > 0")
        step = timedelta(days=interval)

    else:
        raise ValueError(
            "interval must be 'daily', 'weekly', 'monthly', or a positive int"
        )

    # Day-based partitions
    cur = start
    while cur <= end:
        yield cur
        cur += step
