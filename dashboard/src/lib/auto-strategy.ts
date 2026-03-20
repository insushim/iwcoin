import { PaperTradingEngine } from "./paper-trading";
import type { CoinPrice, TradingSettings } from "./types";
import { COINS, DEFAULT_SETTINGS } from "./types";

// ── Signal type for UI ──────────────────────────────────────────────
export interface StrategySignal {
  strategy: string;
  symbol: string;
  side: "long" | "short";
  confidence: number; // 0-100
  reason: string;
  timestamp: number;
}

export interface RegimeData {
  regime: "bull" | "bear" | "sideways";
  fearGreed: number;
}

// ── Helpers ─────────────────────────────────────────────────────────
function ema(data: number[], period: number): number[] {
  const k = 2 / (period + 1);
  const result = [data[0]];
  for (let i = 1; i < data.length; i++) {
    result.push(data[i] * k + result[i - 1] * (1 - k));
  }
  return result;
}

function sma(data: number[], period: number): number {
  const slice = data.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / slice.length;
}

function stdDev(data: number[], period: number): number {
  const slice = data.slice(-period);
  const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
  const variance =
    slice.reduce((sum, v) => sum + (v - mean) ** 2, 0) / slice.length;
  return Math.sqrt(variance);
}

function computeRSI(history: number[]): number {
  const changes: number[] = [];
  for (let i = 1; i < history.length; i++) {
    changes.push(history[i] - history[i - 1]);
  }
  const gains = changes.filter((c) => c > 0);
  const losses = changes.filter((c) => c < 0).map((c) => -c);
  const avgGain =
    gains.length > 0 ? gains.reduce((a, b) => a + b, 0) / changes.length : 0;
  const avgLoss =
    losses.length > 0
      ? losses.reduce((a, b) => a + b, 0) / changes.length
      : 0.001;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

// ── Main class ──────────────────────────────────────────────────────
export class AutoStrategyRunner {
  private engine: PaperTradingEngine;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private priceHistory: Record<string, number[]> = {};
  private lastTradeTime: Record<string, number> = {};
  private settings: TradingSettings = DEFAULT_SETTINGS;
  private getRegimeFn: (() => RegimeData) | null = null;
  private recentSignals: StrategySignal[] = [];
  private activeStrategies: Set<string> = new Set();

  constructor(engine: PaperTradingEngine) {
    this.engine = engine;
  }

  start(getPrices: () => CoinPrice[], getRegime?: () => RegimeData): void {
    if (this.intervalId) return;
    if (getRegime) this.getRegimeFn = getRegime;

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

  setSettings(settings: TradingSettings): void {
    this.settings = settings;
  }

  getRecentSignals(): StrategySignal[] {
    return this.recentSignals.slice(-20);
  }

  getActiveStrategies(): string[] {
    return Array.from(this.activeStrategies);
  }

  private addSignal(signal: StrategySignal): void {
    this.recentSignals.push(signal);
    if (this.recentSignals.length > 50) {
      this.recentSignals = this.recentSignals.slice(-20);
    }
    this.activeStrategies.add(signal.strategy);
    // Clear active set after 5 minutes
    setTimeout(() => {
      this.activeStrategies.delete(signal.strategy);
    }, 300_000);
  }

  tick(prices: CoinPrice[]): void {
    const priceMap: Record<string, number> = {};
    for (const p of prices) {
      priceMap[p.symbol] = p.price;

      // Track price history (max 60 ticks = 30 min)
      if (!this.priceHistory[p.symbol]) this.priceHistory[p.symbol] = [];
      this.priceHistory[p.symbol].push(p.price);
      if (this.priceHistory[p.symbol].length > 60) {
        this.priceHistory[p.symbol].shift();
      }
    }

    // Update existing position prices
    this.engine.updatePrices(priceMap);

    // Check SL/TP triggers
    this.engine.checkTriggers(priceMap);

    // Try to open new positions based on signals
    const account = this.engine.getAccount();
    const availableBalance = account.balance;
    if (availableBalance < 100) return;

    // Respect max_positions setting
    if (account.positions.length >= this.settings.max_positions) return;

    const regime = this.getRegimeFn ? this.getRegimeFn() : null;

    for (const coin of COINS) {
      // Re-check position limit each iteration
      const currentAccount = this.engine.getAccount();
      if (currentAccount.positions.length >= this.settings.max_positions) break;

      const history = this.priceHistory[coin.symbol];
      if (!history || history.length < 5) continue;

      const price = priceMap[coin.symbol];
      if (!price) continue;

      // Don't trade same symbol too frequently (5 min cooldown)
      const lastTime = this.lastTradeTime[coin.symbol] || 0;
      if (Date.now() - lastTime < 300_000) continue;

      // Already have position in this symbol?
      if (currentAccount.positions.some((p) => p.symbol === coin.symbol))
        continue;

      const signal = this.getSignal(coin.symbol, history, price, regime);
      if (!signal) continue;

      // Record signal for UI
      this.addSignal({
        strategy: signal.strategy,
        symbol: coin.symbol,
        side: signal.side,
        confidence: signal.confidence,
        reason: signal.reason,
        timestamp: Date.now(),
      });

      // Position size respects max_position_pct, capped at $2000
      const posSize = Math.min(
        availableBalance * this.settings.max_position_pct,
        2000,
      );
      const slPct = 0.03;
      const tpPct = 0.06;

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
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    // ── Strategy 5: Regime-Aware Composite ──────────────────────────
    if (regime && history.length >= 30) {
      const result = this.regimeStrategy(symbol, history, currentPrice, regime);
      if (result) return result;
    }

    // ── Strategy 3: MACD Cross ──────────────────────────────────────
    if (history.length >= 30) {
      const result = this.macdStrategy(history, regime);
      if (result) return result;
    }

    // ── Strategy 4: Bollinger Bands ─────────────────────────────────
    if (history.length >= 20) {
      const result = this.bollingerStrategy(history, currentPrice, regime);
      if (result) return result;
    }

    // ── Strategy 1: SMA Crossover ───────────────────────────────────
    if (history.length >= 10) {
      const sma5 = sma(history, 5);
      const sma10 = sma(history, 10);

      if (currentPrice > sma5 && sma5 > sma10) {
        if (regime?.regime === "bear") return null;
        return {
          side: "long",
          strategy: "SMA 크로스오버",
          confidence: 55,
          reason: `SMA5(${sma5.toFixed(1)}) > SMA10(${sma10.toFixed(1)}), 상승 추세`,
        };
      }
      if (currentPrice < sma5 && sma5 < sma10) {
        if (regime?.regime === "bull") return null;
        return {
          side: "short",
          strategy: "SMA 크로스오버",
          confidence: 55,
          reason: `SMA5(${sma5.toFixed(1)}) < SMA10(${sma10.toFixed(1)}), 하락 추세`,
        };
      }
    }

    // ── Strategy 2: RSI ─────────────────────────────────────────────
    if (history.length >= 14) {
      const rsi = computeRSI(history);

      if (rsi < 30) {
        if (regime?.regime === "bear") return null;
        return {
          side: "long",
          strategy: "RSI 과매도",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} < 30, 과매도 반등 기대`,
        };
      }
      if (rsi > 70) {
        if (regime?.regime === "bull") return null;
        return {
          side: "short",
          strategy: "RSI 과매수",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} > 70, 과매수 조정 기대`,
        };
      }
    }

    return null;
  }

  // ── MACD Strategy ───────────────────────────────────────────────
  private macdStrategy(
    history: number[],
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const ema12 = ema(history, 12);
    const ema26 = ema(history, 26);

    // MACD line = EMA12 - EMA26
    const macdLine: number[] = [];
    for (let i = 0; i < history.length; i++) {
      macdLine.push(ema12[i] - ema26[i]);
    }

    // Signal line = EMA9 of MACD
    const signalLine = ema(macdLine, 9);

    const len = macdLine.length;
    if (len < 2) return null;

    const macdNow = macdLine[len - 1];
    const macdPrev = macdLine[len - 2];
    const sigNow = signalLine[len - 1];
    const sigPrev = signalLine[len - 2];

    // Bullish crossover: MACD crosses above signal
    if (macdPrev <= sigPrev && macdNow > sigNow) {
      if (regime?.regime === "bear") return null;
      const strength = Math.abs(macdNow - sigNow);
      return {
        side: "long",
        strategy: "MACD 크로스",
        confidence: Math.min(75, 55 + strength * 1000),
        reason: `MACD(${macdNow.toFixed(2)}) 시그널(${sigNow.toFixed(2)}) 상향 돌파`,
      };
    }

    // Bearish crossover: MACD crosses below signal
    if (macdPrev >= sigPrev && macdNow < sigNow) {
      if (regime?.regime === "bull") return null;
      const strength = Math.abs(sigNow - macdNow);
      return {
        side: "short",
        strategy: "MACD 크로스",
        confidence: Math.min(75, 55 + strength * 1000),
        reason: `MACD(${macdNow.toFixed(2)}) 시그널(${sigNow.toFixed(2)}) 하향 돌파`,
      };
    }

    return null;
  }

  // ── Bollinger Bands Strategy ────────────────────────────────────
  private bollingerStrategy(
    history: number[],
    currentPrice: number,
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const period = 20;
    const middle = sma(history, period);
    const sd = stdDev(history, period);
    const upper = middle + 2 * sd;
    const lower = middle - 2 * sd;

    // Buy near lower band (mean reversion)
    if (currentPrice <= lower * 1.005) {
      if (regime?.regime === "bear") return null;
      const distPct = ((middle - currentPrice) / middle) * 100;
      return {
        side: "long",
        strategy: "볼린저 밴드",
        confidence: Math.min(70, 50 + distPct * 5),
        reason: `가격(${currentPrice.toFixed(1)}) ≤ 하단밴드(${lower.toFixed(1)}), 평균회귀 기대`,
      };
    }

    // Sell near upper band
    if (currentPrice >= upper * 0.995) {
      if (regime?.regime === "bull") return null;
      const distPct = ((currentPrice - middle) / middle) * 100;
      return {
        side: "short",
        strategy: "볼린저 밴드",
        confidence: Math.min(70, 50 + distPct * 5),
        reason: `가격(${currentPrice.toFixed(1)}) ≥ 상단밴드(${upper.toFixed(1)}), 평균회귀 기대`,
      };
    }

    return null;
  }

  // ── Regime-Aware Composite Strategy ─────────────────────────────
  private regimeStrategy(
    symbol: string,
    history: number[],
    currentPrice: number,
    regime: RegimeData,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const { regime: r, fearGreed } = regime;

    if (r === "bull") {
      // Aggressive long only — use MACD + RSI confirmation
      const rsi = computeRSI(history);
      const ema12 = ema(history, 12);
      const ema26 = ema(history, 26);
      const macdNow = ema12[ema12.length - 1] - ema26[ema26.length - 1];

      if (macdNow > 0 && rsi < 65) {
        const conf = Math.min(85, 60 + fearGreed * 0.2);
        return {
          side: "long",
          strategy: "레짐 적응형",
          confidence: conf,
          reason: `강세장: MACD 양수(${macdNow.toFixed(2)}), RSI(${rsi.toFixed(0)}) 과열 아님, F&G(${fearGreed})`,
        };
      }
      return null;
    }

    if (r === "bear") {
      // Defensive — short on RSI overbought or stay flat
      const rsi = computeRSI(history);
      if (rsi > 65) {
        const conf = Math.min(80, 55 + (100 - fearGreed) * 0.2);
        return {
          side: "short",
          strategy: "레짐 적응형",
          confidence: conf,
          reason: `약세장: RSI(${rsi.toFixed(0)}) 과매수, F&G(${fearGreed}) 공포 구간`,
        };
      }
      return null;
    }

    // Sideways — use Bollinger mean-reversion
    if (r === "sideways") {
      return this.bollingerStrategy(history, currentPrice, null);
    }

    return null;
  }
}
