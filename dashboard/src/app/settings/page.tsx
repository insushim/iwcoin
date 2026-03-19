"use client";

import { Settings } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">설정</h1>

      <div className="max-w-2xl space-y-6">
        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="flex items-center gap-2 text-sm font-medium text-zinc-300">
            <Settings size={16} /> 데이터베이스 연결
          </h3>
          <div className="mt-4 space-y-3">
            <div>
              <label className="mb-1 block text-xs text-zinc-500">
                Supabase URL
              </label>
              <input
                type="text"
                placeholder="https://xxxxx.supabase.co"
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-zinc-500">
                Anon Key
              </label>
              <input
                type="password"
                placeholder="eyJhbGci..."
                className="w-full rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800/80 bg-gradient-to-br from-zinc-900/80 to-zinc-900/40 p-5">
          <h3 className="text-sm font-medium text-zinc-300">알림 설정</h3>
          <div className="mt-4 space-y-3">
            {["거래 진입", "거래 청산", "레짐 변경", "일일 리포트"].map(
              (label) => (
                <label
                  key={label}
                  className="flex items-center justify-between"
                >
                  <span className="text-sm text-zinc-400">{label}</span>
                  <input
                    type="checkbox"
                    defaultChecked
                    className="h-4 w-4 rounded accent-emerald-500"
                  />
                </label>
              ),
            )}
          </div>
        </div>

        <button className="rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-500 transition-colors">
          설정 저장
        </button>
      </div>
    </div>
  );
}
