// ---- Types ----

export interface CoinPrice {
  symbol: string;
  coingeckoId: string;
  price: number;
  change24h: number;
  volume24h: number;
  marketCap: number;
}

export interface PaperPosition {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  current_price: number;
  quantity: number;
  stop_loss: number;
  take_profit: number;
  strategy: string;
  opened_at: string;
  fee: number; // entry fee paid
  leverage: number; // default 1
}

export interface PaperTrade {
  id: string;
  symbol: string;
  side: "long" | "short";
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  strategy: string;
  opened_at: string;
  closed_at: string;
  entry_fee: number;
  exit_fee: number;
  slippage: number; // total slippage cost
  net_pnl: number; // pnl after fees+slippage
}

export interface PaperAccount {
  balance: number;
  initial_balance: number;
  positions: PaperPosition[];
  trade_history: PaperTrade[];
  created_at: string;
}

export interface EquitySnapshot {
  date: string;
  equity: number;
}

export interface TradingSettings {
  fee_rate: number; // e.g. 0.001 = 0.1%
  slippage_rate: number; // e.g. 0.0005 = 0.05%
  max_position_pct: number; // max % of balance per position (e.g. 0.2 = 20%)
  max_positions: number; // max concurrent positions (e.g. 5)
  max_drawdown_pct: number; // auto-stop if drawdown exceeds this (e.g. 0.15 = 15%)
}

export const DEFAULT_SETTINGS: TradingSettings = {
  fee_rate: 0.001,
  slippage_rate: 0.0005,
  max_position_pct: 0.2,
  max_positions: 5,
  max_drawdown_pct: 0.15,
};

export interface PerformanceStats {
  total_trades: number;
  win_rate: number;
  profit_factor: number; // gross profit / gross loss
  avg_win: number;
  avg_loss: number;
  max_drawdown: number; // max drawdown in $
  max_drawdown_pct: number;
  sharpe_ratio: number;
  total_pnl: number;
  total_fees: number;
  best_trade: number;
  worst_trade: number;
}

export interface FearGreedData {
  value: number;
  classification: string;
}

export interface FearGreedHistoryItem {
  value: number;
  classification: string;
  timestamp: string;
}

export interface RegimeData {
  regime: "bull" | "bear" | "sideways";
  fearGreed: number;
  btcDominance: number;
}

export const COINS = [
  { symbol: "BTC/USDT", coingeckoId: "bitcoin" },
  { symbol: "ETH/USDT", coingeckoId: "ethereum" },
  { symbol: "SOL/USDT", coingeckoId: "solana" },
  { symbol: "AVAX/USDT", coingeckoId: "avalanche-2" },
  { symbol: "ARB/USDT", coingeckoId: "arbitrum" },
] as const;

export function symbolToId(symbol: string): string {
  return COINS.find((c) => c.symbol === symbol)?.coingeckoId ?? "bitcoin";
}

export function idToSymbol(id: string): string {
  return COINS.find((c) => c.coingeckoId === id)?.symbol ?? "BTC/USDT";
}
