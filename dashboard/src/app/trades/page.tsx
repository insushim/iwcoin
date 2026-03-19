"use client";

import { useState, useEffect, useMemo } from "react";
import { useDashboardStore } from "@/lib/store";
import TradeTable from "@/components/TradeTable";

export default function TradesPage() {
  const { trades } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  useEffect(() => setMounted(true), []);

  const symbols = useMemo(
    () => [...new Set(trades.map((t) => t.symbol))],
    [trades],
  );
  const strategies = useMemo(
    () => [...new Set(trades.map((t) => t.strategy))],
    [trades],
  );

  const filtered = useMemo(() => {
    return trades.filter((t) => {
      if (symbolFilter && t.symbol !== symbolFilter) return false;
      if (strategyFilter && t.strategy !== strategyFilter) return false;
      return true;
    });
  }, [trades, symbolFilter, strategyFilter]);

  const totalPnl = filtered.reduce((s, t) => s + (t.pnl ?? 0), 0);

  if (!mounted) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">거래 내역</h1>
        <p
          className={`text-lg font-semibold ${totalPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
        >
          합계: {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <select
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
        >
          <option value="">전체 종목</option>
          {symbols.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={strategyFilter}
          onChange={(e) => setStrategyFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
        >
          <option value="">전체 전략</option>
          {strategies.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        {(symbolFilter || strategyFilter) && (
          <button
            onClick={() => {
              setSymbolFilter("");
              setStrategyFilter("");
            }}
            className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          >
            필터 초기화
          </button>
        )}
      </div>

      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <TradeTable trades={filtered} />
      </div>
    </div>
  );
}
