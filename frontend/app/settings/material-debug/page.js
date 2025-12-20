"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import Link from "next/link";

import { fetchJson } from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";

export default function Page() {
  const [colorMappings, setColorMappings] = useState([]);
  const [material, setMaterial] = useState("");
  const [color, setColor] = useState("");
  const [stocks, setStocks] = useState([]);
  const [colorHex, setColorHex] = useState("");
  const [colorResolution, setColorResolution] = useState(null);
  const [loading, setLoading] = useState(false);

  async function loadColorMappings() {
    setLoading(true);
    try {
      const data = await fetchJson("/debug/color-mappings");
      setColorMappings(Array.isArray(data) ? data : []);
    } catch (error) {
      toast.error(`加载颜色映射失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function searchStocks() {
    if (!material && !color) {
      toast.error("请至少输入材料或颜色");
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (material) params.append("material", material);
      if (color) params.append("color", color);
      
      const data = await fetchJson(`/debug/stocks-by-material-color?${params.toString()}`);
      setStocks(data.stocks || []);
      
      if (data.count === 0) {
        toast.info("未找到匹配的库存");
      } else {
        toast.success(`找到 ${data.count} 个匹配的库存`);
      }
    } catch (error) {
      toast.error(`查询库存失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function resolveColorHex() {
    if (!colorHex) {
      toast.error("请输入颜色码");
      return;
    }

    setLoading(true);
    try {
      const data = await fetchJson(`/debug/color-hex/${encodeURIComponent(colorHex)}/resolve`);
      setColorResolution(data);
    } catch (error) {
      toast.error(`解析颜色码失败: ${error.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadColorMappings();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="text-sm text-muted-foreground">
            <Link className="hover:underline" href="/settings">
              Settings
            </Link>{" "}
            / 材料调试
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">材料映射调试工具</h1>
          <p className="text-sm text-muted-foreground">
            用于调试材料识别和扣除问题的工具集
          </p>
        </div>
        <Button variant="outline" onClick={loadColorMappings} disabled={loading}>
          {loading ? "加载中…" : "刷新"}
        </Button>
      </div>

      {/* 颜色码解析工具 */}
      <Card>
        <CardHeader>
          <CardTitle>颜色码解析工具</CardTitle>
          <CardDescription>
            输入AMS报告的颜色码，查看映射和可能的匹配库存
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="grid gap-2">
              <Label htmlFor="colorHex">颜色码</Label>
              <Input
                id="colorHex"
                placeholder="如: FFFFFF 或 #FFFFFF"
                value={colorHex}
                onChange={(e) => setColorHex(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button onClick={resolveColorHex} disabled={loading}>
                解析颜色码
              </Button>
            </div>
          </div>
          
          {colorResolution && (
            <div className="mt-4 space-y-4">
              <div>
                <h4 className="font-medium">解析结果</h4>
                <div className="mt-2 rounded-md border p-3 text-sm">
                  <p>输入: {colorResolution.input}</p>
                  <p>规范化: {colorResolution.normalized_hex}</p>
                  {colorResolution.color_mapping && (
                    <p>
                      映射: {colorResolution.color_mapping.color_hex} - {colorResolution.color_mapping.color_name}
                    </p>
                  )}
                </div>
              </div>
              
              {colorResolution.matching_stocks && colorResolution.matching_stocks.length > 0 && (
                <div>
                  <h4 className="font-medium">匹配的库存</h4>
                  <div className="mt-2 overflow-auto rounded-md border">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr className="text-left">
                          <th className="px-3 py-2">材料</th>
                          <th className="px-3 py-2">颜色</th>
                          <th className="px-3 py-2">品牌</th>
                          <th className="px-3 py-2">剩余(g)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {colorResolution.matching_stocks.map((stock) => (
                          <tr key={stock.id} className="border-t">
                            <td className="px-3 py-2">{stock.material}</td>
                            <td className="px-3 py-2">{stock.color}</td>
                            <td className="px-3 py-2">{stock.brand}</td>
                            <td className="px-3 py-2">{stock.remaining_grams}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 库存查询工具 */}
      <Card>
        <CardHeader>
          <CardTitle>库存查询工具</CardTitle>
          <CardDescription>
            根据材料和颜色查询库存，检查是否有重复或错误的记录
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="grid gap-2">
              <Label htmlFor="material">材料</Label>
              <Input
                id="material"
                placeholder="如: PLA"
                value={material}
                onChange={(e) => setMaterial(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="color">颜色</Label>
              <Input
                id="color"
                placeholder="如: 灰色"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </div>
            <div className="flex items-end">
              <Button onClick={searchStocks} disabled={loading}>
                查询库存
              </Button>
            </div>
          </div>
          
          {stocks.length > 0 && (
            <div className="mt-4">
              <h4 className="font-medium">查询结果 ({stocks.length}条)</h4>
              <div className="mt-2 overflow-auto rounded-md border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr className="text-left">
                      <th className="px-3 py-2">材料</th>
                      <th className="px-3 py-2">颜色</th>
                      <th className="px-3 py-2">品牌</th>
                      <th className="px-3 py-2">剩余(g)</th>
                      <th className="px-3 py-2">归档</th>
                      <th className="px-3 py-2">更新时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stocks.map((stock) => (
                      <tr key={stock.id} className="border-t">
                        <td className="px-3 py-2">{stock.material}</td>
                        <td className="px-3 py-2">{stock.color}</td>
                        <td className="px-3 py-2">{stock.brand}</td>
                        <td className="px-3 py-2">{stock.remaining_grams}</td>
                        <td className="px-3 py-2">{stock.is_archived ? "是" : "否"}</td>
                        <td className="px-3 py-2">
                          {stock.updated_at ? new Date(stock.updated_at).toLocaleString() : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {stocks.length > 1 && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                  <p className="text-sm text-yellow-800">
                    警告: 找到多个匹配的库存记录，这可能导致材料匹配错误。建议检查这些记录，确保每个材料和颜色组合只有一个活跃记录。
                  </p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 颜色映射表 */}
      <Card>
        <CardHeader>
          <CardTitle>当前颜色映射表</CardTitle>
          <CardDescription>
            AMS颜色码到颜色名称的映射表，用于材料自动识别
          </CardDescription>
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
                {colorMappings.map((mapping) => (
                  <tr key={mapping.id} className="border-t">
                    <td className="px-3 py-2 font-mono">{mapping.color_hex}</td>
                    <td className="px-3 py-2">{mapping.color_name}</td>
                    <td className="px-3 py-2">
                      {mapping.updated_at ? new Date(mapping.updated_at).toLocaleString() : "-"}
                    </td>
                  </tr>
                ))}
                {colorMappings.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-8 text-center text-muted-foreground">
                      暂无颜色映射。前往{" "}
                      <Link href="/settings/color-mappings" className="text-blue-600 hover:underline">
                        颜色映射设置
                      </Link>{" "}
                      添加映射。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
