"use client";

import { useEffect, useMemo, useState } from "react";
import { apiBaseUrl } from "../lib/api";

export default function Page() {
  const [printers, setPrinters] = useState([]);
  const base = useMemo(() => apiBaseUrl(), []);

  useEffect(() => {
    const es = new EventSource(`${base}/realtime/printers`);
    es.addEventListener("printers", (e) => {
      try {
        const payload = JSON.parse(e.data);
        setPrinters(payload.printers || []);
      } catch {
        // ignore
      }
    });
    es.onerror = () => {
      // 自动重连由浏览器处理
    };
    return () => es.close();
  }, [base]);

  const online = printers.filter((p) => p.status === "online").length;
  const total = printers.length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ margin: 0 }}>Dashboard</h1>
      <p style={{ margin: 0, color: "#374151" }}>
        这里会展示打印机在线状态、正在打印任务、以及近期耗材消耗汇总（后续接入 API
        + 实时通道）。
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: 12
        }}
      >
        <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
          在线打印机：{online}/{total}
        </div>
        <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
          正在打印：-
        </div>
        <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
          近 7 天消耗：-
        </div>
      </div>
    </div>
  );
}


