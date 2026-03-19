"use client";

import { useState, useEffect } from "react";
import { DollarSign, TrendingUp, Layers, Zap } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import StatCard from "@/components/StatCard";
import RegimeIndicator from "@/components/RegimeIndicator";
import EquityChart from "@/components/EquityChart";
import TradeTable from "@/components/TradeTable";

function fmt(n: number): string {
  return n.toLocaleString("en-US");
}

export default function DashboardPage() {
  const { summary, equity, trades, strategies } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <RegimeIndicator
          regime={summary.current_regime.regime}
          fearGreed={summary.current_regime.fear_greed_index}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="총 자산"
          value={`$${fmt(summary.total_balance)}`}
          icon={<DollarSign size={18} />}
          trend="neutral"
        />
        <StatCard
          title="일일 수익"
          value={`${summary.daily_pnl >= 0 ? "+" : ""}$${fmt(summary.daily_pnl)}`}
          subtitle={`${summary.daily_pnl_pct >= 0 ? "+" : ""}${summary.daily_pnl_pct}%`}
          icon={<TrendingUp size={18} />}
          trend={summary.daily_pnl >= 0 ? "up" : "down"}
        />
        <StatCard
          title="오픈 포지션"
          value={String(summary.open_positions)}
          icon={<Layers size={18} />}
          trend="neutral"
        />
        <StatCard
          title="활성 전략"
          value={String(summary.active_strategies)}
          icon={<Zap size={18} />}
          trend="neutral"
        />
      </div>

      <EquityChart data={equity} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">활성 전략</h3>
          <div className="space-y-3">
            {strategies
              .filter((s) => s.status === "active")
              .map((s) => (
                <div key={s.id} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {s.name}
                    </p>
                    <p className="text-xs text-zinc-500">승률: {s.win_rate}%</p>
                  </div>
                  <span
                    className={`text-sm font-semibold ${s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    +${fmt(s.total_pnl)}
                  </span>
                </div>
              ))}
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 lg:col-span-2">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">최근 거래</h3>
          <TradeTable trades={trades.slice(0, 8)} compact />
        </div>
      </div>
    </div>
  );
}
