"use client";

import { useState, useEffect, useMemo } from "react";
import { useDashboardStore } from "@/lib/store";
import { Play, Square } from "lucide-react";

export default function StrategiesPage() {
  const { account, isAutoTrading, toggleAutoTrading } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const trades = account.trade_history;

  // Group trades by strategy
  const strategyStats = useMemo(() => {
    const map = new Map<
      string,
      { wins: number; losses: number; totalPnl: number; count: number }
    >();
    for (const t of trades) {
      const s = map.get(t.strategy) || {
        wins: 0,
        losses: 0,
        totalPnl: 0,
        count: 0,
      };
      s.count++;
      s.totalPnl += t.pnl;
      if (t.pnl > 0) s.wins++;
      else s.losses++;
      map.set(t.strategy, s);
    }
    return Array.from(map.entries()).map(([name, stats]) => ({
      name,
      ...stats,
      winRate: stats.count > 0 ? (stats.wins / stats.count) * 100 : 0,
    }));
  }, [trades]);

  const strategies = [
    {
      id: "sma",
      name: "SMA 크로스오버",
      description: "단기/장기 이동평균선 교차 시 매매 신호 생성",
    },
    {
      id: "rsi_over",
      name: "RSI 과매도",
      description: "RSI 30 이하 과매도 구간에서 매수 신호",
    },
    {
      id: "rsi_under",
      name: "RSI 과매수",
      description: "RSI 70 이상 과매수 구간에서 매도 신호",
    },
    {
      id: "manual",
      name: "수동 매매",
      description: "사용자가 직접 진입/청산하는 수동 전략",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">전략 관리</h1>
        <button
          onClick={toggleAutoTrading}
          className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
            isAutoTrading
              ? "bg-red-600 text-white hover:bg-red-500"
              : "bg-emerald-600 text-white hover:bg-emerald-500"
          }`}
        >
          {isAutoTrading ? <Square size={16} /> : <Play size={16} />}
          {isAutoTrading ? "자동매매 중지" : "자동매매 시작"}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {strategies.map((s) => {
          const stats = strategyStats.find((st) => st.name === s.name);
          const isAuto = s.id !== "manual";

          return (
            <div
              key={s.id}
              className={`rounded-2xl border bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 transition-colors ${
                isAuto && isAutoTrading
                  ? "border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.06)]"
                  : "border-zinc-800/80"
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
                    isAuto && isAutoTrading
                      ? "bg-emerald-500/15 text-emerald-400"
                      : isAuto
                        ? "bg-zinc-700/50 text-zinc-400"
                        : "bg-blue-500/15 text-blue-400"
                  }`}
                >
                  {isAuto && isAutoTrading ? (
                    <>
                      <Play size={12} /> 실행중
                    </>
                  ) : isAuto ? (
                    <>
                      <Square size={12} /> 대기
                    </>
                  ) : (
                    "수동"
                  )}
                </span>
              </div>

              {stats ? (
                <div className="mt-5 grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-zinc-500">승률</p>
                    <p className="text-lg font-bold text-zinc-200">
                      {stats.winRate.toFixed(1)}%
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500">총 손익</p>
                    <p
                      className={`text-lg font-bold ${stats.totalPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
                    >
                      {stats.totalPnl >= 0 ? "+" : ""}$
                      {stats.totalPnl.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500">총 거래</p>
                    <p className="text-lg font-bold text-zinc-200">
                      {stats.count}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-zinc-500">승/패</p>
                    <p className="text-lg font-bold text-zinc-200">
                      {stats.wins}/{stats.losses}
                    </p>
                  </div>
                  <div className="col-span-2">
                    <div className="h-1.5 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400"
                        style={{ width: `${stats.winRate}%` }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <p className="mt-5 text-sm text-zinc-600">
                  아직 거래 기록이 없습니다
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
