"""FastAPI server: serves the web UI, the JSON API, and live updates over SSE."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles

from app.events import Broadcaster, watch
from app.models import SubmissionIn
from app.stats import attempt_view, history, stats
from app.store import ROOT, Store

WEB_DIR = ROOT / "web"
PING_SECONDS = 15


def create_app(data_dir: Path | None = None, watch_files: bool = True) -> FastAPI:
    store = Store(data_dir)
    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        task = asyncio.create_task(watch(store.data_dir, broadcaster, stop)) if watch_files else None
        yield
        stop.set()
        if task:
            await task

    app = FastAPI(title="Review Drill", lifespan=lifespan)
    app.state.store = store
    app.state.broadcaster = broadcaster

    @app.get("/api/problems")
    def list_problems() -> list[dict]:
        latest: dict[str, dict] = {}
        for row in history(store):
            latest.setdefault(row["problem_id"], row)
        out = []
        for p in store.problems():
            if store.key(p.id) is None:
                continue
            out.append({
                "id": p.id, "title": p.title, "language": p.language, "format": p.format,
                "difficulty": p.difficulty, "files": len(p.files), "latest": latest.get(p.id),
            })
        return out

    @app.get("/api/problems/{problem_id}")
    def get_problem(problem_id: str) -> dict:
        p = store.problem(problem_id)
        if p is None:
            raise HTTPException(404, f"No problem {problem_id}")
        return p.public()

    @app.post("/api/problems/{problem_id}/submit")
    def submit(problem_id: str, body: SubmissionIn) -> dict:
        p = store.problem(problem_id)
        if p is None or store.key(problem_id) is None:
            raise HTTPException(404, f"No problem {problem_id}")
        paths = {f.path for f in p.files}
        for c in body.comments:
            if c.file not in paths or c.line > p.line_count(c.file):
                raise HTTPException(422, f"Comment {c.id} points at {c.file}:{c.line}, which is not in the problem")
        sub = store.save_submission(problem_id, body)
        return attempt_view(store, sub)

    @app.get("/api/attempts/{attempt_id}")
    def get_attempt(attempt_id: str) -> dict:
        sub = store.submission(attempt_id)
        view = attempt_view(store, sub) if sub else None
        if view is None:
            raise HTTPException(404, f"No attempt {attempt_id}")
        return view

    @app.get("/api/history")
    def get_history() -> list[dict]:
        return history(store)

    @app.get("/api/stats")
    def get_stats() -> dict:
        return stats(store)

    @app.get("/api/events", response_class=EventSourceResponse)
    async def events() -> AsyncIterable[ServerSentEvent]:
        q = broadcaster.subscribe()
        try:
            yield ServerSentEvent(comment="connected")
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=PING_SECONDS)
                except TimeoutError:
                    yield ServerSentEvent(comment="ping")
                    continue
                yield ServerSentEvent(data=event, event=event["type"])
        finally:
            broadcaster.unsubscribe(q)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


app = create_app()
