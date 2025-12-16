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
  spool_id: z.string().min(1, "请选择耗材卷"),
  grams: z.coerce.number().int().min(0, "克数必须 >= 0"),
  note: z.string().trim().optional()
});

export default function Page({ params }) {
  const jobId = params?.id;
  const [job, setJob] = useState(null);
  const [cons, setCons] = useState([]);
  const [spools, setSpools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const form = useForm({
    resolver: zodResolver(manualSchema),
    defaultValues: { spool_id: "", grams: 0, note: "" }
  });

  async function reload() {
    if (!jobId) return;
    setLoading(true);
    try {
      const [j, c, s] = await Promise.all([fetchJson(`/jobs/${jobId}`), fetchJson(`/jobs/${jobId}/consumptions`), fetchJson("/spools")]);
      setJob(j);
      setCons(Array.isArray(c) ? c : []);
      setSpools(Array.isArray(s) ? s : []);
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
        spool_id: values.spool_id,
        grams: Number(values.grams),
        note: values.note ? values.note : null
      })
    });
    toast.success("已补录扣料");
    setOpen(false);
    form.reset({ spool_id: "", grams: 0, note: "" });
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
                      <Link className="font-medium hover:underline" href={`/spools/${c.spool_id}`}>
                        {c.spool_name}
                      </Link>
                      <div className="text-xs text-muted-foreground">
                        {c.spool_material} · {c.spool_color}
                      </div>
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
              <Label>耗材卷</Label>
              <select className="h-9 rounded-md border border-input bg-background px-3 text-sm" {...form.register("spool_id")}>
                <option value="">请选择…</option>
                {spools.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.material}/{s.color}) - {s.remaining_grams_est}g
                  </option>
                ))}
              </select>
              {form.formState.errors.spool_id ? <div className="text-xs text-destructive">{form.formState.errors.spool_id.message}</div> : null}
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

