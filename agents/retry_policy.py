import random

import httpx

from agents.constants import (
    RATE_LIMITED_RETRY_DELAY_MULTIPLIER,
    RATE_LIMITED_STATUS_CODES,
    RETRY_JITTER_RANGE,
)


def compute_retry_delay(
    error: Exception,
    attempt: int,
    max_retries: int,
    *,
    base_retry_delay: float,
    jitter_range: tuple[float, float] = RETRY_JITTER_RANGE,
) -> float:
    """Calculate exponential backoff with jitter and rate-limit multiplier."""
    is_rate_limited = (
        isinstance(error, httpx.HTTPStatusError)
        and error.response.status_code in RATE_LIMITED_STATUS_CODES
    )
    base_delay = (
        base_retry_delay * RATE_LIMITED_RETRY_DELAY_MULTIPLIER
        if is_rate_limited
        else base_retry_delay
    )
    jitter = random.uniform(*jitter_range)
    delay_attempt = attempt % max_retries if max_retries > 0 else attempt
    return base_delay * (2 ** delay_attempt) * jitter
