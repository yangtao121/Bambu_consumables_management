"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { fetchJson } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
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

  const form = useForm({
    resolver: zodResolver(createSchema),
    defaultValues: { material: "PLA", color: "白色", brand: "拓竹", roll_weight_grams: 1000, rolls_count: 1 }
  });

  async function reload() {
    setLoading(true);
    try {
      const data = await fetchJson("/stocks");
      setItems(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  const totalRemaining = useMemo(() => items.reduce((acc, s) => acc + Number(s.remaining_grams || 0), 0), [items]);

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

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">库存</h1>
          <p className="text-sm text-muted-foreground">按「材质 + 颜色 + 品牌」维护总库存（卷数 × 单卷重量）。</p>
        </div>
        <Button variant="outline" onClick={reload} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>新增库存项</CardTitle>
            <CardDescription>建议拓竹官方耗材的品牌填“拓竹”，第三方填品牌名。</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4"
              onSubmit={form.handleSubmit(async (v) => {
                try {
                  await onSubmit(v);
                  form.reset({ material: v.material, color: v.color, brand: v.brand, roll_weight_grams: v.roll_weight_grams, rolls_count: 1 });
                } catch (e) {
                  toast.error(String(e?.message || e));
                }
              })}
            >
              <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
                <div className="grid gap-2">
                  <Label>材质 *</Label>
                  <Input {...form.register("material")} placeholder="PLA/PETG/ABS…" />
                  {form.formState.errors.material ? (
                    <div className="text-xs text-destructive">{form.formState.errors.material.message}</div>
                  ) : null}
                </div>
                <div className="grid gap-2">
                  <Label>颜色 *</Label>
                  <Input {...form.register("color")} placeholder="白色/黑色/… 或 HEX" />
                  {form.formState.errors.color ? <div className="text-xs text-destructive">{form.formState.errors.color.message}</div> : null}
                </div>
                <div className="grid gap-2">
                  <Label>品牌 *</Label>
                  <Input {...form.register("brand")} placeholder="拓竹/某品牌" />
                  {form.formState.errors.brand ? <div className="text-xs text-destructive">{form.formState.errors.brand.message}</div> : null}
                </div>
                <div className="grid gap-2">
                  <Label>单卷克数 *</Label>
                  <Input type="number" {...form.register("roll_weight_grams")} />
                  {form.formState.errors.roll_weight_grams ? (
                    <div className="text-xs text-destructive">{form.formState.errors.roll_weight_grams.message}</div>
                  ) : null}
                </div>
                <div className="grid gap-2">
                  <Label>卷数 *</Label>
                  <Input type="number" {...form.register("rolls_count")} />
                  {form.formState.errors.rolls_count ? (
                    <div className="text-xs text-destructive">{form.formState.errors.rolls_count.message}</div>
                  ) : null}
                </div>
              </div>
              <div>
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting ? "提交中…" : "新增"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>总剩余</CardTitle>
            <CardDescription>所有库存项 remaining_grams 的合计（估算）。</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{totalRemaining}</div>
            <div className="mt-2 text-sm text-muted-foreground">单位：g</div>
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
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id} className="border-t">
                    <td className="px-3 py-2">
                      <Link className="font-medium hover:underline" href={`/stocks/${s.id}`}>
                        {s.material} · {s.color} · {s.brand}
                      </Link>
                    </td>
                    <td className="px-3 py-2">{s.roll_weight_grams}g</td>
                    <td className="px-3 py-2 font-medium">{s.remaining_grams}g</td>
                    <td className="px-3 py-2">{s.updated_at ? new Date(s.updated_at).toLocaleString() : "-"}</td>
                  </tr>
                ))}
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-muted-foreground">
                      暂无库存项，请先新增。
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

