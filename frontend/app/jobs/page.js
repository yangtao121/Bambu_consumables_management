"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { fetchJson } from "../../lib/api";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

export default function Page() {
  const [items, setItems] = useState([]);
  const [printers, setPrinters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [printerId, setPrinterId] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");

  async function reload() {
    try {
      setLoading(true);
      const qs = new URLSearchParams();
      if (printerId) qs.set("printer_id", printerId);
      if (status) qs.set("status", status);
      const data = await fetchJson(`/jobs${qs.toString() ? `?${qs.toString()}` : ""}`);
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const ps = await fetchJson("/printers");
        setPrinters(Array.isArray(ps) ? ps : []);
      } catch (e) {
        toast.error(String(e?.message || e));
      } finally {
        reload();
      }
    })();
  }, []);

  useEffect(() => {
    reload();
  }, [printerId, status]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((j) => {
      const hay = `${j.file_name || ""} ${j.job_key || ""} ${j.status || ""}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [items, q]);

  function fmtTime(iso) {
    if (!iso) return "-";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString();
  }

  function statusVariant(st) {
    const s = String(st || "").toLowerCase();
    if (s === "running") return "default";
    if (s === "finished" || s === "finish") return "secondary";
    if (s === "failed") return "destructive";
    return "outline";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
          <p className="text-sm text-muted-foreground">任务历史：可筛选、查看详情、并手工补录扣料。</p>
        </div>
        <Button variant="outline" onClick={reload} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>筛选</CardTitle>
          <CardDescription>按打印机/状态筛选，支持文件名/JobKey 搜索。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <div className="grid gap-2">
              <Label>打印机</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={printerId}
                onChange={(e) => setPrinterId(e.target.value)}
              >
                <option value="">全部</option>
                {printers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.alias || p.serial}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-2">
              <Label>状态</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="">全部</option>
                <option value="running">running</option>
                <option value="finished">finished</option>
                <option value="failed">failed</option>
                <option value="idle">idle</option>
              </select>
            </div>
            <div className="grid gap-2 md:col-span-2">
              <Label>搜索</Label>
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="文件名 / job_key / 状态" />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>任务列表</CardTitle>
          <CardDescription>共 {filtered.length} 条（点击进入详情查看扣料与快照）。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">开始</th>
                  <th className="px-3 py-2">结束</th>
                  <th className="px-3 py-2">文件</th>
                  <th className="px-3 py-2">打印机</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((j) => (
                  <tr key={j.id} className="border-t">
                    <td className="px-3 py-2">
                      <Badge variant={statusVariant(j.status)}>{j.status}</Badge>
                    </td>
                    <td className="px-3 py-2">{fmtTime(j.started_at)}</td>
                    <td className="px-3 py-2">{j.ended_at ? fmtTime(j.ended_at) : "-"}</td>
                    <td className="px-3 py-2">
                      <Link className="font-medium hover:underline" href={`/jobs/${j.id}`}>
                        {j.file_name || "-"}
                      </Link>
                      {j.job_key ? <div className="text-xs text-muted-foreground">{j.job_key}</div> : null}
                    </td>
                    <td className="px-3 py-2">{String(j.printer_id).slice(0, 8)}…</td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={5}>
                      暂无数据
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


