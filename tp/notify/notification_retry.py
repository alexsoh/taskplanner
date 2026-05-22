from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger("taskplanner.notify.retry")

NOTIFICATION_MAX_ATTEMPTS = 4
NOTIFICATION_RETRY_DELAY_SEC = 3.0


def http_status_should_retry(status: int) -> bool:
    if status >= 500:
        return True
    return status in (408, 429)


class RetryOutcome(str, Enum):
    OK = "ok"
    RETRY = "retry"
    ABORT = "abort"


async def retry_async(
    operation_id: str,
    run_once: Callable[[], Awaitable[RetryOutcome]],
) -> bool:
    """Run ``run_once`` up to ``NOTIFICATION_MAX_ATTEMPTS`` times with fixed delay between failures.

    Returns True if any attempt returned ``RetryOutcome.OK``. On ``RetryOutcome.RETRY``, sleeps
    then tries again. On ``RetryOutcome.ABORT`` or exhausted retries, returns False.
    """
    for attempt in range(1, NOTIFICATION_MAX_ATTEMPTS + 1):
        if attempt > 1:
            await asyncio.sleep(NOTIFICATION_RETRY_DELAY_SEC)
        try:
            last_outcome: RetryOutcome = await run_once()
        except httpx.RequestError as e:
            logger.warning(
                "[%s] attempt %d/%d transport error: %s: %s",
                operation_id,
                attempt,
                NOTIFICATION_MAX_ATTEMPTS,
                type(e).__name__,
                e,
            )
            last_outcome = RetryOutcome.RETRY
        except Exception:
            logger.exception(
                "[%s] attempt %d/%d unexpected error (not retrying)",
                operation_id,
                attempt,
                NOTIFICATION_MAX_ATTEMPTS,
            )
            return False

        if last_outcome == RetryOutcome.OK:
            return True
        if last_outcome == RetryOutcome.ABORT:
            return False
        if attempt < NOTIFICATION_MAX_ATTEMPTS:
            logger.debug(
                "[%s] attempt %d/%d will retry after %.1fs",
                operation_id,
                attempt,
                NOTIFICATION_MAX_ATTEMPTS,
                NOTIFICATION_RETRY_DELAY_SEC,
            )
    logger.error(
        "[%s] failed after %d attempts",
        operation_id,
        NOTIFICATION_MAX_ATTEMPTS,
    )
    return False
