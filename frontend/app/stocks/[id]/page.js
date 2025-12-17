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

const editPurchaseSchema = z.object({
  rolls_count: z.coerce.number().int().min(0, "卷数必须 >= 0").optional(),
  price_per_roll: z
    .union([z.string(), z.number(), z.null(), z.undefined()])
    .transform((v) => {
      if (v === "" || v === null || typeof v === "undefined") return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    })
    .refine((v) => v === null || v >= 0, "卷单价必须 >= 0")
    .optional(),
  price_total: z
    .union([z.string(), z.number(), z.null(), z.undefined()])
    .transform((v) => {
      if (v === "" || v === null || typeof v === "undefined") return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    })
    .refine((v) => v === null || v >= 0, "总价必须 >= 0")
    .optional(),
  has_tray: z.boolean().optional(),
  note: z.string().trim().optional()
});

export default function Page({ params }) {
  const stockId = params?.id;
  const [stock, setStock] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editRow, setEditRow] = useState(null);

  const form = useForm({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: { delta_grams: 0, reason: "" }
  });

  const editForm = useForm({
    resolver: zodResolver(editPurchaseSchema),
    defaultValues: { rolls_count: 0, price_per_roll: null, price_total: null, has_tray: false, note: "" }
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

  async function submitEditPurchase(values) {
    if (!editRow?.id) return;
    await fetchJson(`/stocks/${stockId}/ledger/${editRow.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        rolls_count: typeof values.rolls_count === "number" ? Number(values.rolls_count) : undefined,
        price_per_roll: values.price_per_roll === null || typeof values.price_per_roll === "undefined" ? null : Number(values.price_per_roll),
        price_total: values.price_total === null || typeof values.price_total === "undefined" ? null : Number(values.price_total),
        has_tray: Boolean(values.has_tray),
        note: values.note ? values.note : null
      })
    });
    toast.success("已更新入库流水");
    setEditOpen(false);
    setEditRow(null);
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
                  <th className="px-3 py-2">卷数</th>
                  <th className="px-3 py-2">单价</th>
                  <th className="px-3 py-2">总价</th>
                  <th className="px-3 py-2">带料盘</th>
                  <th className="px-3 py-2">料盘变动</th>
                  <th className="px-3 py-2">备注</th>
                  <th className="px-3 py-2">作业</th>
                  <th className="px-3 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((r, idx) => (
                  <tr key={`${r.at}-${idx}`} className="border-t">
                    <td className="px-3 py-2">{fmtTime(r.at)}</td>
                    <td className="px-3 py-2 font-medium">{r.grams}</td>
                    <td className="px-3 py-2">{typeof r.rolls_count === "number" ? r.rolls_count : "-"}</td>
                    <td className="px-3 py-2">{typeof r.price_per_roll === "number" ? r.price_per_roll : "-"}</td>
                    <td className="px-3 py-2">{typeof r.price_total === "number" ? r.price_total : "-"}</td>
                    <td className="px-3 py-2">
                      {typeof r.has_tray === "boolean" ? (r.has_tray ? "是" : "否") : "-"}
                    </td>
                    <td className="px-3 py-2">{typeof r.tray_delta === "number" ? r.tray_delta : "-"}</td>
                    <td className="px-3 py-2">{r.note || "-"}</td>
                    <td className="px-3 py-2">{r.job_id ? <Link className="hover:underline" href={`/jobs/${r.job_id}`}>{String(r.job_id).slice(0, 8)}…</Link> : "-"}</td>
                    <td className="px-3 py-2">
                      {r.job_id ? null : Number(r.grams || 0) > 0 ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setEditRow(r);
                            editForm.reset({
                              rolls_count: typeof r.rolls_count === "number" ? r.rolls_count : 0,
                              price_per_roll: typeof r.price_per_roll === "number" ? r.price_per_roll : null,
                              price_total: typeof r.price_total === "number" ? r.price_total : null,
                              has_tray: Boolean(r.has_tray),
                              note: r.note || ""
                            });
                            setEditOpen(true);
                          }}
                        >
                          编辑
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
                {ledger.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="px-3 py-8 text-center text-muted-foreground">
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

      <Dialog
        open={editOpen}
        onOpenChange={(v) => {
          setEditOpen(v);
          if (!v) setEditRow(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑入库流水</DialogTitle>
            <DialogDescription>用于补录历史价格/带料盘信息（会影响成本统计与总料盘数）。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={editForm.handleSubmit(async (v) => {
              try {
                await submitEditPurchase(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>卷数</Label>
                <Input type="number" {...editForm.register("rolls_count")} />
                {editForm.formState.errors.rolls_count ? (
                  <div className="text-xs text-destructive">{editForm.formState.errors.rolls_count.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>卷单价（元/卷，可留空）</Label>
                <Input type="number" step="0.01" {...editForm.register("price_per_roll")} />
                {editForm.formState.errors.price_per_roll ? (
                  <div className="text-xs text-destructive">{editForm.formState.errors.price_per_roll.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>总价（元，可留空）</Label>
                <Input type="number" step="0.01" {...editForm.register("price_total")} />
                {editForm.formState.errors.price_total ? (
                  <div className="text-xs text-destructive">{editForm.formState.errors.price_total.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>料盘</Label>
                <label className="flex select-none items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" {...editForm.register("has_tray")} />
                  带料盘（料盘变动 = 卷数）
                </label>
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>备注（可选）</Label>
                <Input {...editForm.register("note")} placeholder="例如：京东 12.12 购入" />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={editForm.formState.isSubmitting}>
                {editForm.formState.isSubmitting ? "提交中…" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

