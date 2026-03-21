"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { DollarSign, TrendingUp, Layers } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import StatCard from "@/components/StatCard";
import TradeModal from "@/components/TradeModal";
import { PaperTradingEngine } from "@/lib/paper-trading";

function fmt(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export default function PositionsPage() {
  const { account, prices, closePosition } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  const [tradeOpen, setTradeOpen] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const engine = new PaperTradingEngine();
  const priceMap: Record<string, number> = {};
  for (const p of prices) priceMap[p.symbol] = p.price;

  const totalEquity = engine.getTotalEquity();
  const dailyPnl = totalEquity - account.initial_balance;
  const dailyPnlPct =
    account.initial_balance > 0
      ? (dailyPnl / account.initial_balance) * 100
      : 0;
  const totalUnrealizedPnl = account.positions.reduce((sum, pos) => {
    return sum + engine.getUnrealizedPnl(pos);
  }, 0);

  return (
    <div className="space-y-6">
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

      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">오픈 포지션</h1>
        <button
          onClick={() => setTradeOpen(true)}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 transition-colors"
        >
          포지션 열기
        </button>
      </div>

      {account.positions.length === 0 ? (
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-12 text-center">
          <p className="text-zinc-500">오픈 포지션이 없습니다</p>
          <button
            onClick={() => setTradeOpen(true)}
            className="mt-3 rounded-lg bg-zinc-800 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-700"
          >
            첫 포지션 열기
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                <th className="px-4 py-3">종목</th>
                <th className="px-4 py-3">방향</th>
                <th className="px-4 py-3">전략</th>
                <th className="px-4 py-3 text-right">진입가</th>
                <th className="px-4 py-3 text-right">현재가</th>
                <th className="px-4 py-3 text-right">수량 (USDT)</th>
                <th className="px-4 py-3 text-right">미실현 손익</th>
                <th className="px-4 py-3 text-right">손절가</th>
                <th className="px-4 py-3 text-right">익절가</th>
                <th className="px-4 py-3">진입시간</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {account.positions.map((p) => {
                const currentPrice = priceMap[p.symbol] ?? p.current_price;
                const unrealizedPnl = engine.getUnrealizedPnl({
                  ...p,
                  current_price: currentPrice,
                });
                const pnlPct =
                  ((currentPrice - p.entry_price) / p.entry_price) *
                  100 *
                  (p.side === "short" ? -1 : 1);

                return (
                  <tr
                    key={p.id}
                    className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-zinc-200">
                      {p.symbol}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-semibold ${p.side === "long" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}
                      >
                        {p.side === "long" ? "롱" : "숏"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-zinc-400">{p.strategy}</td>
                    <td className="px-4 py-3 text-right text-zinc-300">
                      ${p.entry_price.toLocaleString("en-US")}
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-200">
                      $
                      {currentPrice.toLocaleString("en-US", {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                    <td className="px-4 py-3 text-right text-zinc-300">
                      ${p.quantity.toLocaleString("en-US")}
                    </td>
                    <td
                      className={`px-4 py-3 text-right font-semibold ${unrealizedPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                    >
                      {unrealizedPnl >= 0 ? "+" : ""}${unrealizedPnl.toFixed(2)}
                      <span className="ml-1 text-xs opacity-70">
                        ({pnlPct >= 0 ? "+" : ""}
                        {pnlPct.toFixed(2)}%)
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-orange-400">
                      ${p.stop_loss.toLocaleString("en-US")}
                    </td>
                    <td className="px-4 py-3 text-right text-cyan-400">
                      ${p.take_profit.toLocaleString("en-US")}
                    </td>
                    <td className="px-4 py-3 text-zinc-500">
                      {format(new Date(p.opened_at), "MM/dd HH:mm")}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => closePosition(p.id, currentPrice)}
                        className="rounded bg-red-600/20 px-3 py-1 text-xs font-semibold text-red-400 hover:bg-red-600/30 transition-colors"
                      >
                        청산
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <TradeModal open={tradeOpen} onClose={() => setTradeOpen(false)} />
    </div>
  );
}
