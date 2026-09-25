"""Watch the data dir and fan out change events to connected browsers."""

from __future__ import annotations

import asyncio
from pathlib import Path

from watchfiles import awatch


class Broadcaster:
    """Holds one queue per SSE client and pushes every event to all of them."""

    def __init__(self):
        self._queues: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._queues.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass


def classify(path: Path, data_dir: Path) -> dict | None:
    """Map a changed file to an event the browser understands, or None to ignore it."""
    if path.suffix != ".json":
        return None
    try:
        folder = path.resolve().relative_to(data_dir.resolve()).parts[0]
    except (ValueError, IndexError):
        return None
    if folder == "feedback":
        return {"type": "feedback", "attempt_id": path.stem}
    if folder in ("problems", "keys"):
        return {"type": "problems"}
    return None


async def watch(data_dir: Path, broadcaster: Broadcaster, stop: asyncio.Event) -> None:
    """Publish an event for each relevant file change until stop is set."""
    async for changes in awatch(data_dir, stop_event=stop, debounce=300):
        seen = set()
        for _, raw in changes:
            event = classify(Path(raw), data_dir)
            if event and (key := tuple(sorted(event.items()))) not in seen:
                seen.add(key)
                broadcaster.publish(event)
