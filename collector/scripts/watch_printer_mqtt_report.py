"""\
持续抓取拓竹打印机 LAN MQTT 上报（device/<serial>/report），直到打印结束。

目标：
- 把所有上报原样保存为 ndjson（方便回放/检索）
- 终端只打印“关键字段变化”，避免 1.5 小时刷屏
- 检测到打印结束/失败/取消等终态后，继续抓取一小段时间再退出，确保拿到收尾包

推荐在 docker 容器内跑（collector 镜像已包含 paho-mqtt 依赖）：
  docker compose -f /Volumes/extend/code/3d_consumables_management/docker-compose.yml build collector
  docker compose -f /Volumes/extend/code/3d_consumables_management/docker-compose.yml run --rm collector \
    python /app/scripts/watch_printer_mqtt_report.py \
      --host 192.168.5.203 --serial 22E8BJ5B0600545 --access-code 6adef4b9

输出文件默认写到容器内 /logs（compose 已挂载 logs_data 卷）。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import ssl
import string
import time
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_json_loads(b: bytes) -> dict[str, Any] | None:
    try:
        s = b.decode("utf-8", errors="replace")
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _get(d: Any, path: list[str]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return int(float(s))
        except Exception:
            return None
    return None


def _shorten(s: str, n: int = 160) -> str:
    s = s.replace("\n", " ").replace("\r", " ")
    return s if len(s) <= n else (s[: n - 3] + "...")


def _extract_ams_remain_signature(print_obj: dict[str, Any]) -> list[dict[str, Any]]:
    """提取 AMS 托盘关键字段（用于观察 remain 变化与结束时的结算候选数据）。"""
    ams = print_obj.get("ams") if isinstance(print_obj.get("ams"), dict) else {}

    out: list[dict[str, Any]] = []

    # 常见：print.ams.ams = [{id, tray:[{...}]}]
    if isinstance(ams.get("ams"), list):
        for unit in ams.get("ams") or []:
            if not isinstance(unit, dict):
                continue
            unit_id = unit.get("id")
            trays = unit.get("tray") if isinstance(unit.get("tray"), list) else []
            for t in trays:
                if not isinstance(t, dict):
                    continue
                tray_id = t.get("id") or t.get("tray_id") or t.get("index")
                out.append(
                    {
                        "id": f"{unit_id}:{tray_id}",
                        "remain": t.get("remain") or t.get("remain_len") or t.get("remain_weight"),
                        "total_len": t.get("total_len") or t.get("total"),
                        "tray_color": t.get("tray_color") or t.get("color") or t.get("colour"),
                        "tray_type": t.get("tray_type") or t.get("type"),
                        "tray_sub_brands": t.get("tray_sub_brands") or t.get("brand"),
                        "tray_uuid": t.get("tray_uuid") or t.get("uuid"),
                        "state": t.get("state"),
                    }
                )

    # 兼容：ams.tray 是 list（某些固件/字段）
    elif isinstance(ams.get("tray"), list):
        for t in ams.get("tray") or []:
            if not isinstance(t, dict):
                continue
            out.append(
                {
                    "id": t.get("id") or t.get("tray_id") or t.get("index"),
                    "remain": t.get("remain") or t.get("remain_len") or t.get("remain_weight"),
                    "total_len": t.get("total_len") or t.get("total"),
                    "tray_color": t.get("tray_color") or t.get("color") or t.get("colour"),
                    "tray_type": t.get("tray_type") or t.get("type"),
                    "tray_sub_brands": t.get("tray_sub_brands") or t.get("brand"),
                    "tray_uuid": t.get("tray_uuid") or t.get("uuid"),
                    "state": t.get("state"),
                }
            )

    # 排序稳定，便于 diff
    def _key(x: dict[str, Any]) -> str:
        return str(x.get("id") or "")

    out.sort(key=_key)
    return out


def _terminal_state(print_obj: dict[str, Any]) -> str | None:
    """返回终态名称；不是终态则 None。"""
    gcode_state = str(print_obj.get("gcode_state") or "").strip().upper()
    state = str(print_obj.get("state") or "").strip().upper()

    terminal_tokens = {
        "FINISH",
        "FINISHED",
        "DONE",
        "FAILED",
        "FAIL",
        "STOP",
        "STOPPED",
        "CANCEL",
        "CANCELED",
        "CANCELLED",
        "IDLE",
    }

    if gcode_state in terminal_tokens:
        return gcode_state
    if state in terminal_tokens:
        return state

    # 有些机型结束会把 mc_print_stage 置 0/"0"，但也可能是准备阶段；仅作为弱信号
    mc_print_stage = str(print_obj.get("mc_print_stage") or "").strip()
    mc_percent = _to_int(print_obj.get("mc_percent") or print_obj.get("percent"))
    if mc_print_stage == "0" and mc_percent is not None and mc_percent >= 99:
        return "PROBABLE_END"

    return None


def _summarize(print_obj: dict[str, Any]) -> dict[str, Any]:
    ams = print_obj.get("ams") if isinstance(print_obj.get("ams"), dict) else {}
    return {
        "command": print_obj.get("command"),
        "gcode_state": print_obj.get("gcode_state"),
        "state": print_obj.get("state"),
        "mc_print_stage": print_obj.get("mc_print_stage"),
        "mc_stage": print_obj.get("mc_stage"),
        "mc_percent": print_obj.get("mc_percent") or print_obj.get("percent"),
        "remain_time": print_obj.get("remain_time") or print_obj.get("mc_remaining_time"),
        "task_id": print_obj.get("task_id") or print_obj.get("job_id") or print_obj.get("subtask_id"),
        "subtask_id": print_obj.get("subtask_id"),
        "subtask_name": print_obj.get("subtask_name"),
        "gcode_file": print_obj.get("gcode_file") or print_obj.get("file"),
        "tray_now": ams.get("tray_now"),
        "fail_reason": print_obj.get("fail_reason") or print_obj.get("print_error"),
        # 重点候选字段（存在就保留）
        "has_filament": "filament" in print_obj,
        "has_s_obj": "s_obj" in print_obj,
        "has_mapping": "mapping" in print_obj,
        "has_stg": "stg" in print_obj,
    }


def _sig_for_console(print_obj: dict[str, Any]) -> dict[str, Any]:
    """终端打印用的“变化签名”，越小越好，避免刷屏。"""
    s = _summarize(print_obj)
    s["ams_trays"] = _extract_ams_remain_signature(print_obj)
    # filament 有时很大，终端只做存在性+长度
    fil = print_obj.get("filament")
    s["filament_len"] = len(fil) if isinstance(fil, list) else (1 if fil is not None else 0)
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, help="打印机 IP，例如 192.168.5.203")
    ap.add_argument("--port", type=int, default=8883)
    ap.add_argument("--serial", required=True, help="序列号，例如 22E8BJ5B0600545")
    ap.add_argument("--access-code", required=True, help="LAN 访问码")
    ap.add_argument("--username", default="bblp")
    ap.add_argument("--topic", default="", help="默认 device/<serial>/report")
    ap.add_argument(
        "--out",
        default="",
        help="ndjson 输出路径（容器内建议 /logs/...）；默认自动生成到 /logs",
    )
    ap.add_argument(
        "--stop-after-terminal-seconds",
        type=int,
        default=25,
        help="检测到终态后继续抓取多少秒再退出（用于抓收尾包）",
    )
    ap.add_argument(
        "--print-full-on-terminal",
        action="store_true",
        help="检测到终态时，把 print 对象完整打印一次（可能很大）",
    )
    ap.add_argument(
        "--verify-tls",
        action="store_true",
        help="启用证书校验（多数情况下会失败；默认不校验以便连上自签）",
    )
    args = ap.parse_args()

    host: str = str(args.host).strip()
    port: int = int(args.port)
    serial: str = str(args.serial).strip()
    access_code: str = str(args.access_code).strip()
    username: str = str(args.username).strip()

    topic = str(args.topic).strip() or f"device/{serial}/report"

    if args.out:
        out_path = str(args.out)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = f"/logs/mqtt_capture_{serial}_{ts}.ndjson"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    client_id = "cap_" + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))

    print(f"[mqtt-cap] host={host}:{port} topic={topic} client_id={client_id}")
    print(f"[mqtt-cap] out={out_path}")
    print(f"[mqtt-cap] stop_after_terminal_seconds={args.stop_after_terminal_seconds}")

    stop_requested = False
    terminal_seen_at: float | None = None
    last_console_sig_json: str | None = None

    # line-buffered，避免长时间缓存丢数据
    f = open(out_path, "a", encoding="utf-8", buffering=1)

    def _log_line(obj: dict[str, Any]) -> None:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], reason_code: mqtt.ReasonCode, properties: Any) -> None:
        nonlocal terminal_seen_at
        print(f"[{_utc_ts()}] connected: reason={reason_code}")
        terminal_seen_at = None
        client.subscribe(topic, qos=0)
        print(f"[{_utc_ts()}] subscribed: {topic}")

    def on_disconnect(
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: Any,
    ) -> None:
        # stop_requested 时属于正常退出
        print(f"[{_utc_ts()}] disconnected: reason={reason_code} stop={stop_requested}")

    def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        nonlocal terminal_seen_at, last_console_sig_json, stop_requested

        payload = _safe_json_loads(msg.payload)
        if payload is None:
            return

        # 原样落盘（方便之后做更复杂的解析）
        _log_line({"ts": _utc_ts(), "topic": msg.topic, "payload": payload})

        print_obj = payload.get("print") if isinstance(payload.get("print"), dict) else {}
        if not isinstance(print_obj, dict):
            return

        # 只在关键字段变化时打印（减少刷屏）
        sig = _sig_for_console(print_obj)
        sig_json = json.dumps(sig, ensure_ascii=False, sort_keys=True)
        if sig_json != last_console_sig_json:
            last_console_sig_json = sig_json
            # 把 gcode_file/subtask_name 缩短一点
            sig2 = dict(sig)
            if isinstance(sig2.get("subtask_name"), str):
                sig2["subtask_name"] = _shorten(sig2["subtask_name"], 60)
            if isinstance(sig2.get("gcode_file"), str):
                sig2["gcode_file"] = _shorten(sig2["gcode_file"], 80)
            print(f"[{_utc_ts()}] {json.dumps(sig2, ensure_ascii=False)}")

        term = _terminal_state(print_obj)
        if term:
            if terminal_seen_at is None:
                terminal_seen_at = time.time()
                print(f"[{_utc_ts()}] !!! terminal detected: {term}")
                # 终态时把一些潜在字段提示出来
                keys = sorted(list(print_obj.keys()))
                print(f"[{_utc_ts()}] terminal print keys={keys}")
                if args.print_full_on_terminal:
                    print(f"[{_utc_ts()}] terminal print(full)={json.dumps(print_obj, ensure_ascii=False)[:20000]}")

            # 到点自动退出（仍继续把期间包写进文件）
            if time.time() - float(terminal_seen_at) >= float(args.stop_after_terminal_seconds):
                stop_requested = True
                try:
                    client.disconnect()
                except Exception:
                    pass

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.username_pw_set(username=username, password=access_code)

    # TLS（拓竹 LAN MQTT 通常是 8883 + 自签证书）
    ctx = ssl.create_default_context()
    if not args.verify_tls:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    client.tls_set_context(ctx)
    if not args.verify_tls:
        client.tls_insecure_set(True)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # 自动重连：长时间任务里 WiFi 抖动很常见
    backoff = 1.0
    try:
        while True:
            try:
                print(f"[{_utc_ts()}] connecting... backoff={backoff:.1f}s")
                client.connect(host, port=port, keepalive=60)
                client.loop_start()

                # 主循环：等待 disconnect 或 stop
                while True:
                    time.sleep(0.2)
                    if stop_requested:
                        break
                    if not client.is_connected():
                        break

                client.loop_stop()

                if stop_requested:
                    print(f"[{_utc_ts()}] exit requested, bye")
                    break

                # 非 stop 的断线：重连
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
            except KeyboardInterrupt:
                print(f"[{_utc_ts()}] keyboard interrupt, bye")
                break
            except Exception as e:
                print(f"[{_utc_ts()}] error: {e}")
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
    finally:
        try:
            client.loop_stop()
        except Exception:
            pass
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            f.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
