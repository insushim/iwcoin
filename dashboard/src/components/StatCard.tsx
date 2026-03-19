"use client";

import type { ReactNode } from "react";

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon?: ReactNode;
  trend?: "up" | "down" | "neutral";
}

export default function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
}: StatCardProps) {
  const trendColor =
    trend === "up"
      ? "text-emerald-400"
      : trend === "down"
        ? "text-red-400"
        : "text-zinc-400";

  const borderGlow =
    trend === "up"
      ? "border-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.08)]"
      : trend === "down"
        ? "border-red-500/20 shadow-[0_0_15px_rgba(239,68,68,0.08)]"
        : "border-zinc-800/80";

  return (
    <div
      className={`rounded-2xl border bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5 backdrop-blur ${borderGlow}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          {title}
        </p>
        {icon && (
          <div className="rounded-lg bg-zinc-800/60 p-2 text-zinc-400">
            {icon}
          </div>
        )}
      </div>
      <p className={`mt-3 text-3xl font-bold tracking-tight ${trendColor}`}>
        {value}
      </p>
      {subtitle && (
        <p className={`mt-1 text-sm font-medium ${trendColor}`}>{subtitle}</p>
      )}
    </div>
  );
}
