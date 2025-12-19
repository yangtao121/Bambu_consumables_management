from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models.ams_color_mapping import AmsColorMapping
from app.schemas.color_mapping import ColorMappingOut, ColorMappingUpsert, normalize_color_hex


router = APIRouter(prefix="/color-mappings", tags=["color-mappings"])


@router.get("", response_model=list[ColorMappingOut])
async def list_color_mappings(
    color_hex: str | None = Query(default=None, description="Filter by hex (accepts FFFFFF/FFFFFFFF/#FFFFFF)"),
    db: AsyncSession = Depends(get_db),
) -> list[AmsColorMapping]:
    stmt = select(AmsColorMapping)
    if color_hex:
        try:
            hx = normalize_color_hex(color_hex)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        stmt = stmt.where(AmsColorMapping.color_hex == hx)
    stmt = stmt.order_by(AmsColorMapping.updated_at.desc(), AmsColorMapping.created_at.desc())
    return (await db.execute(stmt)).scalars().all()


@router.post("", response_model=ColorMappingOut)
async def upsert_color_mapping(body: ColorMappingUpsert, db: AsyncSession = Depends(get_db)) -> AmsColorMapping:
    now = datetime.now(timezone.utc)
    existing = (
        await db.execute(select(AmsColorMapping).where(AmsColorMapping.color_hex == body.color_hex).limit(1))
    ).scalars().first()
    if existing:
        # Color mapping is immutable: once a hex is mapped, it cannot be edited.
        # Allow idempotent writes only (same color_name).
        if (existing.color_name or "").strip() != (body.color_name or "").strip():
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "color mapping is immutable for an existing color_hex",
                    "color_hex": existing.color_hex,
                    "existing_color_name": existing.color_name,
                    "requested_color_name": body.color_name,
                },
            )
        return existing

    m = AmsColorMapping(color_hex=body.color_hex, color_name=body.color_name, created_at=now, updated_at=now)
    db.add(m)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"upsert color mapping failed: {e}")
    await db.refresh(m)
    return m

