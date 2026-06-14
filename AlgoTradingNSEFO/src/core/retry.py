from __future__ import annotations

import functools
import time
from typing import Callable, Iterable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

T = TypeVar("T")


def default_retry_exceptions() -> tuple[type[BaseException], ...]:
    # Keep generic: network-ish + API-ish errors.
    return (TimeoutError, ConnectionError, OSError, ValueError)


def retry_sync(
    *,
    exceptions: Iterable[type[BaseException]] | None = None,
    attempts: int = 5,
    min_wait_seconds: float = 0.5,
    max_wait_seconds: float = 10.0,
):
    excs = tuple(
        exceptions) if exceptions is not None else default_retry_exceptions()

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        @retry(
            retry=retry_if_exception_type(excs),
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(
                initial=min_wait_seconds,
                max=max_wait_seconds,
            ),
            reraise=True,
        )
        def wrapped(*args, **kwargs) -> T:
            return fn(*args, **kwargs)

        return wrapped

    return decorator


class RetryableError(RuntimeError):
    pass
