import type { CoinPrice, FearGreedData, FearGreedHistoryItem } from "./types";
import { COINS, idToSymbol } from "./types";

const COINGECKO_BASE = "https://api.coingecko.com/api/v3";

// Simple in-memory cache to respect rate limits
const cache: Record<string, { data: unknown; ts: number }> = {};
function cached<T>(
  key: string,
  ttlMs: number,
  fn: () => Promise<T>,
): Promise<T> {
  const entry = cache[key];
  if (entry && Date.now() - entry.ts < ttlMs)
    return Promise.resolve(entry.data as T);
  return fn().then((data) => {
    cache[key] = { data, ts: Date.now() };
    return data;
  });
}

async function fetchWithRetry(url: string, retries = 3): Promise<Response> {
  for (let i = 0; i < retries; i++) {
    const res = await fetch(url);
    if (res.ok) return res;
    if (res.status === 429 && i < retries - 1) {
      await new Promise((r) => setTimeout(r, (i + 1) * 2000));
      continue;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  }
  throw new Error("Max retries reached");
}

export async function fetchPrices(): Promise<CoinPrice[]> {
  return cached("prices", 30_000, async () => {
    const ids = COINS.map((c) => c.coingeckoId).join(",");
    const url = `${COINGECKO_BASE}/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true`;
    const res = await fetchWithRetry(url);
    const data = await res.json();

    return COINS.filter((coin) => data[coin.coingeckoId]?.usd).map((coin) => {
      const d = data[coin.coingeckoId] || {};
      return {
        symbol: coin.symbol,
        coingeckoId: coin.coingeckoId,
        price: d.usd ?? 0,
        change24h: d.usd_24h_change ?? 0,
        volume24h: d.usd_24h_vol ?? 0,
        marketCap: d.usd_market_cap ?? 0,
      };
    });
  });
}

export async function fetchFearGreed(): Promise<FearGreedData> {
  return cached("fng", 300_000, async () => {
    const res = await fetchWithRetry(
      "https://api.alternative.me/fng/?limit=1&format=json",
    );
    const data = await res.json();
    const item = data.data?.[0];
    return {
      value: Number(item?.value ?? 50),
      classification: item?.value_classification ?? "Neutral",
    };
  });
}

export async function fetchFearGreedHistory(): Promise<FearGreedHistoryItem[]> {
  return cached("fng_history", 300_000, async () => {
    const res = await fetchWithRetry(
      "https://api.alternative.me/fng/?limit=30&format=json",
    );
    const data = await res.json();
    return (data.data ?? [])
      .map(
        (item: {
          value: string;
          value_classification: string;
          timestamp: string;
        }) => ({
          value: Number(item.value),
          classification: item.value_classification,
          timestamp: new Date(Number(item.timestamp) * 1000)
            .toISOString()
            .slice(0, 10),
        }),
      )
      .reverse();
  });
}

export async function fetchMarketChart(
  coinId: string,
  days: number,
): Promise<{ date: string; price: number }[]> {
  return cached(`chart_${coinId}_${days}`, 300_000, async () => {
    const url = `${COINGECKO_BASE}/coins/${coinId}/market_chart?vs_currency=usd&days=${days}`;
    const res = await fetchWithRetry(url);
    const data = await res.json();
    const prices: [number, number][] = data.prices ?? [];

    // Reduce to daily points
    const daily = new Map<string, number>();
    for (const [ts, price] of prices) {
      const date = new Date(ts).toISOString().slice(0, 10);
      daily.set(date, price);
    }
    return Array.from(daily.entries()).map(([date, price]) => ({
      date,
      price,
    }));
  });
}

export async function fetchGlobalData(): Promise<{
  btc_dominance: number;
  total_market_cap: number;
}> {
  return cached("global", 300_000, async () => {
    const url = `${COINGECKO_BASE}/global`;
    const res = await fetchWithRetry(url);
    const data = await res.json();
    return {
      btc_dominance: data.data?.market_cap_percentage?.btc ?? 0,
      total_market_cap: data.data?.total_market_cap?.usd ?? 0,
    };
  });
}
