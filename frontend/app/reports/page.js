"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

export default function Page() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");

  async function reload() {
    setErr("");
    try {
      const data = await fetchJson("/reports/monthly");
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
      <h1 style={{ margin: 0 }}>Reports</h1>
      <p style={{ margin: 0, color: "#374151" }}>
        MVP：按月/材质/打印机聚合统计 + CSV 导出。
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={reload}>刷新</button>
        {err ? <div style={{ color: "#b91c1c" }}>{err}</div> : null}
      </div>
      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>月份</th>
              <th style={{ padding: 6 }}>克数</th>
              <th style={{ padding: 6 }}>成本估算</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.month} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{r.month}</td>
                <td style={{ padding: 6 }}>{r.grams}</td>
                <td style={{ padding: 6 }}>{r.cost_est}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


