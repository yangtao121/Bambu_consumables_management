from __future__ import annotations

import os
import sys
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Ensure project root is on sys.path so `import app.*` works in all runtimes (Docker/Alembic/CWD variations).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.base import Base
from app.db import models  # noqa: F401

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
        # Prefer HTTP ingest (works from Docker via host.docker.internal on macOS)
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
        # Fallback: file append (only works when path exists in same FS namespace)
        with open(_DBG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


_agent_log(
    "A",
    "backend/alembic/env.py:import",
    "alembic env imported",
    {
        "cwd": os.getcwd(),
        "sysPathHasAppRoot": ("/app" in sys.path),
        "sysPathHead": sys.path[:5],
        "hasDatabaseUrl": bool(os.getenv("DATABASE_URL")),
    },
)
# endregion

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # region agent log
    try:
        u = urlparse(url)
        _agent_log(
            "B",
            "backend/alembic/env.py:get_url",
            "DATABASE_URL parsed (masked)",
            {
                "scheme": u.scheme,
                "host": u.hostname,
                "port": u.port,
                "db": (u.path or "").lstrip("/")[:32],
            },
        )
    except Exception:
        _agent_log("B", "backend/alembic/env.py:get_url", "DATABASE_URL parse failed", {})
    # endregion
    return url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())


