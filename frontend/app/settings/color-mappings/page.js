"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { fetchJson } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";

const schema = z.object({
  color_hex: z.string().trim().min(1, "请输入颜色码（如 FFFFFF 或 FFFFFFFF）"),
  color_name: z.string().trim().min(1, "请输入颜色名（如 白色）")
});

export default function Page() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);

  const form = useForm({
    resolver: zodResolver(schema),
    defaultValues: { color_hex: "FFFFFF", color_name: "白色" }
  });

  async function reload() {
    setLoading(true);
    try {
      const data = await fetchJson("/color-mappings");
      setItems(Array.isArray(data) ? data : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function onSubmit(values) {
    await fetchJson("/color-mappings", {
      method: "POST",
      body: JSON.stringify({ color_hex: values.color_hex, color_name: values.color_name })
    });
    toast.success("颜色映射已保存");
    await reload();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-muted-foreground">
            <Link className="hover:underline" href="/settings">
              Settings
            </Link>{" "}
            / 颜色映射
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">AMS 颜色映射</h1>
          <p className="text-sm text-muted-foreground">
            把 AMS 读到的颜色码（如 FFFFFF/FFFFFFFF）映射成库存使用的颜色名（如 白色/灰色），用于自动匹配与扣减。
          </p>
        </div>
        <Button variant="outline" onClick={reload} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>新增/更新映射</CardTitle>
          <CardDescription>同一个颜色码再次提交会覆盖颜色名（幂等）。</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-4"
            onSubmit={form.handleSubmit(async (v) => {
              try {
                await onSubmit(v);
              } catch (e) {
                toast.error(String(e?.message || e));
              }
            })}
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="grid gap-2">
                <Label>颜色码 *</Label>
                <Input placeholder="FFFFFF 或 FFFFFFFF 或 #FFFFFF" {...form.register("color_hex")} />
                {form.formState.errors.color_hex ? (
                  <div className="text-xs text-destructive">{form.formState.errors.color_hex.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>颜色名 *</Label>
                <Input placeholder="白色/灰色/黑色…" {...form.register("color_name")} />
                {form.formState.errors.color_name ? (
                  <div className="text-xs text-destructive">{form.formState.errors.color_name.message}</div>
                ) : null}
              </div>
              <div className="flex items-end">
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting ? "提交中…" : "保存"}
                </Button>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>映射列表</CardTitle>
          <CardDescription>按更新时间倒序。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-auto rounded-md border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left">
                  <th className="px-3 py-2">颜色码</th>
                  <th className="px-3 py-2">颜色名</th>
                  <th className="px-3 py-2">更新时间</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id} className="border-t">
                    <td className="px-3 py-2 font-mono">{r.color_hex}</td>
                    <td className="px-3 py-2 font-medium">{r.color_name}</td>
                    <td className="px-3 py-2">{r.updated_at ? new Date(r.updated_at).toLocaleString() : "-"}</td>
                  </tr>
                ))}
                {items.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-3 py-8 text-center text-muted-foreground">
                      暂无映射。你也可以在 Printers 页面看到未映射颜色并直接保存。
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

