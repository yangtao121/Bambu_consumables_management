"use client";

import { useEffect, useState } from "react";
import { apiBaseUrl, fetchJson } from "../../lib/api";

function formatGcodeState(st) {
  if (!st) return "-";
  const s = String(st).toUpperCase();
  if (s === "RUNNING") return "打印中";
  if (s === "PAUSE" || s === "PAUSED") return "暂停";
  if (s === "FINISH" || s === "IDLE") return "空闲";
  if (s === "PREPARE" || s === "PREPARING") return "准备中";
  if (s === "FAILED" || s === "ERROR") return "异常";
  return s;
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

export default function Page() {
  const [items, setItems] = useState([]);
  const [reportsById, setReportsById] = useState({});
  const [form, setForm] = useState({
    ip: "",
    serial: "",
    lan_access_code: "",
    alias: "",
    model: ""
  });
  const [err, setErr] = useState("");

  const printerIdsKey = items
    .map((p) => p && p.id)
    .filter(Boolean)
    .join("|");

  async function reload() {
    setErr("");
    try {
      const data = await fetchJson("/printers");
      setItems(data);
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  useEffect(() => {
    reload();

    // Realtime updates via SSE
    const url = `${apiBaseUrl()}/realtime/printers`;
    const es = new EventSource(url);
    es.addEventListener("printers", (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload && Array.isArray(payload.printers)) {
          setItems(payload.printers);
        }
      } catch (_err) {
        // ignore parse errors; user can still manually refresh
      }
    });
    es.onerror = () => {
      // Don't spam errors; keep manual refresh available
    };

    // Fallback polling (SSE may be blocked in some network/proxy setups)
    const pollId = setInterval(() => {
      reload();
    }, 5000);

    return () => {
      es.close();
      clearInterval(pollId);
    };
  }, []);

  // Per-printer live report (print status / progress / tray info)
  useEffect(() => {
    let cancelled = false;
    const sources = new Map();

    async function loadLatest(printerId) {
      try {
        const r = await fetchJson(`/printers/${printerId}/latest-report`);
        if (!cancelled) {
          setReportsById((prev) => ({ ...prev, [printerId]: r }));
        }
      } catch (_e) {
        // ignore; SSE may still fill
      }
    }

    for (const p of items) {
      if (!p?.id) continue;
      loadLatest(p.id);

      const sseUrl = `${apiBaseUrl()}/realtime/printers/${p.id}`;
      const es = new EventSource(sseUrl);
      es.addEventListener("printer", (e) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload && payload.printer_id) {
            setReportsById((prev) => ({ ...prev, [payload.printer_id]: payload }));
          }
        } catch (_err) {
          // ignore parse errors
        }
      });
      es.onerror = () => {
        // ignore; polling still works
      };
      sources.set(p.id, es);
    }

    // low-frequency polling to cover SSE blocked cases
    const pollId = setInterval(() => {
      for (const p of items) {
        if (p?.id) loadLatest(p.id);
      }
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(pollId);
      for (const es of sources.values()) es.close();
    };
  }, [printerIdsKey]);

  async function onSubmit(e) {
    e.preventDefault();
    setErr("");
    try {
      await fetchJson("/printers", {
        method: "POST",
        body: JSON.stringify({
          ip: form.ip,
          serial: form.serial,
          lan_access_code: form.lan_access_code,
          alias: form.alias || null,
          model: form.model || null
        })
      });
      setForm({ ip: "", serial: "", lan_access_code: "", alias: "", model: "" });
      await reload();
    } catch (e2) {
      setErr(String(e2.message || e2));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ margin: 0 }}>Printers</h1>
      <p style={{ margin: 0, color: "#374151" }}>添加/查看打印机（IP、Serial、LAN Code）。</p>

      <form onSubmit={onSubmit} style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 8 }}>
          <input
            placeholder="IP"
            value={form.ip}
            onChange={(e) => setForm({ ...form, ip: e.target.value })}
          />
          <input
            placeholder="Serial"
            value={form.serial}
            onChange={(e) => setForm({ ...form, serial: e.target.value })}
          />
          <input
            placeholder="LAN Code"
            value={form.lan_access_code}
            onChange={(e) => setForm({ ...form, lan_access_code: e.target.value })}
          />
          <input
            placeholder="Alias（可选）"
            value={form.alias}
            onChange={(e) => setForm({ ...form, alias: e.target.value })}
          />
          <input
            placeholder="Model（可选）"
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
          />
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <button type="submit">添加</button>
          <button type="button" onClick={reload}>
            刷新
          </button>
        </div>
        {err ? <div style={{ marginTop: 8, color: "#b91c1c" }}>{err}</div> : null}
      </form>

      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>打印机列表</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>Alias</th>
              <th style={{ padding: 6 }}>Serial</th>
              <th style={{ padding: 6 }}>IP</th>
              <th style={{ padding: 6 }}>Status</th>
              <th style={{ padding: 6 }}>LastSeen</th>
              <th style={{ padding: 6 }}>打印状态</th>
              <th style={{ padding: 6 }}>进度</th>
              <th style={{ padding: 6 }}>任务</th>
              <th style={{ padding: 6 }}>当前托盘</th>
              <th style={{ padding: 6 }}>上报时间</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => {
              const rep = reportsById[p.id];
              const ev = rep?.event || rep?.data || null;
              const gcodeState = ev?.gcode_state || ev?.gcodeState || null;
              const progress = ev?.progress ?? null;
              const taskId = ev?.task_id || ev?.subtask_id || null;
              const taskName = ev?.subtask_name || ev?.gcode_file || null;
              const trayNow = ev?.tray_now ?? null;
              const trays = Array.isArray(ev?.ams_trays) ? ev.ams_trays : [];
              const trayObj = trays.find((t) => t && t.id === trayNow);
              const remain = trayObj?.remain ?? null;
              const occurredAt = rep?.occurred_at || null;

              return (
              <tr key={p.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{p.alias || "-"}</td>
                <td style={{ padding: 6 }}>{p.serial}</td>
                <td style={{ padding: 6 }}>{p.ip}</td>
                <td style={{ padding: 6 }}>{p.status}</td>
                <td style={{ padding: 6 }}>{p.last_seen || "-"}</td>
                  <td style={{ padding: 6 }}>{formatGcodeState(gcodeState)}</td>
                  <td style={{ padding: 6 }}>{progress == null ? "-" : `${progress}%`}</td>
                  <td style={{ padding: 6 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <div>{taskId || "-"}</div>
                      <div style={{ color: "#6b7280", fontSize: 12 }}>{taskName || ""}</div>
                    </div>
                  </td>
                  <td style={{ padding: 6 }}>
                    {trayNow == null || trayNow === 255 ? "-" : `Tray ${trayNow}`}
                    {remain == null ? "" : `（remain ${remain}%）`}
                  </td>
                  <td style={{ padding: 6 }}>{fmtTime(occurredAt)}</td>
              </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ marginTop: 8, color: "#6b7280", fontSize: 12 }}>
          注：当前“消耗克数”一般在打印结束后结算生成（`consumption_records`）。这里先展示打印机上报的托盘 remain(%) 与实时状态/进度。
        </div>
      </div>
    </div>
  );
}


