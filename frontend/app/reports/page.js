"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

export default function Page() {
  const [monthly, setMonthly] = useState([]);
  const [daily, setDaily] = useState([]);
  const [err, setErr] = useState("");

  async function reload() {
    setErr("");
    try {
      const [d, m] = await Promise.all([fetchJson("/reports/daily?days=30"), fetchJson("/reports/monthly")]);
      setDaily(Array.isArray(d?.daily) ? d.daily : []);
      setMonthly(Array.isArray(m) ? m : []);
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
      <p style={{ margin: 0, color: "#374151" }}>按日/按月消耗统计（成本仅统计“已计价覆盖”的部分；未计价部分不计入成本）。</p>
      <div style={{ display: "flex", gap: 8 }}>
        <button onClick={reload}>刷新</button>
        {err ? <div style={{ color: "#b91c1c" }}>{err}</div> : null}
      </div>

      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>近 30 天（按日）</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>日期</th>
              <th style={{ padding: 6 }}>消耗(g)</th>
              <th style={{ padding: 6 }}>折合成本(元)</th>
              <th style={{ padding: 6 }}>不可计价(g)</th>
            </tr>
          </thead>
          <tbody>
            {daily.map((r) => (
              <tr key={r.day} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{r.day}</td>
                <td style={{ padding: 6 }}>{r.grams_total}</td>
                <td style={{ padding: 6 }}>{r.cost_total}</td>
                <td style={{ padding: 6 }}>{r.unpriced_grams}</td>
              </tr>
            ))}
            {daily.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ padding: 12, color: "#6b7280" }}>
                  暂无数据
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>按月</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>月份</th>
              <th style={{ padding: 6 }}>克数</th>
              <th style={{ padding: 6 }}>成本估算</th>
            </tr>
          </thead>
          <tbody>
            {monthly.map((r) => (
              <tr key={r.month} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{r.month}</td>
                <td style={{ padding: 6 }}>{r.grams}</td>
                <td style={{ padding: 6 }}>{r.cost_est}</td>
              </tr>
            ))}
            {monthly.length === 0 ? (
              <tr>
                <td colSpan={3} style={{ padding: 12, color: "#6b7280" }}>
                  暂无数据
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}


