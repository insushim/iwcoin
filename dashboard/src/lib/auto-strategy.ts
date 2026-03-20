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

// ── Internal signal with SL/TP info ─────────────────────────────────
interface InternalSignal {
  symbol: string;
  side: "long" | "short";
  strategy: string;
  confidence: number;
  reason: string;
  slPct: number;
  tpPct: number;
  sector: string;
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

  // ── Dynamic position size based on confidence ─────────────────────
  private getPositionSize(confidence: number, balance: number): number {
    let pctMultiplier: number;
    if (confidence < 60) pctMultiplier = 0.5;
    else if (confidence <= 75) pctMultiplier = 0.75;
    else pctMultiplier = 1.0;

    const posSize = balance * this.settings.max_position_pct * pctMultiplier;
    return Math.min(posSize, 2000);
  }

  // ── Diversification checks ────────────────────────────────────────
  private canOpenPosition(signal: InternalSignal): boolean {
    const account = this.engine.getAccount();

    // Max positions
    if (account.positions.length >= this.settings.max_positions) return false;

    // No more than 3 positions in the same sector
    const sectorCount = account.positions.filter((p) => {
      const coin = COINS.find((c) => c.symbol === p.symbol);
      return coin && coin.sector === signal.sector;
    }).length;
    if (sectorCount >= 3) return false;

    // No more than 2 positions using the same strategy
    const strategyCount = account.positions.filter(
      (p) => p.strategy === signal.strategy,
    ).length;
    if (strategyCount >= 2) return false;

    // Total exposure should not exceed 80% of initial balance
    const totalExposure = account.positions.reduce(
      (sum, p) => sum + p.quantity,
      0,
    );
    if (totalExposure >= account.initial_balance * 0.8) return false;

    // Already have position in this symbol WITH THIS STRATEGY?
    if (
      account.positions.some(
        (p) => p.symbol === signal.symbol && p.strategy === signal.strategy,
      )
    )
      return false;

    return true;
  }

  tick(prices: CoinPrice[]): void {
    const priceMap: Record<string, number> = {};
    const coinPriceMap: Record<string, CoinPrice> = {};
    for (const p of prices) {
      priceMap[p.symbol] = p.price;
      coinPriceMap[p.symbol] = p;

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

    const account = this.engine.getAccount();
    const availableBalance = account.balance;
    if (availableBalance < 100) return;

    const regime = this.getRegimeFn ? this.getRegimeFn() : null;

    // Collect ALL signals from ALL coins
    const allSignals: InternalSignal[] = [];

    for (const coin of COINS) {
      const history = this.priceHistory[coin.symbol];
      if (!history || history.length < 5) continue;

      const price = priceMap[coin.symbol];
      if (!price) continue;

      // Don't trade same symbol too frequently (5 min cooldown)
      const lastTime = this.lastTradeTime[coin.symbol] || 0;
      if (Date.now() - lastTime < 300_000) continue;

      const coinPrice = coinPriceMap[coin.symbol];
      const signals = this.getAllSignals(
        coin.symbol,
        coin.sector,
        history,
        price,
        regime,
        coinPrice,
      );
      allSignals.push(...signals);
    }

    // Sort by confidence descending - pick best signals first
    allSignals.sort((a, b) => b.confidence - a.confidence);

    // Fill positions respecting diversification rules
    for (const signal of allSignals) {
      if (availableBalance < 100) break;
      if (!this.canOpenPosition(signal)) continue;

      const price = priceMap[signal.symbol];
      if (!price) continue;

      // Record signal for UI
      this.addSignal({
        strategy: signal.strategy,
        symbol: signal.symbol,
        side: signal.side,
        confidence: signal.confidence,
        reason: signal.reason,
        timestamp: Date.now(),
      });

      const posSize = this.getPositionSize(signal.confidence, availableBalance);

      const sl =
        signal.side === "long"
          ? price * (1 - signal.slPct)
          : price * (1 + signal.slPct);
      const tp =
        signal.side === "long"
          ? price * (1 + signal.tpPct)
          : price * (1 - signal.tpPct);

      this.engine.openPosition({
        symbol: signal.symbol,
        side: signal.side,
        quantity: posSize,
        entry_price: price,
        stop_loss: +sl.toFixed(2),
        take_profit: +tp.toFixed(2),
        strategy: signal.strategy,
      });

      this.lastTradeTime[signal.symbol] = Date.now();
    }

    // Snapshot equity
    this.engine.snapshotEquity();
  }

  // ── Collect ALL signals for a coin, return sorted by confidence ────
  private getAllSignals(
    symbol: string,
    sector: string,
    history: number[],
    currentPrice: number,
    regime: RegimeData | null,
    coinPrice: CoinPrice | undefined,
  ): InternalSignal[] {
    const signals: InternalSignal[] = [];

    // Regime-Aware Composite
    if (regime && history.length >= 30) {
      const r = this.regimeStrategy(symbol, history, currentPrice, regime);
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.03, tpPct: 0.06 });
    }

    // Sector Rotation
    if (regime && history.length >= 14) {
      const r = this.sectorRotationStrategy(
        symbol,
        sector,
        history,
        currentPrice,
        regime,
      );
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.03, tpPct: 0.06 });
    }

    // MACD Cross (trend following)
    if (history.length >= 30) {
      const r = this.macdStrategy(history, regime);
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.04, tpPct: 0.08 });
    }

    // EMA Ribbon (trend following)
    if (history.length >= 55) {
      const r = this.emaRibbonStrategy(history, currentPrice, regime);
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.04, tpPct: 0.08 });
    }

    // Momentum Breakout
    if (history.length >= 20 && coinPrice) {
      const r = this.momentumBreakoutStrategy(
        history,
        currentPrice,
        coinPrice,
        regime,
      );
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.03, tpPct: 0.1 });
    }

    // RSI+BB Convergence (mean reversion)
    if (history.length >= 20) {
      const r = this.rsiBBStrategy(history, currentPrice, regime);
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.02, tpPct: 0.04 });
    }

    // Bollinger Bands (mean reversion)
    if (history.length >= 20) {
      const r = this.bollingerStrategy(history, currentPrice, regime);
      if (r) signals.push({ ...r, symbol, sector, slPct: 0.02, tpPct: 0.04 });
    }

    // SMA Crossover (trend following)
    if (history.length >= 10) {
      const sma5 = sma(history, 5);
      const sma10 = sma(history, 10);

      if (currentPrice > sma5 && sma5 > sma10) {
        if (regime?.regime !== "bear") {
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "SMA 크로스오버",
            confidence: 55,
            reason: `SMA5(${sma5.toFixed(1)}) > SMA10(${sma10.toFixed(1)}), 상승 추세`,
            slPct: 0.04,
            tpPct: 0.08,
          });
        }
      }
      if (currentPrice < sma5 && sma5 < sma10) {
        if (regime?.regime !== "bull") {
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "SMA 크로스오버",
            confidence: 55,
            reason: `SMA5(${sma5.toFixed(1)}) < SMA10(${sma10.toFixed(1)}), 하락 추세`,
            slPct: 0.04,
            tpPct: 0.08,
          });
        }
      }
    }

    // RSI
    if (history.length >= 14) {
      const rsi = computeRSI(history);

      if (rsi < 30 && regime?.regime !== "bear") {
        signals.push({
          symbol,
          sector,
          side: "long",
          strategy: "RSI 과매도",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} < 30, 과매도 반등 기대`,
          slPct: 0.02,
          tpPct: 0.04,
        });
      }
      if (rsi > 70 && regime?.regime !== "bull") {
        signals.push({
          symbol,
          sector,
          side: "short",
          strategy: "RSI 과매수",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} > 70, 과매수 조정 기대`,
          slPct: 0.02,
          tpPct: 0.04,
        });
      }
    }

    return signals;
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

    const macdLine: number[] = [];
    for (let i = 0; i < history.length; i++) {
      macdLine.push(ema12[i] - ema26[i]);
    }

    const signalLine = ema(macdLine, 9);

    const len = macdLine.length;
    if (len < 2) return null;

    const macdNow = macdLine[len - 1];
    const macdPrev = macdLine[len - 2];
    const sigNow = signalLine[len - 1];
    const sigPrev = signalLine[len - 2];

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

    if (r === "sideways") {
      return this.bollingerStrategy(history, currentPrice, null);
    }

    return null;
  }

  // ── EMA Ribbon Strategy ───────────────────────────────────────
  private emaRibbonStrategy(
    history: number[],
    currentPrice: number,
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const ema8 = ema(history, 8);
    const ema13 = ema(history, 13);
    const ema21 = ema(history, 21);
    const ema55 = ema(history, 55);

    const len = history.length;
    const e8 = ema8[len - 1];
    const e13 = ema13[len - 1];
    const e21 = ema21[len - 1];
    const e55 = ema55[len - 1];

    // Bullish alignment: price > EMA8 > EMA13 > EMA21 > EMA55
    if (currentPrice > e8 && e8 > e13 && e13 > e21 && e21 > e55) {
      if (regime?.regime === "bear") return null;
      return {
        side: "long",
        strategy: "EMA 리본",
        confidence: 75,
        reason: `EMA 정렬 상승: 8(${e8.toFixed(1)})>13(${e13.toFixed(1)})>21(${e21.toFixed(1)})>55(${e55.toFixed(1)})`,
      };
    }

    // Bearish alignment: price < EMA8 < EMA13 < EMA21 < EMA55
    if (currentPrice < e8 && e8 < e13 && e13 < e21 && e21 < e55) {
      if (regime?.regime === "bull") return null;
      return {
        side: "short",
        strategy: "EMA 리본",
        confidence: 75,
        reason: `EMA 정렬 하락: 8(${e8.toFixed(1)})<13(${e13.toFixed(1)})<21(${e21.toFixed(1)})<55(${e55.toFixed(1)})`,
      };
    }

    return null;
  }

  // ── Momentum Breakout Strategy ────────────────────────────────
  private momentumBreakoutStrategy(
    history: number[],
    currentPrice: number,
    coinPrice: CoinPrice,
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const lookback = 20;
    const recent = history.slice(-lookback);
    const high = Math.max(...recent);
    const low = Math.min(...recent);

    // Volume filter: 24h change must exceed 2%
    if (Math.abs(coinPrice.change24h) < 2) return null;

    // Breakout above 20-tick high
    if (currentPrice > high) {
      if (regime?.regime === "bear") return null;
      return {
        side: "long",
        strategy: "모멘텀 돌파",
        confidence: 65,
        reason: `${lookback}봉 고점(${high.toFixed(1)}) 돌파, 24h변동 ${coinPrice.change24h.toFixed(1)}%`,
      };
    }

    // Breakout below 20-tick low
    if (currentPrice < low) {
      if (regime?.regime === "bull") return null;
      return {
        side: "short",
        strategy: "모멘텀 돌파",
        confidence: 65,
        reason: `${lookback}봉 저점(${low.toFixed(1)}) 돌파, 24h변동 ${coinPrice.change24h.toFixed(1)}%`,
      };
    }

    return null;
  }

  // ── RSI + Bollinger Convergence Strategy ──────────────────────
  private rsiBBStrategy(
    history: number[],
    currentPrice: number,
    regime: RegimeData | null,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const rsi = computeRSI(history);
    const period = 20;
    const middle = sma(history, period);
    const sd = stdDev(history, period);
    const upper = middle + 2 * sd;
    const lower = middle - 2 * sd;

    // Strong buy: RSI < 35 AND price near lower BB
    if (rsi < 35 && currentPrice <= lower * 1.01) {
      if (regime?.regime === "bear") return null;
      return {
        side: "long",
        strategy: "RSI+BB 복합",
        confidence: Math.min(85, 75 + (35 - rsi) * 0.5),
        reason: `RSI(${rsi.toFixed(1)})<35 + 하단밴드(${lower.toFixed(1)}) 근접, 강한 매수 신호`,
      };
    }

    // Strong sell: RSI > 65 AND price near upper BB
    if (rsi > 65 && currentPrice >= upper * 0.99) {
      if (regime?.regime === "bull") return null;
      return {
        side: "short",
        strategy: "RSI+BB 복합",
        confidence: Math.min(85, 75 + (rsi - 65) * 0.5),
        reason: `RSI(${rsi.toFixed(1)})>65 + 상단밴드(${upper.toFixed(1)}) 근접, 강한 매도 신호`,
      };
    }

    return null;
  }

  // ── Sector Rotation Strategy ──────────────────────────────────
  private sectorRotationStrategy(
    symbol: string,
    sector: string,
    history: number[],
    currentPrice: number,
    regime: RegimeData,
  ): {
    side: "long" | "short";
    strategy: string;
    confidence: number;
    reason: string;
  } | null {
    const { regime: r } = regime;
    const rsi = computeRSI(history);

    // Determine if this sector is favored in current regime
    let favored = false;
    let regimeLabel = "";

    if (r === "bull") {
      favored =
        sector === "smart-contract" || sector === "defi" || sector === "layer2";
      regimeLabel = "강세장";
    } else if (r === "bear") {
      favored = sector === "store-of-value" || sector === "payment";
      regimeLabel = "약세장";
    } else {
      favored = sector === "exchange" || sector === "store-of-value";
      regimeLabel = "횡보장";
    }

    if (!favored) return null;

    // Use RSI for entry timing within favored sector
    if (r === "bull" && rsi < 55) {
      return {
        side: "long",
        strategy: "섹터 로테이션",
        confidence: 65,
        reason: `${regimeLabel}: ${sector} 섹터 유리, RSI(${rsi.toFixed(0)}) 진입 적기`,
      };
    }

    if (r === "bear" && rsi > 55) {
      return {
        side: "short",
        strategy: "섹터 로테이션",
        confidence: 65,
        reason: `${regimeLabel}: ${sector} 섹터 방어적, RSI(${rsi.toFixed(0)}) 숏 진입`,
      };
    }

    if (r === "sideways" && rsi < 45) {
      return {
        side: "long",
        strategy: "섹터 로테이션",
        confidence: 60,
        reason: `${regimeLabel}: ${sector} 섹터 안정적, RSI(${rsi.toFixed(0)}) 저점 매수`,
      };
    }

    return null;
  }
}
