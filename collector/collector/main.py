from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import urllib.request

import orjson
import paho.mqtt.client as mqtt
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from collector.core.config import settings
from collector.core.crypto import decrypt_str
from collector.gcode_estimator import GcodeEstimateManager
from collector.db.models.normalized_event import NormalizedEvent
from collector.db.models.printer import Printer
from collector.db.models.raw_event import RawEvent
from collector.db.session import async_session_factory


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collector")

_GCODE_ESTIMATOR = GcodeEstimateManager()

# region agent log
import os

_DBG_PATH = os.getenv("AGENT_DEBUG_LOG_PATH") or "/Volumes/extend/code/3d_consumables_management/.cursor/debug.log"
_DBG_SESSION = "debug-session"
_DBG_RUN = settings.__dict__.get("debug_run_id") if False else __import__("os").getenv("DEBUG_RUN_ID", "run1")


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
# endregion


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _event_id_for_payload(printer_id: uuid.UUID, payload_hash: str) -> str:
    raw = f"{printer_id}:{payload_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class IngestItem:
    printer_id: uuid.UUID
    topic: str
    payload_bytes: bytes
    received_at: datetime


class PrinterWatcher:
    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        ingest_q: "asyncio.Queue[IngestItem]",
        printer: Printer,
        lan_code_plain: str,
    ) -> None:
        self.loop = loop
        self.ingest_q = ingest_q
        self.printer = printer
        self.lan_code_plain = lan_code_plain
        self.topic_report = f"device/{printer.serial}/report"

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
        self._client.username_pw_set("bblp", self.lan_code_plain)

        # TLS（拓竹 LAN MQTT 通常使用 8883）
        if settings.allow_insecure_mqtt_tls:
            self._client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
            self._client.tls_insecure_set(True)
        else:
            self._client.tls_set(tls_version=ssl.PROTOCOL_TLS)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        logger.info("mqtt connected serial=%s reason=%s", self.printer.serial, reason_code)
        client.subscribe(self.topic_report)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: Any = None,
        reason_code: Any = None,
        properties: Any = None,
    ) -> None:
        # Callback API v2: (client, userdata, disconnect_flags, reason_code, properties)
        logger.warning("mqtt disconnected serial=%s reason=%s", self.printer.serial, reason_code)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        # callback 在 paho 线程内执行：用 loop.call_soon_threadsafe 安全入队
        item = IngestItem(
            printer_id=self.printer.id,
            topic=msg.topic,
            payload_bytes=bytes(msg.payload),
            received_at=_utcnow(),
        )

        def _put_nowait() -> None:
            try:
                self.ingest_q.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning("ingest queue full, dropping message serial=%s", self.printer.serial)

        self.loop.call_soon_threadsafe(_put_nowait)

    def start_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self._run, name=f"mqtt-{self.printer.serial}", daemon=True)
        t.start()
        return t

    def _run(self) -> None:
        # 断线重连：paho 内部有重连逻辑，但这里用 loop_forever 简化
        while True:
            try:
                # region agent log
                _agent_log(
                    "D",
                    "collector/collector/main.py:connect",
                    "mqtt connect attempt",
                    {"serial": (self.printer.serial or "")[:8], "ip": self.printer.ip, "port": 8883},
                )
                # endregion
                self._client.connect(self.printer.ip, 8883, keepalive=60)
                self._client.loop_forever(retry_first_connection=True)
            except Exception:
                logger.exception("mqtt loop crashed serial=%s, retrying in 5s", self.printer.serial)
                import time

                time.sleep(5)


def _normalize_color_hex(v: object) -> str | None:
    """
    Normalize Bambu color field to '#RRGGBB' when possible.
    Accepts: 'FFFFFF', '#FFFFFF', 'FFFFFFFF' (take last 6), etc.
    """
    if not isinstance(v, str):
        return None
    s0 = v.strip()
    if not s0:
        return None
    raw = s0[1:].strip() if s0.startswith("#") else s0
    hx = raw.upper()
    if not hx:
        return None
    if not all(c in "0123456789ABCDEF" for c in hx):
        return None
    if len(hx) == 8:
        # Bambu tray_color often looks like RRGGBBAA (alpha last), e.g. '8E9089FF'.
        # Some other sources use AARRGGBB. Use simple heuristics to support both.
        if hx.endswith(("FF", "00")):
            return f"#{hx[:6]}"
        if hx.startswith(("FF", "00")):
            return f"#{hx[-6:]}"
        # ambiguous: keep previous behavior
        return f"#{hx[-6:]}"
    if len(hx) == 6:
        return f"#{hx}"
    return None


def _to_int(v: object) -> int | None:
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        vv = v.strip()
        if vv.isdigit():
            try:
                return int(vv)
            except Exception:
                return None
    return None


def _to_float(v: object) -> float | None:
    if isinstance(v, (int, float)):
        fv = float(v)
        return fv if fv == fv else None  # NaN guard
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            fv = float(s)
            return fv if fv == fv else None
        except Exception:
            return None
    return None


def _normalize_filament_items(print_obj: dict) -> list[dict]:
    """
    Best-effort extraction for slice estimated / runtime filament usage.
    Field names vary between firmwares; we keep a normalized subset + raw for debugging.
    """
    raw_items = print_obj.get("filament")
    if not isinstance(raw_items, list):
        return []

    out: list[dict] = []
    for idx, it in enumerate(raw_items):
        if not isinstance(it, dict):
            continue

        tray_id = (
            _to_int(it.get("tray_id"))
            or _to_int(it.get("tray"))
            or _to_int(it.get("trayId"))
            or _to_int(it.get("ams_tray"))
        )

        material = it.get("type") or it.get("tray_type") or it.get("material")
        material_s = material if isinstance(material, str) and material.strip() else None
        color_hex = _normalize_color_hex(it.get("color") or it.get("tray_color") or it.get("colour"))

        used_len = _to_float(it.get("used") or it.get("used_len") or it.get("used_mm") or it.get("length_used"))
        total_len = _to_float(it.get("total") or it.get("total_len") or it.get("total_mm") or it.get("length_total"))

        used_g = _to_float(
            it.get("used_g")
            or it.get("used_grams")
            or it.get("grams_used")
            or it.get("weight_used")
            or it.get("used_weight")
        )
        total_g = _to_float(
            it.get("total_g")
            or it.get("total_grams")
            or it.get("grams_total")
            or it.get("weight_total")
            or it.get("total_weight")
        )

        gcode = it.get("gcode") or it.get("extruder") or it.get("tool")
        gcode_s = str(gcode).strip() if gcode is not None and str(gcode).strip() else None

        out.append(
            {
                "idx": idx,
                "tray_id": tray_id,
                "type": material_s,
                "color_hex": color_hex,
                "gcode": gcode_s,
                "used_mm": used_len,
                "total_mm": total_len,
                "used_g": used_g,
                "total_g": total_g,
                "raw": it,
            }
        )

    return out


def _normalize_event_from_payload(payload: dict) -> dict | None:
    # 只关心 print 字段（按 docs/局域网读取方法.md 的描述）
    p = payload.get("print")
    if not isinstance(p, dict):
        return None

    gcode_state = p.get("gcode_state")
    progress = p.get("mc_percent") or p.get("progress") or p.get("mc_print_percent")
    try:
        progress_int = int(progress) if progress is not None else None
    except Exception:
        progress_int = None

    ams = p.get("ams") if isinstance(p.get("ams"), dict) else None
    tray_now_raw = ams.get("tray_now") if isinstance(ams, dict) else None

    trays: list[dict] = []
    if isinstance(ams, dict):
        # Some firmwares report trays directly under `ams.tray`
        if isinstance(ams.get("tray"), list):
            trays.extend([t for t in ams["tray"] if isinstance(t, dict)])
        # More commonly: `ams.ams` is a list of AMS units, each has `tray` list
        if isinstance(ams.get("ams"), list):
            for unit in ams["ams"]:
                if isinstance(unit, dict) and isinstance(unit.get("tray"), list):
                    trays.extend([t for t in unit["tray"] if isinstance(t, dict)])

    tray_now = _to_int(tray_now_raw)

    tray_list = []
    for t in trays:
        # id/tray_now are often strings in payload
        tid = _to_int(t.get("id"))
        if tid is None:
            continue
        tray_list.append(
            {
                "id": tid,
                "type": t.get("tray_type") or t.get("type"),
                "color": t.get("tray_color") or t.get("color"),
                "remain": t.get("remain"),
                # Useful for future auto-mapping / debugging
                "tag_uid": t.get("tag_uid"),
                "tray_uuid": t.get("tray_uuid"),
                "tray_id_name": t.get("tray_id_name"),
            }
        )

    filament_items = _normalize_filament_items(p)

    return {
        "gcode_state": gcode_state,
        "progress": progress_int,
        "tray_now": tray_now,
        "ams_trays": tray_list,
        "filament": filament_items,
        "mc_remaining_time": p.get("mc_remaining_time"),
        "gcode_start_time": p.get("gcode_start_time"),
        "gcode_file": p.get("gcode_file"),
        "task_id": p.get("task_id") or p.get("job_id") or p.get("subtask_id"),
        "subtask_id": p.get("subtask_id"),
        "subtask_name": p.get("subtask_name"),
    }


def _derive_event_type(gcode_state: str | None, last_state: str | None) -> str:
    # MVP：用 gcode_state 变更推导生命周期
    if last_state != gcode_state:
        running_states = {"RUNNING"}
        ended_states = {"IDLE", "FINISH"}
        failed_states = {"FAILED", "STOPPED", "CANCELED"}

        # Start when entering RUNNING from non-running state
        if gcode_state in running_states and last_state not in running_states:
            return "PrintStarted"
        # End when leaving RUNNING to FINISH/IDLE
        if gcode_state in ended_states and last_state in running_states:
            return "PrintEnded"
        if gcode_state in failed_states:
            return "PrintFailed"
        return "StateChanged"
    return "PrintProgress"


def _ams_signature(normalized_data: dict) -> str:
    """
    Build a stable signature for AMS-related state to avoid over-aggressive de-duplication.

    We intentionally include fields that reflect *physical* tray changes even when progress
    does not move (e.g. user swaps filament, tray becomes empty/filled).
    """
    tray_now = normalized_data.get("tray_now")
    trays = normalized_data.get("ams_trays")
    items: list[dict] = []
    if isinstance(trays, list):
        for t in trays:
            if not isinstance(t, dict):
                continue
            tid = t.get("id")
            try:
                tid_i = int(tid)
            except Exception:
                continue
            items.append(
                {
                    "id": tid_i,
                    "type": t.get("type"),
                    "color": t.get("color"),
                    "remain": t.get("remain"),
                    "tag_uid": t.get("tag_uid"),
                    "tray_uuid": t.get("tray_uuid"),
                    "tray_id_name": t.get("tray_id_name"),
                }
            )
    items.sort(key=lambda x: x.get("id", 0))
    blob = {
        "tray_now": tray_now,
        "trays": items,
    }
    # orjson.dumps is stable with OPT_SORT_KEYS; then hash to a short comparable string.
    return _sha256_hex(orjson.dumps(blob, option=orjson.OPT_SORT_KEYS))


def _filament_signature(normalized_data: dict) -> str:
    """
    Signature for filament usage/estimate fields.
    Ensures we don't drop usage changes when progress is unchanged.
    """
    items = normalized_data.get("filament")
    if not isinstance(items, list):
        items = []
    normalized_items: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        normalized_items.append(
            {
                "idx": it.get("idx"),
                "tray_id": it.get("tray_id"),
                "type": it.get("type"),
                "color_hex": it.get("color_hex"),
                "gcode": it.get("gcode"),
                "used_mm": it.get("used_mm"),
                "total_mm": it.get("total_mm"),
                "used_g": it.get("used_g"),
                "total_g": it.get("total_g"),
            }
        )
    normalized_items.sort(key=lambda x: (x.get("idx") if isinstance(x.get("idx"), int) else 0))
    return _sha256_hex(orjson.dumps({"filament": normalized_items}, option=orjson.OPT_SORT_KEYS))


def _estimate_signature(normalized_data: dict) -> str:
    """
    Signature for gcode-derived estimate fields.
    We must include this in the dedupe rule; otherwise an estimate that arrives later
    (while progress stays the same) could be skipped and never persisted.
    """
    ge = normalized_data.get("gcode_estimate")
    if not isinstance(ge, dict):
        return _sha256_hex(orjson.dumps({"gcode_estimate": None}, option=orjson.OPT_SORT_KEYS))

    # Keep it small + stable.
    total_g = ge.get("total_g")
    try:
        total_g_v = round(float(total_g), 4) if total_g is not None else None
    except Exception:
        total_g_v = None

    blob = {
        "source": ge.get("source"),
        "confidence": ge.get("confidence"),
        "gcode_3mf_name": ge.get("gcode_3mf_name"),
        "member_gcode_path": ge.get("member_gcode_path"),
        "total_g": total_g_v,
        "per_filament_len": ge.get("per_filament_len"),
        "error": ge.get("error"),
    }
    return _sha256_hex(orjson.dumps({"gcode_estimate": blob}, option=orjson.OPT_SORT_KEYS))


def _make_job_key_from_normalized(printer_id: uuid.UUID, normalized_data: dict, occurred_at: datetime) -> str:
    task_id = normalized_data.get("task_id") or normalized_data.get("subtask_id")
    if isinstance(task_id, (int, float)) and task_id:
        return f"{printer_id}:{int(task_id)}"
    if isinstance(task_id, str) and task_id.strip() and task_id.strip() != "0":
        return f"{printer_id}:{task_id.strip()}"
    gcode_start_time = normalized_data.get("gcode_start_time")
    gcode_file = normalized_data.get("gcode_file") or ""
    if isinstance(gcode_start_time, (int, float)) and gcode_start_time > 0:
        return f"{printer_id}:{int(gcode_start_time)}:{gcode_file}"
    return f"{printer_id}:{int(occurred_at.timestamp())}:{gcode_file}"


def _maybe_inject_cached_gcode_estimate(normalized_data: dict, *, est_key: str) -> None:
    est = _GCODE_ESTIMATOR.get_cached(est_key)
    if est is None:
        return

    normalized_data["gcode_estimate"] = est.as_json()

    # Only override `filament` when MQTT doesn't provide it and we have per-filament totals.
    existing = normalized_data.get("filament")
    if (not isinstance(existing, list) or len(existing) == 0) and isinstance(est.per_filament, list) and est.per_filament:
        normalized_data["filament"] = est.per_filament
        # Strict mode: backend must NOT fallback to tray_now if tray_id can't be matched uniquely.
        normalized_data["filament_strict_no_fallback"] = True


def _selftest_ams_dedup() -> None:
    """
    Lightweight regression test for the dedupe rule:
    - progress unchanged + AMS changed => MUST NOT skip normalized_events write
    - progress unchanged + AMS unchanged => MAY skip
    """

    def _payload_with_trays(trays: list[dict]) -> dict:
        return {
            "print": {
                "gcode_state": "RUNNING",
                "mc_percent": 50,
                "gcode_file": "demo.gcode",
                "task_id": 123,
                "ams": {
                    "tray_now": "0",
                    "ams": [
                        {
                            "tray": trays,
                        }
                    ],
                },
            }
        }

    # No AMS field -> normalize to empty trays; signature should still be stable
    p_none = {"print": {"gcode_state": "RUNNING", "mc_percent": 50, "gcode_file": "demo.gcode", "task_id": 123}}
    n_none = _normalize_event_from_payload(p_none)
    assert isinstance(n_none, dict)
    assert n_none.get("progress") == 50
    assert n_none.get("tray_now") is None
    assert isinstance(n_none.get("ams_trays"), list) and len(n_none["ams_trays"]) == 0
    sig_none = _ams_signature(n_none)
    assert sig_none == _ams_signature(n_none)

    # 3 trays (0/1/2)
    p1 = _payload_with_trays(
        [
            {"id": "0", "tray_type": "PLA", "tray_color": "FFFFFF", "remain": 90},
            {"id": "1", "tray_type": "PLA", "tray_color": "FF0000", "remain": 80},
            {"id": "2", "tray_type": "PLA", "tray_color": "00FF00", "remain": 70},
        ]
    )
    n1 = _normalize_event_from_payload(p1)
    assert isinstance(n1, dict)
    assert n1.get("progress") == 50
    assert isinstance(n1.get("ams_trays"), list) and len(n1["ams_trays"]) == 3
    assert any(t.get("id") == 2 for t in n1["ams_trays"])
    sig1 = _ams_signature(n1)
    assert isinstance(sig1, str) and len(sig1) > 0

    # 4th tray appears (id="3" string) while progress stays the same
    p2 = _payload_with_trays(
        [
            {"id": "0", "tray_type": "PLA", "tray_color": "FFFFFF", "remain": 90},
            {"id": "1", "tray_type": "PLA", "tray_color": "FF0000", "remain": 80},
            {"id": "2", "tray_type": "PLA", "tray_color": "00FF00", "remain": 70},
            # remain can be 0~1 fraction in some firmwares; include to ensure signature captures it.
            {"id": "3", "tray_type": "PLA", "tray_color": "0000FF", "remain": 0.6},
        ]
    )
    n2 = _normalize_event_from_payload(p2)
    assert isinstance(n2, dict)
    assert n2.get("progress") == 50
    assert isinstance(n2.get("ams_trays"), list) and len(n2["ams_trays"]) == 4
    assert any(t.get("id") == 3 for t in n2["ams_trays"])
    sig2 = _ams_signature(n2)
    assert sig2 != sig1

    # Simulate dedupe decision with prior state (PrintProgress)
    last_state = "RUNNING"
    last_progress = 50
    last_sig = sig1
    event_type = _derive_event_type(n2.get("gcode_state"), last_state)
    assert event_type == "PrintProgress"

    should_skip_when_changed = event_type == "PrintProgress" and n2.get("progress") == last_progress and sig2 == last_sig
    assert should_skip_when_changed is False

    # Unchanged AMS + unchanged progress => skip is allowed
    should_skip_when_same = event_type == "PrintProgress" and n1.get("progress") == last_progress and _ams_signature(n1) == last_sig
    assert should_skip_when_same is True

    # Filament usage changes while progress stays the same => must NOT be treated as identical.
    p3 = _payload_with_trays(
        [
            {"id": "0", "tray_type": "PLA", "tray_color": "FFFFFF", "remain": 90},
            {"id": "1", "tray_type": "PLA", "tray_color": "FF0000", "remain": 80},
            {"id": "2", "tray_type": "PLA", "tray_color": "00FF00", "remain": 70},
        ]
    )
    p3["print"]["filament"] = [{"tray_id": "0", "total_g": 12.3, "used_g": 0.1}]
    n3 = _normalize_event_from_payload(p3)
    assert isinstance(n3, dict)
    assert _filament_signature(n3) != _filament_signature(n1)


async def ingest_loop(ingest_q: "asyncio.Queue[IngestItem]") -> None:
    # (last_gcode_state, last_progress, last_ams_sig, last_fil_sig, last_est_sig)
    state_by_printer: dict[uuid.UUID, tuple[str | None, int | None, str | None, str | None, str | None]] = {}
    # Small cache to avoid decrypting the LAN code for every message.
    # printer_id -> (loaded_at_ts, printer_ip, access_code_plain)
    printer_info_cache: dict[uuid.UUID, tuple[float, str, str]] = {}

    while True:
        item = await ingest_q.get()
        payload_hash = _sha256_hex(item.payload_bytes)

        try:
            payload = orjson.loads(item.payload_bytes)
        except Exception:
            # 无法解析则也存 raw_events（以字符串形式），但 normalized 忽略
            payload = {"_raw": item.payload_bytes.decode("utf-8", errors="replace")}

        normalized_data = _normalize_event_from_payload(payload) if isinstance(payload, dict) else None

        async with async_session_factory() as session:
            raw = RawEvent(
                printer_id=item.printer_id,
                topic=item.topic,
                payload_json=payload if isinstance(payload, dict) else {"_raw": str(payload)},
                payload_hash=payload_hash,
                received_at=item.received_at,
            )
            session.add(raw)
            await session.flush()

            # 更新 printer last_seen/status
            await session.execute(
                update(Printer)
                .where(Printer.id == item.printer_id)
                .values(last_seen=item.received_at, status="online")
            )

            if normalized_data is not None:
                gcode_state = normalized_data.get("gcode_state")
                progress_int = normalized_data.get("progress")

                # G-code estimate: schedule fetch during PREPARE/RUNNING; inject cached result when available.
                try:
                    if isinstance(gcode_state, str) and gcode_state in {"PREPARE", "RUNNING"}:
                        est_key = _make_job_key_from_normalized(item.printer_id, normalized_data, item.received_at)
                        _maybe_inject_cached_gcode_estimate(normalized_data, est_key=est_key)

                        if _GCODE_ESTIMATOR.get_cached(est_key) is None:
                            now = time.time()
                            cached = printer_info_cache.get(item.printer_id)
                            if not cached or (now - float(cached[0])) > 300.0:
                                pr = await session.get(Printer, item.printer_id)
                                if pr and pr.ip and pr.lan_access_code_enc:
                                    lan_code_plain = decrypt_str(settings.app_secret_key, pr.lan_access_code_enc)
                                    printer_info_cache[item.printer_id] = (now, str(pr.ip), str(lan_code_plain))
                                    cached = printer_info_cache[item.printer_id]

                            if cached:
                                _loaded_at, ip, lan_code_plain = cached
                                await _GCODE_ESTIMATOR.maybe_schedule(
                                    key=est_key,
                                    printer_ip=ip,
                                    access_code=lan_code_plain,
                                    subtask_name=normalized_data.get("subtask_name") if isinstance(normalized_data.get("subtask_name"), str) else None,
                                    gcode_file=normalized_data.get("gcode_file") if isinstance(normalized_data.get("gcode_file"), str) else None,
                                )
                except Exception:
                    # Never break ingestion due to estimator issues.
                    pass

                ams_sig = _ams_signature(normalized_data)
                fil_sig = _filament_signature(normalized_data)
                est_sig = _estimate_signature(normalized_data)

                last_state, last_progress, last_ams_sig, last_fil_sig, last_est_sig = state_by_printer.get(
                    item.printer_id, (None, None, None, None, None)
                )
                event_type = _derive_event_type(gcode_state, last_state)

                # 降噪：只有在 *进度不变* 且 *AMS 也不变* 时才跳过写入 normalized_events（raw_events 仍保留）。
                # 这样可以保证“换料/空槽变化（但进度不动）”也会生成新事件，驱动前端更新。
                if (
                    event_type == "PrintProgress"
                    and progress_int == last_progress
                    and ams_sig == last_ams_sig
                    and fil_sig == last_fil_sig
                    and est_sig == last_est_sig
                ):
                    await session.commit()
                    continue

                state_by_printer[item.printer_id] = (gcode_state, progress_int, ams_sig, fil_sig, est_sig)

                ev = {
                    "event_id": _event_id_for_payload(item.printer_id, payload_hash),
                    "printer_id": item.printer_id,
                    "type": event_type,
                    "occurred_at": item.received_at,
                    "data_json": normalized_data,
                    "raw_event_id": raw.id,
                }
                stmt = insert(NormalizedEvent).values(**ev).on_conflict_do_nothing(index_elements=["event_id"])
                await session.execute(stmt)

            await session.commit()


async def main() -> None:
    ingest_q: asyncio.Queue[IngestItem] = asyncio.Queue(maxsize=2000)

    # DB/迁移可能尚未就绪：允许重试
    try:
        async with async_session_factory() as session:
            printers = (await session.execute(select(Printer))).scalars().all()
        # region agent log
        _agent_log(
            "D",
            "collector/collector/main.py:load_printers",
            "printers loaded",
            {"count": len(printers), "serials": [(p.serial or "")[:8] for p in printers[:5]]},
        )
        # endregion
        if not printers:
            logger.warning("no printers found in DB; collector will still run and retry periodically")
    except Exception:
        # region agent log
        _agent_log("D", "collector/collector/main.py:load_printers", "printers load failed", {})
        # endregion
        logger.warning("db not ready yet; will retry loading printers")

    loop = asyncio.get_running_loop()
    threads: list[threading.Thread] = []

    async def _spawn_watchers() -> None:
        nonlocal threads
        while True:
            try:
                async with async_session_factory() as session:
                    printers_local = (await session.execute(select(Printer))).scalars().all()
            except Exception:
                await asyncio.sleep(5)
                continue

            # 简化：每轮都重建 watchers（MVP），后续可做增量与去重
            if printers_local:
                threads = []
                for p in printers_local:
                    lan_code_plain = decrypt_str(settings.app_secret_key, p.lan_access_code_enc)
                    w = PrinterWatcher(loop=loop, ingest_q=ingest_q, printer=p, lan_code_plain=lan_code_plain)
                    threads.append(w.start_in_thread())
                logger.info("watchers started: %d", len(printers_local))
                return

            await asyncio.sleep(10)

    await asyncio.gather(_spawn_watchers(), ingest_loop(ingest_q))


if __name__ == "__main__":
    # Allow running a quick regression test without any DB/mqtt dependency:
    #   COLLECTOR_SELFTEST=1 python -m collector.main
    if (__import__("os").getenv("COLLECTOR_SELFTEST") or "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
        _selftest_ams_dedup()
        print("collector selftest OK")
    else:
        asyncio.run(main())


