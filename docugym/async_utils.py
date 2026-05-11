"""Small helpers for bridging synchronous and asynchronous call sites."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


def run_async_from_sync(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    running_loop_message: str,
) -> T:
    """Run a coroutine from sync code while rejecting nested event loops."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    raise RuntimeError(running_loop_message)
