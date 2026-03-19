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
