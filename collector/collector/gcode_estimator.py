from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GcodeEstimate:
    source: str
    confidence: str
    gcode_3mf_name: str | None
    member_gcode_path: str | None
    total_g: float | None
    per_filament: list[dict[str, Any]]
    error: str | None

    def as_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "confidence": self.confidence,
            "gcode_3mf_name": self.gcode_3mf_name,
            "member_gcode_path": self.member_gcode_path,
            "total_g": self.total_g,
            "per_filament_len": len(self.per_filament) if isinstance(self.per_filament, list) else 0,
            "error": self.error,
        }


def _normalize_name_for_match(s: str) -> str:
    # Keep Chinese/letters/numbers; drop punctuation/space.
    # This is intentionally simple and deterministic.
    return "".join(ch for ch in s.strip() if ("0" <= ch <= "9") or ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ("\u4e00" <= ch <= "\u9fff"))


def _best_match_gcode3mf(candidates: list[str], *, subtask_name: str | None) -> tuple[str | None, str | None]:
    if not candidates:
        return (None, "no_candidates")

    # If no name, we cannot safely choose.
    if not (isinstance(subtask_name, str) and subtask_name.strip()):
        return (None, "missing_subtask_name")

    key = _normalize_name_for_match(subtask_name)
    if not key:
        return (None, "empty_subtask_name")

    # Direct hit: <subtask_name>.gcode.3mf
    direct = f"{subtask_name}.gcode.3mf"
    if direct in candidates:
        return (direct, None)

    scored: list[tuple[int, str]] = []
    for fn in candidates:
        base = fn
        if base.endswith(".gcode.3mf"):
            base = base[: -len(".gcode.3mf")]
        n = _normalize_name_for_match(base)
        if not n:
            continue
        # Very simple similarity: containment + overlap length.
        if key in n or n in key:
            scored.append((min(len(key), len(n)), fn))
        else:
            # overlap heuristic: longest common substring length (bounded, O(n^2) worst but strings are short)
            best = 0
            for i in range(len(key)):
                for j in range(i + 1, min(len(key), i + 32) + 1):
                    if key[i:j] in n:
                        best = max(best, j - i)
            if best > 0:
                scored.append((best, fn))

    if not scored:
        return (None, "no_match")

    scored.sort(reverse=True)
    top_score = scored[0][0]
    top = [fn for sc, fn in scored if sc == top_score]
    if len(top) != 1:
        return (None, "ambiguous_match")

    return (top[0], None)


def _curl_list_root(ip: str, *, username: str, password: str, timeout_sec: int = 12) -> list[str]:
    # --list-only makes parsing easy (one name per line)
    url = f"ftps://{ip}/"
    cmd = [
        "curl",
        "-sS",
        "-k",
        "--list-only",
        "--user",
        f"{username}:{password}",
        url,
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip() or f"curl list failed rc={p.returncode}")
    lines = [ln.strip() for ln in (p.stdout or "").splitlines()]
    return [ln for ln in lines if ln and ln not in {".", ".."}]


def _curl_download(ip: str, *, username: str, password: str, remote_name: str, out_path: str, timeout_sec: int = 60) -> None:
    url = f"ftps://{ip}/{remote_name}"
    cmd = [
        "curl",
        "-sS",
        "-k",
        "--user",
        f"{username}:{password}",
        url,
        "-o",
        out_path,
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout_sec)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip() or f"curl download failed rc={p.returncode}")


_TOTAL_G_RE = re.compile(r"^\s*;\s*total\s+filament\s+weight\s*\[g\]\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.IGNORECASE)


def _split_csv_values(s: str) -> list[str]:
    # Values are usually comma separated. Some fields may use ';' too.
    # Keep raw tokens trimmed.
    parts: list[str] = []
    for chunk in s.replace(";", ",").split(","):
        t = chunk.strip()
        if t:
            parts.append(t)
    return parts


def _parse_gcode_comments(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for ln in text.splitlines():
        if not ln.startswith(";"):
            continue
        # Common patterns:
        #   ; key : value
        #   ; key = value
        ln2 = ln[1:].strip()
        if not ln2:
            continue
        if ":" in ln2:
            k, v = ln2.split(":", 1)
        elif "=" in ln2:
            k, v = ln2.split("=", 1)
        else:
            continue
        k = k.strip().lower()
        v = v.strip()
        if not k or not v:
            continue
        # keep first occurrence only
        out.setdefault(k, v)
    return out


def _extract_per_filament(meta: dict[str, str]) -> list[dict[str, Any]]:
    # Best-effort. We only produce items when we can build aligned arrays.
    # Candidates seen in various slicers/firmwares.
    color_keys = [
        "filament_color",
        "filament_colour",
        "filament_colors",
        "filament_colours",
    ]
    type_keys = [
        "filament_type",
        "filament_types",
        "filament material",
        "filament_material",
    ]
    weight_keys = [
        "filament_weight [g]",
        "filament weight [g]",
        "filament_weight[g]",
        "filament used [g]",
        "filament_used [g]",
        "filament_used[g]",
    ]

    colors: list[str] = []
    types: list[str] = []
    weights: list[str] = []

    for k in color_keys:
        v = meta.get(k)
        if v:
            colors = _split_csv_values(v)
            break

    for k in type_keys:
        v = meta.get(k)
        if v:
            types = _split_csv_values(v)
            break

    for k in weight_keys:
        v = meta.get(k)
        if v:
            weights = _split_csv_values(v)
            break

    if not weights:
        return []

    # Align by weights length; fill missing type/color with None.
    n = len(weights)
    if n <= 0:
        return []

    items: list[dict[str, Any]] = []
    for i in range(n):
        w = weights[i]
        try:
            wg = float(w)
        except Exception:
            continue
        if not (wg == wg) or wg <= 0:
            continue

        c = colors[i] if i < len(colors) else ""
        t = types[i] if i < len(types) else ""

        # Normalize color: accept '#RRGGBB'/'RRGGBB'/'AARRGGBB'
        color_hex: str | None = None
        c0 = c.strip()
        if c0:
            raw = c0[1:] if c0.startswith("#") else c0
            hx = raw.strip().upper()
            if re.fullmatch(r"[0-9A-F]{8}", hx):
                color_hex = f"#{hx[-6:]}"
            elif re.fullmatch(r"[0-9A-F]{6}", hx):
                color_hex = f"#{hx}"

        type_s = t.strip() or None

        items.append(
            {
                "idx": i,
                # tray_id unknown from gcode estimate; backend will match by type+color_hex when unique.
                "tray_id": None,
                "type": type_s,
                "color_hex": color_hex,
                "gcode": None,
                "used_mm": None,
                "total_mm": None,
                "used_g": None,
                "total_g": float(wg),
                "raw": {"from": "gcode_comment"},
            }
        )

    return items


def _extract_single_filament_from_meta(meta: dict[str, str], *, total_g: float | None) -> list[dict[str, Any]]:
    """
    Fallback for common single-material prints where slicer only provides:
      - filament_colour / filament_type (single values)
      - total filament weight [g]
    """
    if total_g is None or not (total_g == total_g) or total_g <= 0:
        return []

    # Prefer british spelling used by Bambu comments: filament_colour
    color_raw = meta.get("filament_colour") or meta.get("filament_color") or ""
    type_raw = meta.get("filament_type") or ""

    colors = _split_csv_values(color_raw) if color_raw else []
    types = _split_csv_values(type_raw) if type_raw else []

    # Only safe when we can confidently say it's a single filament.
    if len(colors) > 1 or len(types) > 1:
        return []

    color_hex: str | None = None
    if colors:
        c0 = colors[0].strip()
        raw = c0[1:] if c0.startswith("#") else c0
        hx = raw.strip().upper()
        if re.fullmatch(r"[0-9A-F]{8}", hx):
            color_hex = f"#{hx[-6:]}"
        elif re.fullmatch(r"[0-9A-F]{6}", hx):
            color_hex = f"#{hx}"

    type_s = types[0].strip() if types else ""
    type_s = type_s or None

    return [
        {
            "idx": 0,
            "tray_id": None,
            "type": type_s,
            "color_hex": color_hex,
            "gcode": None,
            "used_mm": None,
            "total_mm": None,
            "used_g": None,
            "total_g": float(total_g),
            "raw": {"from": "gcode_comment_total"},
        }
    ]


def _parse_gcode_from_3mf(path: str, *, member_hint: str | None) -> tuple[float | None, list[dict[str, Any]], str | None, str | None]:
    with zipfile.ZipFile(path, "r") as z:
        names = z.namelist()

        member: str | None = None
        if isinstance(member_hint, str) and member_hint.strip():
            hint = member_hint.strip().lstrip("/")
            # common: 'Metadata/plate_1.gcode'
            if hint in names:
                member = hint
            elif hint.startswith("data/") and hint[5:] in names:
                member = hint[5:]

        if member is None:
            # fallback: first Metadata/plate_*.gcode
            for n in names:
                if n.startswith("Metadata/") and n.endswith(".gcode") and "plate_" in n:
                    member = n
                    break

        if member is None:
            return (None, [], None, "missing_gcode_member")

        raw = z.read(member)
        # gcode header comments are usually near the beginning.
        head = raw[: min(len(raw), 512_000)]
        txt = head.decode("utf-8", errors="replace")

        total_g: float | None = None
        for ln in txt.splitlines()[:5000]:
            m = _TOTAL_G_RE.match(ln)
            if m:
                try:
                    total_g = float(m.group(1))
                except Exception:
                    total_g = None
                break

        meta = _parse_gcode_comments(txt)
        per = _extract_per_filament(meta)
        if not per:
            per = _extract_single_filament_from_meta(meta, total_g=total_g)

        return (total_g, per, member, None)


class GcodeEstimateManager:
    def __init__(self, *, ttl_sec: int = 2 * 60 * 60) -> None:
        self._ttl_sec = int(ttl_sec)
        self._cache: dict[str, tuple[float, GcodeEstimate]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    def get_cached(self, key: str) -> GcodeEstimate | None:
        now = time.time()
        ent = self._cache.get(key)
        if not ent:
            return None
        exp, est = ent
        if exp <= now:
            return None
        return est

    async def maybe_schedule(
        self,
        *,
        key: str,
        printer_ip: str,
        access_code: str,
        subtask_name: str | None,
        gcode_file: str | None,
        username: str = "bblp",
    ) -> None:
        async with self._lock:
            if self.get_cached(key) is not None:
                return
            if key in self._tasks and not self._tasks[key].done():
                return

            async def _runner() -> None:
                try:
                    est = await asyncio.to_thread(
                        _compute_estimate,
                        printer_ip,
                        username,
                        access_code,
                        subtask_name,
                        gcode_file,
                    )
                except Exception as e:
                    est = GcodeEstimate(
                        source="gcode_3mf",
                        confidence="low",
                        gcode_3mf_name=None,
                        member_gcode_path=None,
                        total_g=None,
                        per_filament=[],
                        error=str(e),
                    )

                # store even failures for a short time to avoid hammering
                exp = time.time() + float(self._ttl_sec)
                async with self._lock:
                    self._cache[key] = (exp, est)

            self._tasks[key] = asyncio.create_task(_runner())


def _compute_estimate(
    printer_ip: str,
    username: str,
    access_code: str,
    subtask_name: str | None,
    gcode_file: str | None,
) -> GcodeEstimate:
    try:
        root = _curl_list_root(printer_ip, username=username, password=access_code)
    except Exception as e:
        return GcodeEstimate(
            source="gcode_3mf",
            confidence="low",
            gcode_3mf_name=None,
            member_gcode_path=None,
            total_g=None,
            per_filament=[],
            error=f"list_root_failed:{e}",
        )

    candidates = [x for x in root if x.endswith(".gcode.3mf")]
    name, why = _best_match_gcode3mf(candidates, subtask_name=subtask_name)
    if name is None:
        return GcodeEstimate(
            source="gcode_3mf",
            confidence="low",
            gcode_3mf_name=None,
            member_gcode_path=None,
            total_g=None,
            per_filament=[],
            error=f"select_failed:{why}",
        )

    # Hint member path: MQTT gives '/data/Metadata/plate_1.gcode'
    member_hint: str | None = None
    if isinstance(gcode_file, str) and gcode_file.strip():
        member_hint = gcode_file.strip()
        if member_hint.startswith("/data/"):
            member_hint = member_hint[len("/data/") :]
        member_hint = member_hint.lstrip("/")

    with tempfile.TemporaryDirectory(prefix="bambu_gcode_") as td:
        local = os.path.join(td, name)
        try:
            _curl_download(printer_ip, username=username, password=access_code, remote_name=name, out_path=local)
        except Exception as e:
            return GcodeEstimate(
                source="gcode_3mf",
                confidence="low",
                gcode_3mf_name=name,
                member_gcode_path=None,
                total_g=None,
                per_filament=[],
                error=f"download_failed:{e}",
            )

        try:
            total_g, per, member_used, err = _parse_gcode_from_3mf(local, member_hint=member_hint)
        except zipfile.BadZipFile:
            return GcodeEstimate(
                source="gcode_3mf",
                confidence="low",
                gcode_3mf_name=name,
                member_gcode_path=None,
                total_g=None,
                per_filament=[],
                error="bad_zip",
            )
        except Exception as e:
            return GcodeEstimate(
                source="gcode_3mf",
                confidence="low",
                gcode_3mf_name=name,
                member_gcode_path=None,
                total_g=None,
                per_filament=[],
                error=f"parse_failed:{e}",
            )

        conf = "high" if (total_g is not None and per) else ("medium" if total_g is not None else "low")
        return GcodeEstimate(
            source="gcode_3mf",
            confidence=conf,
            gcode_3mf_name=name,
            member_gcode_path=member_used,
            total_g=total_g,
            per_filament=per,
            error=err,
        )
