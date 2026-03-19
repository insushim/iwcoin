"use client";

import dynamic from "next/dynamic";
import { useState, useEffect } from "react";

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
  data: { date: string; price?: number; equity?: number }[];
  dataKey?: string;
  title?: string;
  color?: string;
  formatValue?: (v: number) => string;
}

export default function EquityChart({
  data,
  dataKey = "equity",
  title = "자산 곡선",
  color = "#10b981",
  formatValue,
}: Props) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const fmt =
    formatValue ??
    ((v: number) =>
      `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`);

  if (!mounted || data.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
        <h3 className="mb-4 text-sm font-medium text-zinc-400">{title}</h3>
        <div className="h-[300px] animate-pulse rounded-lg bg-zinc-800/50" />
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
      <h3 className="mb-4 text-sm font-medium text-zinc-400">{title}</h3>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id={`grad_${dataKey}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.4} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
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
            tickFormatter={(v: number) => fmt(v)}
            domain={["dataMin * 0.99", "dataMax * 1.01"]}
          />
          <Tooltip
            contentStyle={{
              background: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: 8,
            }}
            labelStyle={{ color: "#a1a1aa" }}
            formatter={(v) => [fmt(Number(v)), title]}
          />
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={2}
            fill={`url(#grad_${dataKey})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
