import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// ---- Types ----

export interface Trade {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number | null;
  strategy: string;
  opened_at: string;
  closed_at: string | null;
  status: "open" | "closed";
}

export interface Position {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pnl: number;
  stop_loss: number;
  take_profit: number;
  strategy: string;
  opened_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  status: "active" | "paused";
  win_rate: number;
  total_pnl: number;
  sharpe_ratio: number;
  total_trades: number;
  allocation_pct: number;
}

export interface RegimeData {
  id: string;
  regime: "bull" | "bear" | "sideways";
  fear_greed_index: number;
  timestamp: string;
  btc_dominance: number;
  volatility: number;
}

export interface EquityPoint {
  date: string;
  equity: number;
}

export interface DashboardSummary {
  total_balance: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  open_positions: number;
  active_strategies: number;
  current_regime: RegimeData;
}
