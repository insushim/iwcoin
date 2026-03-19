"use client";

import { DollarSign, TrendingUp, Layers, Zap } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import StatCard from "@/components/StatCard";
import RegimeIndicator from "@/components/RegimeIndicator";
import EquityChart from "@/components/EquityChart";
import TradeTable from "@/components/TradeTable";

export default function DashboardPage() {
  const { summary, equity, trades, strategies } = useDashboardStore();

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <RegimeIndicator
          regime={summary.current_regime.regime}
          fearGreed={summary.current_regime.fear_greed_index}
        />
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Balance"
          value={`$${summary.total_balance.toLocaleString()}`}
          icon={<DollarSign size={18} />}
          trend="neutral"
        />
        <StatCard
          title="Daily P/L"
          value={`${summary.daily_pnl >= 0 ? "+" : ""}$${summary.daily_pnl.toLocaleString()}`}
          subtitle={`${summary.daily_pnl_pct >= 0 ? "+" : ""}${summary.daily_pnl_pct}%`}
          icon={<TrendingUp size={18} />}
          trend={summary.daily_pnl >= 0 ? "up" : "down"}
        />
        <StatCard
          title="Open Positions"
          value={String(summary.open_positions)}
          icon={<Layers size={18} />}
          trend="neutral"
        />
        <StatCard
          title="Active Strategies"
          value={String(summary.active_strategies)}
          icon={<Zap size={18} />}
          trend="neutral"
        />
      </div>

      {/* Equity chart */}
      <EquityChart data={equity} />

      {/* Bottom row */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Active strategies */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Active Strategies
          </h3>
          <div className="space-y-3">
            {strategies
              .filter((s) => s.status === "active")
              .map((s) => (
                <div key={s.id} className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {s.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      Win rate: {s.win_rate}%
                    </p>
                  </div>
                  <span
                    className={`text-sm font-semibold ${s.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    +${s.total_pnl.toLocaleString()}
                  </span>
                </div>
              ))}
          </div>
        </div>

        {/* Recent trades */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 lg:col-span-2">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            Recent Trades
          </h3>
          <TradeTable trades={trades.slice(0, 8)} compact />
        </div>
      </div>
    </div>
  );
}
