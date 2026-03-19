"use client";

import { useState, useEffect } from "react";
import { useDashboardStore } from "@/lib/store";
import { Pause, Play } from "lucide-react";

export default function StrategiesPage() {
  const { strategies } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">전략 관리</h1>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {strategies.map((s) => (
          <div
            key={s.id}
            className={`rounded-2xl border bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 transition-colors ${
              s.status === "active"
                ? "border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.06)]"
                : "border-zinc-800/80 opacity-70"
            }`}
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-zinc-100">
                  {s.name}
                </h3>
                <p className="mt-1 text-xs text-zinc-500">{s.description}</p>
              </div>
              <span
                className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${
                  s.status === "active"
                    ? "bg-emerald-500/15 text-emerald-400"
                    : "bg-zinc-700/50 text-zinc-400"
                }`}
              >
                {s.status === "active" ? (
                  <Play size={12} />
                ) : (
                  <Pause size={12} />
                )}
                {s.status === "active" ? "활성" : "일시정지"}
              </span>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">승률</p>
                <p className="text-lg font-bold text-zinc-200">{s.win_rate}%</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">총 손익</p>
                <p
                  className={`text-lg font-bold ${s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                >
                  {s.total_pnl >= 0 ? "+" : ""}$
                  {s.total_pnl.toLocaleString("en-US")}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">샤프 비율</p>
                <p className="text-lg font-bold text-zinc-200">
                  {s.sharpe_ratio.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">총 거래</p>
                <p className="text-lg font-bold text-zinc-200">
                  {s.total_trades}
                </p>
              </div>
            </div>

            <div className="mt-4">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>성과</span>
                <span>배분 {s.allocation_pct}%</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400"
                  style={{ width: `${s.win_rate}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
