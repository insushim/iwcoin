"use client";

interface Props {
  regime: "bull" | "bear" | "sideways";
  fearGreed: number;
}

const regimeConfig = {
  bull: {
    label: "상승장",
    color: "bg-emerald-500",
    textColor: "text-emerald-400",
    ring: "ring-emerald-500/30",
  },
  bear: {
    label: "하락장",
    color: "bg-red-500",
    textColor: "text-red-400",
    ring: "ring-red-500/30",
  },
  sideways: {
    label: "횡보장",
    color: "bg-yellow-500",
    textColor: "text-yellow-400",
    ring: "ring-yellow-500/30",
  },
};

export default function RegimeIndicator({ regime, fearGreed }: Props) {
  const cfg = regimeConfig[regime];

  return (
    <div className="flex items-center gap-4">
      <div
        className={`flex items-center gap-2 rounded-full ${cfg.ring} ring-2 px-4 py-1.5`}
      >
        <span
          className={`h-2.5 w-2.5 rounded-full ${cfg.color} animate-pulse`}
        />
        <span className={`text-sm font-bold tracking-wider ${cfg.textColor}`}>
          {cfg.label}
        </span>
      </div>
      <div className="text-sm text-zinc-400">
        공포/탐욕:{" "}
        <span className="font-semibold text-zinc-200">{fearGreed}</span>
      </div>
    </div>
  );
}
