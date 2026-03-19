"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { useDashboardStore } from "@/lib/store";

export default function PositionsPage() {
  const { positions } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">오픈 포지션</h1>

      <div className="overflow-x-auto rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-3">종목</th>
              <th className="px-4 py-3">방향</th>
              <th className="px-4 py-3">전략</th>
              <th className="px-4 py-3 text-right">진입가</th>
              <th className="px-4 py-3 text-right">현재가</th>
              <th className="px-4 py-3 text-right">수량</th>
              <th className="px-4 py-3 text-right">미실현 손익</th>
              <th className="px-4 py-3 text-right">손절가</th>
              <th className="px-4 py-3 text-right">익절가</th>
              <th className="px-4 py-3">진입시간</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const pnlPct =
                ((p.current_price - p.entry_price) / p.entry_price) *
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
                    ${p.current_price.toLocaleString("en-US")}
                  </td>
                  <td className="px-4 py-3 text-right text-zinc-300">
                    {p.quantity}
                  </td>
                  <td
                    className={`px-4 py-3 text-right font-semibold ${p.unrealized_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {p.unrealized_pnl >= 0 ? "+" : ""}$
                    {p.unrealized_pnl.toFixed(2)}
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
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
