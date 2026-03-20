"use client";

import { useState, useEffect, useMemo } from "react";
import { useDashboardStore } from "@/lib/store";
import {
  Play,
  Square,
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Zap,
  Clock,
} from "lucide-react";

export default function StrategiesPage() {
  const {
    account,
    isAutoTrading,
    toggleAutoTrading,
    performanceStats,
    recentSignals,
  } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const trades = account.trade_history;

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
      id: "regime",
      name: "레짐 적응형",
      description:
        "시장 레짐(강세/약세/횡보)에 따라 MACD, RSI, 볼린저밴드를 복합 활용",
    },
    {
      id: "macd",
      name: "MACD 크로스",
      description: "MACD 라인과 시그널 라인 교차로 추세 전환 포착",
    },
    {
      id: "bollinger",
      name: "볼린저 밴드",
      description: "상/하단 밴드 이탈 시 평균회귀 매매 신호 생성",
    },
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

  // Check if a strategy has recent signals (within last 5 min)
  const activeStrategyNames = new Set(
    recentSignals
      .filter((s) => Date.now() - s.timestamp < 300_000)
      .map((s) => s.strategy),
  );

  const ps = performanceStats;

  return (
    <div className="space-y-6">
      {/* Header */}
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

      {/* Performance Stats */}
      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
          <BarChart3 size={16} /> 성과 통계
        </h3>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div>
            <p className="text-xs text-zinc-500">총 거래</p>
            <p className="text-lg font-bold text-zinc-200">{ps.total_trades}</p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">승률</p>
            <p className="text-lg font-bold text-zinc-200">
              {(ps.win_rate * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">수익 팩터</p>
            <p
              className={`text-lg font-bold ${ps.profit_factor >= 1 ? "text-emerald-400" : "text-red-400"}`}
            >
              {ps.profit_factor === Infinity
                ? "-"
                : ps.profit_factor.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">샤프 비율</p>
            <p
              className={`text-lg font-bold ${ps.sharpe_ratio >= 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              {ps.sharpe_ratio.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">최대 낙폭</p>
            <p className="text-lg font-bold text-red-400">
              {(ps.max_drawdown_pct * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">총 손익</p>
            <p
              className={`text-lg font-bold ${ps.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              {ps.total_pnl >= 0 ? "+" : ""}${ps.total_pnl.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">총 수수료</p>
            <p className="text-lg font-bold text-zinc-400">
              ${ps.total_fees.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">최고 거래</p>
            <p className="text-lg font-bold text-emerald-400">
              {ps.best_trade > 0 ? "+" : ""}${ps.best_trade.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">최악 거래</p>
            <p className="text-lg font-bold text-red-400">
              ${ps.worst_trade.toFixed(2)}
            </p>
          </div>
          <div>
            <p className="text-xs text-zinc-500">평균 승/패</p>
            <p className="text-sm font-bold text-zinc-200">
              <span className="text-emerald-400">
                +${ps.avg_win.toFixed(2)}
              </span>{" "}
              / <span className="text-red-400">${ps.avg_loss.toFixed(2)}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Strategy Cards */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        {strategies.map((s) => {
          const stats = strategyStats.find((st) => st.name === s.name);
          const isAuto = s.id !== "manual";
          const isActive = activeStrategyNames.has(s.name);

          return (
            <div
              key={s.id}
              className={`rounded-2xl border bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 transition-colors ${
                isAuto && isAutoTrading && isActive
                  ? "border-emerald-500/30 shadow-[0_0_20px_rgba(16,185,129,0.08)]"
                  : isAuto && isAutoTrading
                    ? "border-emerald-500/10"
                    : "border-zinc-800/80"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="flex items-center gap-2 text-lg font-semibold text-zinc-100">
                    {s.name}
                    {isAuto && isAutoTrading && isActive && (
                      <span className="relative flex h-2.5 w-2.5">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                      </span>
                    )}
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
                      <Zap size={12} /> 실행중
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

      {/* Recent Signals */}
      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
          <Activity size={16} /> 최근 신호
        </h3>
        {recentSignals.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-600">
            {isAutoTrading
              ? "자동매매가 실행 중입니다. 신호를 기다리는 중..."
              : "자동매매를 시작하면 전략 신호가 여기에 표시됩니다."}
          </p>
        ) : (
          <div className="mt-4 space-y-2">
            {[...recentSignals]
              .reverse()
              .slice(0, 15)
              .map((signal, i) => (
                <div
                  key={`${signal.timestamp}-${i}`}
                  className="flex items-center gap-3 rounded-xl bg-zinc-800/50 px-4 py-3"
                >
                  <div className="flex-shrink-0">
                    {signal.side === "long" ? (
                      <TrendingUp size={16} className="text-emerald-400" />
                    ) : (
                      <TrendingDown size={16} className="text-red-400" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-zinc-200">
                        {signal.symbol}
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                          signal.side === "long"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : "bg-red-500/15 text-red-400"
                        }`}
                      >
                        {signal.side}
                      </span>
                      <span className="rounded bg-zinc-700/50 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        {signal.strategy}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-zinc-500">
                      {signal.reason}
                    </p>
                  </div>
                  <div className="flex-shrink-0 text-right">
                    <p className="text-sm font-bold text-zinc-300">
                      {signal.confidence}%
                    </p>
                    <p className="flex items-center gap-1 text-[10px] text-zinc-600">
                      <Clock size={10} />
                      {new Date(signal.timestamp).toLocaleTimeString("ko-KR", {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </p>
                  </div>
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
