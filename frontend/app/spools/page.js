"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "../../lib/api";

export default function Page() {
  const [items, setItems] = useState([]);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({
    name: "",
    material: "PLA",
    color: "",
    brand: "",
    initial_grams: 1000,
    price_total: ""
  });

  async function reload() {
    setErr("");
    try {
      const data = await fetchJson("/spools");
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
      await fetchJson("/spools", {
        method: "POST",
        body: JSON.stringify({
          name: form.name,
          material: form.material,
          color: form.color,
          brand: form.brand || null,
          initial_grams: Number(form.initial_grams),
          price_total: form.price_total === "" ? null : Number(form.price_total)
        })
      });
      setForm({ name: "", material: "PLA", color: "", brand: "", initial_grams: 1000, price_total: "" });
      await reload();
    } catch (e2) {
      setErr(String(e2.message || e2));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <h1 style={{ margin: 0 }}>Spools</h1>
      <p style={{ margin: 0, color: "#374151" }}>耗材卷管理（MVP：CRUD + 剩余估计）。</p>

      <form onSubmit={onSubmit} style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0, 1fr))", gap: 8 }}>
          <input
            placeholder="名称"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <input
            placeholder="材质(PLA/PETG/...)"
            value={form.material}
            onChange={(e) => setForm({ ...form, material: e.target.value })}
          />
          <input
            placeholder="颜色"
            value={form.color}
            onChange={(e) => setForm({ ...form, color: e.target.value })}
          />
          <input
            placeholder="品牌(可选)"
            value={form.brand}
            onChange={(e) => setForm({ ...form, brand: e.target.value })}
          />
          <input
            placeholder="初始克数"
            type="number"
            value={form.initial_grams}
            onChange={(e) => setForm({ ...form, initial_grams: e.target.value })}
          />
        </div>
        <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
          <input
            placeholder="总价(可选)"
            type="number"
            value={form.price_total}
            onChange={(e) => setForm({ ...form, price_total: e.target.value })}
          />
          <button type="submit">添加</button>
          <button type="button" onClick={reload}>
            刷新
          </button>
        </div>
        {err ? <div style={{ marginTop: 8, color: "#b91c1c" }}>{err}</div> : null}
      </form>

      <div style={{ border: "1px solid #e5e7eb", padding: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>耗材列表</div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #e5e7eb" }}>
              <th style={{ padding: 6 }}>名称</th>
              <th style={{ padding: 6 }}>材质</th>
              <th style={{ padding: 6 }}>颜色</th>
              <th style={{ padding: 6 }}>剩余估计(g)</th>
              <th style={{ padding: 6 }}>状态</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #f3f4f6" }}>
                <td style={{ padding: 6 }}>{s.name}</td>
                <td style={{ padding: 6 }}>{s.material}</td>
                <td style={{ padding: 6 }}>{s.color}</td>
                <td style={{ padding: 6 }}>{s.remaining_grams_est}</td>
                <td style={{ padding: 6 }}>{s.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}


