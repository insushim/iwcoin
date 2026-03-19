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
const PieChart = dynamic(() => import("recharts").then((m) => m.PieChart), {
  ssr: false,
});
const Pie = dynamic(() => import("recharts").then((m) => m.Pie), {
  ssr: false,
});
const Cell = dynamic(() => import("recharts").then((m) => m.Cell), {
  ssr: false,
});

const REGIME_COLORS = { bull: "#10b981", bear: "#ef4444", sideways: "#eab308" };

export default function RegimePage() {
  const { summary, regimeHistory, strategies } = useDashboardStore();
  const current = summary.current_regime;
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const pieData = strategies
    .filter((s) => s.status === "active")
    .map((s) => ({ name: s.name, value: s.allocation_pct }));
  const PIE_COLORS = ["#10b981", "#06b6d4", "#8b5cf6", "#f59e0b", "#ec4899"];

  if (!mounted) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold">시장 레짐</h1>
        <RegimeIndicator
          regime={current.regime}
          fearGreed={current.fear_greed_index}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">BTC 도미넌스</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            {current.btc_dominance.toFixed(1)}%
          </p>
        </div>
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">변동성 지수</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            {current.volatility.toFixed(1)}
          </p>
        </div>
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <p className="text-xs text-zinc-500">공포·탐욕 지수</p>
          <p className="mt-1 text-2xl font-bold text-zinc-200">
            {current.fear_greed_index}
          </p>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full"
              style={{
                width: `${current.fear_greed_index}%`,
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

      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="mb-4 text-sm font-medium text-zinc-400">
          공포·탐욕 히스토리
        </h3>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={regimeHistory}>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
            <XAxis
              dataKey="timestamp"
              tick={{ fontSize: 11, fill: "#71717a" }}
              tickFormatter={(v: string) => v.slice(5, 10)}
            />
            <YAxis tick={{ fontSize: 11, fill: "#71717a" }} domain={[0, 100]} />
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
              dataKey="fear_greed_index"
              stroke="#eab308"
              strokeWidth={2}
              dot={false}
              name="공포·탐욕"
            />
            <Line
              type="monotone"
              dataKey="volatility"
              stroke="#8b5cf6"
              strokeWidth={1.5}
              dot={false}
              name="변동성"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">
            레짐 히스토리
          </h3>
          <div className="space-y-2">
            {regimeHistory.slice(-14).map((r) => (
              <div key={r.id} className="flex items-center gap-3">
                <span className="w-20 text-xs text-zinc-500">
                  {r.timestamp.slice(5, 10)}
                </span>
                <span
                  className="h-4 rounded"
                  style={{
                    backgroundColor: REGIME_COLORS[r.regime],
                    width: "100%",
                    opacity: 0.6,
                  }}
                />
                <span className="w-20 text-right text-xs text-zinc-400">
                  {r.regime === "bull"
                    ? "상승"
                    : r.regime === "bear"
                      ? "하락"
                      : "횡보"}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="mb-4 text-sm font-medium text-zinc-400">전략 배분</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={90}
                label={({ name, value }: { name?: string; value?: number }) =>
                  `${name ?? ""} ${value ?? 0}%`
                }
              >
                {pieData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: 8,
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
