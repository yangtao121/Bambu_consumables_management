"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "../lib/utils";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/printers", label: "Printers" },
  { href: "/spools", label: "Spools" },
  { href: "/jobs", label: "Jobs" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" }
];

function NavLink({ href, label }) {
  const pathname = usePathname() || "/";
  const active = pathname === href;
  return (
    <Link
      href={href}
      className={cn(
        "rounded-md px-3 py-2 text-sm transition-colors",
        active ? "bg-accent text-foreground font-medium" : "text-muted-foreground hover:bg-accent hover:text-foreground"
      )}
    >
      {label}
    </Link>
  );
}

export function AppShell({ children }) {
  return (
    <div className="min-h-screen">
      <div className="border-b bg-background">
        <div className="container flex h-14 items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="font-semibold tracking-tight">耗材管理</div>
            <div className="hidden md:flex items-center gap-1">
              {NAV.map((n) => (
                <NavLink key={n.href} href={n.href} label={n.label} />
              ))}
            </div>
          </div>
          <div className="text-xs text-muted-foreground">Docker / LAN MQTT</div>
        </div>
      </div>

      <main className="container py-6">{children}</main>
    </div>
  );
}

