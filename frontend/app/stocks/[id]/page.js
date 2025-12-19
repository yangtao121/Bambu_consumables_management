"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { ApiError, fetchJson } from "../../../lib/api";
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

const manualStockConsumptionSchema = z.object({
  grams: z.coerce.number().int().min(1, "克数必须 >= 1"),
  note: z.string().trim().optional()
});

const editStockSchema = z.object({
  material: z.string().trim().min(1, "请输入材质"),
  color: z.string().trim().min(1, "请输入颜色"),
  brand: z.string().trim().min(1, "请输入品牌"),
  roll_weight_grams: z.coerce.number().int().min(1, "单卷克数必须 >= 1")
});

const voidSchema = z.object({
  reason: z.string().trim().optional()
});

function round2(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return null;
  return Math.round(v * 100) / 100;
}

function fmtMoney(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "-";
  return (Math.round(v * 100) / 100).toFixed(2);
}

export default function Page({ params }) {
  const stockId = params?.id;
  const router = useRouter();
  const [stock, setStock] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [valuation, setValuation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editRow, setEditRow] = useState(null);
  const [lastPriceEdited, setLastPriceEdited] = useState(null); // "per_roll" | "total" | null
  const [manualOpen, setManualOpen] = useState(false);
  const [editStockOpen, setEditStockOpen] = useState(false);
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidTarget, setVoidTarget] = useState(null); // { kind: "adjustment"|"manual_stock_consumption", row }

  const form = useForm({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: { delta_grams: 0, reason: "" }
  });

  const editForm = useForm({
    resolver: zodResolver(editPurchaseSchema),
    defaultValues: { rolls_count: 0, price_per_roll: null, price_total: null, has_tray: false, note: "" }
  });

  const manualForm = useForm({
    resolver: zodResolver(manualStockConsumptionSchema),
    defaultValues: { grams: 0, note: "" }
  });

  const editStockForm = useForm({
    resolver: zodResolver(editStockSchema),
    defaultValues: { material: "", color: "", brand: "", roll_weight_grams: 1000 }
  });

  const voidForm = useForm({
    resolver: zodResolver(voidSchema),
    defaultValues: { reason: "" }
  });

  const watchEditRolls = editForm.watch("rolls_count");
  const watchEditPpr = editForm.watch("price_per_roll");
  const watchEditTotal = editForm.watch("price_total");
  useEffect(() => {
    const n = Number(watchEditRolls || 0);
    if (!Number.isFinite(n) || n <= 0) return;
    const ppr = watchEditPpr === null || typeof watchEditPpr === "undefined" ? null : Number(watchEditPpr);
    const pt = watchEditTotal === null || typeof watchEditTotal === "undefined" ? null : Number(watchEditTotal);
    if (lastPriceEdited === "per_roll" && Number.isFinite(ppr)) {
      const next = round2(ppr * n);
      if (next !== null) editForm.setValue("price_total", next, { shouldDirty: true, shouldValidate: true });
    } else if (lastPriceEdited === "total" && Number.isFinite(pt)) {
      const next = round2(pt / n);
      if (next !== null) editForm.setValue("price_per_roll", next, { shouldDirty: true, shouldValidate: true });
    }
  }, [watchEditRolls, watchEditPpr, watchEditTotal, lastPriceEdited]);

  async function reload() {
    if (!stockId) return;
    setLoading(true);
    try {
      const [s, l, v] = await Promise.all([
        fetchJson(`/stocks/${stockId}`),
        fetchJson(`/stocks/${stockId}/ledger`),
        fetchJson(`/stocks/${stockId}/valuation`).catch(() => null)
      ]);
      setStock(s);
      setLedger(Array.isArray(l) ? l : []);
      setValuation(v && typeof v === "object" ? v : null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [stockId]);

  const totalDelta = useMemo(() => ledger.reduce((acc, r) => acc + Number(r.grams || 0), 0), [ledger]);

  function parseConsumptionIdFromNote(note) {
    const s = String(note || "");
    const m = s.match(/consumption=([0-9a-fA-F-]{36})/);
    return m ? m[1] : null;
  }

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

  async function submitManualConsumption(values) {
    await fetchJson(`/stocks/${stockId}/consumptions`, {
      method: "POST",
      body: JSON.stringify({ grams: Number(values.grams), note: values.note ? values.note : null })
    });
    toast.success("已写入手工扣料");
    setManualOpen(false);
    manualForm.reset({ grams: 0, note: "" });
    await reload();
  }

  async function submitEditStock(values) {
    try {
      const res = await fetchJson(`/stocks/${stockId}`, {
        method: "PATCH",
        body: JSON.stringify({
          material: values.material,
          color: values.color,
          brand: values.brand,
          roll_weight_grams: Number(values.roll_weight_grams)
        })
      });
      toast.success("库存项已更新");
      setEditStockOpen(false);
      await reload();
      return res;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail && typeof e.detail === "object") {
        const msg = String(e.detail?.message || "");
        if (msg === "stock key conflict") {
          const ok = window.confirm("该材质/颜色/品牌已存在其他库存项。是否合并到现有库存？（将迁移剩余克数并归档当前库存项）");
          if (!ok) throw e;
          const merged = await fetchJson(`/stocks/${stockId}?merge=1`, {
            method: "PATCH",
            body: JSON.stringify({
              material: values.material,
              color: values.color,
              brand: values.brand,
              roll_weight_grams: Number(values.roll_weight_grams)
            })
          });
          toast.success("已合并到现有库存项");
          setEditStockOpen(false);
          if (merged?.id && String(merged.id) !== String(stockId)) {
            router.push(`/stocks/${merged.id}`);
            return merged;
          }
          await reload();
          return merged;
        }
      }
      throw e;
    }
  }

  async function submitVoid(values) {
    if (!voidTarget) return;
    const reason = values.reason ? values.reason : null;
    if (voidTarget.kind === "adjustment") {
      await fetchJson(`/material-ledger/${voidTarget.row.id}/reverse`, {
        method: "POST",
        body: JSON.stringify({ reason })
      });
      toast.success("已冲销调整");
    } else if (voidTarget.kind === "manual_stock_consumption") {
      await fetchJson(`/stocks/${stockId}/consumptions/${voidTarget.consumptionId}/void`, {
        method: "POST",
        body: JSON.stringify({ reason })
      });
      toast.success("已撤销扣料");
    }
    setVoidOpen(false);
    setVoidTarget(null);
    voidForm.reset({ reason: "" });
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
          <Button variant="outline" onClick={() => {
            if (!stock) return;
            editStockForm.reset({
              material: stock.material || "",
              color: stock.color || "",
              brand: stock.brand || "",
              roll_weight_grams: Number(stock.roll_weight_grams || 1000)
            });
            setEditStockOpen(true);
          }}>
            编辑库存项
          </Button>
          <Button variant="outline" onClick={() => setManualOpen(true)}>
            手工扣料
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>累计购入总价值</CardTitle>
            <CardDescription>该库存项可计价入库累计（元）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {valuation && typeof valuation.purchased_value_total === "number" ? fmtMoney(valuation.purchased_value_total) : "-"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">单位：元</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>已消耗价值</CardTitle>
            <CardDescription>按移动加权平均估算（仅计已计价部分）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {valuation && typeof valuation.consumed_value_est === "number" ? fmtMoney(valuation.consumed_value_est) : "-"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">单位：元</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>当前剩余价值</CardTitle>
            <CardDescription>已计价余额的剩余成本估算。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {valuation && typeof valuation.remaining_value_est === "number" ? fmtMoney(valuation.remaining_value_est) : "-"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">单位：元</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>已消耗卷数</CardTitle>
            <CardDescription>按消耗克数 / 单卷克数估算。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {valuation && typeof valuation.consumed_rolls_est === "number" ? round2(valuation.consumed_rolls_est) : "-"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">单位：卷（估算）</div>
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
                    <td className="px-3 py-2">
                      {r.voided_at ? (
                        <div>
                          <div className="text-xs text-destructive">已作废</div>
                          <div className="text-xs text-muted-foreground">
                            {fmtTime(r.voided_at)}{r.void_reason ? ` · ${r.void_reason}` : ""}
                          </div>
                          <div className="text-xs text-muted-foreground">{r.note || "-"}</div>
                        </div>
                      ) : (
                        r.note || "-"
                      )}
                    </td>
                    <td className="px-3 py-2">{r.job_id ? <Link className="hover:underline" href={`/jobs/${r.job_id}`}>{String(r.job_id).slice(0, 8)}…</Link> : "-"}</td>
                    <td className="px-3 py-2">
                      {r.voided_at ? null : (r.kind === "adjustment") ? (
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => {
                            setVoidTarget({ kind: "adjustment", row: r });
                            voidForm.reset({ reason: "" });
                            setVoidOpen(true);
                          }}
                        >
                          冲销
                        </Button>
                      ) : (r.kind === "consumption" && String(r.note || "").includes("manual_stock")) ? (() => {
                        const cid = parseConsumptionIdFromNote(r.note);
                        if (!cid) return null;
                        return (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => {
                              setVoidTarget({ kind: "manual_stock_consumption", row: r, consumptionId: cid });
                              voidForm.reset({ reason: "" });
                              setVoidOpen(true);
                            }}
                          >
                            撤销
                          </Button>
                        );
                      })() : Number(r.grams || 0) > 0 ? (
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
                            setLastPriceEdited(null);
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
                if (e instanceof ApiError && e.detail && typeof e.detail === "object" && typeof e.detail.message === "string") {
                  toast.error(e.detail.message);
                } else {
                  toast.error(String(e?.message || e));
                }
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

      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>手工扣料（按库存）</DialogTitle>
            <DialogDescription>用于不关联 Job 的手工扣减。将写入扣料记录并同步写入库存流水。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={manualForm.handleSubmit(async (v) => {
              try {
                await submitManualConsumption(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid gap-2">
              <Label>克数</Label>
              <Input type="number" {...manualForm.register("grams")} />
              {manualForm.formState.errors.grams ? (
                <div className="text-xs text-destructive">{manualForm.formState.errors.grams.message}</div>
              ) : null}
            </div>
            <div className="grid gap-2">
              <Label>备注（可选）</Label>
              <Input {...manualForm.register("note")} placeholder="例如：手工估算 23g" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setManualOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={manualForm.formState.isSubmitting}>
                {manualForm.formState.isSubmitting ? "提交中…" : "提交"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={editStockOpen} onOpenChange={setEditStockOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑库存项</DialogTitle>
            <DialogDescription>可修改材质/颜色/品牌/单卷克数。若目标 key 已存在，会提示是否合并。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={editStockForm.handleSubmit(async (v) => {
              try {
                await submitEditStock(v);
              } catch (e) {
                if (e instanceof ApiError && e.detail && typeof e.detail === "object" && typeof e.detail.message === "string") {
                  toast.error(e.detail.message);
                } else {
                  toast.error(String(e?.message || e));
                }
              }
            })}
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="grid gap-2">
                <Label>材质 *</Label>
                <Input {...editStockForm.register("material")} />
                {editStockForm.formState.errors.material ? (
                  <div className="text-xs text-destructive">{editStockForm.formState.errors.material.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>颜色 *</Label>
                <Input {...editStockForm.register("color")} />
                {editStockForm.formState.errors.color ? (
                  <div className="text-xs text-destructive">{editStockForm.formState.errors.color.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>品牌 *</Label>
                <Input {...editStockForm.register("brand")} />
                {editStockForm.formState.errors.brand ? (
                  <div className="text-xs text-destructive">{editStockForm.formState.errors.brand.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>单卷克数 *</Label>
                <Input type="number" {...editStockForm.register("roll_weight_grams")} />
                {editStockForm.formState.errors.roll_weight_grams ? (
                  <div className="text-xs text-destructive">{editStockForm.formState.errors.roll_weight_grams.message}</div>
                ) : null}
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditStockOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={editStockForm.formState.isSubmitting}>
                {editStockForm.formState.isSubmitting ? "保存中…" : "保存"}
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
                if (e instanceof ApiError && e.detail && typeof e.detail === "object" && typeof e.detail.message === "string") {
                  toast.error(e.detail.message);
                } else {
                  toast.error(String(e?.message || e));
                }
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
                <Input
                  type="number"
                  step="0.01"
                  {...editForm.register("price_per_roll", {
                    onChange: () => setLastPriceEdited("per_roll")
                  })}
                />
                {editForm.formState.errors.price_per_roll ? (
                  <div className="text-xs text-destructive">{editForm.formState.errors.price_per_roll.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>总价（元，可留空）</Label>
                <Input
                  type="number"
                  step="0.01"
                  {...editForm.register("price_total", {
                    onChange: () => setLastPriceEdited("total")
                  })}
                />
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

      <Dialog
        open={voidOpen}
        onOpenChange={(v) => {
          setVoidOpen(v);
          if (!v) setVoidTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>撤销记录</DialogTitle>
            <DialogDescription>撤销会保留审计记录，并写入一条反向流水回滚库存。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={voidForm.handleSubmit(async (v) => {
              try {
                await submitVoid(v);
              } catch (e) {
                if (e instanceof ApiError && e.detail && typeof e.detail === "object" && typeof e.detail.message === "string") {
                  toast.error(e.detail.message);
                } else {
                  toast.error(String(e?.message || e));
                }
              }
            })}
          >
            <div className="grid gap-2">
              <Label>原因（可选）</Label>
              <Input {...voidForm.register("reason")} placeholder="例如：误操作" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setVoidOpen(false)}>
                取消
              </Button>
              <Button type="submit" variant="destructive" disabled={voidForm.formState.isSubmitting}>
                {voidForm.formState.isSubmitting ? "处理中…" : "确认撤销"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

