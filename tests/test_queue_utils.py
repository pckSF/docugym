"""Queue utility tests for drop-oldest and drain-latest semantics."""

from __future__ import annotations

import asyncio
import queue

from docugym.queue_utils import (
    clear_async_queue,
    drain_latest_async,
    drain_latest_sync,
    push_drop_oldest_async,
    push_drop_oldest_sync,
)


def test_push_drop_oldest_async_drops_when_full() -> None:
    q: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
    q.put_nowait(1)

    dropped = push_drop_oldest_async(q, 2)

    assert dropped is True
    assert q.get_nowait() == 2


def test_drain_latest_async_returns_newest() -> None:
    q: asyncio.Queue[int] = asyncio.Queue(maxsize=4)
    q.put_nowait(1)
    q.put_nowait(2)
    q.put_nowait(3)

    latest = drain_latest_async(q)

    assert latest == 3
    assert q.empty()


def test_clear_async_queue_empties_all_items() -> None:
    q: asyncio.Queue[int] = asyncio.Queue(maxsize=4)
    q.put_nowait(1)
    q.put_nowait(2)

    clear_async_queue(q)

    assert q.empty()


def test_push_drop_oldest_sync_drops_when_full() -> None:
    q: queue.Queue[int] = queue.Queue(maxsize=1)
    q.put_nowait(1)

    dropped = push_drop_oldest_sync(q, 2)

    assert dropped is True
    assert q.get_nowait() == 2


def test_drain_latest_sync_returns_newest() -> None:
    q: queue.Queue[int] = queue.Queue(maxsize=4)
    q.put_nowait(4)
    q.put_nowait(5)
    q.put_nowait(6)

    latest = drain_latest_sync(q)

    assert latest == 6
    assert q.empty()
