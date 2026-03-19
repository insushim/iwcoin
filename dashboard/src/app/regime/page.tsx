"use client";

import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { useDashboardStore } from "@/lib/store";
import RegimeIndicator from "@/components/RegimeIndicator";

const ResponsiveContainer = dynamic(
  () => import("recharts").then((m) => m.ResponsiveContainer),
  { ssr: false },
);
const LineChart = dynamic(() => import("recharts").then((m) => m.LineChart), {
  ssr: false,
});
const Line = dynamic(() => import("recharts").then((m) => m.Line), {
  ssr: false,
});
const XAxis = dynamic(() => import("recharts").then((m) => m.XAxis), {
  ssr: false,
});
const YAxis = dynamic(() => import("recharts").then((m) => m.YAxis), {
  ssr: false,
});
const Tooltip = dynamic(() => import("recharts").then((m) => m.Tooltip), {
  ssr: false,
});
const CartesianGrid = dynamic(
  () => import("recharts").then((m) => m.CartesianGrid),
  { ssr: false },
);

const REGIME_COLORS = { bull: "#10b981", bear: "#ef4444", sideways: "#eab308" };

export default function RegimePage() {
  const {
    regime,
    fearGreed,
    fearGreedHistory,
    btcDominance,
    totalMarketCap,
    loading,
  } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) return null;

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">시장 레짐</h1>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-24 animate-pulse rounded-2xl bg-zinc-800/50"
            />
          ))}
        </div>
      </div>
    );
  }

  // Derive regime history from fear/greed history
  const regimeHistory = fearGreedHistory.map((item) => ({
    ...item,
    regime: item.value > 60 ? "bull" : item.value < 40 ? "bear" : "sideways",
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">시장 레짐</h1>
        <RegimeIndicator regime={regime.regime} fearGreed={fearGreed.value} />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">BTC 도미넌스</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            {btcDominance.toFixed(1)}%
          </p>
        </div>
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">전체 시가총액</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            ${(totalMarketCap / 1e12).toFixed(2)}T
          </p>
        </div>
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">공포/탐욕 지수</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            {fearGreed.value}
          </p>
          <p className="text-xs text-zinc-400">{fearGreed.classification}</p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full"
              style={{
                width: `${fearGreed.value}%`,
                background:
                  "linear-gradient(90deg, #ef4444 0%, #eab308 50%, #10b981 100%)",
              }}
            />
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-zinc-600">
            <span>극단적 공포</span>
            <span>극단적 탐욕</span>
          </div>
        </div>
      </div>

      {fearGreedHistory.length > 0 && (
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            공포/탐욕 히스토리 (30일)
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={fearGreedHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis
                dataKey="timestamp"
                tick={{ fontSize: 11, fill: "#71717a" }}
                tickFormatter={(v: string) => v.slice(5)}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#71717a" }}
                domain={[0, 100]}
              />
              <Tooltip
                contentStyle={{
                  background: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: 8,
                }}
                labelStyle={{ color: "#a1a1aa" }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#eab308"
                strokeWidth={2}
                dot={false}
                name="공포/탐욕"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="mb-4 text-sm font-medium text-zinc-400">
          레짐 히스토리
        </h3>
        {regimeHistory.length === 0 ? (
          <p className="text-sm text-zinc-500">데이터 로딩 중...</p>
        ) : (
          <div className="space-y-2">
            {regimeHistory.map((r, i) => (
              <div key={i} className="flex items-center gap-3">
                <span className="w-20 text-xs text-zinc-500">
                  {r.timestamp.slice(5)}
                </span>
                <span
                  className="h-4 rounded"
                  style={{
                    backgroundColor:
                      REGIME_COLORS[r.regime as keyof typeof REGIME_COLORS],
                    width: "100%",
                    opacity: 0.6,
                  }}
                />
                <span className="w-16 text-right text-xs text-zinc-400">
                  {r.value}
                </span>
                <span className="w-12 text-right text-xs text-zinc-400">
                  {r.regime === "bull"
                    ? "상승"
                    : r.regime === "bear"
                      ? "하락"
                      : "횡보"}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
