"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import { COINS } from "@/lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function TradeModal({ open, onClose }: Props) {
  const { prices, openPosition } = useDashboardStore();
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [side, setSide] = useState<"long" | "short">("long");
  const [quantity, setQuantity] = useState("500");
  const [slPct, setSlPct] = useState("3");
  const [tpPct, setTpPct] = useState("6");

  if (!open) return null;

  const currentPrice = prices.find((p) => p.symbol === symbol)?.price ?? 0;
  const sl =
    side === "long"
      ? currentPrice * (1 - Number(slPct) / 100)
      : currentPrice * (1 + Number(slPct) / 100);
  const tp =
    side === "long"
      ? currentPrice * (1 + Number(tpPct) / 100)
      : currentPrice * (1 - Number(tpPct) / 100);

  const handleSubmit = () => {
    if (!currentPrice || !Number(quantity)) return;
    openPosition({
      symbol,
      side,
      quantity: Number(quantity),
      entry_price: currentPrice,
      stop_loss: +sl.toFixed(2),
      take_profit: +tp.toFixed(2),
      strategy: "수동 매매",
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-2xl border border-zinc-700 bg-zinc-900 p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold text-zinc-100">포지션 열기</h2>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-200"
          >
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-zinc-500">종목</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
            >
              {COINS.map((c) => (
                <option key={c.symbol} value={c.symbol}>
                  {c.symbol}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs text-zinc-500">현재가</label>
            <p className="text-lg font-bold text-zinc-200">
              $
              {currentPrice.toLocaleString("en-US", {
                maximumFractionDigits: 2,
              })}
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs text-zinc-500">방향</label>
            <div className="flex gap-2">
              <button
                onClick={() => setSide("long")}
                className={`flex-1 rounded-lg py-2 text-sm font-semibold transition-colors ${
                  side === "long"
                    ? "bg-emerald-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                롱 (매수)
              </button>
              <button
                onClick={() => setSide("short")}
                className={`flex-1 rounded-lg py-2 text-sm font-semibold transition-colors ${
                  side === "short"
                    ? "bg-red-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                }`}
              >
                숏 (매도)
              </button>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-zinc-500">
              주문 금액 (USDT)
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">
                손절 (%)
              </label>
              <input
                type="number"
                value={slPct}
                onChange={(e) => setSlPct(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
              <p className="mt-1 text-xs text-orange-400">
                ${sl.toLocaleString("en-US", { maximumFractionDigits: 2 })}
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">
                익절 (%)
              </label>
              <input
                type="number"
                value={tpPct}
                onChange={(e) => setTpPct(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
              <p className="mt-1 text-xs text-cyan-400">
                ${tp.toLocaleString("en-US", { maximumFractionDigits: 2 })}
              </p>
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!currentPrice || !Number(quantity)}
            className="w-full rounded-lg bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            주문 실행
          </button>
        </div>
      </div>
    </div>
  );
}
