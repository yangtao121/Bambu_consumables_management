from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


@dataclass(frozen=True)
class PricingConflict(ValueError):
    message: str
    detail: dict


def _to_decimal(v: float | int | str | Decimal | None) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _round2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def derive_purchase_prices(
    *,
    rolls_count: int | None,
    price_per_roll: float | None,
    price_total: float | None,
) -> tuple[float | None, float | None]:
    """
    Derive missing pricing fields for a purchase-like record.

    Rules:
    - If only price_per_roll is provided: price_total = price_per_roll * rolls_count
    - If only price_total is provided: price_per_roll = price_total / rolls_count
    - If both provided: must be consistent within 0.01, else conflict
    - If any price is provided, rolls_count must be > 0
    """
    n = int(rolls_count) if rolls_count is not None else None

    ppr = _to_decimal(price_per_roll)
    pt = _to_decimal(price_total)

    any_price = (ppr is not None) or (pt is not None)
    if any_price:
        if n is None or n <= 0:
            raise PricingConflict(
                message="录入价格时必须提供 rolls_count（且 > 0）",
                detail={"message": "rolls_count must be > 0 when providing price", "rolls_count": n},
            )

    if ppr is None and pt is None:
        return None, None

    if ppr is not None and ppr < 0:
        raise PricingConflict(message="卷单价必须 >= 0", detail={"message": "price_per_roll must be >= 0"})
    if pt is not None and pt < 0:
        raise PricingConflict(message="总价必须 >= 0", detail={"message": "price_total must be >= 0"})

    dn = Decimal(int(n or 0))
    if ppr is not None and pt is None:
        pt2 = _round2(ppr * dn)
        return float(_round2(ppr)), float(pt2)

    if ppr is None and pt is not None:
        ppr2 = _round2(pt / dn)
        return float(ppr2), float(_round2(pt))

    # both provided
    assert ppr is not None and pt is not None
    exp_total = _round2(ppr * dn)
    pt2 = _round2(pt)
    if abs(pt2 - exp_total) > Decimal("0.01"):
        raise PricingConflict(
            message="卷单价 × 卷数 与 总价 不一致，请修正",
            detail={
                "message": "price_total inconsistent with price_per_roll * rolls_count",
                "rolls_count": int(n or 0),
                "price_per_roll": float(_round2(ppr)),
                "price_total": float(pt2),
                "expected_total": float(exp_total),
            },
        )
    return float(_round2(ppr)), float(pt2)


def derive_missing_price_total(
    *,
    rolls_count: int | None,
    price_per_roll: float | None,
    price_total: float | None,
) -> float | None:
    """Response-layer helper: only fill missing total if derivable."""
    if price_total is not None:
        try:
            return float(price_total)
        except Exception:
            return None
    if price_per_roll is None or rolls_count is None:
        return None
    try:
        n = int(rolls_count)
        if n <= 0:
            return None
        ppr = Decimal(str(price_per_roll))
        return float(_round2(ppr * Decimal(n)))
    except Exception:
        return None


def derive_missing_price_per_roll(
    *,
    rolls_count: int | None,
    price_per_roll: float | None,
    price_total: float | None,
) -> float | None:
    """Response-layer helper: only fill missing per-roll if derivable."""
    if price_per_roll is not None:
        try:
            return float(price_per_roll)
        except Exception:
            return None
    if price_total is None or rolls_count is None:
        return None
    try:
        n = int(rolls_count)
        if n <= 0:
            return None
        pt = Decimal(str(price_total))
        return float(_round2(pt / Decimal(n)))
    except Exception:
        return None
