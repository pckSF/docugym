from __future__ import annotations

import asyncio
import queue
from typing import Any


def push_drop_oldest_async(queue_obj: asyncio.Queue[Any], item: Any) -> bool:
    """Enqueue without blocking, dropping oldest item when queue is full."""

    dropped = False
    if queue_obj.full():
        try:
            _ = queue_obj.get_nowait()
            dropped = True
        except asyncio.QueueEmpty:
            dropped = False

    try:
        queue_obj.put_nowait(item)
    except asyncio.QueueFull:
        dropped = True

    return dropped


def drain_latest_async(
    queue_obj: asyncio.Queue[Any],
    initial: Any | None = None,
) -> Any | None:
    """Drain an asyncio queue and return the newest available item."""

    latest = initial
    while True:
        try:
            latest = queue_obj.get_nowait()
        except asyncio.QueueEmpty:
            return latest


def clear_async_queue(queue_obj: asyncio.Queue[Any]) -> None:
    """Remove all currently queued items from an asyncio queue."""

    while True:
        try:
            _ = queue_obj.get_nowait()
        except asyncio.QueueEmpty:
            return


def push_drop_oldest_sync(queue_obj: queue.Queue[Any], item: Any) -> bool:
    """Enqueue without blocking, dropping oldest item when queue is full."""

    dropped = False
    if queue_obj.full():
        try:
            _ = queue_obj.get_nowait()
            dropped = True
        except queue.Empty:
            dropped = False

    try:
        queue_obj.put_nowait(item)
    except queue.Full:
        dropped = True

    return dropped


def drain_latest_sync(
    queue_obj: queue.Queue[Any],
    initial: Any | None = None,
) -> Any | None:
    """Drain a sync queue and return the newest available item."""

    latest = initial
    while True:
        try:
            latest = queue_obj.get_nowait()
        except queue.Empty:
            return latest
