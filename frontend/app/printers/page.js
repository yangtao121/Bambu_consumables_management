"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

export default function Page() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({
    ip: "",
    serial: "",
    lan_access_code: "",
    alias: "",
    model: ""
  });
  const [err, setErr] = useState("");

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
  }, []);

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
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{p.alias || "-"}</td>
                <td style={{ padding: 6 }}>{p.serial}</td>
                <td style={{ padding: 6 }}>{p.ip}</td>
                <td style={{ padding: 6 }}>{p.status}</td>
                <td style={{ padding: 6 }}>{p.last_seen || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


