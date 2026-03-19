import type {
  PaperAccount,
  PaperPosition,
  PaperTrade,
  EquitySnapshot,
} from "./types";

const STORAGE_KEY = "iwcoin_paper";
const EQUITY_KEY = "iwcoin_equity";

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

export class PaperTradingEngine {
  private account: PaperAccount;

  constructor() {
    this.account = load();
  }

  init(balance: number): void {
    this.account = defaultAccount(balance);
    save(this.account);
    saveEquity([]);
  }

  openPosition(params: {
    symbol: string;
    side: "long" | "short";
    quantity: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    strategy: string;
  }): PaperPosition | null {
    const cost = params.quantity;
    if (cost > this.account.balance) return null;

    const pos: PaperPosition = {
      id: genId(),
      symbol: params.symbol,
      side: params.side,
      entry_price: params.entry_price,
      current_price: params.entry_price,
      quantity: params.quantity,
      stop_loss: params.stop_loss,
      take_profit: params.take_profit,
      strategy: params.strategy,
      opened_at: new Date().toISOString(),
    };

    this.account.balance -= cost;
    this.account.positions.push(pos);
    save(this.account);
    return pos;
  }

  closePosition(positionId: string, exit_price: number): PaperTrade | null {
    const idx = this.account.positions.findIndex((p) => p.id === positionId);
    if (idx === -1) return null;

    const pos = this.account.positions[idx];
    const priceDiff =
      pos.side === "long"
        ? exit_price - pos.entry_price
        : pos.entry_price - exit_price;
    const sizeInUnits = pos.quantity / pos.entry_price;
    const pnl = priceDiff * sizeInUnits;
    const pnl_pct = (priceDiff / pos.entry_price) * 100;

    const trade: PaperTrade = {
      id: genId(),
      symbol: pos.symbol,
      side: pos.side,
      entry_price: pos.entry_price,
      exit_price,
      quantity: pos.quantity,
      pnl: +pnl.toFixed(2),
      pnl_pct: +pnl_pct.toFixed(2),
      strategy: pos.strategy,
      opened_at: pos.opened_at,
      closed_at: new Date().toISOString(),
    };

    this.account.balance += pos.quantity + pnl;
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
    }
    if (changed) save(this.account);
  }

  checkTriggers(prices: Record<string, number>): PaperTrade[] {
    const closed: PaperTrade[] = [];
    const toClose: { id: string; price: number }[] = [];

    for (const pos of this.account.positions) {
      const price = prices[pos.symbol];
      if (price === undefined) continue;

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
}
