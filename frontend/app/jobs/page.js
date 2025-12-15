"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

export default function Page() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");

  async function reload() {
    setErr("");
    try {
      const data = await fetchJson("/jobs");
      setItems(data);
    } catch (e) {
      setErr(String(e.message || e));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ margin: 0 }}>Jobs</h1>
      <p style={{ margin: 0, color: "#374151" }}>任务历史（由事件处理器从 normalized_events 生成/更新）。</p>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={reload}>刷新</button>
        {err ? <div style={{ color: "#b91c1c" }}>{err}</div> : null}
      </div>

      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>状态</th>
              <th style={{ padding: 6 }}>开始</th>
              <th style={{ padding: 6 }}>结束</th>
              <th style={{ padding: 6 }}>文件</th>
              <th style={{ padding: 6 }}>PrinterId</th>
            </tr>
          </thead>
          <tbody>
            {items.map((j) => (
              <tr key={j.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{j.status}</td>
                <td style={{ padding: 6 }}>{j.started_at}</td>
                <td style={{ padding: 6 }}>{j.ended_at || "-"}</td>
                <td style={{ padding: 6 }}>{j.file_name || "-"}</td>
                <td style={{ padding: 6 }}>{j.printer_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


