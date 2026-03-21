"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  History,
  Brain,
  Activity,
  Settings,
  Menu,
  X,
} from "lucide-react";
import { useDashboardStore } from "@/lib/store";

const links = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/positions/", label: "포지션", icon: Briefcase },
  { href: "/trades/", label: "거래내역", icon: History },
  { href: "/strategies/", label: "전략", icon: Brain },
  { href: "/regime/", label: "시장레짐", icon: Activity },
  { href: "/settings/", label: "설정", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useDashboardStore();

  return (
    <>
      <button
        onClick={toggleSidebar}
        className="fixed top-4 left-4 z-50 rounded-lg bg-zinc-800 p-2 text-zinc-300 lg:hidden"
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={toggleSidebar}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 border-r border-zinc-800 bg-zinc-950 transition-transform lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex h-16 items-center gap-2 border-b border-zinc-800 px-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-cyan-400">
            <span className="text-[11px] font-black leading-none tracking-tight text-zinc-900">
              IW
            </span>
          </div>
          <span className="text-lg font-bold text-zinc-100">IWCoin</span>
        </div>

        <nav className="mt-4 flex flex-col gap-1 px-3">
          {links.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname === href.slice(0, -1);
            return (
              <Link
                key={href}
                href={href}
                onClick={() => sidebarOpen && toggleSidebar()}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
                }`}
              >
                <Icon size={18} />
                {label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
