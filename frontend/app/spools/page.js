"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import { fetchJson } from "../../lib/api";
import { cn } from "../../lib/utils";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "../../components/ui/dropdown-menu";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

function refinePrices(v, ctx) {
  const pt = v.price_total === "" ? null : v.price_total;
  const ppk = v.price_per_kg === "" ? null : v.price_per_kg;
  if (pt != null && typeof pt === "number" && Number.isNaN(pt)) ctx.addIssue({ code: "custom", path: ["price_total"], message: "总价格式不正确" });
  if (ppk != null && typeof ppk === "number" && Number.isNaN(ppk)) ctx.addIssue({ code: "custom", path: ["price_per_kg"], message: "单价格式不正确" });
}

const createBaseSchema = z.object({
    name: z.string().trim().min(1, "请输入名称"),
    material: z.string().trim().min(1, "请输入材质"),
    color: z.string().trim().min(1, "请输入颜色"),
    brand: z.string().trim().optional(),
    diameter_mm: z.coerce.number().positive().default(1.75),
    initial_grams: z.coerce.number().int().min(0, "初始克数必须 >= 0"),
    tare_grams: z
      .union([z.coerce.number().int().min(0, "空盘克数必须 >= 0"), z.literal(""), z.null(), z.undefined()])
      .optional(),
    price_total: z.union([z.coerce.number().min(0, "总价必须 >= 0"), z.literal(""), z.null(), z.undefined()]).optional(),
    price_per_kg: z.union([z.coerce.number().min(0, "单价必须 >= 0"), z.literal(""), z.null(), z.undefined()]).optional(),
    purchase_date: z.string().optional(),
    note: z.string().trim().optional()
});

const createSchema = createBaseSchema.superRefine(refinePrices);
const editSchema = createBaseSchema.omit({ initial_grams: true }).superRefine(refinePrices);

const adjustmentSchema = z.object({
  delta_grams: z.coerce.number().int().refine((n) => n !== 0, "调整值不能为 0"),
  reason: z.string().trim().optional()
});

function statusVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "active") return "default";
  if (s === "empty") return "secondary";
  if (s === "retired") return "outline";
  return "outline";
}

export default function Page() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [editing, setEditing] = useState(null); // spool
  const [adjusting, setAdjusting] = useState(null); // spool
  const [createOpen, setCreateOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [emptyOpen, setEmptyOpen] = useState(false);
  const [emptying, setEmptying] = useState(null);

  async function reload() {
    try {
      setLoading(true);
      const data = await fetchJson("/spools");
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items
      .filter((s) => {
        if (status !== "all" && String(s.status || "").toLowerCase() !== status) return false;
        if (!q) return true;
        const hay = `${s.name || ""} ${s.material || ""} ${s.color || ""} ${s.brand || ""}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => {
        // 默认按创建时间 desc（后端已排序），这里保持稳定
        return 0;
      });
  }, [items, query, status]);

  const createForm = useForm({
    resolver: zodResolver(createSchema),
    defaultValues: {
      name: "",
      material: "PLA",
      color: "",
      brand: "",
      diameter_mm: 1.75,
      initial_grams: 1000,
      tare_grams: "",
      price_total: "",
      price_per_kg: "",
      purchase_date: "",
      note: ""
    }
  });

  const editForm = useForm({
    resolver: zodResolver(editSchema),
    defaultValues: {
      name: "",
      material: "PLA",
      color: "",
      brand: "",
      diameter_mm: 1.75,
      tare_grams: "",
      price_total: "",
      price_per_kg: "",
      purchase_date: "",
      note: ""
    }
  });

  const adjForm = useForm({
    resolver: zodResolver(adjustmentSchema),
    defaultValues: { delta_grams: 0, reason: "" }
  });

  async function submitCreate(values) {
    const body = {
      name: values.name,
      material: values.material,
      color: values.color,
      brand: values.brand ? values.brand : null,
      diameter_mm: Number(values.diameter_mm),
      initial_grams: Number(values.initial_grams),
      tare_grams: values.tare_grams === "" || values.tare_grams == null ? null : Number(values.tare_grams),
      price_total: values.price_total === "" || values.price_total == null ? null : Number(values.price_total),
      price_per_kg: values.price_per_kg === "" || values.price_per_kg == null ? null : Number(values.price_per_kg),
      purchase_date: values.purchase_date ? values.purchase_date : null,
      note: values.note ? values.note : null
    };
    await fetchJson("/spools", { method: "POST", body: JSON.stringify(body) });
    toast.success("耗材已创建");
    setCreateOpen(false);
    createForm.reset();
    await reload();
  }

  async function openEdit(spool) {
    setEditing(spool);
    editForm.reset({
      name: spool.name || "",
      material: spool.material || "",
      color: spool.color || "",
      brand: spool.brand || "",
      diameter_mm: spool.diameter_mm ?? 1.75,
      tare_grams: spool.tare_grams == null ? "" : spool.tare_grams,
      price_total: spool.price_total == null ? "" : spool.price_total,
      price_per_kg: spool.price_per_kg == null ? "" : spool.price_per_kg,
      purchase_date: spool.purchase_date || "",
      note: spool.note || ""
    });
    setEditOpen(true);
  }

  async function submitEdit(values) {
    if (!editing?.id) return;
    const patch = {
      name: values.name,
      material: values.material,
      color: values.color,
      brand: values.brand ? values.brand : null,
      diameter_mm: Number(values.diameter_mm),
      tare_grams: values.tare_grams === "" || values.tare_grams == null ? null : Number(values.tare_grams),
      price_total: values.price_total === "" || values.price_total == null ? null : Number(values.price_total),
      price_per_kg: values.price_per_kg === "" || values.price_per_kg == null ? null : Number(values.price_per_kg),
      purchase_date: values.purchase_date ? values.purchase_date : null,
      note: values.note ? values.note : null
    };
    await fetchJson(`/spools/${editing.id}`, { method: "PATCH", body: JSON.stringify(patch) });
    toast.success("耗材已更新");
    setEditOpen(false);
    setEditing(null);
    await reload();
  }

  async function openAdjustment(spool) {
    setAdjusting(spool);
    adjForm.reset({ delta_grams: 0, reason: "" });
    setAdjustOpen(true);
  }

  async function submitAdjustment(values) {
    if (!adjusting?.id) return;
    await fetchJson(`/spools/${adjusting.id}/adjustments`, {
      method: "POST",
      body: JSON.stringify({ delta_grams: Number(values.delta_grams), reason: values.reason ? values.reason : null })
    });
    toast.success("盘点调整已记录");
    setAdjustOpen(false);
    setAdjusting(null);
    await reload();
  }

  function openMarkEmpty(spool) {
    setEmptying(spool);
    setEmptyOpen(true);
  }

  async function submitMarkEmpty() {
    if (!emptying?.id) return;
    await fetchJson(`/spools/${emptying.id}/mark-empty`, { method: "POST", body: JSON.stringify({ confirm: true }) });
    toast.success("已标记用完，并解绑相关托盘");
    setEmptyOpen(false);
    setEmptying(null);
    await reload();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Spools</h1>
          <p className="text-sm text-muted-foreground">耗材卷管理：新增/编辑/盘点/用完 + 详情账本。</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>

          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button>新增耗材</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>新增耗材卷</DialogTitle>
                <DialogDescription>必填：名称/材质/颜色；其余可选。</DialogDescription>
              </DialogHeader>
              <form
                className="grid gap-4"
                onSubmit={createForm.handleSubmit(async (v) => {
                  try {
                    await submitCreate(v);
                  } catch (e) {
                    toast.error(String(e?.message || e));
                  }
                })}
              >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="grid gap-2">
                    <Label>名称 *</Label>
                    <Input {...createForm.register("name")} placeholder="例如：PLA 白 1kg" />
                    {createForm.formState.errors.name ? (
                      <div className="text-xs text-destructive">{createForm.formState.errors.name.message}</div>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    <Label>材质 *</Label>
                    <Input {...createForm.register("material")} placeholder="PLA / PETG / ABS / TPU" />
                    {createForm.formState.errors.material ? (
                      <div className="text-xs text-destructive">{createForm.formState.errors.material.message}</div>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    <Label>颜色 *</Label>
                    <Input {...createForm.register("color")} placeholder="白 / 黑 / Gray..." />
                    {createForm.formState.errors.color ? (
                      <div className="text-xs text-destructive">{createForm.formState.errors.color.message}</div>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    <Label>品牌</Label>
                    <Input {...createForm.register("brand")} placeholder="可选" />
                  </div>
                  <div className="grid gap-2">
                    <Label>初始克数 *</Label>
                    <Input type="number" {...createForm.register("initial_grams")} />
                    {createForm.formState.errors.initial_grams ? (
                      <div className="text-xs text-destructive">{createForm.formState.errors.initial_grams.message}</div>
                    ) : null}
                  </div>
                  <div className="grid gap-2">
                    <Label>空盘克数</Label>
                    <Input type="number" {...createForm.register("tare_grams")} placeholder="可选" />
                  </div>
                  <div className="grid gap-2">
                    <Label>总价</Label>
                    <Input type="number" {...createForm.register("price_total")} placeholder="可选" />
                  </div>
                  <div className="grid gap-2">
                    <Label>单价（元/kg）</Label>
                    <Input type="number" {...createForm.register("price_per_kg")} placeholder="可选" />
                  </div>
                  <div className="grid gap-2">
                    <Label>购买日期</Label>
                    <Input type="date" {...createForm.register("purchase_date")} />
                  </div>
                  <div className="grid gap-2">
                    <Label>直径（mm）</Label>
                    <Input type="number" step="0.01" {...createForm.register("diameter_mm")} />
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label>备注</Label>
                  <Input {...createForm.register("note")} placeholder="可选" />
                </div>
                <DialogFooter>
                  <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
                    取消
                  </Button>
                  <Button type="submit" disabled={createForm.formState.isSubmitting}>
                    {createForm.formState.isSubmitting ? "提交中…" : "创建"}
                  </Button>
                </DialogFooter>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>筛选</CardTitle>
          <CardDescription>支持关键字搜索与状态筛选。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索：名称 / 材质 / 颜色 / 品牌" />
            <div className="flex items-center gap-2">
              <Label className="text-muted-foreground">状态</Label>
              <select
                className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value)}
              >
                <option value="all">全部</option>
                <option value="active">active</option>
                <option value="empty">empty</option>
                <option value="retired">retired</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>耗材列表</CardTitle>
          <CardDescription className="flex items-center justify-between">
            <span>共 {filtered.length} 条</span>
            <span className="text-xs">提示：点击名称进入详情账本</span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">名称</th>
                  <th className="px-3 py-2">材质</th>
                  <th className="px-3 py-2">颜色</th>
                  <th className="px-3 py-2">剩余估计(g)</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((s) => (
                  <tr key={s.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link className="font-medium hover:underline" href={`/spools/${s.id}`}>
                        {s.name}
                      </Link>
                      {s.brand ? <div className="text-xs text-muted-foreground">{s.brand}</div> : null}
                    </td>
                    <td className="px-3 py-2">{s.material}</td>
                    <td className="px-3 py-2">{s.color}</td>
                    <td className={cn("px-3 py-2 font-medium", s.remaining_grams_est <= 0 ? "text-destructive" : "")}>{s.remaining_grams_est}</td>
                    <td className="px-3 py-2">
                      <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="outline" size="sm">
                            操作
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openEdit(s)}>编辑</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => openAdjustment(s)}>盘点调整</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive" onClick={() => openMarkEmpty(s)}>
                            标记用完
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr>
                    <td className="px-3 py-8 text-center text-muted-foreground" colSpan={6}>
                      暂无数据
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editOpen} onOpenChange={(v) => (setEditOpen(v), v ? null : setEditing(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>编辑耗材卷</DialogTitle>
            <DialogDescription>更新基础信息、价格与备注（不会改历史扣料记录）。</DialogDescription>
          </DialogHeader>
          <form
            className="grid gap-4"
            onSubmit={editForm.handleSubmit(async (v) => {
              try {
                await submitEdit(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>名称 *</Label>
                <Input {...editForm.register("name")} />
                {editForm.formState.errors.name ? <div className="text-xs text-destructive">{editForm.formState.errors.name.message}</div> : null}
              </div>
              <div className="grid gap-2">
                <Label>材质 *</Label>
                <Input {...editForm.register("material")} />
                {editForm.formState.errors.material ? (
                  <div className="text-xs text-destructive">{editForm.formState.errors.material.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>颜色 *</Label>
                <Input {...editForm.register("color")} />
                {editForm.formState.errors.color ? <div className="text-xs text-destructive">{editForm.formState.errors.color.message}</div> : null}
              </div>
              <div className="grid gap-2">
                <Label>品牌</Label>
                <Input {...editForm.register("brand")} />
              </div>
              <div className="grid gap-2">
                <Label>空盘克数</Label>
                <Input type="number" {...editForm.register("tare_grams")} />
              </div>
              <div className="grid gap-2">
                <Label>总价</Label>
                <Input type="number" {...editForm.register("price_total")} />
              </div>
              <div className="grid gap-2">
                <Label>单价（元/kg）</Label>
                <Input type="number" {...editForm.register("price_per_kg")} />
              </div>
              <div className="grid gap-2">
                <Label>购买日期</Label>
                <Input type="date" {...editForm.register("purchase_date")} />
              </div>
              <div className="grid gap-2">
                <Label>直径（mm）</Label>
                <Input type="number" step="0.01" {...editForm.register("diameter_mm")} />
              </div>
              <div className="grid gap-2 sm:col-span-2">
                <Label>备注</Label>
                <Input {...editForm.register("note")} />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditOpen(false)}>
                取消
              </Button>
              <Button type="submit" disabled={editForm.formState.isSubmitting}>
                {editForm.formState.isSubmitting ? "保存中…" : "保存"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={adjustOpen} onOpenChange={(v) => (setAdjustOpen(v), v ? null : setAdjusting(null))}>
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

      <Dialog open={emptyOpen} onOpenChange={(v) => (setEmptyOpen(v), v ? null : setEmptying(null))}>
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
