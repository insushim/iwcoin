import { PaperTradingEngine } from "./paper-trading";
import type { CoinPrice } from "./types";
import { COINS } from "./types";

export class AutoStrategyRunner {
  private engine: PaperTradingEngine;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private priceHistory: Record<string, number[]> = {};
  private lastTradeTime: Record<string, number> = {};

  constructor(engine: PaperTradingEngine) {
    this.engine = engine;
  }

  start(getPrices: () => CoinPrice[]): void {
    if (this.intervalId) return;
    this.intervalId = setInterval(() => {
      const prices = getPrices();
      if (prices.length > 0) this.tick(prices);
    }, 30_000);
    // Run immediately too
    const prices = getPrices();
    if (prices.length > 0) this.tick(prices);
  }

  stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  isRunning(): boolean {
    return this.intervalId !== null;
  }

  tick(prices: CoinPrice[]): void {
    const priceMap: Record<string, number> = {};
    for (const p of prices) {
      priceMap[p.symbol] = p.price;

      // Track price history (max 30 ticks)
      if (!this.priceHistory[p.symbol]) this.priceHistory[p.symbol] = [];
      this.priceHistory[p.symbol].push(p.price);
      if (this.priceHistory[p.symbol].length > 30) {
        this.priceHistory[p.symbol].shift();
      }
    }

    // Update existing position prices
    this.engine.updatePrices(priceMap);

    // Check SL/TP triggers
    this.engine.checkTriggers(priceMap);

    // Try to open new positions based on simple signals
    const account = this.engine.getAccount();
    const availableBalance = account.balance;
    if (availableBalance < 100) return; // Not enough to trade

    for (const coin of COINS) {
      const history = this.priceHistory[coin.symbol];
      if (!history || history.length < 5) continue;

      const price = priceMap[coin.symbol];
      if (!price) continue;

      // Don't trade same symbol too frequently (5 min cooldown)
      const lastTime = this.lastTradeTime[coin.symbol] || 0;
      if (Date.now() - lastTime < 300_000) continue;

      // Already have position in this symbol?
      if (account.positions.some((p) => p.symbol === coin.symbol)) continue;

      const signal = this.getSignal(coin.symbol, history, price);
      if (!signal) continue;

      // Position size: 20% of available balance, max $2000
      const posSize = Math.min(availableBalance * 0.2, 2000);
      const slPct = 0.03; // 3% stop loss
      const tpPct = 0.06; // 6% take profit

      const sl =
        signal.side === "long" ? price * (1 - slPct) : price * (1 + slPct);
      const tp =
        signal.side === "long" ? price * (1 + tpPct) : price * (1 - tpPct);

      this.engine.openPosition({
        symbol: coin.symbol,
        side: signal.side,
        quantity: posSize,
        entry_price: price,
        stop_loss: +sl.toFixed(2),
        take_profit: +tp.toFixed(2),
        strategy: signal.strategy,
      });

      this.lastTradeTime[coin.symbol] = Date.now();
    }

    // Snapshot equity
    this.engine.snapshotEquity();
  }

  private getSignal(
    symbol: string,
    history: number[],
    currentPrice: number,
  ): { side: "long" | "short"; strategy: string } | null {
    // Strategy 1: Simple Moving Average (SMA5 vs SMA20 approximation)
    if (history.length >= 10) {
      const sma5 = history.slice(-5).reduce((a, b) => a + b, 0) / 5;
      const sma10 = history.slice(-10).reduce((a, b) => a + b, 0) / 10;

      if (currentPrice > sma5 && sma5 > sma10) {
        return { side: "long", strategy: "SMA 크로스오버" };
      }
      if (currentPrice < sma5 && sma5 < sma10) {
        return { side: "short", strategy: "SMA 크로스오버" };
      }
    }

    // Strategy 2: Simple RSI approximation
    if (history.length >= 14) {
      const changes = [];
      for (let i = 1; i < history.length; i++) {
        changes.push(history[i] - history[i - 1]);
      }
      const gains = changes.filter((c) => c > 0);
      const losses = changes.filter((c) => c < 0).map((c) => -c);
      const avgGain =
        gains.length > 0
          ? gains.reduce((a, b) => a + b, 0) / changes.length
          : 0;
      const avgLoss =
        losses.length > 0
          ? losses.reduce((a, b) => a + b, 0) / changes.length
          : 0.001;
      const rs = avgGain / avgLoss;
      const rsi = 100 - 100 / (1 + rs);

      if (rsi < 30) {
        return { side: "long", strategy: "RSI 과매도" };
      }
      if (rsi > 70) {
        return { side: "short", strategy: "RSI 과매수" };
      }
    }

    return null;
  }
}
