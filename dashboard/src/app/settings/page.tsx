"use client";

import { useState, useEffect } from "react";
import { Settings, RotateCcw, Sliders } from "lucide-react";
import { useDashboardStore } from "@/lib/store";
import type { TradingSettings } from "@/lib/types";

export default function SettingsPage() {
  const { account, resetAccount, tradingSettings, updateTradingSettings } =
    useDashboardStore();
  const [mounted, setMounted] = useState(false);
  const [balance, setBalance] = useState("10000");
  const [confirmReset, setConfirmReset] = useState(false);

  // Trading settings local state (display values in %)
  const [feeRate, setFeeRate] = useState("");
  const [slippageRate, setSlippageRate] = useState("");
  const [maxPositionSize, setMaxPositionSize] = useState("");
  const [maxPositions, setMaxPositions] = useState("");
  const [maxDrawdown, setMaxDrawdown] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) {
      setFeeRate((tradingSettings.fee_rate * 100).toString());
      setSlippageRate((tradingSettings.slippage_rate * 100).toString());
      setMaxPositionSize((tradingSettings.max_position_pct * 100).toString());
      setMaxPositions(tradingSettings.max_positions.toString());
      setMaxDrawdown((tradingSettings.max_drawdown_pct * 100).toString());
    }
  }, [mounted, tradingSettings]);

  if (!mounted) return null;

  const handleReset = () => {
    if (!confirmReset) {
      setConfirmReset(true);
      return;
    }
    resetAccount(Number(balance) || 10000);
    setConfirmReset(false);
  };

  const handleSaveSettings = () => {
    const newSettings: TradingSettings = {
      fee_rate: (parseFloat(feeRate) || 0.1) / 100,
      slippage_rate: (parseFloat(slippageRate) || 0.05) / 100,
      max_position_pct: (parseFloat(maxPositionSize) || 20) / 100,
      max_positions: parseInt(maxPositions) || 5,
      max_drawdown_pct: (parseFloat(maxDrawdown) || 15) / 100,
    };
    updateTradingSettings(newSettings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">설정</h1>

      <div className="max-w-2xl space-y-6">
        {/* Trading Settings */}
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
            <Sliders size={16} /> 거래 설정
          </h3>
          <p className="mt-1 text-xs text-zinc-500">
            수수료, 슬리피지, 포지션 크기 등 거래 엔진 파라미터를 조정합니다.
          </p>
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-xs text-zinc-500">
                  수수료율 (%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={feeRate}
                  onChange={(e) => setFeeRate(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                  placeholder="0.1"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">
                  슬리피지율 (%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={slippageRate}
                  onChange={(e) => setSlippageRate(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                  placeholder="0.05"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">
                  최대 포지션 크기 (%)
                </label>
                <input
                  type="number"
                  step="1"
                  value={maxPositionSize}
                  onChange={(e) => setMaxPositionSize(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                  placeholder="20"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-zinc-500">
                  최대 동시 포지션
                </label>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={maxPositions}
                  onChange={(e) => setMaxPositions(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                  placeholder="5"
                />
              </div>
              <div className="col-span-2">
                <label className="mb-1 block text-xs text-zinc-500">
                  최대 낙폭 제한 (%)
                </label>
                <input
                  type="number"
                  step="1"
                  value={maxDrawdown}
                  onChange={(e) => setMaxDrawdown(e.target.value)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
                  placeholder="15"
                />
                <p className="mt-1 text-[10px] text-zinc-600">
                  이 비율을 초과하면 자동매매가 중단됩니다
                </p>
              </div>
            </div>
            <button
              onClick={handleSaveSettings}
              className={`rounded-lg px-5 py-2.5 text-sm font-medium transition-colors ${
                saved
                  ? "bg-emerald-600 text-white"
                  : "bg-zinc-700 text-zinc-300 hover:bg-zinc-600"
              }`}
            >
              {saved ? "저장 완료" : "설정 저장"}
            </button>
          </div>
        </div>

        {/* Account Info */}
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

        {/* Reset Account */}
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

        {/* Data Sources */}
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
