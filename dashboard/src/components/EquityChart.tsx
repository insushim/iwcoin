"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";
import type { EquityPoint } from "@/lib/supabase";

const ResponsiveContainer = dynamic(
  () => import("recharts").then((m) => m.ResponsiveContainer),
  { ssr: false },
);
const AreaChart = dynamic(() => import("recharts").then((m) => m.AreaChart), {
  ssr: false,
});
const Area = dynamic(() => import("recharts").then((m) => m.Area), {
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

interface Props {
  data: EquityPoint[];
}

export default function EquityChart({ data }: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="mb-4 text-sm font-medium text-zinc-400">Equity Curve</h3>
        <div className="h-[300px] animate-pulse rounded-lg bg-zinc-800/50" />
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-400">Equity Curve</h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#71717a" }}
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            domain={["dataMin - 2000", "dataMax + 2000"]}
          />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 8,
            }}
            labelStyle={{ color: "#a1a1aa" }}
            formatter={(v) => [`$${Number(v).toFixed(2)}`, "Equity"]}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="#10b981"
            strokeWidth={2}
            fill="url(#eqGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
