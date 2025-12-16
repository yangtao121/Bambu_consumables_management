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
  rolls_count: z.coerce.number().int().min(0, "卷数必须 >= 0")
});

export default function Page() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteRefInfo, setDeleteRefInfo] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [colorQuery, setColorQuery] = useState("");
  const [sortKey, setSortKey] = useState("remaining"); // remaining | created | updated
  const [sortDir, setSortDir] = useState("desc"); // asc | desc

  const form = useForm({
    resolver: zodResolver(createSchema),
    defaultValues: { material: "PLA", color: "白色", brand: "拓竹", roll_weight_grams: 1000, rolls_count: 1 }
  });

  async function reload(opts = {}) {
    const inc = typeof opts.includeArchived === "boolean" ? opts.includeArchived : includeArchived;
    setLoading(true);
    try {
      const data = await fetchJson(`/stocks${inc ? "?include_archived=1" : ""}`);
      setItems(Array.isArray(data) ? data : []);
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
    await fetchJson("/stocks", {
      method: "POST",
      body: JSON.stringify({
        material: values.material,
        color: values.color,
        brand: values.brand,
        roll_weight_grams: Number(values.roll_weight_grams),
        rolls_count: Number(values.rolls_count)
      })
    });
    toast.success("库存已新增");
    await reload();
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
                  <th className="px-3 py-2">更新时间</th>
                  <th className="px-3 py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedActiveItems.map((s) => (
                  <tr key={s.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link className="font-medium hover:underline" href={`/stocks/${s.id}`}>
                        {s.material} · {s.color} · {s.brand}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{s.roll_weight_grams}g</td>
                    <td className="px-3 py-2 font-medium">{s.remaining_grams}g</td>
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
                ))}
                {includeArchived && sortedArchivedItems.length ? (
                  <tr className="border-t bg-muted/30">
                    <td colSpan={5} className="px-3 py-2 text-xs text-muted-foreground">
                      已归档（不参与颜色搜索过滤）
                    </td>
                  </tr>
                ) : null}
                {includeArchived
                  ? sortedArchivedItems.map((s) => (
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
                        <td className="px-3 py-2">{s.updated_at ? new Date(s.updated_at).toLocaleString() : "-"}</td>
                        <td className="px-3 py-2">
                          <Button variant="destructive" size="sm" disabled>
                            删除
                          </Button>
                        </td>
                      </tr>
                    ))
                  : null}
                {!includeArchived && sortedActiveItems.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">
                      {colorQuery.trim()
                        ? "未找到匹配该颜色的未归档库存项。"
                        : "暂无库存项，请点击右上角“新增库存”。"}
                    </td>
                  </tr>
                ) : null}
                {includeArchived && sortedActiveItems.length === 0 && sortedArchivedItems.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-muted-foreground">
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
            <DialogDescription>按「材质 + 颜色 + 品牌」录入总库存：卷数 × 单卷克数。</DialogDescription>
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
                  rolls_count: 1
                });
                setCreateOpen(false);
              } catch (e) {
                toast.error(String(e?.message || e));
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
    </div>
  );
}

