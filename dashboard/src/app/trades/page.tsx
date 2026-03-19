"use client";

import { useState, useMemo } from "react";
import { useDashboardStore } from "@/lib/store";
import TradeTable from "@/components/TradeTable";

export default function TradesPage() {
  const { trades } = useDashboardStore();
  const [symbolFilter, setSymbolFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");

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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">Trade History</h1>
        <p
          className={`text-lg font-semibold ${totalPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
        >
          Total: {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
        >
          <option value="">All Symbols</option>
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
          <option value="">All Strategies</option>
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
            Clear Filters
          </button>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5">
        <TradeTable trades={filtered} />
      </div>
    </div>
  );
}
