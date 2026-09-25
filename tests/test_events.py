import asyncio
from pathlib import Path

from app.events import Broadcaster, classify, watch


def test_classify(tmp_path: Path):
    assert classify(tmp_path / "feedback" / "a1.json", tmp_path) == {"type": "feedback", "attempt_id": "a1"}
    assert classify(tmp_path / "problems" / "p.json", tmp_path) == {"type": "problems"}
    assert classify(tmp_path / "keys" / "p.json", tmp_path) == {"type": "problems"}
    assert classify(tmp_path / "submissions" / "a1.json", tmp_path) is None
    assert classify(tmp_path / "feedback" / "a1.tmp", tmp_path) is None
    assert classify(Path("/elsewhere/feedback/a1.json"), tmp_path) is None


def test_broadcaster_fans_out():
    b = Broadcaster()
    q1, q2 = b.subscribe(), b.subscribe()
    b.publish({"type": "problems"})
    assert q1.get_nowait() == q2.get_nowait() == {"type": "problems"}
    b.unsubscribe(q1)
    b.publish({"type": "x"})
    assert q1.empty() and q2.get_nowait() == {"type": "x"}


def test_watch_publishes_feedback_event(tmp_path: Path):
    (tmp_path / "feedback").mkdir()

    async def run():
        b = Broadcaster()
        q = b.subscribe()
        stop = asyncio.Event()
        task = asyncio.create_task(watch(tmp_path, b, stop))
        await asyncio.sleep(0.5)
        (tmp_path / "feedback" / "a1.json").write_text("{}", encoding="utf-8")
        try:
            return await asyncio.wait_for(q.get(), timeout=10)
        finally:
            stop.set()
            await task

    assert asyncio.run(run()) == {"type": "feedback", "attempt_id": "a1"}
