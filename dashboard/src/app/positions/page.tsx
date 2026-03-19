"use client";

import { format } from "date-fns";
import { useDashboardStore } from "@/lib/store";

export default function PositionsPage() {
  const { positions } = useDashboardStore();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Open Positions</h1>

      <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900/60">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Strategy</th>
              <th className="px-4 py-3 text-right">Entry</th>
              <th className="px-4 py-3 text-right">Current</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Unrealized P/L</th>
              <th className="px-4 py-3 text-right">Stop Loss</th>
              <th className="px-4 py-3 text-right">Take Profit</th>
              <th className="px-4 py-3">Opened</th>
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
                      {p.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{p.strategy}</td>
                  <td className="px-4 py-3 text-right text-zinc-300">
                    ${p.entry_price.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-zinc-200">
                    ${p.current_price.toLocaleString()}
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
                    ${p.stop_loss.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-cyan-400">
                    ${p.take_profit.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">
                    {format(new Date(p.opened_at), "MMM dd, HH:mm")}
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
