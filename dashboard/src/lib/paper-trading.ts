import type {
  PaperAccount,
  PaperPosition,
  PaperTrade,
  EquitySnapshot,
  TradingSettings,
  PerformanceStats,
} from "./types";
import { DEFAULT_SETTINGS } from "./types";

const STORAGE_KEY = "iwcoin_paper";
const EQUITY_KEY = "iwcoin_equity";
const SETTINGS_KEY = "iwcoin_settings";

function genId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function load(): PaperAccount {
  if (typeof window === "undefined") return defaultAccount(10000);
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return defaultAccount(10000);
}

function save(account: PaperAccount): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(account));
}

function defaultAccount(balance: number): PaperAccount {
  return {
    balance,
    initial_balance: balance,
    positions: [],
    trade_history: [],
    created_at: new Date().toISOString(),
  };
}

function loadEquity(): EquitySnapshot[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(EQUITY_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return [];
}

function saveEquity(snapshots: EquitySnapshot[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(EQUITY_KEY, JSON.stringify(snapshots));
}

function loadSettings(): TradingSettings {
  if (typeof window === "undefined") return { ...DEFAULT_SETTINGS };
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {}
  return { ...DEFAULT_SETTINGS };
}

function saveSettings(settings: TradingSettings): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

export class PaperTradingEngine {
  private account: PaperAccount;
  private settings: TradingSettings;

  constructor(settings?: TradingSettings) {
    this.account = load();
    this.settings = settings ?? loadSettings();
  }

  init(balance: number): void {
    this.account = defaultAccount(balance);
    save(this.account);
    saveEquity([]);
  }

  updateSettings(settings: TradingSettings): void {
    this.settings = { ...settings };
    saveSettings(this.settings);
  }

  getSettings(): TradingSettings {
    return { ...this.settings };
  }

  openPosition(params: {
    symbol: string;
    side: "long" | "short";
    quantity: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    strategy: string;
    leverage?: number;
  }): PaperPosition | null {
    // Risk limit: max concurrent positions
    if (this.account.positions.length >= this.settings.max_positions)
      return null;

    // Risk limit: max position size as % of balance
    const maxCost = this.account.balance * this.settings.max_position_pct;
    if (params.quantity > maxCost) return null;

    // Risk limit: check drawdown
    if (!this.checkRiskLimits()) return null;

    const leverage = params.leverage ?? 1;
    const { fee_rate, slippage_rate } = this.settings;

    // Apply slippage to entry price
    const slippageMultiplier =
      params.side === "long" ? 1 + slippage_rate : 1 - slippage_rate;
    const simulatedEntry = params.entry_price * slippageMultiplier;

    // Calculate entry fee
    const entryFee = params.quantity * fee_rate;

    const totalCost = params.quantity + entryFee;
    if (totalCost > this.account.balance) return null;

    const pos: PaperPosition = {
      id: genId(),
      symbol: params.symbol,
      side: params.side,
      entry_price: simulatedEntry,
      current_price: params.entry_price,
      quantity: params.quantity,
      stop_loss: params.stop_loss,
      take_profit: params.take_profit,
      strategy: params.strategy,
      opened_at: new Date().toISOString(),
      fee: entryFee,
      leverage,
      trailing_stop: 0,
      highest_price: params.entry_price,
      lowest_price: params.entry_price,
    };

    this.account.balance -= totalCost;
    this.account.positions.push(pos);
    save(this.account);
    return pos;
  }

  closePosition(positionId: string, exit_price: number): PaperTrade | null {
    const idx = this.account.positions.findIndex((p) => p.id === positionId);
    if (idx === -1) return null;

    const pos = this.account.positions[idx];
    const { fee_rate, slippage_rate } = this.settings;

    // Apply slippage to exit price
    const slippageMultiplier =
      pos.side === "long" ? 1 - slippage_rate : 1 + slippage_rate;
    const simulatedExit = exit_price * slippageMultiplier;

    // Calculate exit fee
    const exitFee = pos.quantity * fee_rate;

    // Backward compat: old positions without fee field
    const entryFee = pos.fee ?? 0;

    // PnL based on simulated prices (slippage already baked into entry_price)
    const priceDiff =
      pos.side === "long"
        ? simulatedExit - pos.entry_price
        : pos.entry_price - simulatedExit;
    const sizeInUnits = pos.quantity / pos.entry_price;
    const pnl = priceDiff * sizeInUnits;
    const pnl_pct = (priceDiff / pos.entry_price) * 100;

    // Slippage cost = difference between raw and simulated on both sides
    const entrySlippage =
      Math.abs(pos.entry_price - exit_price * (pos.side === "long" ? 1 : 1)) *
      0; // already in entry_price
    const exitSlippage = Math.abs(exit_price - simulatedExit) * sizeInUnits;
    const entrySlippageCost =
      pos.entry_price !== 0
        ? Math.abs(pos.entry_price * slippage_rate) * sizeInUnits
        : 0;
    const totalSlippage = entrySlippageCost + exitSlippage;

    const netPnl = pnl - entryFee - exitFee;

    const trade: PaperTrade = {
      id: genId(),
      symbol: pos.symbol,
      side: pos.side,
      entry_price: pos.entry_price,
      exit_price: simulatedExit,
      quantity: pos.quantity,
      pnl: +pnl.toFixed(2),
      pnl_pct: +pnl_pct.toFixed(2),
      strategy: pos.strategy,
      opened_at: pos.opened_at,
      closed_at: new Date().toISOString(),
      entry_fee: +entryFee.toFixed(4),
      exit_fee: +exitFee.toFixed(4),
      slippage: +totalSlippage.toFixed(4),
      net_pnl: +netPnl.toFixed(2),
    };

    this.account.balance += pos.quantity + pnl - exitFee;
    this.account.positions.splice(idx, 1);
    this.account.trade_history.push(trade);
    save(this.account);
    return trade;
  }

  updatePrices(prices: Record<string, number>): void {
    let changed = false;
    for (const pos of this.account.positions) {
      const p = prices[pos.symbol];
      if (p !== undefined && p !== pos.current_price) {
        pos.current_price = p;
        changed = true;
      }
      if (p !== undefined) {
        if (pos.side === "long") {
          if (p > (pos.highest_price ?? pos.entry_price)) pos.highest_price = p;
        } else {
          if (p < (pos.lowest_price ?? pos.entry_price)) pos.lowest_price = p;
        }
      }
    }
    if (changed) save(this.account);
  }

  checkTriggers(prices: Record<string, number>): PaperTrade[] {
    const closed: PaperTrade[] = [];
    const toClose: { id: string; price: number }[] = [];

    for (const pos of this.account.positions) {
      const price = prices[pos.symbol];
      if (price === undefined) continue;

      // Trailing stop: if price has moved 2% in profit direction, set trailing stop at 1.5% behind peak
      const profitPct =
        pos.side === "long"
          ? (price - pos.entry_price) / pos.entry_price
          : (pos.entry_price - price) / pos.entry_price;

      if (profitPct > 0.02) {
        // Activate trailing stop
        if (pos.side === "long") {
          const trailingPrice = (pos.highest_price ?? price) * 0.985; // 1.5% below peak
          if (trailingPrice > pos.stop_loss) {
            pos.trailing_stop = trailingPrice;
          }
          if (
            price <= (pos.trailing_stop ?? 0) &&
            (pos.trailing_stop ?? 0) > 0
          ) {
            toClose.push({ id: pos.id, price });
            continue; // skip normal SL/TP check
          }
        } else {
          const trailingPrice = (pos.lowest_price ?? price) * 1.015; // 1.5% above trough
          if (trailingPrice < pos.stop_loss) {
            pos.trailing_stop = trailingPrice;
          }
          if (
            price >= (pos.trailing_stop ?? 0) &&
            (pos.trailing_stop ?? 0) > 0
          ) {
            toClose.push({ id: pos.id, price });
            continue;
          }
        }
      }

      if (pos.side === "long") {
        if (price <= pos.stop_loss || price >= pos.take_profit) {
          toClose.push({ id: pos.id, price });
        }
      } else {
        if (price >= pos.stop_loss || price <= pos.take_profit) {
          toClose.push({ id: pos.id, price });
        }
      }
    }

    for (const { id, price } of toClose) {
      const trade = this.closePosition(id, price);
      if (trade) closed.push(trade);
    }

    return closed;
  }

  getAccount(): PaperAccount {
    return { ...this.account };
  }

  getTotalEquity(): number {
    let equity = this.account.balance;
    for (const pos of this.account.positions) {
      const priceDiff =
        pos.side === "long"
          ? pos.current_price - pos.entry_price
          : pos.entry_price - pos.current_price;
      const sizeInUnits = pos.quantity / pos.entry_price;
      equity += pos.quantity + priceDiff * sizeInUnits;
    }
    return equity;
  }

  getEquityHistory(): EquitySnapshot[] {
    return loadEquity();
  }

  snapshotEquity(): void {
    const snapshots = loadEquity();
    const today = new Date().toISOString().slice(0, 10);
    const equity = this.getTotalEquity();

    const existing = snapshots.findIndex((s) => s.date === today);
    if (existing >= 0) {
      snapshots[existing].equity = equity;
    } else {
      snapshots.push({ date: today, equity });
    }

    // Keep last 90 days
    while (snapshots.length > 90) snapshots.shift();
    saveEquity(snapshots);
  }

  reset(balance: number): void {
    this.init(balance);
  }

  getUnrealizedPnl(pos: PaperPosition): number {
    const priceDiff =
      pos.side === "long"
        ? pos.current_price - pos.entry_price
        : pos.entry_price - pos.current_price;
    const sizeInUnits = pos.quantity / pos.entry_price;
    return priceDiff * sizeInUnits;
  }

  /**
   * Check if risk limits allow continued trading.
   * Returns false if max drawdown has been exceeded.
   */
  checkRiskLimits(): boolean {
    const equity = this.getTotalEquity();
    const drawdownPct =
      (this.account.initial_balance - equity) / this.account.initial_balance;
    return drawdownPct < this.settings.max_drawdown_pct;
  }

  /**
   * Calculate today's realized + unrealized P&L.
   */
  getDailyPnl(): {
    realized: number;
    unrealized: number;
    total: number;
    trades_today: number;
  } {
    const today = new Date().toISOString().slice(0, 10);
    const todayTrades = this.account.trade_history.filter((t) =>
      t.closed_at.startsWith(today),
    );
    const realized = todayTrades.reduce((s, t) => s + (t.net_pnl ?? t.pnl), 0);

    let unrealized = 0;
    for (const pos of this.account.positions) {
      unrealized += this.getUnrealizedPnl(pos);
    }

    return {
      realized: +realized.toFixed(2),
      unrealized: +unrealized.toFixed(2),
      total: +(realized + unrealized).toFixed(2),
      trades_today: todayTrades.length,
    };
  }

  /**
   * Returns true if today's total P&L loss exceeds the given limit percentage
   * of initial balance. Used by strategy runner to halt trading.
   */
  isDailyLossExceeded(limitPct: number = 0.03): boolean {
    const { total } = this.getDailyPnl();
    const threshold = -limitPct * this.account.initial_balance;
    return total < threshold;
  }

  /**
   * Count consecutive losses for a symbol from the most recent trade backwards.
   */
  getConsecutiveLosses(symbol: string): number {
    const symbolTrades = this.account.trade_history.filter(
      (t) => t.symbol === symbol,
    );
    let count = 0;
    for (let i = symbolTrades.length - 1; i >= 0; i--) {
      const pnl = symbolTrades[i].net_pnl ?? symbolTrades[i].pnl;
      if (pnl < 0) {
        count++;
      } else {
        break;
      }
    }
    return count;
  }

  /**
   * Close a percentage (0-1) of a position. Returns the trade record for
   * the closed portion; the remaining position stays open with reduced quantity.
   */
  partialClose(
    positionId: string,
    percentage: number,
    exit_price: number,
  ): PaperTrade | null {
    if (percentage <= 0 || percentage > 1) return null;
    if (percentage === 1) return this.closePosition(positionId, exit_price);

    const idx = this.account.positions.findIndex((p) => p.id === positionId);
    if (idx === -1) return null;

    const pos = this.account.positions[idx];
    const closedQuantity = pos.quantity * percentage;
    const remainingQuantity = pos.quantity - closedQuantity;

    const { fee_rate, slippage_rate } = this.settings;

    // Apply slippage to exit price
    const slippageMultiplier =
      pos.side === "long" ? 1 - slippage_rate : 1 + slippage_rate;
    const simulatedExit = exit_price * slippageMultiplier;

    // Fees proportional to closed portion
    const entryFee = (pos.fee ?? 0) * percentage;
    const exitFee = closedQuantity * fee_rate;

    // PnL for closed portion
    const priceDiff =
      pos.side === "long"
        ? simulatedExit - pos.entry_price
        : pos.entry_price - simulatedExit;
    const sizeInUnits = closedQuantity / pos.entry_price;
    const pnl = priceDiff * sizeInUnits;
    const pnl_pct = (priceDiff / pos.entry_price) * 100;

    const exitSlippage = Math.abs(exit_price - simulatedExit) * sizeInUnits;
    const entrySlippageCost =
      pos.entry_price !== 0
        ? Math.abs(pos.entry_price * slippage_rate) * sizeInUnits
        : 0;
    const totalSlippage = entrySlippageCost + exitSlippage;

    const netPnl = pnl - entryFee - exitFee;

    const trade: PaperTrade = {
      id: genId(),
      symbol: pos.symbol,
      side: pos.side,
      entry_price: pos.entry_price,
      exit_price: simulatedExit,
      quantity: closedQuantity,
      pnl: +pnl.toFixed(2),
      pnl_pct: +pnl_pct.toFixed(2),
      strategy: pos.strategy,
      opened_at: pos.opened_at,
      closed_at: new Date().toISOString(),
      entry_fee: +entryFee.toFixed(4),
      exit_fee: +exitFee.toFixed(4),
      slippage: +totalSlippage.toFixed(4),
      net_pnl: +netPnl.toFixed(2),
    };

    // Update remaining position
    pos.quantity = remainingQuantity;
    pos.fee = (pos.fee ?? 0) * (1 - percentage);

    // Credit closed portion back to balance
    this.account.balance += closedQuantity + pnl - exitFee;
    this.account.trade_history.push(trade);
    save(this.account);
    return trade;
  }

  /**
   * Get portfolio exposure statistics across all open positions.
   */
  getPortfolioExposure(): {
    longExposure: number;
    shortExposure: number;
    netExposure: number;
    longCount: number;
    shortCount: number;
  } {
    let longExposure = 0;
    let shortExposure = 0;
    let longCount = 0;
    let shortCount = 0;

    for (const pos of this.account.positions) {
      if (pos.side === "long") {
        longExposure += pos.quantity;
        longCount++;
      } else {
        shortExposure += pos.quantity;
        shortCount++;
      }
    }

    return {
      longExposure: +longExposure.toFixed(2),
      shortExposure: +shortExposure.toFixed(2),
      netExposure: +(longExposure - shortExposure).toFixed(2),
      longCount,
      shortCount,
    };
  }

  /**
   * Calculate comprehensive performance statistics from trade history.
   */
  getPerformanceStats(): PerformanceStats {
    const trades = this.account.trade_history;
    const total_trades = trades.length;

    if (total_trades === 0) {
      return {
        total_trades: 0,
        win_rate: 0,
        profit_factor: 0,
        avg_win: 0,
        avg_loss: 0,
        max_drawdown: 0,
        max_drawdown_pct: 0,
        sharpe_ratio: 0,
        total_pnl: 0,
        total_fees: 0,
        best_trade: 0,
        worst_trade: 0,
      };
    }

    // Use net_pnl if available, fall back to pnl for old trades
    const netPnls = trades.map((t) => t.net_pnl ?? t.pnl);
    const wins = netPnls.filter((p) => p > 0);
    const losses = netPnls.filter((p) => p < 0);

    const grossProfit = wins.reduce((s, v) => s + v, 0);
    const grossLoss = Math.abs(losses.reduce((s, v) => s + v, 0));

    const total_pnl = netPnls.reduce((s, v) => s + v, 0);
    const total_fees = trades.reduce(
      (s, t) => s + (t.entry_fee ?? 0) + (t.exit_fee ?? 0),
      0,
    );

    // Max drawdown: track peak equity through trade sequence
    let peak = this.account.initial_balance;
    let maxDd = 0;
    let runningEquity = this.account.initial_balance;
    for (const pnl of netPnls) {
      runningEquity += pnl;
      if (runningEquity > peak) peak = runningEquity;
      const dd = peak - runningEquity;
      if (dd > maxDd) maxDd = dd;
    }

    // Sharpe ratio: (avg daily return / std dev) * sqrt(365)
    // Approximate daily returns from individual trade returns
    const returns = netPnls.map(
      (p, i) =>
        p /
        (this.account.initial_balance +
          netPnls.slice(0, i).reduce((s, v) => s + v, 0)),
    );
    const avgReturn =
      returns.length > 0
        ? returns.reduce((s, v) => s + v, 0) / returns.length
        : 0;
    const variance =
      returns.length > 1
        ? returns.reduce((s, v) => s + (v - avgReturn) ** 2, 0) /
          (returns.length - 1)
        : 0;
    const stdDev = Math.sqrt(variance);
    const sharpe_ratio = stdDev > 0 ? (avgReturn / stdDev) * Math.sqrt(365) : 0;

    return {
      total_trades,
      win_rate: wins.length / total_trades,
      profit_factor:
        grossLoss > 0
          ? grossProfit / grossLoss
          : grossProfit > 0
            ? Infinity
            : 0,
      avg_win: wins.length > 0 ? grossProfit / wins.length : 0,
      avg_loss: losses.length > 0 ? grossLoss / losses.length : 0,
      max_drawdown: +maxDd.toFixed(2),
      max_drawdown_pct: peak > 0 ? +(maxDd / peak).toFixed(4) : 0,
      sharpe_ratio: +sharpe_ratio.toFixed(2),
      total_pnl: +total_pnl.toFixed(2),
      total_fees: +total_fees.toFixed(4),
      best_trade: Math.max(...netPnls),
      worst_trade: Math.min(...netPnls),
    };
  }
}
