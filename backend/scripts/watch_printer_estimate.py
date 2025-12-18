"""
实时抓取打印机上报，验证“估算用量/filament”是否可获取。

用法（在宿主机运行）：
  python /Volumes/extend/code/3d_consumables_management/backend/scripts/watch_printer_estimate.py \
    --printer-id d3c66b43-9e5a-45cb-ad37-84322a77b486

它会通过 `docker compose exec db psql` 轮询数据库（不需要额外 Python 依赖）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from typing import Any


def _run_psql(sql: str) -> str:
    cmd = [
        "docker",
        "compose",
        "-f",
        "/Volumes/extend/code/3d_consumables_management/docker-compose.yml",
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "consumables",
        "-d",
        "consumables",
        "-At",
        "-c",
        sql,
    ]
    p = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip() or f"psql failed rc={p.returncode}")
    return p.stdout.strip()


def _safe_get(d: dict, path: list[str]) -> Any:
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _summarize_print_obj(p: dict) -> dict:
    ams = p.get("ams") if isinstance(p.get("ams"), dict) else {}
    tray_now = ams.get("tray_now")
    return {
        "command": p.get("command"),
        "gcode_state": p.get("gcode_state"),
        "mc_print_stage": p.get("mc_print_stage"),
        "mc_percent": p.get("mc_percent") or p.get("percent"),
        "task_id": p.get("task_id") or p.get("job_id") or p.get("subtask_id"),
        "subtask_id": p.get("subtask_id"),
        "subtask_name": p.get("subtask_name"),
        "gcode_file": p.get("gcode_file") or p.get("file"),
        "tray_now": tray_now,
        # 这些是我们要重点关注的“估算/用量”候选字段（存在即打印出来）
        "has_filament": "filament" in p,
        "has_mapping": "mapping" in p,
        "has_stg": "stg" in p,
        "has_s_obj": "s_obj" in p,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--printer-id", required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--show-raw-keys", action="store_true", help="额外打印 print 对象的 top-level keys")
    args = ap.parse_args()

    printer_id = str(args.printer_id).strip()
    if not printer_id:
        raise SystemExit("missing --printer-id")

    last_raw_id: str | None = None
    last_norm_id: str | None = None

    print(f"[watch] printer_id={printer_id} interval={args.interval}s")
    print("[watch] waiting for new raw_events/normalized_events ...")

    while True:
        # raw_events: grab latest print object
        raw_sql = (
            "select id::text || '|' || coalesce(payload_json->'print','{}'::jsonb)::text "
            f"from raw_events where printer_id='{printer_id}' "
            "order by received_at desc, id desc limit 1;"
        )
        raw_line = _run_psql(raw_sql)
        if raw_line and "|" in raw_line:
            raw_id, raw_print_text = raw_line.split("|", 1)
            if raw_id != last_raw_id:
                last_raw_id = raw_id
                try:
                    raw_print = json.loads(raw_print_text)
                except Exception:
                    raw_print = {}
                if isinstance(raw_print, dict) and raw_print:
                    s = _summarize_print_obj(raw_print)
                    print(f"\n[raw:{raw_id}] {json.dumps(s, ensure_ascii=False)}")
                    if args.show_raw_keys:
                        print(f"[raw:{raw_id}] keys={sorted(list(raw_print.keys()))}")
                    if "filament" in raw_print:
                        try:
                            fil = raw_print.get("filament")
                            print(f"[raw:{raw_id}] filament={json.dumps(fil, ensure_ascii=False)[:4000]}")
                        except Exception:
                            print(f"[raw:{raw_id}] filament=<unprintable>")

        # normalized_events: verify collector extracted `filament` (even empty list)
        norm_sql = (
            "select id::text || '|' || coalesce(data_json,'{}'::jsonb)::text "
            f"from normalized_events where printer_id='{printer_id}' "
            "order by occurred_at desc, id desc limit 1;"
        )
        norm_line = _run_psql(norm_sql)
        if norm_line and "|" in norm_line:
            norm_id, norm_text = norm_line.split("|", 1)
            if norm_id != last_norm_id:
                last_norm_id = norm_id
                try:
                    norm = json.loads(norm_text)
                except Exception:
                    norm = {}
                if isinstance(norm, dict) and norm:
                    fil = norm.get("filament")
                    print(
                        f"[norm:{norm_id}] gcode_state={norm.get('gcode_state')} progress={norm.get('progress')} tray_now={norm.get('tray_now')} "
                        f"filament_len={len(fil) if isinstance(fil, list) else None}"
                    )
                    if isinstance(fil, list) and fil:
                        print(f"[norm:{norm_id}] filament_sample={json.dumps(fil[:3], ensure_ascii=False)[:4000]}")

        time.sleep(float(args.interval))


if __name__ == "__main__":
    main()

