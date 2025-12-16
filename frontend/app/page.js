"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiBaseUrl, fetchJson } from "../lib/api";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";

export default function Page() {
  const [printers, setPrinters] = useState([]);
  const [reportsById, setReportsById] = useState({});
  const [summary, setSummary] = useState(null);
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

  const printerIdsKey = printers
    .map((p) => p && p.id)
    .filter(Boolean)
    .join("|");

  useEffect(() => {
    let cancelled = false;
    const sources = new Map();

    async function loadLatest(printerId) {
      try {
        const r = await fetchJson(`/printers/${printerId}/latest-report`);
        if (!cancelled) setReportsById((prev) => ({ ...prev, [printerId]: r }));
      } catch {
        // ignore
      }
    }

    for (const p of printers) {
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
        } catch {
          // ignore
        }
      });
      sources.set(p.id, es);
    }

    const pollId = setInterval(() => {
      for (const p of printers) {
        if (p?.id) loadLatest(p.id);
      }
    }, 8000);

    return () => {
      cancelled = true;
      clearInterval(pollId);
      for (const es of sources.values()) es.close();
    };
  }, [printerIdsKey]);

  useEffect(() => {
    let stopped = false;
    async function loadSummary() {
      try {
        const s = await fetchJson("/reports/summary?days=7");
        if (!stopped) setSummary(s);
      } catch {
        // ignore
      }
    }
    loadSummary();
    const id = setInterval(loadSummary, 30000);
    return () => {
      stopped = true;
      clearInterval(id);
    };
  }, []);

  const online = printers.filter((p) => p.status === "online").length;
  const total = printers.length;

  const printingPrinters = printers
    .map((p) => {
      const rep = reportsById[p.id];
      const ev = rep?.event || rep?.data || null;
      const gcodeState = String(ev?.gcode_state || ev?.gcodeState || "").toUpperCase();
      const progress = ev?.progress ?? null;
      const file = ev?.subtask_name || ev?.gcode_file || null;
      return { p, gcodeState, progress, file };
    })
    .filter((x) => x.gcodeState === "RUNNING");

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">概览：在线状态、正在打印、近期消耗趋势与快捷入口。</p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline">
            <Link href="/printers">去打印机</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/stocks">去库存</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/jobs">去历史</Link>
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">在线打印机</CardTitle>
            <CardDescription>来自实时通道</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {online}/{total}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">正在打印</CardTitle>
            <CardDescription>RUNNING</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{printingPrinters.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">今日消耗</CardTitle>
            <CardDescription>克数 / 成本估算</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{summary?.today?.grams ?? "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">≈ {summary?.today?.cost_est ?? "-"} 元</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">近 7 天消耗</CardTitle>
            <CardDescription>克数 / 成本估算</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{summary?.last?.grams ?? "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">≈ {summary?.last?.cost_est ?? "-"} 元</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>正在打印</CardTitle>
            <CardDescription>显示当前 RUNNING 的打印机与进度。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr className="text-left">
                    <th className="px-3 py-2">打印机</th>
                    <th className="px-3 py-2">进度</th>
                    <th className="px-3 py-2">任务</th>
                    <th className="px-3 py-2">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {printingPrinters.map(({ p, progress, file }) => (
                    <tr key={p.id} className="border-t">
                      <td className="px-3 py-2 font-medium">{p.alias || p.serial}</td>
                      <td className="px-3 py-2">{progress == null ? "-" : `${progress}%`}</td>
                      <td className="px-3 py-2">{file || "-"}</td>
                      <td className="px-3 py-2">
                        <Badge>RUNNING</Badge>
                      </td>
                    </tr>
                  ))}
                  {printingPrinters.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-8 text-center text-muted-foreground">
                        当前没有正在打印的任务
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>近 7 天趋势</CardTitle>
            <CardDescription>按天汇总（g）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr className="text-left">
                    <th className="px-3 py-2">日期</th>
                    <th className="px-3 py-2">克数</th>
                    <th className="px-3 py-2">成本估算</th>
                  </tr>
                </thead>
                <tbody>
                  {(summary?.daily || []).map((r) => (
                    <tr key={r.day} className="border-t">
                      <td className="px-3 py-2">{r.day}</td>
                      <td className="px-3 py-2 font-medium">{r.grams}</td>
                      <td className="px-3 py-2">{r.cost_est}</td>
                    </tr>
                  ))}
                  {(summary?.daily || []).length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-8 text-center text-muted-foreground">
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
    </div>
  );
}


