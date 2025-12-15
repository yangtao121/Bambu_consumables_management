from __future__ import annotations

from collections.abc import AsyncIterator
import json
import os
import urllib.request
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# region agent log
_DBG_PATH = os.getenv("AGENT_DEBUG_LOG_PATH") or "/Volumes/extend/code/3d_consumables_management/.cursor/debug.log"
_DBG_SESSION = "debug-session"
_DBG_RUN = os.getenv("DEBUG_RUN_ID", "run1")


def _agent_log(hypothesisId: str, location: str, message: str, data: dict) -> None:
    try:
        payload = {
            "sessionId": _DBG_SESSION,
            "runId": _DBG_RUN,
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        for endpoint in (
            "http://host.docker.internal:7242/ingest/4ce5cedd-1b32-4497-a199-8b8693bfebf9",
            "http://127.0.0.1:7242/ingest/4ce5cedd-1b32-4497-a199-8b8693bfebf9",
        ):
            try:
                req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
                urllib.request.urlopen(req, timeout=0.5)  # noqa: S310
                return
            except Exception:
                pass
        with open(_DBG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


try:
    u = urlparse(settings.database_url)
    _agent_log(
        "C",
        "backend/app/db/session.py:engine",
        "create_async_engine url parsed (masked)",
        {"scheme": u.scheme, "host": u.hostname, "port": u.port, "db": (u.path or "").lstrip("/")[:32]},
    )
except Exception:
    _agent_log("C", "backend/app/db/session.py:engine", "create_async_engine url parse failed", {})
# endregion


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


