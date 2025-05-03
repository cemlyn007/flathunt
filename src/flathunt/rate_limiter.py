import time
from functools import wraps
from threading import Lock, BoundedSemaphore
from typing import Callable, TypeVar, cast

T = TypeVar("T", bound=Callable)


class RateLimiter:
    def __init__(self, max_calls: int, interval: float):
        """
        Initialize the RateLimiter.

        :param max_calls: Maximum number of calls allowed within the interval.
        :param interval: Time interval in seconds.
        """
        self.max_calls = max_calls
        self.interval = interval
        self.semaphore = BoundedSemaphore(max_calls)
        self.lock = Lock()
        self._call_times = []

    def __call__(self, func: T) -> T:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self.semaphore:
                with self.lock:
                    current_time = time.monotonic()

                    # Remove timestamps outside the interval
                    self._call_times = [
                        t for t in self._call_times if current_time - t < self.interval
                    ]

                    if len(self._call_times) >= self.max_calls:
                        # Calculate the wait time for the next allowed call
                        wait_time = self.interval - (
                            current_time - min(self._call_times)
                        )
                        if wait_time > 0:
                            time.sleep(wait_time)

                    # Record the current call
                    call_time = time.monotonic()
                    self._call_times.append(call_time)

                try:
                    return func(*args, **kwargs)
                finally:
                    end_call_time = time.monotonic()
                    # Remove the call time from the list
                    with self.lock:
                        try:
                            self._call_times[self._call_times.index(call_time)] = (
                                end_call_time
                            )
                        except ValueError:
                            self._call_times.append(end_call_time)

        return cast(T, wrapper)
