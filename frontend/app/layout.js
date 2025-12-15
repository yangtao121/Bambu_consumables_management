export const metadata = {
  title: "耗材管理系统",
  description: "拓竹耗材管理系统（LAN MQTT）"
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body style={{ fontFamily: "ui-sans-serif, system-ui", margin: 0 }}>
        <div style={{ display: "flex", minHeight: "100vh" }}>
          <nav
            style={{
              width: 240,
              padding: 16,
              borderRight: "1px solid #e5e7eb",
              background: "#fafafa"
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: 12 }}>耗材管理</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <a href="/" style={{ color: "#111827", textDecoration: "none" }}>
                Dashboard
              </a>
              <a
                href="/printers"
                style={{ color: "#111827", textDecoration: "none" }}
              >
                Printers
              </a>
              <a
                href="/spools"
                style={{ color: "#111827", textDecoration: "none" }}
              >
                Spools
              </a>
              <a
                href="/jobs"
                style={{ color: "#111827", textDecoration: "none" }}
              >
                Jobs
              </a>
              <a
                href="/reports"
                style={{ color: "#111827", textDecoration: "none" }}
              >
                Reports
              </a>
              <a
                href="/settings"
                style={{ color: "#111827", textDecoration: "none" }}
              >
                Settings
              </a>
            </div>
          </nav>
          <main style={{ flex: 1, padding: 20 }}>{children}</main>
        </div>
      </body>
    </html>
  );
}


