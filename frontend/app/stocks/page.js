"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { ApiError, fetchJson } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { ColorBlock } from "../../components/ui/color-block";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

const createSchema = z.object({
  material: z.string().trim().min(1, "请输入材质"),
  color: z.string().trim().min(1, "请输入颜色"),
  brand: z.string().trim().min(1, "请输入品牌（拓竹/其他）"),
  roll_weight_grams: z.coerce.number().int().min(1, "单卷克数必须 >= 1"),
  rolls_count: z.coerce.number().int().min(0, "卷数必须 >= 0"),
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
  has_tray: z.boolean().optional()
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

export default function Page() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [trayTotal, setTrayTotal] = useState(null);
  const [valuations, setValuations] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteRefInfo, setDeleteRefInfo] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [bindColorOpen, setBindColorOpen] = useState(false);
  const [bindColorTarget, setBindColorTarget] = useState(null);
  const [colorHexInput, setColorHexInput] = useState("");
  const [binding, setBinding] = useState(false);
  const [colorQuery, setColorQuery] = useState("");
  const [sortKey, setSortKey] = useState("remaining"); // remaining | created | updated
  const [sortDir, setSortDir] = useState("desc"); // asc | desc
  const [lastPriceEdited, setLastPriceEdited] = useState(null); // "per_roll" | "total" | null

  const form = useForm({
    resolver: zodResolver(createSchema),
    defaultValues: {
      material: "PLA",
      color: "白色",
      brand: "拓竹",
      roll_weight_grams: 1000,
      rolls_count: 1,
      price_per_roll: null,
      price_total: null,
      has_tray: false
    }
  });

  const watchRollWeight = form.watch("roll_weight_grams");
  const watchRollsCount = form.watch("rolls_count");
  const watchPricePerRoll = form.watch("price_per_roll");
  const watchPriceTotal = form.watch("price_total");

  useEffect(() => {
    const n = Number(watchRollsCount || 0);
    if (!Number.isFinite(n) || n <= 0) return;
    const ppr = watchPricePerRoll === null || typeof watchPricePerRoll === "undefined" ? null : Number(watchPricePerRoll);
    const pt = watchPriceTotal === null || typeof watchPriceTotal === "undefined" ? null : Number(watchPriceTotal);
    if (lastPriceEdited === "per_roll" && Number.isFinite(ppr)) {
      const next = round2(ppr * n);
      if (next !== null) form.setValue("price_total", next, { shouldDirty: true, shouldValidate: true });
    } else if (lastPriceEdited === "total" && Number.isFinite(pt)) {
      const next = round2(pt / n);
      if (next !== null) form.setValue("price_per_roll", next, { shouldDirty: true, shouldValidate: true });
    }
  }, [watchRollsCount, watchPricePerRoll, watchPriceTotal, lastPriceEdited]);

  const previewAddGrams = useMemo(() => {
    const w = Number(watchRollWeight || 0);
    const n = Number(watchRollsCount || 0);
    if (!Number.isFinite(w) || !Number.isFinite(n)) return 0;
    return Math.max(0, Math.floor(w) * Math.floor(n));
  }, [watchRollWeight, watchRollsCount]);
  const previewTotalPrice = useMemo(() => {
    const n = Number(watchRollsCount || 0);
    const p = watchPricePerRoll === null || typeof watchPricePerRoll === "undefined" ? null : Number(watchPricePerRoll);
    const t = watchPriceTotal === null || typeof watchPriceTotal === "undefined" ? null : Number(watchPriceTotal);
    if (!Number.isFinite(n) || n <= 0) return null;
    if (Number.isFinite(t) && t >= 0) return round2(t);
    if (!Number.isFinite(p) || p < 0) return null;
    return round2(p * n);
  }, [watchRollsCount, watchPricePerRoll, watchPriceTotal]);

  async function reload(opts = {}) {
    const inc = typeof opts.includeArchived === "boolean" ? opts.includeArchived : includeArchived;
    setLoading(true);
    try {
      const [data, tray, vals] = await Promise.all([
        fetchJson(`/stocks${inc ? "?include_archived=1" : ""}`),
        fetchJson("/trays/summary").catch(() => null),
        Promise.resolve(null) // 不再需要获取价值数据
      ]);
      setItems(Array.isArray(data) ? data : []);
      setTrayTotal(tray && typeof tray.total_trays === "number" ? tray.total_trays : null);
      setValuations(vals && typeof vals === "object" ? vals : null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  const activeItems = useMemo(() => items.filter((s) => !s?.is_archived), [items]);
  const archivedItems = useMemo(() => items.filter((s) => Boolean(s?.is_archived)), [items]);

  const filteredActiveItems = useMemo(() => {
    const needle = colorQuery.trim().toLowerCase();
    if (!needle) return activeItems;
    return activeItems.filter((s) => String(s?.color || "").toLowerCase().includes(needle));
  }, [activeItems, colorQuery]);

  const sortedActiveItems = useMemo(() => {
    const dirMul = sortDir === "asc" ? 1 : -1;
    const getVal = (s) => {
      if (sortKey === "created") return Date.parse(s?.created_at || "") || 0;
      if (sortKey === "updated") return Date.parse(s?.updated_at || "") || 0;
      return Number(s?.remaining_grams || 0);
    };
    const cmp = (a, b) => {
      const av = getVal(a);
      const bv = getVal(b);
      if (av < bv) return -1 * dirMul;
      if (av > bv) return 1 * dirMul;
      const ah = `${a?.material || ""}\u0000${a?.color || ""}\u0000${a?.brand || ""}`.toLowerCase();
      const bh = `${b?.material || ""}\u0000${b?.color || ""}\u0000${b?.brand || ""}`.toLowerCase();
      if (ah < bh) return -1;
      if (ah > bh) return 1;
      return String(a?.id || "").localeCompare(String(b?.id || ""));
    };
    return [...filteredActiveItems].sort(cmp);
  }, [filteredActiveItems, sortKey, sortDir]);

  const sortedArchivedItems = useMemo(() => {
    const dirMul = sortDir === "asc" ? 1 : -1;
    const getVal = (s) => {
      if (sortKey === "created") return Date.parse(s?.created_at || "") || 0;
      if (sortKey === "updated") return Date.parse(s?.updated_at || "") || 0;
      return Number(s?.remaining_grams || 0);
    };
    const cmp = (a, b) => {
      const av = getVal(a);
      const bv = getVal(b);
      if (av < bv) return -1 * dirMul;
      if (av > bv) return 1 * dirMul;
      const ah = `${a?.material || ""}\u0000${a?.color || ""}\u0000${a?.brand || ""}`.toLowerCase();
      const bh = `${b?.material || ""}\u0000${b?.color || ""}\u0000${b?.brand || ""}`.toLowerCase();
      if (ah < bh) return -1;
      if (ah > bh) return 1;
      return String(a?.id || "").localeCompare(String(b?.id || ""));
    };
    return [...archivedItems].sort(cmp);
  }, [archivedItems, sortKey, sortDir]);
  const totalRemaining = useMemo(
    () => activeItems.reduce((acc, s) => acc + Number(s.remaining_grams || 0), 0),
    [activeItems]
  );

  async function onSubmit(values) {
    const res = await fetchJson("/stocks", {
      method: "POST",
      body: JSON.stringify({
        material: values.material,
        color: values.color,
        brand: values.brand,
        roll_weight_grams: Number(values.roll_weight_grams),
        rolls_count: Number(values.rolls_count),
        price_per_roll:
          values.price_per_roll === null || typeof values.price_per_roll === "undefined" ? null : Number(values.price_per_roll),
        price_total: values.price_total === null || typeof values.price_total === "undefined" ? null : Number(values.price_total),
        has_tray: Boolean(values.has_tray)
      })
    });
    const stock = res?.stock ?? res;
    const merged = Boolean(res?.merged);
    const deltaFallback = Math.max(
      0,
      Math.floor(Number(values.roll_weight_grams || 0)) * Math.floor(Number(values.rolls_count || 0))
    );
    const delta = Number(res?.delta_grams ?? deltaFallback);
    const after = Number(res?.remaining_grams_after ?? stock?.remaining_grams ?? 0);
    if (merged) {
      toast.success(`已合并到现有库存，累加 ${delta}g（当前 ${after}g）`);
    } else {
      toast.success(`库存已新增（当前 ${after}g）`);
    }
    await reload();
    return res;
  }

  async function doArchive(force) {
    if (!deleteTarget?.id) return;
    setDeleting(true);
    try {
      await fetchJson(`/stocks/${deleteTarget.id}${force ? "?force=1" : ""}`, { method: "DELETE" });
      toast.success("已删除（归档）");
      setDeleteOpen(false);
      setDeleteTarget(null);
      setDeleteRefInfo(null);
      await reload();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.detail && typeof e.detail === "object") {
        setDeleteRefInfo({
          consumption_count: Number(e.detail?.consumption_count || 0),
          job_count: Number(e.detail?.job_count || 0)
        });
        toast.error("该库存已被历史引用，请确认是否强制删除（归档）");
        return;
      }
      toast.error(String(e?.message || e));
    } finally {
      setDeleting(false);
    }
  }

  async function bindColor() {
    if (!bindColorTarget?.id || !colorHexInput.trim()) return;
    
    // 简单的格式验证，更详细的验证由后端处理
    const cleanHex = colorHexInput.replace(/^#/, '');
    if (!/^[0-9A-Fa-f]{6,8}$/.test(cleanHex)) {
      toast.error("请输入6位或8位十六进制颜色码");
      return;
    }
    
    setBinding(true);
    try {
      await fetchJson(`/stocks/${bindColorTarget.id}/bind-color?color_hex=${encodeURIComponent(cleanHex)}`, {
        method: "POST"
      });
      toast.success("颜色绑定成功");
      setBindColorOpen(false);
      setBindColorTarget(null);
      setColorHexInput("");
      await reload();
    } catch (e) {
      toast.error(String(e?.message || e));
    } finally {
      setBinding(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">库存</h1>
          <p className="text-sm text-muted-foreground">按「材质 + 颜色 + 品牌」维护总库存（卷数 × 单卷重量）。</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-9 w-56"
            placeholder="按颜色搜索（未归档）"
            value={colorQuery}
            onChange={(e) => setColorQuery(e.target.value)}
          />
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value)}
            aria-label="排序字段"
          >
            <option value="remaining">按剩余克数</option>
            <option value="updated">按更新时间</option>
            <option value="created">按创建时间</option>
          </select>
          <Button
            type="button"
            variant="outline"
            onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
            aria-label="切换升序/降序"
          >
            {sortDir === "desc" ? "降序" : "升序"}
          </Button>
          <label className="flex select-none items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={includeArchived}
              onChange={async (e) => {
                const v = Boolean(e.target.checked);
                setIncludeArchived(v);
                await reload({ includeArchived: v });
              }}
            />
            显示已删除（归档）
          </label>
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>
          <Button variant="outline" onClick={() => setDiscardOpen(true)}>
            丢弃料盘
          </Button>
          <Button onClick={() => setCreateOpen(true)}>新增库存</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>使用说明</CardTitle>
            <CardDescription>建议拓竹官方耗材的品牌填“拓竹”，第三方填品牌名。颜色建议用“白色/灰色/黑色”等名称（AMS 十六进制颜色码可在打印机页做映射）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">
              你可以在“库存列表”里查看/调整每个库存项，并通过“新增库存”按钮录入新库存。删除不会丢历史，只是归档隐藏。
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>总剩余</CardTitle>
            <CardDescription>未归档库存项 remaining_grams 合计（估算）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{totalRemaining}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
            {includeArchived ? (
              <div className="mt-2 text-xs text-muted-foreground">
                当前列表包含归档项（总计 {items.length} 条，其中未归档 {activeItems.length} 条）
              </div>
            ) : (
              <div className="mt-2 text-xs text-muted-foreground">当前未归档 {activeItems.length} 条</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>总料盘</CardTitle>
            <CardDescription>按入库（带料盘）与丢弃累计。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{trayTotal === null ? "-" : trayTotal}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：个</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>已消耗卷数</CardTitle>
            <CardDescription>按消耗克数 / 单卷克数估算。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {valuations && valuations.by_stock_id ? 
                round2(Object.values(valuations.by_stock_id)
                  .filter(v => v && typeof v.consumed_rolls_est === "number")
                  .reduce((sum, v) => sum + v.consumed_rolls_est, 0)) 
                : "-"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">单位：卷（估算）</div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>颜色覆盖率</CardTitle>
            <CardDescription>已绑定颜色的库存项占比。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">
              {activeItems.length > 0 ? 
                `${Math.round((activeItems.filter(s => s.color_hex).length / activeItems.length) * 100)}%` 
                : "0%"}
            </div>
            <div className="mt-2 text-sm text-muted-foreground">
              已绑定 {activeItems.filter(s => s.color_hex).length} / {activeItems.length} 项
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>库存列表</CardTitle>
          <CardDescription>点击进入详情可查看流水并做盘点调整。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">库存项</th>
                  <th className="px-3 py-2">单卷</th>
                  <th className="px-3 py-2">剩余</th>
                  <th className="px-3 py-2">颜色</th>
                  <th className="px-3 py-2">已消耗（卷）</th>
                  <th className="px-3 py-2">更新时间</th>
                  <th className="px-3 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedActiveItems.map((s) => {
                  const v = s?.id && valuations && valuations.by_stock_id ? valuations.by_stock_id[String(s.id)] : null;
                  const cr = v && typeof v.consumed_rolls_est === "number" ? v.consumed_rolls_est : null;
                  return (
                  <tr key={s.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link className="font-medium hover:underline" href={`/stocks/${s.id}`}>
                        {s.material} · {s.color} · {s.brand}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{s.roll_weight_grams}g</td>
                    <td className="px-3 py-2 font-medium">{s.remaining_grams}g</td>
                    <td className="px-3 py-2">
                      {s.color_hex ? (
                        <ColorBlock colorHex={s.color_hex} colorName={s.color} />
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="text-muted-foreground">未绑定颜色</span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setBindColorTarget(s);
                              setBindColorOpen(true);
                            }}
                          >
                            绑定颜色
                          </Button>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">{cr === null ? "-" : round2(cr)}</td>
                    <td className="px-3 py-2">{s.updated_at ? new Date(s.updated_at).toLocaleString() : "-"}</td>
                    <td className="px-3 py-2">
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={Boolean(s?.is_archived)}
                        onClick={() => {
                          setDeleteTarget(s);
                          setDeleteRefInfo(null);
                          setDeleteOpen(true);
                        }}
                      >
                        删除
                      </Button>
                    </td>
                  </tr>
                  );
                })}
                {includeArchived && sortedArchivedItems.length ? (
                  <tr className="border-t bg-muted/30">
                    <td colSpan={7} className="px-3 py-2 text-xs text-muted-foreground">
                      已归档（不参与颜色搜索过滤）
                    </td>
                  </tr>
                ) : null}
                {includeArchived
                  ? sortedArchivedItems.map((s) => {
                      const v = s?.id && valuations && valuations.by_stock_id ? valuations.by_stock_id[String(s.id)] : null;
                      const cr = v && typeof v.consumed_rolls_est === "number" ? v.consumed_rolls_est : null;
                      return (
                      <tr key={s.id} className="border-t">
                        <td className="px-3 py-2">
                          <Link className="font-medium hover:underline" href={`/stocks/${s.id}`}>
                            {s.material} · {s.color} · {s.brand}
                          </Link>
                          <span className="ml-2 align-middle">
                            <Badge variant="outline">已归档</Badge>
                          </span>
                        </td>
                        <td className="px-3 py-2">{s.roll_weight_grams}g</td>
                        <td className="px-3 py-2 font-medium">{s.remaining_grams}g</td>
                        <td className="px-3 py-2">
                          {s.color_hex ? (
                            <ColorBlock colorHex={s.color_hex} colorName={s.color} />
                          ) : (
                            <span className="text-muted-foreground">未绑定颜色</span>
                          )}
                        </td>
                        <td className="px-3 py-2">{cr === null ? "-" : round2(cr)}</td>
                        <td className="px-3 py-2">{s.updated_at ? new Date(s.updated_at).toLocaleString() : "-"}</td>
                        <td className="px-3 py-2">
                          <Button variant="destructive" size="sm" disabled>
                            删除
                          </Button>
                        </td>
                      </tr>
                      );
                    })
                  : null}
                {!includeArchived && sortedActiveItems.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                      {colorQuery.trim()
                        ? "未找到匹配该颜色的未归档库存项。"
                        : "暂无库存项，请点击右上角“新增库存”。"}
                    </td>
                  </tr>
                ) : null}
                {includeArchived && sortedActiveItems.length === 0 && sortedArchivedItems.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                      {colorQuery.trim()
                        ? "未找到匹配该颜色的未归档库存项。（归档项不会参与搜索过滤）"
                        : "暂无库存项，请点击右上角“新增库存”。"}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增库存</DialogTitle>
            <DialogDescription>按「材质 + 颜色 + 品牌」录入总库存：卷数 × 单卷克数。可选录入卷单价与是否带料盘。</DialogDescription>
          </DialogHeader>

          <form
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (v) => {
              try {
                await onSubmit(v);
                form.reset({
                  material: v.material,
                  color: v.color,
                  brand: v.brand,
                  roll_weight_grams: v.roll_weight_grams,
                  rolls_count: 1,
                  price_per_roll: null,
                  price_total: null,
                  has_tray: false
                });
                setCreateOpen(false);
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
                <Input {...form.register("material")} placeholder="PLA/PETG/ABS…" />
                {form.formState.errors.material ? (
                  <div className="text-xs text-destructive">{form.formState.errors.material.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>颜色 *</Label>
                <Input {...form.register("color")} placeholder="白色/黑色/…" />
                {form.formState.errors.color ? (
                  <div className="text-xs text-destructive">{form.formState.errors.color.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>品牌 *</Label>
                <Input {...form.register("brand")} placeholder="拓竹/某品牌" />
                {form.formState.errors.brand ? (
                  <div className="text-xs text-destructive">{form.formState.errors.brand.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>单卷克数 *</Label>
                <Input type="number" {...form.register("roll_weight_grams")} />
                {form.formState.errors.roll_weight_grams ? (
                  <div className="text-xs text-destructive">{form.formState.errors.roll_weight_grams.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2 md:col-span-2">
                <Label>卷数 *</Label>
                <Input type="number" {...form.register("rolls_count")} />
                {form.formState.errors.rolls_count ? (
                  <div className="text-xs text-destructive">{form.formState.errors.rolls_count.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>卷单价（元/卷，可选）</Label>
                <Input
                  type="number"
                  step="0.01"
                  {...form.register("price_per_roll", {
                    onChange: () => setLastPriceEdited("per_roll")
                  })}
                  placeholder="例如：41"
                />
                {form.formState.errors.price_per_roll ? (
                  <div className="text-xs text-destructive">{form.formState.errors.price_per_roll.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>总价（元，可选）</Label>
                <Input
                  type="number"
                  step="0.01"
                  {...form.register("price_total", {
                    onChange: () => setLastPriceEdited("total")
                  })}
                  placeholder="例如：82"
                />
                {form.formState.errors.price_total ? (
                  <div className="text-xs text-destructive">{form.formState.errors.price_total.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>料盘</Label>
                <label className="flex select-none items-center gap-2 text-sm text-muted-foreground">
                  <input type="checkbox" {...form.register("has_tray")} />
                  本次入库带料盘（料盘数 + 卷数）
                </label>
              </div>
            </div>

            <div className="rounded-md border p-3 text-sm">
              <div className="font-medium">本次将新增</div>
              <div className="mt-1 text-muted-foreground">
                约 <span className="font-medium text-foreground">{previewAddGrams}</span> g（卷数 × 单卷克数）。如遇同材质/颜色/品牌已存在，将自动合并累加。
              </div>
              {previewTotalPrice !== null ? (
                <div className="mt-1 text-muted-foreground">
                  预估总价：<span className="font-medium text-foreground">{previewTotalPrice}</span> 元（仅用于后续折合成本统计）。
                </div>
              ) : null}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "提交中…" : "新增"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>丢弃料盘</DialogTitle>
            <DialogDescription>丢弃只影响“总料盘数”，不影响任何库存克数与消耗。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={async (e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const count = Number(fd.get("count") || 0);
              const note = String(fd.get("note") || "").trim();
              if (!Number.isFinite(count) || count <= 0) {
                toast.error("请输入要丢弃的料盘数量（>=1）");
                return;
              }
              try {
                await fetchJson("/trays/discard", {
                  method: "POST",
                  body: JSON.stringify({ count: Math.floor(count), note: note ? note : null })
                });
                toast.success("已记录丢弃料盘");
                setDiscardOpen(false);
                await reload();
              } catch (err) {
                toast.error(String(err?.message || err));
              }
            }}
          >
            <div className="grid gap-2">
              <Label>丢弃数量 *</Label>
              <Input name="count" type="number" min="1" placeholder="例如：1" />
            </div>
            <div className="grid gap-2">
              <Label>备注（可选）</Label>
              <Input name="note" placeholder="例如：坏了/丢了" />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDiscardOpen(false)}>
                取消
              </Button>
              <Button type="submit">提交</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteOpen}
        onOpenChange={(v) => {
          setDeleteOpen(v);
          if (!v) {
            setDeleteTarget(null);
            setDeleteRefInfo(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除库存（归档）</DialogTitle>
            <DialogDescription>删除不会丢历史，只会把库存项归档隐藏。</DialogDescription>
          </DialogHeader>
          <div className="text-sm">
            你将删除：{" "}
            <span className="font-medium">
              {deleteTarget ? `${deleteTarget.material} · ${deleteTarget.color} · ${deleteTarget.brand}` : "-"}
            </span>
          </div>
          {deleteRefInfo ? (
            <div className="rounded-md border p-3 text-sm">
              <div className="font-medium text-destructive">检测到历史引用</div>
              <div className="mt-1 text-muted-foreground">
                消费记录引用：{deleteRefInfo.consumption_count} 条；作业快照引用：{deleteRefInfo.job_count} 条。
              </div>
              <div className="mt-2 text-muted-foreground">仍要继续删除（归档）吗？</div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">确认后该库存项将从默认列表隐藏（可通过“显示已删除”查看）。</div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDeleteOpen(false)} disabled={deleting}>
              取消
            </Button>
            {deleteRefInfo ? (
              <Button type="button" variant="destructive" onClick={() => doArchive(true)} disabled={deleting}>
                {deleting ? "处理中…" : "继续删除（强制）"}
              </Button>
            ) : (
              <Button type="button" variant="destructive" onClick={() => doArchive(false)} disabled={deleting}>
                {deleting ? "处理中…" : "删除"}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={bindColorOpen}
        onOpenChange={(v) => {
          setBindColorOpen(v);
          if (!v) {
            setBindColorTarget(null);
            setColorHexInput("");
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>绑定颜色</DialogTitle>
            <DialogDescription>
              为库存项绑定AMS颜色码。颜色码格式为6位或8位十六进制，如FFFFFFFF表示白色。
            </DialogDescription>
          </DialogHeader>
          <div className="text-sm">
            库存项：{" "}
            <span className="font-medium">
              {bindColorTarget ? `${bindColorTarget.material} · ${bindColorTarget.color} · ${bindColorTarget.brand}` : "-"}
            </span>
          </div>
          <div className="grid gap-2">
            <Label>颜色码 *</Label>
            <Input
              placeholder="例如：FFFFFFFF（白色）"
              value={colorHexInput}
              onChange={(e) => setColorHexInput(e.target.value)}
            />
            {colorHexInput && (
              <div className="flex items-center gap-2 mt-2">
                <span>预览：</span>
                <ColorBlock colorHex={colorHexInput} colorName={bindColorTarget?.color || "预览"} />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setBindColorOpen(false)} disabled={binding}>
              取消
            </Button>
            <Button type="button" onClick={bindColor} disabled={binding || !colorHexInput.trim()}>
              {binding ? "绑定中…" : "绑定"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

