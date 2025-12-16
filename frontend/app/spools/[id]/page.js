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

const adjustmentSchema = z.object({
  delta_grams: z.coerce.number().int().refine((n) => n !== 0, "调整值不能为 0"),
  reason: z.string().trim().optional()
});

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

function statusVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "active") return "default";
  if (s === "empty") return "secondary";
  if (s === "retired") return "outline";
  return "outline";
}

export default function Page({ params }) {
  const spoolId = params?.id;
  const [spool, setSpool] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [emptyOpen, setEmptyOpen] = useState(false);

  const adjForm = useForm({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: { delta_grams: 0, reason: "" }
  });

  async function reload() {
    if (!spoolId) return;
    setLoading(true);
    try {
      const [s, l] = await Promise.all([fetchJson(`/spools/${spoolId}`), fetchJson(`/spools/${spoolId}/ledger`)]);
      setSpool(s);
      setLedger(Array.isArray(l) ? l : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [spoolId]);

  const summary = useMemo(() => {
    const consumption = ledger.filter((r) => r.kind === "consumption").reduce((acc, r) => acc + Math.abs(Number(r.grams || 0)), 0);
    const adjustment = ledger.filter((r) => r.kind === "adjustment").reduce((acc, r) => acc + Number(r.grams || 0), 0);
    return { consumption, adjustment };
  }, [ledger]);

  async function submitAdjustment(values) {
    await fetchJson(`/spools/${spoolId}/adjustments`, {
      method: "POST",
      body: JSON.stringify({ delta_grams: Number(values.delta_grams), reason: values.reason ? values.reason : null })
    });
    toast.success("盘点调整已记录");
    setAdjustOpen(false);
    adjForm.reset({ delta_grams: 0, reason: "" });
    await reload();
  }

  async function submitMarkEmpty() {
    await fetchJson(`/spools/${spoolId}/mark-empty`, { method: "POST", body: JSON.stringify({ confirm: true }) });
    toast.success("已标记用完，并解绑相关托盘");
    setEmptyOpen(false);
    await reload();
  }

  if (!spoolId) return null;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-muted-foreground">
            <Link className="hover:underline" href="/spools">
              Spools
            </Link>{" "}
            / 详情
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{spool?.name || "加载中…"}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant={statusVariant(spool?.status)}>{spool?.status || "-"}</Badge>
            <div className="text-sm text-muted-foreground">
              {spool ? `${spool.material} · ${spool.color}` : "-"}
              {spool?.brand ? ` · ${spool.brand}` : ""}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>
          <Button variant="outline" onClick={() => (adjForm.reset({ delta_grams: 0, reason: "" }), setAdjustOpen(true))}>
            盘点调整
          </Button>
          <Button variant="destructive" onClick={() => setEmptyOpen(true)} disabled={spool?.status === "empty"}>
            标记用完
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>剩余估计</CardTitle>
            <CardDescription>由初始克数 + 盘点调整 - 扣料汇总得到。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{spool?.remaining_grams_est ?? "-"}</div>
            <div className="mt-2 text-sm text-muted-foreground">初始：{spool?.initial_grams ?? "-"} g</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>累计扣料</CardTitle>
            <CardDescription>来自 `consumption_records`（自动或手工）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{summary.consumption}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>盘点调整合计</CardTitle>
            <CardDescription>来自 `inventory_adjustments`。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{summary.adjustment}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g（可正可负）</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>账本（Ledger）</CardTitle>
          <CardDescription>扣料为负值；盘点调整为正/负值。点击 job_id 可跳转任务详情（稍后会补齐）。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">时间</th>
                  <th className="px-3 py-2">类型</th>
                  <th className="px-3 py-2">克数</th>
                  <th className="px-3 py-2">来源</th>
                  <th className="px-3 py-2">置信度</th>
                  <th className="px-3 py-2">关联任务</th>
                  <th className="px-3 py-2">备注</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((r, idx) => (
                  <tr key={`${r.kind}-${r.at}-${idx}`} className="border-t">
                    <td className="px-3 py-2">{fmtTime(r.at)}</td>
                    <td className="px-3 py-2">{r.kind}</td>
                    <td className="px-3 py-2 font-medium">{r.grams}</td>
                    <td className="px-3 py-2">{r.source || "-"}</td>
                    <td className="px-3 py-2">{r.confidence || "-"}</td>
                    <td className="px-3 py-2">
                      {r.job_id ? (
                        <Link className="hover:underline" href={`/jobs/${r.job_id}`}>
                          {String(r.job_id).slice(0, 8)}…
                        </Link>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="px-3 py-2">{r.note || "-"}</td>
                  </tr>
                ))}
                {ledger.length === 0 ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={7}>
                      暂无记录
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>盘点调整</DialogTitle>
            <DialogDescription>输入正/负克数：正数表示加回库存，负数表示扣减库存。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={adjForm.handleSubmit(async (v) => {
              try {
                await submitAdjustment(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid gap-2">
              <Label>调整值（克）</Label>
              <Input type="number" {...adjForm.register("delta_grams")} />
              {adjForm.formState.errors.delta_grams ? (
                <div className="text-xs text-destructive">{adjForm.formState.errors.delta_grams.message}</div>
              ) : null}
            </div>
            <div className="grid gap-2">
              <Label>原因（可选）</Label>
              <Input {...adjForm.register("reason")} placeholder="例如：手动称重盘点" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setAdjustOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={adjForm.formState.isSubmitting}>
                {adjForm.formState.isSubmitting ? "提交中…" : "提交"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={emptyOpen} onOpenChange={setEmptyOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认标记用完？</DialogTitle>
            <DialogDescription>该操作会将剩余置 0，并自动解除所有激活的托盘绑定。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmptyOpen(false)}>
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                try {
                  await submitMarkEmpty();
                } catch (e) {
                  toast.error(String(e?.message || e));
                }
              }}
            >
              确认
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

