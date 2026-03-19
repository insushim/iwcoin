"use client";

import { useState, useEffect } from "react";
import { Settings, RotateCcw } from "lucide-react";
import { useDashboardStore } from "@/lib/store";

export default function SettingsPage() {
  const { account, resetAccount } = useDashboardStore();
  const [mounted, setMounted] = useState(false);
  const [balance, setBalance] = useState("10000");
  const [confirmReset, setConfirmReset] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) return null;

  const handleReset = () => {
    if (!confirmReset) {
      setConfirmReset(true);
      return;
    }
    resetAccount(Number(balance) || 10000);
    setConfirmReset(false);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">설정</h1>

      <div className="max-w-2xl space-y-6">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
            <Settings size={16} /> 모의투자 계좌
          </h3>
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-zinc-500">현재 잔액</p>
                <p className="text-lg font-bold text-zinc-200">
                  $
                  {account.balance.toLocaleString("en-US", {
                    maximumFractionDigits: 2,
                  })}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">초기 자본</p>
                <p className="text-lg font-bold text-zinc-200">
                  ${account.initial_balance.toLocaleString("en-US")}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">오픈 포지션</p>
                <p className="text-lg font-bold text-zinc-200">
                  {account.positions.length}
                </p>
              </div>
              <div>
                <p className="text-xs text-zinc-500">총 거래 수</p>
                <p className="text-lg font-bold text-zinc-200">
                  {account.trade_history.length}
                </p>
              </div>
            </div>

            <div>
              <p className="text-xs text-zinc-500">계좌 생성일</p>
              <p className="text-sm text-zinc-400">
                {new Date(account.created_at).toLocaleString("ko-KR")}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
            <RotateCcw size={16} /> 계좌 초기화
          </h3>
          <p className="mt-2 text-xs text-zinc-500">
            모든 포지션과 거래 내역이 삭제되고 새 잔액으로 시작합니다.
          </p>
          <div className="mt-4 space-y-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">
                초기 자본 (USDT)
              </label>
              <input
                type="number"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
            </div>
            <button
              onClick={handleReset}
              className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors ${
                confirmReset
                  ? "bg-red-600 text-white hover:bg-red-500"
                  : "bg-zinc-700 text-zinc-300 hover:bg-zinc-600"
              }`}
            >
              {confirmReset ? "정말 초기화하시겠습니까?" : "계좌 초기화"}
            </button>
            {confirmReset && (
              <button
                onClick={() => setConfirmReset(false)}
                className="ml-2 rounded-lg bg-zinc-800 px-4 py-2.5 text-sm text-zinc-400 hover:text-zinc-200"
              >
                취소
              </button>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="text-sm font-medium text-zinc-300">데이터 소스</h3>
          <div className="mt-3 space-y-2 text-xs text-zinc-500">
            <p>가격 데이터: CoinGecko API (30초마다 갱신)</p>
            <p>공포/탐욕 지수: Alternative.me API (5분마다 갱신)</p>
            <p>모의투자 데이터: 브라우저 localStorage</p>
          </div>
        </div>
      </div>
    </div>
  );
}
