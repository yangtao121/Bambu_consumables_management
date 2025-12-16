from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import jobs, mappings, printers, realtime, reports, spools, stocks
from app.db.session import async_session_factory
from app.schemas.common import Health
from app.services.event_processor import EventProcessor


@asynccontextmanager
async def lifespan(app: FastAPI):
    processor = EventProcessor(poll_interval_sec=2.0)
    task = None
    try:
        task = asyncio.create_task(processor.run(async_session_factory))
        yield
    finally:
        processor.stop()
        if task:
            task.cancel()


app = FastAPI(title="Consumables Management API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(printers.router)
app.include_router(spools.router)
app.include_router(stocks.router)
app.include_router(mappings.router)
app.include_router(jobs.router)
app.include_router(reports.router)
app.include_router(realtime.router)


@app.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", time=datetime.now(timezone.utc))


