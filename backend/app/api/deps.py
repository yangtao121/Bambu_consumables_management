from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session as _get_session


async def get_db() -> AsyncIterator[AsyncSession]:
    async for s in _get_session():
        yield s


