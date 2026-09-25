"""Run the real server, submit a review, drop a feedback file, and expect the SSE push."""

import json
import os
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest

from app.store import ROOT, Store
from tests.conftest import write_feedback


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(data_dir):
    port = free_port()
    env = {**os.environ, "REVIEW_DRILL_DATA": str(data_dir)}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            httpx.get(base + "/api/problems", timeout=1)
            break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield base
    proc.terminate()
    proc.wait(timeout=10)


def test_feedback_file_is_pushed_over_sse(server, data_dir):
    view = httpx.post(server + "/api/problems/real-thefuck-php-s/submit", json={
        "elapsed_seconds": 40, "verdict": "changes", "confidence": 3,
        "comments": [{"id": "c1", "file": "thefuck/rules/php_s.py", "line": 6, "category": "correctness",
                      "text": "Only matches when -s directly follows php"}],
    }).json()
    attempt_id = view["attempt_id"]
    assert view["result"]["found"] == ["k1"]

    events = []

    def listen():
        with httpx.stream("GET", server + "/api/events", timeout=15) as res:
            event = None
            for line in res.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:") and event == "feedback":
                    events.append(json.loads(line.split(":", 1)[1]))
                    return

    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(1)
    write_feedback(Store(data_dir), attempt_id, {"c1": 2}, summary="Found the real bug.")
    t.join(timeout=12)

    assert events == [{"type": "feedback", "attempt_id": attempt_id}]
    graded = httpx.get(f"{server}/api/attempts/{attempt_id}").json()
    assert graded["feedback"]["summary"] == "Found the real bug." and graded["result"]["score"] is not None
