import { create } from "zustand";
import type {
  Trade,
  Position,
  Strategy,
  RegimeData,
  EquityPoint,
  DashboardSummary,
} from "./supabase";

// ---- Mock data ----

const mockRegime: RegimeData = {
  id: "1",
  regime: "bull",
  fear_greed_index: 72,
  timestamp: "2026-03-19T09:00:00Z",
  btc_dominance: 54.2,
  volatility: 32.1,
};

const mockSummary: DashboardSummary = {
  total_balance: 125430.56,
  daily_pnl: 2340.12,
  daily_pnl_pct: 1.9,
  open_positions: 4,
  active_strategies: 3,
  current_regime: mockRegime,
};

const mockEquity: EquityPoint[] = Array.from({ length: 90 }, (_, i) => {
  const d = new Date("2025-12-20");
  d.setDate(d.getDate() + i);
  return {
    date: d.toISOString().slice(0, 10),
    equity:
      100000 + Math.sin(i / 8) * 5000 + i * 280 + (Math.random() - 0.3) * 2000,
  };
});

const symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AVAX/USDT", "ARB/USDT"];
const strats = [
  "Momentum Alpha",
  "Mean Reversion",
  "Breakout Hunter",
  "Grid Bot",
  "DCA Smart",
];

const mockPositions: Position[] = [
  {
    id: "p1",
    symbol: "BTC/USDT",
    side: "long",
    entry_price: 84200,
    current_price: 86540,
    quantity: 0.5,
    unrealized_pnl: 1170,
    stop_loss: 82000,
    take_profit: 92000,
    strategy: "Momentum Alpha",
    opened_at: "2026-03-17T14:30:00Z",
  },
  {
    id: "p2",
    symbol: "ETH/USDT",
    side: "long",
    entry_price: 3150,
    current_price: 3280,
    quantity: 5,
    unrealized_pnl: 650,
    stop_loss: 2950,
    take_profit: 3600,
    strategy: "Breakout Hunter",
    opened_at: "2026-03-18T08:15:00Z",
  },
  {
    id: "p3",
    symbol: "SOL/USDT",
    side: "short",
    entry_price: 142,
    current_price: 138.5,
    quantity: 40,
    unrealized_pnl: 140,
    stop_loss: 150,
    take_profit: 125,
    strategy: "Mean Reversion",
    opened_at: "2026-03-18T22:00:00Z",
  },
  {
    id: "p4",
    symbol: "ARB/USDT",
    side: "long",
    entry_price: 1.12,
    current_price: 1.08,
    quantity: 2000,
    unrealized_pnl: -80,
    stop_loss: 1.0,
    take_profit: 1.35,
    strategy: "DCA Smart",
    opened_at: "2026-03-16T11:00:00Z",
  },
];

const mockTrades: Trade[] = Array.from({ length: 40 }, (_, i) => {
  const d = new Date("2026-03-01");
  d.setDate(d.getDate() + Math.floor(i / 2));
  const sym = symbols[i % symbols.length];
  const side = i % 3 === 0 ? ("short" as const) : ("long" as const);
  const entry = 1000 + Math.random() * 500;
  const pnl = (Math.random() - 0.35) * 400;
  return {
    id: `t${i}`,
    symbol: sym,
    side,
    entry_price: +entry.toFixed(2),
    exit_price: +(entry + pnl / 10).toFixed(2),
    quantity: +(Math.random() * 5 + 0.1).toFixed(3),
    pnl: +pnl.toFixed(2),
    strategy: strats[i % strats.length],
    opened_at: d.toISOString(),
    closed_at: new Date(
      d.getTime() + 3600000 * (1 + Math.random() * 48),
    ).toISOString(),
    status: "closed" as const,
  };
});

const mockStrategies: Strategy[] = [
  {
    id: "s1",
    name: "Momentum Alpha",
    description: "Trend-following on 4H timeframe with volume confirmation",
    status: "active",
    win_rate: 62.5,
    total_pnl: 18420,
    sharpe_ratio: 1.84,
    total_trades: 156,
    allocation_pct: 35,
  },
  {
    id: "s2",
    name: "Mean Reversion",
    description: "Bollinger band mean reversion on 1H with RSI filter",
    status: "active",
    win_rate: 58.1,
    total_pnl: 9870,
    sharpe_ratio: 1.42,
    total_trades: 243,
    allocation_pct: 25,
  },
  {
    id: "s3",
    name: "Breakout Hunter",
    description: "Breakout detection with ATR-based stop placement",
    status: "active",
    win_rate: 45.3,
    total_pnl: 12650,
    sharpe_ratio: 1.65,
    total_trades: 98,
    allocation_pct: 20,
  },
  {
    id: "s4",
    name: "Grid Bot",
    description: "Range-bound grid trading for sideways markets",
    status: "paused",
    win_rate: 71.2,
    total_pnl: 4320,
    sharpe_ratio: 0.92,
    total_trades: 512,
    allocation_pct: 10,
  },
  {
    id: "s5",
    name: "DCA Smart",
    description: "Dollar cost averaging with regime-aware entry sizing",
    status: "paused",
    win_rate: 54.8,
    total_pnl: 3210,
    sharpe_ratio: 1.12,
    total_trades: 87,
    allocation_pct: 10,
  },
];

const mockRegimeHistory: RegimeData[] = Array.from({ length: 30 }, (_, i) => {
  const d = new Date("2026-02-18");
  d.setDate(d.getDate() + i);
  const regimes: RegimeData["regime"][] = [
    "bull",
    "bull",
    "sideways",
    "bear",
    "bull",
  ];
  return {
    id: `r${i}`,
    regime: regimes[Math.floor(i / 7) % regimes.length],
    fear_greed_index: 30 + Math.floor(Math.random() * 50),
    timestamp: d.toISOString(),
    btc_dominance: 52 + Math.random() * 5,
    volatility: 20 + Math.random() * 25,
  };
});

// ---- Store ----

interface DashboardStore {
  summary: DashboardSummary;
  equity: EquityPoint[];
  positions: Position[];
  trades: Trade[];
  strategies: Strategy[];
  regimeHistory: RegimeData[];
  sidebarOpen: boolean;
  toggleSidebar: () => void;
}

export const useDashboardStore = create<DashboardStore>((set) => ({
  summary: mockSummary,
  equity: mockEquity,
  positions: mockPositions,
  trades: mockTrades,
  strategies: mockStrategies,
  regimeHistory: mockRegimeHistory,
  sidebarOpen: false,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
