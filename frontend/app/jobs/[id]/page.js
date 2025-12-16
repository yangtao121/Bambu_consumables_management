"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { fetchJson } from "../../../lib/api";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../../../components/ui/dialog";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";

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

const manualSchema = z.object({
  stock_id: z.string().min(1, "请选择库存项"),
  grams: z.coerce.number().int().min(0, "克数必须 >= 0"),
  note: z.string().trim().optional()
});

export default function Page({ params }) {
  const jobId = params?.id;
  const [job, setJob] = useState(null);
  const [cons, setCons] = useState([]);
  const [stocks, setStocks] = useState([]);
  const [colorMappings, setColorMappings] = useState({});
  const [colorDraftByHex, setColorDraftByHex] = useState({});
  const [savingColorHex, setSavingColorHex] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [resolveMap, setResolveMap] = useState({});

  const form = useForm({
    resolver: zodResolver(manualSchema),
    defaultValues: { stock_id: "", grams: 0, note: "" }
  });

  function normalizeColorHex(v) {
    if (v == null) return null;
    const s0 = String(v).trim();
    if (!s0) return null;
    const raw = s0.startsWith("#") ? s0.slice(1).trim() : s0;
    const hx = raw.toUpperCase();
    if (!/^[0-9A-F]+$/.test(hx)) return null;
    if (hx.length === 8) return `#${hx.slice(-6)}`;
    if (hx.length === 6) return `#${hx}`;
    return null;
  }

  async function saveColorMapping(colorHex) {
    const name = String(colorDraftByHex[colorHex] || "").trim();
    if (!name) {
      toast.error("请输入要映射的颜色名（如：白色/灰色）");
      return;
    }
    try {
      setSavingColorHex(colorHex);
      await fetchJson("/color-mappings", {
        method: "POST",
        body: JSON.stringify({ color_hex: colorHex, color_name: name })
      });
      toast.success(`已保存映射：${colorHex} -> ${name}`);
      setColorDraftByHex((prev) => ({ ...prev, [colorHex]: "" }));
      await reload();
    } catch (e) {
      toast.error(String(e?.message || e));
    } finally {
      setSavingColorHex(null);
    }
  }

  async function reload() {
    if (!jobId) return;
    setLoading(true);
    try {
      const [j, c, s, cm] = await Promise.all([
        fetchJson(`/jobs/${jobId}`),
        fetchJson(`/jobs/${jobId}/consumptions`),
        fetchJson("/stocks"),
        fetchJson("/color-mappings")
      ]);
      setJob(j);
      setCons(Array.isArray(c) ? c : []);
      setStocks(Array.isArray(s) ? s : []);
      const map = {};
      for (const r of Array.isArray(cm) ? cm : []) {
        if (r?.color_hex && r?.color_name) map[String(r.color_hex)] = String(r.color_name);
      }
      setColorMappings(map);
      setResolveMap({});
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [jobId]);

  const totalGrams = useMemo(() => cons.reduce((acc, r) => acc + Number(r.grams || 0), 0), [cons]);

  async function addManual(values) {
    await fetchJson(`/jobs/${jobId}/consumptions`, {
      method: "POST",
      body: JSON.stringify({
        stock_id: values.stock_id,
        grams: Number(values.grams),
        note: values.note ? values.note : null
      })
    });
    toast.success("已补录扣料");
    setOpen(false);
    form.reset({ stock_id: "", grams: 0, note: "" });
    await reload();
  }

  const pending = useMemo(() => {
    const p = job?.spool_binding_snapshot_json?.pending_consumptions;
    return Array.isArray(p) ? p.filter((x) => x && typeof x === "object") : [];
  }, [job]);

  const pendingTrays = useMemo(() => {
    const s = new Set();
    for (const e of pending) {
      const tid = e.tray_id;
      const n = Number(tid);
      if (Number.isFinite(n)) s.add(String(Math.trunc(n)));
    }
    return Array.from(s.values()).sort((a, b) => Number(a) - Number(b));
  }, [pending]);

  function candidatesFor(entry) {
    const material = entry?.material;
    const colorHex = normalizeColorHex(entry?.color_hex);
    const color = entry?.color || (colorHex ? colorMappings[colorHex] || null : null);
    const isOfficial = Boolean(entry?.is_official);
    if (!material || !color) return [];
    return stocks.filter(
      (s) => s.material === material && s.color === color && (isOfficial ? s.brand === "拓竹" : s.brand !== "拓竹")
    );
  }

  async function resolvePending() {
    const items = [];
    for (const trayId of pendingTrays) {
      const entry = pending.find((e) => String(e.tray_id) === String(trayId)) || null;
      const colorHex = normalizeColorHex(entry?.color_hex);
      const colorName = entry?.color || (colorHex ? colorMappings[colorHex] || null : null);
      if (entry?.material && colorHex && !colorName) {
        toast.error(`Tray ${trayId} 颜色未映射（${colorHex}），请先映射颜色名再归因`);
        return;
      }
      const stockId = resolveMap[trayId];
      if (!stockId) {
        toast.error(`请为 Tray ${trayId} 选择库存项`);
        return;
      }
      items.push({ tray_id: Number(trayId), stock_id: stockId });
    }
    await fetchJson(`/jobs/${jobId}/materials/resolve`, {
      method: "POST",
      body: JSON.stringify({ items })
    });
    toast.success("已归因并结算扣料");
    await reload();
  }

  if (!jobId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-muted-foreground">
            <Link className="hover:underline" href="/jobs">
              Jobs
            </Link>{" "}
            / 详情
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{job?.file_name || "任务详情"}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(job?.status)}>{job?.status || "-"}</Badge>
            <div className="text-sm text-muted-foreground">
              开始：{job?.started_at ? fmtTime(job.started_at) : "-"} · 结束：{job?.ended_at ? fmtTime(job.ended_at) : "-"}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>
          <Button onClick={() => setOpen(true)}>手工补录扣料</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>消耗汇总</CardTitle>
            <CardDescription>来自 `consumption_records`（自动或手工）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{totalGrams}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Printer</CardTitle>
            <CardDescription>关联打印机 ID（后续可增强为别名显示）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="font-mono text-sm">{job?.printer_id || "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">job_key：{job?.job_key || "-"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>绑定快照</CardTitle>
            <CardDescription>任务开始时的 tray→spool 快照（用于审计）。</CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="max-h-40 overflow-auto rounded-md border bg-muted/30 p-3 text-xs">
              {JSON.stringify(job?.spool_binding_snapshot_json || {}, null, 2)}
            </pre>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>扣料记录</CardTitle>
          <CardDescription>source/confidence 会告诉你这条记录来自自动结算还是手工补录。</CardDescription>
        </CardHeader>
        <CardContent>
          {pendingTrays.length > 0 ? (
            <div className="mb-4 rounded-md border bg-muted/20 p-4">
              <div className="font-medium">待归因扣料</div>
              <div className="mt-1 text-sm text-muted-foreground">
                该作业有无法唯一匹配品牌的托盘消耗，请为每个 Tray 选择要扣减的「库存项」后结算。
              </div>
              <div className="mt-3 grid gap-3">
                {pendingTrays.map((trayId) => {
                  const entry = pending.find((e) => String(e.tray_id) === String(trayId)) || null;
                  const opts = entry ? candidatesFor(entry) : [];
                  const colorHex = normalizeColorHex(entry?.color_hex);
                  const colorName = entry?.color || (colorHex ? colorMappings[colorHex] || null : null);
                  const colorDisplay = colorName ? `${colorName}${colorHex ? ` (${colorHex})` : ""}` : colorHex || entry?.color || "-";
                  const needsMapping = Boolean(entry?.material && colorHex && !colorName);
                  return (
                    <div key={trayId} className="grid grid-cols-1 gap-2 md:grid-cols-12 md:items-center">
                      <div className="md:col-span-2 font-medium">Tray {trayId}</div>
                      <div className="md:col-span-4 text-sm text-muted-foreground">
                        {entry ? `${entry.material || "-"} · ${colorDisplay} ${entry.is_official ? "（拓竹）" : ""}` : "-"}
                        {entry?.unit === "pct" && entry?.pct_delta != null ? ` · 消耗 ${Number(entry.pct_delta).toFixed(1)}%` : ""}
                        {entry?.unit === "grams" && entry?.grams != null ? ` · 消耗 ${entry.grams}g` : ""}
                        {needsMapping ? <span className="ml-2 text-xs text-destructive">颜色未映射</span> : null}
                      </div>
                      <div className="md:col-span-6">
                        {needsMapping ? (
                          <div className="mb-2 flex items-center gap-2">
                            <Input
                              className="h-9"
                              placeholder="先把颜色码映射为：白色/灰色/…"
                              value={colorDraftByHex[colorHex] || ""}
                              onChange={(e) =>
                                setColorDraftByHex((prev) => ({ ...prev, [colorHex]: e.target.value }))
                              }
                            />
                            <Button
                              variant="outline"
                              disabled={savingColorHex === colorHex}
                              onClick={() => saveColorMapping(colorHex)}
                            >
                              {savingColorHex === colorHex ? "保存中…" : "保存映射"}
                            </Button>
                          </div>
                        ) : null}
                        <select
                          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                          value={resolveMap[trayId] || ""}
                          onChange={(e) => setResolveMap((prev) => ({ ...prev, [trayId]: e.target.value }))}
                          disabled={needsMapping}
                        >
                          <option value="">选择库存项…</option>
                          {(opts.length ? opts : stocks).map((s) => (
                            <option key={s.id} value={s.id}>
                              {s.material}/{s.color}/{s.brand} - {s.remaining_grams}g
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="mt-3">
                <Button onClick={resolvePending}>提交归因并结算</Button>
              </div>
            </div>
          ) : null}

          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">时间</th>
                  <th className="px-3 py-2">耗材</th>
                  <th className="px-3 py-2">克数</th>
                  <th className="px-3 py-2">来源</th>
                  <th className="px-3 py-2">置信度</th>
                </tr>
              </thead>
              <tbody>
                {cons.map((c) => (
                  <tr key={c.id} className="border-t">
                    <td className="px-3 py-2">{fmtTime(c.created_at)}</td>
                    <td className="px-3 py-2">
                      {c.stock_id ? (
                        <>
                          <Link className="font-medium hover:underline" href={`/stocks/${c.stock_id}`}>
                            {c.material} · {c.color} · {c.brand}
                          </Link>
                          <div className="text-xs text-muted-foreground">
                            {c.tray_id != null ? `Tray ${c.tray_id}` : "-"}
                          </div>
                        </>
                      ) : c.spool_id ? (
                        <>
                          <Link className="font-medium hover:underline" href={`/spools/${c.spool_id}`}>
                            {c.spool_name || "Spool"}
                          </Link>
                          <div className="text-xs text-muted-foreground">
                            {c.spool_material} · {c.spool_color}
                          </div>
                        </>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-medium">{c.grams}</td>
                    <td className="px-3 py-2">{c.source}</td>
                    <td className="px-3 py-2">{c.confidence}</td>
                  </tr>
                ))}
                {cons.length === 0 ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={5}>
                      暂无扣料记录
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>手工补录扣料</DialogTitle>
            <DialogDescription>用于自动扣料缺失/不准时的最终兜底（会写入 consumption_records）。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (v) => {
              try {
                await addManual(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid gap-2">
              <Label>库存项</Label>
              <select className="h-9 rounded-md border border-input bg-background px-3 text-sm" {...form.register("stock_id")}>
                <option value="">请选择…</option>
                {stocks.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.material}/{s.color}/{s.brand} - {s.remaining_grams}g
                  </option>
                ))}
              </select>
              {form.formState.errors.stock_id ? <div className="text-xs text-destructive">{form.formState.errors.stock_id.message}</div> : null}
            </div>
            <div className="grid gap-2">
              <Label>克数</Label>
              <Input type="number" {...form.register("grams")} />
              {form.formState.errors.grams ? <div className="text-xs text-destructive">{form.formState.errors.grams.message}</div> : null}
            </div>
            <div className="grid gap-2">
              <Label>备注（可选）</Label>
              <Input {...form.register("note")} placeholder="例如：按切片估算 23g" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "提交中…" : "提交"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

