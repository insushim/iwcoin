"use client";

import { useDashboardStore } from "@/lib/store";
import { TrendingUp, Pause, Play } from "lucide-react";

export default function StrategiesPage() {
  const { strategies } = useDashboardStore();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Strategies</h1>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {strategies.map((s) => (
          <div
            key={s.id}
            className={`rounded-xl border bg-zinc-900/60 p-5 transition-colors ${
              s.status === "active"
                ? "border-zinc-700"
                : "border-zinc-800 opacity-70"
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
                {s.status.toUpperCase()}
              </span>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">Win Rate</p>
                <p className="text-lg font-bold text-zinc-200">{s.win_rate}%</p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Total P/L</p>
                <p
                  className={`text-lg font-bold ${s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                >
                  {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Sharpe Ratio</p>
                <p className="text-lg font-bold text-zinc-200">
                  {s.sharpe_ratio.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">Total Trades</p>
                <p className="text-lg font-bold text-zinc-200">
                  {s.total_trades}
                </p>
              </div>
            </div>

            {/* Win rate bar */}
            <div className="mt-4">
              <div className="flex justify-between text-xs text-zinc-500">
                <span>Performance</span>
                <span>{s.allocation_pct}% allocation</span>
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
