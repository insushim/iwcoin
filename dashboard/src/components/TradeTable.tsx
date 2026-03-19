"use client";

import { format } from "date-fns";
import type { Trade } from "@/lib/supabase";

interface Props {
  trades: Trade[];
  compact?: boolean;
}

export default function TradeTable({ trades, compact }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-3 py-3">종목</th>
            <th className="px-3 py-3">방향</th>
            <th className="px-3 py-3">전략</th>
            <th className="px-3 py-3 text-right">진입가</th>
            <th className="px-3 py-3 text-right">청산가</th>
            <th className="px-3 py-3 text-right">손익</th>
            {!compact && <th className="px-3 py-3">청산시간</th>}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr
              key={t.id}
              className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
            >
              <td className="px-3 py-2.5 font-medium text-zinc-200">
                {t.symbol}
              </td>
              <td className="px-3 py-2.5">
                <span
                  className={`rounded px-1.5 py-0.5 text-xs font-semibold ${t.side === "long" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}
                >
                  {t.side === "long" ? "롱" : "숏"}
                </span>
              </td>
              <td className="px-3 py-2.5 text-zinc-400">{t.strategy}</td>
              <td className="px-3 py-2.5 text-right text-zinc-300">
                ${t.entry_price.toLocaleString("en-US")}
              </td>
              <td className="px-3 py-2.5 text-right text-zinc-300">
                {t.exit_price
                  ? `$${t.exit_price.toLocaleString("en-US")}`
                  : "—"}
              </td>
              <td
                className={`px-3 py-2.5 text-right font-semibold ${(t.pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}
              >
                {(t.pnl ?? 0) >= 0 ? "+" : ""}${(t.pnl ?? 0).toFixed(2)}
              </td>
              {!compact && (
                <td className="px-3 py-2.5 text-zinc-500">
                  {t.closed_at
                    ? format(new Date(t.closed_at), "MM/dd HH:mm")
                    : "—"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
