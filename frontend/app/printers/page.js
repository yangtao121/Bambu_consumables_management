"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { apiBaseUrl, fetchJson } from "../../lib/api";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

function formatGcodeState(st) {
  if (!st) return "-";
  const s = String(st).toUpperCase();
  if (s === "RUNNING") return "打印中";
  if (s === "PAUSE" || s === "PAUSED") return "暂停";
  if (s === "FINISH" || s === "IDLE") return "空闲";
  if (s === "PREPARE" || s === "PREPARING") return "准备中";
  if (s === "FAILED" || s === "ERROR") return "异常";
  return s;
}

function fmtTime(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

function statusVariant(status) {
  const s = String(status || "").toLowerCase();
  if (s === "online") return "default";
  if (s === "unknown") return "outline";
  if (s === "offline") return "secondary";
  return "outline";
}

const printerSchema = z.object({
  ip: z.string().trim().min(1, "请输入 IP"),
  serial: z.string().trim().min(1, "请输入 Serial"),
  lan_access_code: z.string().trim().min(1, "请输入 LAN Code"),
  alias: z.string().trim().optional(),
  model: z.string().trim().optional()
});

export default function Page() {
  const [items, setItems] = useState([]);
  const [reportsById, setReportsById] = useState({});
  const [stocks, setStocks] = useState([]);
  const [colorMappings, setColorMappings] = useState({});
  const [colorDraftByHex, setColorDraftByHex] = useState({});
  const [savingColorHex, setSavingColorHex] = useState(null);
  const [loading, setLoading] = useState(false);

  const printerIdsKey = items
    .map((p) => p && p.id)
    .filter(Boolean)
    .join("|");

  async function reload() {
    try {
      setLoading(true);
      const data = await fetchJson("/printers");
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  async function reloadStocks() {
    try {
      const s = await fetchJson("/stocks");
      setStocks(Array.isArray(s) ? s : []);
    } catch (e) {
      toast.error(String(e?.message || e));
    }
  }

  function normalizeColorHex(v) {
    if (v == null) return null;
    const s0 = String(v).trim();
    if (!s0) return null;
    const raw = s0.startsWith("#") ? s0.slice(1).trim() : s0;
    const hx = raw.toUpperCase();
    if (!/^[0-9A-F]+$/.test(hx)) return null;
    if (hx.length === 8) return `#${hx.slice(-6)}`;
    if (hx.length === 6) return `#${hx}`;
    return null;
  }

  async function reloadColorMappings() {
    try {
      const rows = await fetchJson("/color-mappings");
      const map = {};
      for (const r of Array.isArray(rows) ? rows : []) {
        if (r?.color_hex && r?.color_name) map[String(r.color_hex)] = String(r.color_name);
      }
      setColorMappings(map);
    } catch (e) {
      toast.error(String(e?.message || e));
    }
  }

  async function saveColorMapping(colorHex) {
    const name = String(colorDraftByHex[colorHex] || "").trim();
    if (!name) {
      toast.error("请输入要映射的颜色名（如：白色/灰色）");
      return;
    }
    try {
      setSavingColorHex(colorHex);
      await fetchJson("/color-mappings", {
        method: "POST",
        body: JSON.stringify({ color_hex: colorHex, color_name: name })
      });
      toast.success(`已保存映射：${colorHex} -> ${name}`);
      setColorDraftByHex((prev) => ({ ...prev, [colorHex]: "" }));
      await reloadColorMappings();
      await reloadStocks();
    } catch (e) {
      toast.error(String(e?.message || e));
    } finally {
      setSavingColorHex(null);
    }
  }

  useEffect(() => {
    reload();
    reloadStocks();
    reloadColorMappings();

    // Realtime updates via SSE
    const url = `${apiBaseUrl()}/realtime/printers`;
    const es = new EventSource(url);
    es.addEventListener("printers", (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload && Array.isArray(payload.printers)) {
          setItems(payload.printers);
        }
      } catch (_err) {
        // ignore parse errors; user can still manually refresh
      }
    });
    es.onerror = () => {
      // Don't spam errors; keep manual refresh available
    };

    // Fallback polling (SSE may be blocked in some network/proxy setups)
    const pollId = setInterval(() => {
      reload();
    }, 5000);

    return () => {
      es.close();
      clearInterval(pollId);
    };
  }, []);

  // Per-printer live report (print status / progress / tray info)
  useEffect(() => {
    let cancelled = false;
    const sources = new Map();

    async function loadLatest(printerId) {
      try {
        const r = await fetchJson(`/printers/${printerId}/latest-report`);
        if (!cancelled) {
          setReportsById((prev) => ({ ...prev, [printerId]: r }));
        }
      } catch (_e) {
        // ignore; SSE may still fill
      }
    }

    for (const p of items) {
      if (!p?.id) continue;
      loadLatest(p.id);

      const sseUrl = `${apiBaseUrl()}/realtime/printers/${p.id}`;
      const es = new EventSource(sseUrl);
      es.addEventListener("printer", (e) => {
        try {
          const payload = JSON.parse(e.data);
          if (payload && payload.printer_id) {
            setReportsById((prev) => ({ ...prev, [payload.printer_id]: payload }));
          }
        } catch (_err) {
          // ignore parse errors
        }
      });
      es.onerror = () => {
        // ignore; polling still works
      };
      sources.set(p.id, es);
    }

    // low-frequency polling to cover SSE blocked cases
    const pollId = setInterval(() => {
      for (const p of items) {
        if (p?.id) loadLatest(p.id);
      }
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(pollId);
      for (const es of sources.values()) es.close();
    };
  }, [printerIdsKey]);

  const form = useForm({
    resolver: zodResolver(printerSchema),
    defaultValues: { ip: "", serial: "", lan_access_code: "", alias: "", model: "" }
  });

  async function onSubmit(values) {
    await fetchJson("/printers", {
      method: "POST",
      body: JSON.stringify({
        ip: values.ip,
        serial: values.serial,
        lan_access_code: values.lan_access_code,
        alias: values.alias ? values.alias : null,
        model: values.model ? values.model : null
      })
    });
    toast.success("打印机已添加");
    form.reset({ ip: "", serial: "", lan_access_code: "", alias: "", model: "" });
    await reload();
  }

  function normalizeRemainPct(v) {
    if (v == null) return null;
    const n = Number(v);
    if (!Number.isFinite(n) || n < 0) return null;
    if (n <= 1) return n * 100; // fraction -> percent
    if (n <= 100) return n;
    return null; // unknown unit
  }

  function isOfficialTray(t) {
    if (!t || typeof t !== "object") return false;
    const tag = t.tag_uid;
    const uuid = t.tray_uuid;
    const name = t.tray_id_name;
    if (typeof tag === "number" && tag > 0) return true;
    if (typeof tag === "string" && tag.trim() && tag.trim() !== "0") return true;
    if (typeof uuid === "string" && uuid.trim()) return true;
    if (typeof name === "string" && name.trim()) return true;
    return false;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Printers</h1>
          <p className="text-sm text-muted-foreground">
            添加/查看打印机。耗材不再按“具体卷”绑定托盘，而是按「材质+颜色+品牌」的库存项扣减；第三方品牌读不到时会在作业里提示归因。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={reload} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </Button>
          <Button variant="outline" onClick={reloadStocks}>
            刷新库存
          </Button>
          <Button variant="outline" onClick={reloadColorMappings}>
            刷新颜色映射
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>添加打印机</CardTitle>
          <CardDescription>LAN Code 会在后端加密存储。</CardDescription>
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
            <div className="grid grid-cols-1 gap-4 md:grid-cols-5">
              <div className="grid gap-2">
                <Label>IP *</Label>
                <Input placeholder="192.168.x.x" {...form.register("ip")} />
                {form.formState.errors.ip ? <div className="text-xs text-destructive">{form.formState.errors.ip.message}</div> : null}
              </div>
              <div className="grid gap-2">
                <Label>Serial *</Label>
                <Input placeholder="A1Pxxxx..." {...form.register("serial")} />
                {form.formState.errors.serial ? <div className="text-xs text-destructive">{form.formState.errors.serial.message}</div> : null}
              </div>
              <div className="grid gap-2">
                <Label>LAN Code *</Label>
                <Input placeholder="LAN Access Code" {...form.register("lan_access_code")} />
                {form.formState.errors.lan_access_code ? (
                  <div className="text-xs text-destructive">{form.formState.errors.lan_access_code.message}</div>
                ) : null}
              </div>
              <div className="grid gap-2">
                <Label>Alias</Label>
                <Input placeholder="可选" {...form.register("alias")} />
              </div>
              <div className="grid gap-2">
                <Label>Model</Label>
                <Input placeholder="可选" {...form.register("model")} />
              </div>
            </div>
            <div>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting ? "提交中…" : "添加"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {items.map((p) => {
          const rep = reportsById[p.id];
          const ev = rep?.event || rep?.data || null;
          const gcodeState = ev?.gcode_state || ev?.gcodeState || null;
          const progress = ev?.progress ?? null;
          const taskId = ev?.task_id || ev?.subtask_id || null;
          const taskName = ev?.subtask_name || ev?.gcode_file || null;
          const trayNow = ev?.tray_now ?? null;
          const trays = Array.isArray(ev?.ams_trays) ? ev.ams_trays : [];
          // 固定 1 个 AMS（4 槽）：即便固件不回传空槽，也要稳定展示 0-3。
          const slotIds = [0, 1, 2, 3];
          const trayById = new Map();
          for (const t of trays) {
            const tid = t?.id;
            if (tid == null) continue;
            const n = Number(tid);
            if (!Number.isFinite(n)) continue;
            trayById.set(n, t);
          }
          const displayTrays = slotIds.map((id) => trayById.get(id) || { id, __missing: true });
          const occurredAt = rep?.occurred_at || null;
          const currentTray =
            trayNow == null || trayNow === 255 ? null : trays.find((t) => Number(t?.id) === Number(trayNow)) || null;
          const currentMaterial = currentTray?.type || "-";
          const currentColorHex = normalizeColorHex(currentTray?.color);
          const currentColorName = currentColorHex ? colorMappings[currentColorHex] || null : currentTray?.color || null;
          const currentColor = currentColorName ? `${currentColorName}${currentColorHex ? ` (${currentColorHex})` : ""}` : currentColorHex || currentTray?.color || "-";
          const currentOfficial = currentTray ? isOfficialTray(currentTray) : false;
          const currentColorKey = currentColorName || (!currentColorHex && typeof currentTray?.color === "string" ? currentTray.color : null);
          const currentCandidates = currentTray
            ? stocks.filter(
                (s) =>
                  s.material === currentMaterial &&
                  (currentColorKey ? s.color === currentColorKey : false) &&
                  (currentOfficial ? s.brand === "拓竹" : s.brand !== "拓竹")
              )
            : [];
          const currentStock = currentCandidates.length === 1 ? currentCandidates[0] : null;

          return (
            <Card key={p.id}>
              <CardHeader>
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2">
                      <span>{p.alias || p.serial}</span>
                      <Badge variant={statusVariant(p.status)}>{p.status}</Badge>
                    </CardTitle>
                    <CardDescription>
                      {p.ip} · {p.serial} · last_seen {p.last_seen ? fmtTime(p.last_seen) : "-"}
                    </CardDescription>
                  </div>
                  <div className="text-sm">
                    <div className="font-medium">{formatGcodeState(gcodeState)}</div>
                    <div className="text-muted-foreground">{progress == null ? "-" : `进度 ${progress}%`}</div>
                    <div className="text-muted-foreground">{taskId ? `${taskId}` : "-"} {taskName ? `· ${taskName}` : ""}</div>
                    <div className="text-muted-foreground">上报：{fmtTime(occurredAt)}</div>
                    <div className="text-muted-foreground">当前托盘：{trayNow == null || trayNow === 255 ? "-" : `Tray ${trayNow}`}</div>
                    <div className="text-muted-foreground">
                      当前耗材：{currentTray ? `${currentMaterial} · ${currentColor}${currentOfficial ? "（拓竹）" : ""}` : "-"}
                    </div>
                    <div className="text-muted-foreground">
                      扣减库存：
                      {currentTray
                        ? currentColorHex && !currentColorName
                          ? "颜色未映射（先映射再匹配）"
                          : currentStock
                            ? `${currentStock.brand}（剩余 ${currentStock.remaining_grams}g）`
                            : currentCandidates.length > 1
                              ? "多品牌冲突（打印后归因）"
                              : "未匹配库存项"
                        : "-"}
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="text-sm text-muted-foreground">AMS 托盘信息（材质/颜色/剩余）。系统会尝试匹配到唯一库存项；匹配不到会在作业里提示归因。</div>
                <div className="overflow-auto rounded-md border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr className="text-left">
                        <th className="px-3 py-2">Tray</th>
                        <th className="px-3 py-2">材质</th>
                        <th className="px-3 py-2">颜色</th>
                        <th className="px-3 py-2">remain(%)</th>
                        <th className="px-3 py-2">来源</th>
                        <th className="px-3 py-2">库存匹配</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayTrays.map((t) => {
                        const trayId = t?.id;
                        if (trayId == null) return null;
                        const key = `${p.id}:${trayId}`;
                        const isActiveTray = trayNow != null && trayNow !== 255 && Number(trayNow) === Number(trayId);
                        const isMissing = Boolean(t?.__missing);
                        const pct = normalizeRemainPct(t?.remain);
                        const material = isMissing ? "-" : t?.type || "-";
                        const colorHex = isMissing ? null : normalizeColorHex(t?.color);
                        const mappedName = colorHex ? colorMappings[colorHex] || null : null;
                        const colorKey = mappedName || (!colorHex && !isMissing && typeof t?.color === "string" ? t.color : null);
                        const colorDisplay = isMissing ? "-" : mappedName ? `${mappedName} (${colorHex})` : colorHex || t?.color || "-";
                        const official = !isMissing && isOfficialTray(t);
                        const candidates = stocks.filter(
                          (s) =>
                            s.material === material &&
                            (colorKey ? s.color === colorKey : false) &&
                            (official ? s.brand === "拓竹" : s.brand !== "拓竹")
                        );
                        const matched = candidates.length === 1 ? candidates[0] : null;
                        const matchText =
                          isMissing
                            ? "-"
                            : colorHex && !mappedName
                            ? "颜色未映射（先映射）"
                            : matched
                              ? `${matched.brand}（剩余 ${matched.remaining_grams}g）`
                              : candidates.length > 1
                                ? `多品牌冲突：${candidates.map((c) => c.brand).join(" / ")}（打印后归因）`
                                : "未匹配（去库存新增）";
                        return (
                          <tr key={key} className={`border-t ${isActiveTray ? "bg-accent/30" : ""}`}>
                            <td className="px-3 py-2 font-medium">
                              Tray {trayId} {isActiveTray ? <span className="ml-2 text-xs text-muted-foreground">(正在使用)</span> : null}
                            </td>
                            <td className="px-3 py-2">{material}</td>
                            <td className="px-3 py-2">
                              <div>{colorDisplay}</div>
                              {colorHex && !mappedName && !isMissing ? (
                                <div className="mt-2 flex items-center gap-2">
                                  <Input
                                    className="h-8"
                                    placeholder="映射为：白色/灰色/…"
                                    value={colorDraftByHex[colorHex] || ""}
                                    onChange={(e) =>
                                      setColorDraftByHex((prev) => ({ ...prev, [colorHex]: e.target.value }))
                                    }
                                  />
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    disabled={savingColorHex === colorHex}
                                    onClick={() => saveColorMapping(colorHex)}
                                  >
                                    {savingColorHex === colorHex ? "保存中…" : "保存"}
                                  </Button>
                                </div>
                              ) : null}
                            </td>
                            <td className="px-3 py-2">{isMissing ? "-" : pct == null ? (t?.remain == null ? "-" : t.remain) : `${Math.round(pct)}%`}</td>
                            <td className="px-3 py-2">{isMissing ? "空槽/未上报" : official ? "拓竹" : "第三方/未知"}</td>
                            <td className="px-3 py-2">{matchText}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          );
        })}
        {items.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">暂无打印机，请先添加。</CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}


