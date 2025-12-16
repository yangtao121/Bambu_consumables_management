"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { fetchJson } from "../../../lib/api";
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

const adjustmentSchema = z.object({
  delta_grams: z.coerce.number().int().refine((n) => n !== 0, "调整值不能为 0"),
  reason: z.string().trim().optional()
});

export default function Page({ params }) {
  const stockId = params?.id;
  const [stock, setStock] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const form = useForm({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: { delta_grams: 0, reason: "" }
  });

  async function reload() {
    if (!stockId) return;
    setLoading(true);
    try {
      const [s, l] = await Promise.all([fetchJson(`/stocks/${stockId}`), fetchJson(`/stocks/${stockId}/ledger`)]);
      setStock(s);
      setLedger(Array.isArray(l) ? l : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [stockId]);

  const totalDelta = useMemo(() => ledger.reduce((acc, r) => acc + Number(r.grams || 0), 0), [ledger]);

  async function submitAdjustment(values) {
    await fetchJson(`/stocks/${stockId}/adjustments`, {
      method: "POST",
      body: JSON.stringify({ delta_grams: Number(values.delta_grams), reason: values.reason ? values.reason : null })
    });
    toast.success("已写入盘点调整");
    setOpen(false);
    form.reset({ delta_grams: 0, reason: "" });
    await reload();
  }

  if (!stockId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-muted-foreground">
            <Link className="hover:underline" href="/stocks">
              库存
            </Link>{" "}
            / 详情
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {stock ? `${stock.material} · ${stock.color} · ${stock.brand}` : "库存详情"}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>
          <Button onClick={() => setOpen(true)}>盘点调整</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>剩余</CardTitle>
            <CardDescription>总库存剩余（估算）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{stock ? stock.remaining_grams : "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>单卷克数</CardTitle>
            <CardDescription>用于 AMS remain% → 克数 的换算。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{stock ? stock.roll_weight_grams : "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g/卷</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>流水合计</CardTitle>
            <CardDescription>当前列表中 delta_grams 的合计（便于核对）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{totalDelta}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>流水</CardTitle>
          <CardDescription>自动扣料与手工盘点都会写入这里。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">时间</th>
                  <th className="px-3 py-2">变动(g)</th>
                  <th className="px-3 py-2">备注</th>
                  <th className="px-3 py-2">作业</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((r, idx) => (
                  <tr key={`${r.at}-${idx}`} className="border-t">
                    <td className="px-3 py-2">{fmtTime(r.at)}</td>
                    <td className="px-3 py-2 font-medium">{r.grams}</td>
                    <td className="px-3 py-2">{r.note || "-"}</td>
                    <td className="px-3 py-2">{r.job_id ? <Link className="hover:underline" href={`/jobs/${r.job_id}`}>{String(r.job_id).slice(0, 8)}…</Link> : "-"}</td>
                  </tr>
                ))}
                {ledger.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-muted-foreground">
                      暂无流水
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
            <DialogTitle>盘点调整</DialogTitle>
            <DialogDescription>正数表示入库/盘盈，负数表示盘亏/纠偏（会写入库存流水）。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (v) => {
              try {
                await submitAdjustment(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid gap-2">
              <Label>调整克数</Label>
              <Input type="number" {...form.register("delta_grams")} />
              {form.formState.errors.delta_grams ? <div className="text-xs text-destructive">{form.formState.errors.delta_grams.message}</div> : null}
            </div>
            <div className="grid gap-2">
              <Label>原因（可选）</Label>
              <Input {...form.register("reason")} placeholder="例如：盘点纠偏 / 新购入库" />
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

