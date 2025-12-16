export default function Page() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">配置入口（逐步补齐）。</p>
      </div>

      <div className="rounded-md border p-4">
        <div className="font-medium">颜色映射</div>
        <div className="mt-1 text-sm text-muted-foreground">
          将 AMS 颜色码（如 FFFFFF/FFFFFFFF）映射成“白色/灰色”等，用于库存匹配与自动扣减。
        </div>
        <div className="mt-3">
          <a className="text-sm font-medium underline underline-offset-4" href="/settings/color-mappings">
            去管理颜色映射
          </a>
        </div>
      </div>
    </div>
  );
}


