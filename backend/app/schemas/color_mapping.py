from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


def normalize_color_hex(v: object) -> str:
    """
    Normalize AMS color input into canonical '#RRGGBB'.

    Accepts:
    - 'FFFFFFFF' / 'FFFFFF' / '#FFFFFF'
    - 8-hex supports both RRGGBBAA (Bambu common) and AARRGGBB (some slicers)
    """
    if not isinstance(v, str):
        raise ValueError("color_hex must be a string")
    s = v.strip()
    if not s:
        raise ValueError("color_hex is empty")
    hx = s[1:].strip() if s.startswith("#") else s
    hx_u = hx.upper()
    is_hex = all(c in "0123456789ABCDEF" for c in hx_u)
    if not is_hex:
        raise ValueError("color_hex must be hex string like FFFFFF/FFFFFFFF")
    if len(hx_u) == 8:
        # Keep consistent with event_processor._normalize_color_to_hex_or_name():
        # - Bambu commonly uses RRGGBBAA (alpha last), e.g. 8E9089FF -> #8E9089
        # - Some systems use AARRGGBB (alpha first), e.g. FF8E9089 -> #8E9089
        if hx_u.endswith(("FF", "00")):
            hx_u = hx_u[:6]
        elif hx_u.startswith(("FF", "00")):
            hx_u = hx_u[-6:]
        else:
            # Fallback: assume AARRGGBB-like and use last 6
            hx_u = hx_u[-6:]
    if len(hx_u) != 6:
        raise ValueError("color_hex must be 6 or 8 hex digits")
    return f"#{hx_u}"


class ColorMappingUpsert(BaseModel):
    color_hex: str = Field(..., description="Canonical hex like '#FFFFFF' (input can be 'FFFFFF'/'FFFFFFFF')")
    color_name: str = Field(..., min_length=1, description="Human color name like '白色'")

    @model_validator(mode="after")
    def _normalize(self) -> "ColorMappingUpsert":
        self.color_hex = normalize_color_hex(self.color_hex)
        self.color_name = self.color_name.strip()
        if not self.color_name:
            raise ValueError("color_name is empty")
        return self


class ColorMappingOut(BaseModel):
    id: UUID
    color_hex: str
    color_name: str
    created_at: datetime
    updated_at: datetime

