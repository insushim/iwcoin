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

// ── Correlation groups for diversification ──────────────────────────
const CORRELATED_GROUPS: string[][] = [
  ["BTC/USDT"], // BTC moves alone
  [
    "ETH/USDT",
    "SOL/USDT",
    "ADA/USDT",
    "AVAX/USDT",
    "DOT/USDT",
    "NEAR/USDT",
    "SUI/USDT",
  ], // L1s move together
  ["ARB/USDT", "OP/USDT", "MATIC/USDT"], // L2s
  ["LINK/USDT", "UNI/USDT", "AAVE/USDT"], // DeFi
  ["FET/USDT", "RENDER/USDT"], // AI
  ["DOGE/USDT"], // Meme
  ["XRP/USDT", "XLM/USDT"], // Payment
  ["BNB/USDT"], // Exchange
];

function getCorrelationGroup(symbol: string): string[] | undefined {
  return CORRELATED_GROUPS.find((g) => g.includes(symbol));
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

function computeATR(history: number[], period: number = 14): number {
  if (history.length < period + 1) return 0;
  let sum = 0;
  for (let i = history.length - period; i < history.length; i++) {
    sum += Math.abs(history[i] - history[i - 1]);
  }
  return sum / period;
}

// ── Volatility-adjusted SL/TP ───────────────────────────────────────
function adjustSlTp(
  baseSlPct: number,
  baseTpPct: number,
  history: number[],
  currentPrice: number,
): { slPct: number; tpPct: number } {
  const atr = computeATR(history);
  if (atr === 0 || currentPrice === 0) {
    return { slPct: baseSlPct, tpPct: baseTpPct };
  }
  const atrPct = atr / currentPrice;
  const slPct = Math.min(0.06, baseSlPct * (1 + atrPct));
  const tpPct = Math.min(0.15, baseTpPct * (1 + atrPct));
  return { slPct, tpPct };
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
  private tickCount: number = 0;
  private partialClosedIds: Set<string> = new Set();

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

  // ── Dynamic position size based on confidence + equity ────────────
  private getPositionSize(confidence: number): number {
    const account = this.engine.getAccount();
    // Profit reinvestment: use current equity instead of initial balance
    const equity =
      account.balance + account.positions.reduce((s, p) => s + p.quantity, 0);

    let pctMultiplier: number;
    if (confidence < 60) pctMultiplier = 0.5;
    else if (confidence <= 75) pctMultiplier = 0.75;
    else pctMultiplier = 1.0;

    const posSize = equity * this.settings.max_position_pct * pctMultiplier;
    return Math.min(posSize, 2000);
  }

  // ── Correlation-aware diversification ─────────────────────────────
  private canOpenPosition(signal: InternalSignal): boolean {
    const account = this.engine.getAccount();

    // Max positions
    if (account.positions.length >= this.settings.max_positions) return false;

    // No more than 4 positions in the same correlation group
    const group = getCorrelationGroup(signal.symbol);
    if (group) {
      const groupCount = account.positions.filter((p) =>
        group.includes(p.symbol),
      ).length;
      if (groupCount >= 4) return false;
    }

    // No more than 5 positions using the same strategy
    const strategyCount = account.positions.filter(
      (p) => p.strategy === signal.strategy,
    ).length;
    if (strategyCount >= 5) return false;

    // Total exposure should not exceed 80% of initial balance
    const totalExposure = account.positions.reduce(
      (sum, p) => sum + p.quantity,
      0,
    );
    if (totalExposure >= account.initial_balance * 0.93) return false;

    // Dynamic portfolio balance based on market regime
    const exposure = this.engine.getPortfolioExposure();
    const totalExp = exposure.longExposure + exposure.shortExposure;
    if (totalExp > 0) {
      const shortRatio = exposure.shortExposure / totalExp;
      const longRatio = exposure.longExposure / totalExp;
      // Max short ratio depends on Fear & Greed
      const regime = this.getRegimeFn ? this.getRegimeFn() : null;
      const fg = regime?.fearGreed ?? 50;

      let maxShortRatio: number;
      let maxLongRatio: number;

      if (fg < 15) {
        // Extreme fear (< 15): contrarian mode — already bottomed, favor longs
        // Shorting at the bottom is dangerous, flip bias toward longs
        maxShortRatio = 0.35; // limit shorts to 35%
        maxLongRatio = 0.75; // allow up to 75% longs
      } else if (fg < 25) {
        // High fear (15-24): cautious — reduce short bias, balanced
        maxShortRatio = 0.5; // limit shorts to 50%
        maxLongRatio = 0.6; // allow up to 60% longs
      } else {
        // Normal F&G-based calculation
        // F&G 25 → maxShort 67%, F&G 50 → 55%, F&G 90 → 35%
        maxShortRatio = Math.max(
          0.35,
          Math.min(0.75, 0.75 - (fg / 100) * 0.45),
        );
        maxLongRatio = 1 - maxShortRatio + 0.1;
      }

      if (shortRatio > maxShortRatio && signal.side === "short") return false;
      if (longRatio > maxLongRatio && signal.side === "long") return false;
    }

    // Never open opposite directions on same coin (long+short = pointless, just pays fees)
    if (
      account.positions.some(
        (p) => p.symbol === signal.symbol && p.side !== signal.side,
      )
    )
      return false;

    // Already have position in this symbol WITH THIS STRATEGY?
    // (DCA strategy is exempt from this check - it's handled separately)
    if (signal.strategy !== "DCA 분할매수") {
      if (
        account.positions.some(
          (p) => p.symbol === signal.symbol && p.strategy === signal.strategy,
        )
      )
        return false;
    }

    return true;
  }

  // ── Adaptive confidence threshold based on market regime ────────
  private getMinConfidence(
    regime: RegimeData | null,
    side?: "long" | "short",
  ): number {
    if (!regime) return 50;
    const fg = regime.fearGreed;

    // Extreme fear (< 15): contrarian — shorts need very high confidence, longs easier
    if (fg < 15) {
      return side === "short" ? 72 : 48;
    }
    // High fear (15-24): shorts still need higher confidence
    if (fg < 25) {
      return side === "short" ? 65 : 52;
    }
    // In bear market, require higher confidence to enter
    if (regime.regime === "bear") return 60;
    // Normal conditions
    return 50;
  }

  // ── Portfolio hedge protection ────────────────────────────────────
  private checkHedgeNeed(
    priceMap: Record<string, number>,
    regime: RegimeData | null,
  ): void {
    const exposure = this.engine.getPortfolioExposure();
    const account = this.engine.getAccount();
    const equity =
      account.balance + account.positions.reduce((s, p) => s + p.quantity, 0);

    // If portfolio is heavily skewed to one side (>50% of equity), add hedge
    const longPct = exposure.longExposure / equity;
    const shortPct = exposure.shortExposure / equity;

    // Too many longs, need a short hedge
    if (longPct > 0.5 && exposure.longCount > 3 && shortPct < 0.15) {
      const btcPrice = priceMap["BTC/USDT"];
      if (
        btcPrice &&
        !account.positions.some(
          (p) => p.symbol === "BTC/USDT" && p.side === "short",
        )
      ) {
        const hedgeSize = Math.min(equity * 0.1, 1000); // 10% hedge
        this.engine.openPosition({
          symbol: "BTC/USDT",
          side: "short",
          quantity: hedgeSize,
          entry_price: btcPrice,
          stop_loss: +(btcPrice * 1.05).toFixed(2),
          take_profit: +(btcPrice * 0.95).toFixed(2),
          strategy: "헤지 보호",
        });
        this.addSignal({
          strategy: "헤지 보호",
          symbol: "BTC/USDT",
          side: "short",
          confidence: 80,
          reason: `포트폴리오 롱 비중 ${(longPct * 100).toFixed(0)}% 과다, BTC 숏 헤지`,
          timestamp: Date.now(),
        });
      }
    }

    // Too many shorts, need a long hedge
    if (shortPct > 0.5 && exposure.shortCount > 3 && longPct < 0.15) {
      const btcPrice = priceMap["BTC/USDT"];
      if (
        btcPrice &&
        !account.positions.some(
          (p) => p.symbol === "BTC/USDT" && p.side === "long",
        )
      ) {
        const hedgeSize = Math.min(equity * 0.1, 1000);
        this.engine.openPosition({
          symbol: "BTC/USDT",
          side: "long",
          quantity: hedgeSize,
          entry_price: btcPrice,
          stop_loss: +(btcPrice * 0.95).toFixed(2),
          take_profit: +(btcPrice * 1.05).toFixed(2),
          strategy: "헤지 보호",
        });
        this.addSignal({
          strategy: "헤지 보호",
          symbol: "BTC/USDT",
          side: "long",
          confidence: 80,
          reason: `포트폴리오 숏 비중 ${(shortPct * 100).toFixed(0)}% 과다, BTC 롱 헤지`,
          timestamp: Date.now(),
        });
      }
    }
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

    this.tickCount++;

    // Update existing position prices
    this.engine.updatePrices(priceMap);

    // Check SL/TP triggers
    this.engine.checkTriggers(priceMap);

    // Daily loss circuit breaker: stop trading if daily loss > 3% of initial balance
    if (this.engine.isDailyLossExceeded(0.03)) {
      // Still update prices and check triggers above (to honor existing SL/TP)
      this.engine.snapshotEquity();
      return; // Don't open new positions
    }

    const account = this.engine.getAccount();
    const availableBalance = account.balance;

    const regime = this.getRegimeFn ? this.getRegimeFn() : null;
    // Collect ALL signals from ALL coins
    const allSignals: InternalSignal[] = [];

    for (const coin of COINS) {
      const history = this.priceHistory[coin.symbol];
      if (!history || history.length < 1) continue;

      const price = priceMap[coin.symbol];
      if (!price) continue;

      // Don't trade same symbol too frequently (60s cooldown) - skip on first 3 ticks
      if (this.tickCount > 3) {
        const lastTime = this.lastTradeTime[coin.symbol] || 0;
        if (Date.now() - lastTime < 60_000) continue;
      }

      // Skip coins with 3+ consecutive losses (cool off for 10 min)
      const consecutiveLosses = this.engine.getConsecutiveLosses(coin.symbol);
      if (consecutiveLosses >= 3) {
        const lastLossTime = this.lastTradeTime[coin.symbol] || 0;
        if (Date.now() - lastLossTime < 600_000) continue; // 10 min cooldown after 3 losses
      }

      const coinPrice = coinPriceMap[coin.symbol];
      const signals = this.getAllSignals(
        coin.symbol,
        coin.sector,
        history,
        price,
        regime,
        coinPrice,
      );

      // Filter by adaptive confidence threshold (side-aware in extreme fear)
      for (const signal of signals) {
        const minConf = this.getMinConfidence(regime, signal.side);
        if (signal.confidence >= minConf) {
          allSignals.push(signal);
        }
      }
    }

    // Check DCA opportunities on existing losing positions
    const dcaSignals = this.getDCASignals(priceMap, regime);
    allSignals.push(...dcaSignals);

    // Sort by confidence descending - pick best signals first
    allSignals.sort((a, b) => b.confidence - a.confidence);

    // Fill positions respecting diversification rules
    for (const signal of allSignals) {
      if (availableBalance < 100) break;
      if (!this.canOpenPosition(signal)) continue;

      const price = priceMap[signal.symbol];
      if (!price) continue;

      // Record signal for UI (always, even if we can't open)
      this.addSignal({
        strategy: signal.strategy,
        symbol: signal.symbol,
        side: signal.side,
        confidence: signal.confidence,
        reason: signal.reason,
        timestamp: Date.now(),
      });

      if (availableBalance < 100) continue;

      const posSize = this.getPositionSize(signal.confidence);

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

    // Partial profit taking: take 40% at halfway to TP
    for (const pos of this.engine.getAccount().positions) {
      if (this.partialClosedIds.has(pos.id)) continue;

      const price = priceMap[pos.symbol];
      if (!price) continue;

      const profitPct =
        pos.side === "long"
          ? (price - pos.entry_price) / pos.entry_price
          : (pos.entry_price - price) / pos.entry_price;

      const tpDistance =
        pos.side === "long"
          ? (pos.take_profit - pos.entry_price) / pos.entry_price
          : (pos.entry_price - pos.take_profit) / pos.entry_price;

      // If we've reached 50% of TP target but not yet at TP
      if (profitPct >= tpDistance * 0.5 && profitPct < tpDistance) {
        this.engine.partialClose(pos.id, 0.4, price);
        this.partialClosedIds.add(pos.id);
        this.addSignal({
          strategy: pos.strategy,
          symbol: pos.symbol,
          side: pos.side,
          confidence: 90,
          reason: `${(profitPct * 100).toFixed(1)}% 수익 도달, 40% 부분 익절`,
          timestamp: Date.now(),
        });
      }
    }

    // Portfolio hedge protection
    this.checkHedgeNeed(priceMap, regime);

    // Snapshot equity
    this.engine.snapshotEquity();
  }

  // ── DCA: Dollar Cost Averaging for losing positions ───────────────
  private getDCASignals(
    priceMap: Record<string, number>,
    regime: RegimeData | null,
  ): InternalSignal[] {
    const account = this.engine.getAccount();
    const signals: InternalSignal[] = [];

    for (const pos of account.positions) {
      const currentPrice = priceMap[pos.symbol];
      if (!currentPrice) continue;

      // Calculate unrealized PnL %
      let pnlPct: number;
      if (pos.side === "long") {
        pnlPct = (currentPrice - pos.entry_price) / pos.entry_price;
      } else {
        pnlPct = (pos.entry_price - currentPrice) / pos.entry_price;
      }

      // Only DCA when position is losing between -1% and -3%
      if (pnlPct < -0.01 && pnlPct > -0.03) {
        // Max 2 positions in same symbol same direction (original + 1 DCA)
        const sameSymbolSideCount = account.positions.filter(
          (p) => p.symbol === pos.symbol && p.side === pos.side,
        ).length;
        if (sameSymbolSideCount >= 2) continue;

        // Don't DCA against the regime
        if (pos.side === "long" && regime?.regime === "bear") continue;
        if (pos.side === "short" && regime?.regime === "bull") continue;

        const coin = COINS.find((c) => c.symbol === pos.symbol);
        const sector = coin?.sector ?? "";
        const history = this.priceHistory[pos.symbol];
        const { slPct, tpPct } = history
          ? adjustSlTp(0.03, 0.05, history, currentPrice)
          : { slPct: 0.03, tpPct: 0.05 };

        signals.push({
          symbol: pos.symbol,
          side: pos.side,
          strategy: "DCA 분할매수",
          confidence: 70,
          reason: `기존 포지션 ${(pnlPct * 100).toFixed(1)}% 손실 중, 평단가 개선 분할매수`,
          slPct,
          tpPct,
          sector,
        });
      }
    }

    return signals;
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

    // Balanced regime entry: mix trend + contrarian for true diversification
    // In bear: 60% short (trend), 40% long (mean reversion on oversold)
    // In bull: 60% long (trend), 40% short (mean reversion on overbought)
    if (regime && coinPrice) {
      const change = coinPrice.change24h;
      if (regime.regime === "bear") {
        // Coins dropping hard → short (trend following)
        if (change < -1) {
          const { slPct, tpPct } = adjustSlTp(
            0.03,
            0.06,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "레짐 적응형",
            confidence: Math.min(66, 56 + Math.abs(change)),
            reason: `약세장 추세추종: 24h ${change.toFixed(1)}% 하락 중`,
            slPct,
            tpPct,
          });
        }
        // Coins dropped TOO much → long (oversold bounce)
        if (change < -3) {
          const { slPct, tpPct } = adjustSlTp(
            0.02,
            0.04,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "레짐 적응형",
            confidence: Math.min(64, 54 + Math.abs(change) * 0.5),
            reason: `약세장 반등매매: 24h ${change.toFixed(1)}% 과매도, 단기 반등 기대`,
            slPct,
            tpPct,
          });
        }
        // Coins going UP in bear market → contrarian long (relative strength)
        if (change > 0.5) {
          const { slPct, tpPct } = adjustSlTp(
            0.03,
            0.06,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "모멘텀 돌파",
            confidence: Math.min(62, 54 + change * 2),
            reason: `약세장 역행 강세: 24h +${change.toFixed(1)}%, 상대적 강세`,
            slPct,
            tpPct,
          });
        }
      }
      if (regime.regime === "bull") {
        if (change > 1) {
          const { slPct, tpPct } = adjustSlTp(
            0.03,
            0.06,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "레짐 적응형",
            confidence: Math.min(66, 56 + change),
            reason: `강세장 추세추종: 24h +${change.toFixed(1)}% 상승 중`,
            slPct,
            tpPct,
          });
        }
        if (change > 4) {
          const { slPct, tpPct } = adjustSlTp(
            0.02,
            0.04,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "레짐 적응형",
            confidence: Math.min(64, 54 + change * 0.5),
            reason: `강세장 과열 조정: 24h +${change.toFixed(1)}% 과매수`,
            slPct,
            tpPct,
          });
        }
        if (change < -0.5) {
          const { slPct, tpPct } = adjustSlTp(
            0.03,
            0.06,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "모멘텀 돌파",
            confidence: Math.min(62, 54 + Math.abs(change) * 2),
            reason: `강세장 역행 약세: 24h ${change.toFixed(1)}%, 상대적 약세`,
            slPct,
            tpPct,
          });
        }
      }
      if (regime.regime === "sideways") {
        // Mean reversion both ways
        if (change > 2) {
          const { slPct, tpPct } = adjustSlTp(
            0.02,
            0.04,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "레짐 적응형",
            confidence: Math.min(64, 55 + change),
            reason: `횡보장 평균회귀: 24h +${change.toFixed(1)}% 숏`,
            slPct,
            tpPct,
          });
        }
        if (change < -2) {
          const { slPct, tpPct } = adjustSlTp(
            0.02,
            0.04,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "레짐 적응형",
            confidence: Math.min(64, 55 + Math.abs(change)),
            reason: `횡보장 평균회귀: 24h ${change.toFixed(1)}% 롱`,
            slPct,
            tpPct,
          });
        }
      }
    }

    // Instant entry: 24h change-based (works from first tick!)
    if (coinPrice) {
      const change = coinPrice.change24h;

      // Regime-aligned momentum: in bear market, short everything that's dropping
      if (regime?.regime === "bear" && change < -0.5) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.06, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "short",
          strategy: "모멘텀 돌파",
          confidence: Math.min(70, 55 + Math.abs(change) * 2),
          reason: `약세장 + 24h ${change.toFixed(1)}% 하락, 숏 진입`,
          slPct,
          tpPct,
        });
      }
      if (regime?.regime === "bull" && change > 0.5) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.06, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "long",
          strategy: "모멘텀 돌파",
          confidence: Math.min(70, 55 + change * 2),
          reason: `강세장 + 24h +${change.toFixed(1)}% 상승, 롱 진입`,
          slPct,
          tpPct,
        });
      }

      // Strong movers: if 24h change > 2%, ride the momentum
      if (change > 2 && regime?.regime !== "bear") {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.1, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "long",
          strategy: "모멘텀 돌파",
          confidence: Math.min(70, 55 + change),
          reason: `24h +${change.toFixed(1)}% 강한 상승 모멘텀`,
          slPct,
          tpPct,
        });
      }
      if (change < -2 && regime?.regime !== "bull") {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.1, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "short",
          strategy: "모멘텀 돌파",
          confidence: Math.min(70, 55 + Math.abs(change)),
          reason: `24h ${change.toFixed(1)}% 강한 하락 모멘텀`,
          slPct,
          tpPct,
        });
      }
      // Mean reversion: if 24h change > 4%, expect pullback
      if (change > 4 && regime?.regime !== "bull") {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "short",
          strategy: "RSI+BB 복합",
          confidence: Math.min(75, 60 + change * 0.5),
          reason: `24h +${change.toFixed(1)}% 과열, 조정 기대`,
          slPct,
          tpPct,
        });
      }
      if (change < -4 && regime?.regime !== "bear") {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "long",
          strategy: "RSI+BB 복합",
          confidence: Math.min(75, 60 + Math.abs(change) * 0.5),
          reason: `24h ${change.toFixed(1)}% 과매도, 반등 기대`,
          slPct,
          tpPct,
        });
      }
    }

    // Sector rotation: works from first tick with regime
    if (regime && history.length >= 1) {
      const r = this.sectorRotationStrategy(
        symbol,
        sector,
        history,
        currentPrice,
        regime,
      );
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.06, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // Regime-Aware Composite
    if (regime && history.length >= 30) {
      const r = this.regimeStrategy(symbol, history, currentPrice, regime);
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.06, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // Sector Rotation (longer history)
    if (regime && history.length >= 14) {
      const r = this.sectorRotationStrategy(
        symbol,
        sector,
        history,
        currentPrice,
        regime,
      );
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.06, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // MACD Cross (trend following)
    if (history.length >= 30) {
      const r = this.macdStrategy(history, regime);
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.04, 0.08, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // EMA Ribbon (trend following)
    if (history.length >= 55) {
      const r = this.emaRibbonStrategy(history, currentPrice, regime);
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.04, 0.08, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // Momentum Breakout
    if (history.length >= 20 && coinPrice) {
      const r = this.momentumBreakoutStrategy(
        history,
        currentPrice,
        coinPrice,
        regime,
      );
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.03, 0.1, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // RSI+BB Convergence (mean reversion)
    if (history.length >= 20) {
      const r = this.rsiBBStrategy(history, currentPrice, regime);
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // Bollinger Bands (mean reversion)
    if (history.length >= 20) {
      const r = this.bollingerStrategy(history, currentPrice, regime);
      if (r) {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({ ...r, symbol, sector, slPct, tpPct });
      }
    }

    // SMA Crossover (trend following)
    if (history.length >= 10) {
      const sma5 = sma(history, 5);
      const sma10 = sma(history, 10);

      if (currentPrice > sma5 && sma5 > sma10) {
        if (regime?.regime !== "bear") {
          const { slPct, tpPct } = adjustSlTp(
            0.04,
            0.08,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "long",
            strategy: "SMA 크로스오버",
            confidence: 55,
            reason: `SMA5(${sma5.toFixed(1)}) > SMA10(${sma10.toFixed(1)}), 상승 추세`,
            slPct,
            tpPct,
          });
        }
      }
      if (currentPrice < sma5 && sma5 < sma10) {
        if (regime?.regime !== "bull") {
          const { slPct, tpPct } = adjustSlTp(
            0.04,
            0.08,
            history,
            currentPrice,
          );
          signals.push({
            symbol,
            sector,
            side: "short",
            strategy: "SMA 크로스오버",
            confidence: 55,
            reason: `SMA5(${sma5.toFixed(1)}) < SMA10(${sma10.toFixed(1)}), 하락 추세`,
            slPct,
            tpPct,
          });
        }
      }
    }

    // RSI
    if (history.length >= 14) {
      const rsi = computeRSI(history);

      if (rsi < 30 && regime?.regime !== "bear") {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "long",
          strategy: "RSI 과매도",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} < 30, 과매도 반등 기대`,
          slPct,
          tpPct,
        });
      }
      if (rsi > 70 && regime?.regime !== "bull") {
        const { slPct, tpPct } = adjustSlTp(0.02, 0.04, history, currentPrice);
        signals.push({
          symbol,
          sector,
          side: "short",
          strategy: "RSI 과매수",
          confidence: 60,
          reason: `RSI ${rsi.toFixed(1)} > 70, 과매수 조정 기대`,
          slPct,
          tpPct,
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
      // Mean reversion: allow longs even in bear (that's the whole point)
      const distPct = ((middle - currentPrice) / middle) * 100;
      return {
        side: "long",
        strategy: "볼린저 밴드",
        confidence: Math.min(70, 50 + distPct * 5),
        reason: `가격(${currentPrice.toFixed(1)}) ≤ 하단밴드(${lower.toFixed(1)}), 평균회귀 기대`,
      };
    }

    if (currentPrice >= upper * 0.995) {
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

    // Strong buy: RSI < 35 AND price near lower BB (mean reversion - regime independent)
    if (rsi < 35 && currentPrice <= lower * 1.01) {
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
    const rsi = history.length >= 14 ? computeRSI(history) : 50;

    let regimeLabel = "";

    if (r === "bull") {
      // Bull: all sectors can long, but growth sectors get higher confidence
      const isGrowth =
        sector === "smart-contract" ||
        sector === "defi" ||
        sector === "layer2" ||
        sector === "ai";
      regimeLabel = "강세장";
      if (rsi < 60) {
        return {
          side: "long",
          strategy: "섹터 로테이션",
          confidence: isGrowth ? 68 : 58,
          reason: `${regimeLabel}: ${sector} 섹터${isGrowth ? " 성장" : ""}, RSI(${rsi.toFixed(0)}) 롱 진입`,
        };
      }
      return null;
    }

    if (r === "bear") {
      regimeLabel = "약세장";
      const isDefensive =
        sector === "store-of-value" ||
        sector === "payment" ||
        sector === "exchange";
      // Defensive sectors → long (safe haven buying)
      if (isDefensive && rsi <= 55) {
        return {
          side: "long",
          strategy: "섹터 로테이션",
          confidence: 63,
          reason: `${regimeLabel}: ${sector} 방어 섹터 롱, RSI(${rsi.toFixed(0)})`,
        };
      }
      // Growth sectors → short (they drop more in bear)
      if (!isDefensive && rsi >= 45) {
        return {
          side: "short",
          strategy: "섹터 로테이션",
          confidence: 65,
          reason: `${regimeLabel}: ${sector} 성장 섹터 숏, RSI(${rsi.toFixed(0)})`,
        };
      }
      return null;
    }

    // Sideways
    regimeLabel = "횡보장";
    const isStable =
      sector === "exchange" ||
      sector === "store-of-value" ||
      sector === "payment";
    if (rsi < 55) {
      return {
        side: "long",
        strategy: "섹터 로테이션",
        confidence: isStable ? 62 : 55,
        reason: `${regimeLabel}: ${sector} 섹터${isStable ? " 안정" : ""}, RSI(${rsi.toFixed(0)}) 저점 매수`,
      };
    }

    return null;
  }
}
