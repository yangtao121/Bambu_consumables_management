from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import ssl
import threading
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
from collector.db.models.normalized_event import NormalizedEvent
from collector.db.models.printer import Printer
from collector.db.models.raw_event import RawEvent
from collector.db.session import async_session_factory


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collector")

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

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, reason_code: Any, properties: Any = None) -> None:
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
    tray_now = ams.get("tray_now") if isinstance(ams, dict) else None
    trays = ams.get("tray") if isinstance(ams, dict) and isinstance(ams.get("tray"), list) else []

    tray_list = []
    for t in trays:
        if not isinstance(t, dict):
            continue
        tray_list.append(
            {
                "id": t.get("id"),
                "type": t.get("type"),
                "color": t.get("color"),
                "remain": t.get("remain"),
            }
        )

    return {
        "gcode_state": gcode_state,
        "progress": progress_int,
        "tray_now": tray_now,
        "ams_trays": tray_list,
        "mc_remaining_time": p.get("mc_remaining_time"),
        "gcode_start_time": p.get("gcode_start_time"),
        "gcode_file": p.get("gcode_file"),
    }


def _derive_event_type(gcode_state: str | None, last_state: str | None) -> str:
    # MVP：用 gcode_state 变更推导生命周期
    if last_state != gcode_state:
        if gcode_state in {"RUNNING"}:
            return "PrintStarted"
        if gcode_state in {"IDLE"} and last_state in {"RUNNING"}:
            return "PrintEnded"
        if gcode_state in {"FAILED", "STOPPED", "CANCELED"}:
            return "PrintFailed"
        return "StateChanged"
    return "PrintProgress"


async def ingest_loop(ingest_q: "asyncio.Queue[IngestItem]") -> None:
    state_by_printer: dict[uuid.UUID, tuple[str | None, int | None]] = {}

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

                last_state, last_progress = state_by_printer.get(item.printer_id, (None, None))
                event_type = _derive_event_type(gcode_state, last_state)

                # 降噪：progress 未变化时不写 normalized_events（但 raw_events 仍保留）
                if event_type == "PrintProgress" and progress_int is not None and progress_int == last_progress:
                    await session.commit()
                    continue

                state_by_printer[item.printer_id] = (gcode_state, progress_int)

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
    asyncio.run(main())


