"use client";

import { useState, useEffect } from "react";
import { DollarSign, TrendingUp, Layers, Play, Square } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import StatCard from "@/components/StatCard";
import RegimeIndicator from "@/components/RegimeIndicator";
import EquityChart from "@/components/EquityChart";
import TradeTable from "@/components/TradeTable";
import TradeModal from "@/components/TradeModal";
import { PaperTradingEngine } from "@/lib/paper-trading";

function fmt(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export default function DashboardPage() {
  const {
    prices,
    account,
    equityHistory,
    btcChart,
    regime,
    fearGreed,
    isAutoTrading,
    toggleAutoTrading,
    loading,
    error,
  } = useDashboardStore();

  const [mounted, setMounted] = useState(false);
  const [tradeOpen, setTradeOpen] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const engine = new PaperTradingEngine();
  const totalEquity = engine.getTotalEquity();
  const dailyPnl = totalEquity - account.initial_balance;
  const dailyPnlPct =
    account.initial_balance > 0
      ? (dailyPnl / account.initial_balance) * 100
      : 0;

  const totalUnrealizedPnl = account.positions.reduce((sum, pos) => {
    return sum + engine.getUnrealizedPnl(pos);
  }, 0);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-32 animate-pulse rounded-2xl bg-zinc-800/50"
            />
          ))}
        </div>
        <div className="h-[340px] animate-pulse rounded-2xl bg-zinc-800/50" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <div className="rounded-2xl border border-red-500/20 bg-red-500/5 p-6 text-center">
          <p className="text-red-400">{error}</p>
          <button
            onClick={() => useDashboardStore.getState().initialize()}
            className="mt-3 rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700"
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <div className="flex items-center gap-3">
          <RegimeIndicator regime={regime.regime} fearGreed={fearGreed.value} />
          <button
            onClick={toggleAutoTrading}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
              isAutoTrading
                ? "bg-red-600/20 text-red-400 hover:bg-red-600/30"
                : "bg-emerald-600/20 text-emerald-400 hover:bg-emerald-600/30"
            }`}
          >
            {isAutoTrading ? <Square size={14} /> : <Play size={14} />}
            {isAutoTrading ? "자동매매 중지" : "자동매매 시작"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="총 자산"
          value={`$${fmt(totalEquity)}`}
          icon={<DollarSign size={18} />}
          trend="neutral"
        />
        <StatCard
          title="총 손익"
          value={`${dailyPnl >= 0 ? "+" : ""}$${fmt(dailyPnl)}`}
          subtitle={`${dailyPnlPct >= 0 ? "+" : ""}${dailyPnlPct.toFixed(2)}%`}
          icon={<TrendingUp size={18} />}
          trend={dailyPnl >= 0 ? "up" : "down"}
        />
        <StatCard
          title="오픈 포지션"
          value={String(account.positions.length)}
          subtitle={`미실현: ${totalUnrealizedPnl >= 0 ? "+" : ""}$${fmt(totalUnrealizedPnl)}`}
          icon={<Layers size={18} />}
          trend={totalUnrealizedPnl >= 0 ? "up" : "down"}
        />
        <StatCard
          title="잔액"
          value={`$${fmt(account.balance)}`}
          subtitle={`초기: $${fmt(account.initial_balance)}`}
          icon={<DollarSign size={18} />}
          trend="neutral"
        />
      </div>

      <EquityChart
        data={btcChart}
        dataKey="price"
        title="BTC 가격 (90일)"
        color="#f59e0b"
        formatValue={(v) => `$${(v / 1000).toFixed(1)}k`}
      />

      {equityHistory.length > 0 && (
        <EquityChart
          data={equityHistory}
          dataKey="equity"
          title="자산 곡선"
          color="#10b981"
        />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            실시간 가격
          </h3>
          <div className="space-y-3">
            {prices.map((p) => (
              <div key={p.symbol} className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-zinc-200">
                    {p.symbol}
                  </p>
                  <p className="text-xs text-zinc-500">
                    거래량: ${(p.volume24h / 1e9).toFixed(2)}B
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-zinc-200">
                    $
                    {p.price.toLocaleString("en-US", {
                      maximumFractionDigits: 2,
                    })}
                  </p>
                  <p
                    className={`text-xs font-medium ${p.change24h >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {p.change24h >= 0 ? "+" : ""}
                    {p.change24h.toFixed(2)}%
                  </p>
                </div>
              </div>
            ))}
          </div>
          <button
            onClick={() => setTradeOpen(true)}
            className="mt-4 w-full rounded-lg bg-emerald-600/20 py-2 text-sm font-semibold text-emerald-400 hover:bg-emerald-600/30 transition-colors"
          >
            포지션 열기
          </button>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 lg:col-span-2">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">최근 거래</h3>
          <TradeTable
            trades={account.trade_history.slice(-8).reverse()}
            compact
          />
        </div>
      </div>

      <TradeModal open={tradeOpen} onClose={() => setTradeOpen(false)} />
    </div>
  );
}
