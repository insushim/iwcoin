import { create } from "zustand";
import type {
  CoinPrice,
  FearGreedData,
  FearGreedHistoryItem,
  PaperAccount,
  PaperPosition,
  PaperTrade,
  EquitySnapshot,
  RegimeData,
  TradingSettings,
  PerformanceStats,
} from "./types";
import { DEFAULT_SETTINGS } from "./types";
import { PaperTradingEngine } from "./paper-trading";
import { AutoStrategyRunner } from "./auto-strategy";
import type { StrategySignal } from "./auto-strategy";
import {
  fetchPrices,
  fetchFearGreed,
  fetchFearGreedHistory,
  fetchMarketChart,
  fetchGlobalData,
} from "./api";

const engine = new PaperTradingEngine();
let strategyRunner: AutoStrategyRunner | null = null;
let priceInterval: ReturnType<typeof setInterval> | null = null;
let fngInterval: ReturnType<typeof setInterval> | null = null;

interface DashboardStore {
  // Real data
  prices: CoinPrice[];
  fearGreed: FearGreedData;
  fearGreedHistory: FearGreedHistoryItem[];
  btcDominance: number;
  totalMarketCap: number;
  btcChart: { date: string; price: number }[];

  // Paper trading
  account: PaperAccount;
  equityHistory: EquitySnapshot[];

  // Trading settings & performance
  tradingSettings: TradingSettings;
  performanceStats: PerformanceStats;
  recentSignals: StrategySignal[];

  // Actions
  openPosition: (params: {
    symbol: string;
    side: "long" | "short";
    quantity: number;
    entry_price: number;
    stop_loss: number;
    take_profit: number;
    strategy: string;
  }) => PaperPosition | null;
  closePosition: (id: string, price: number) => PaperTrade | null;
  resetAccount: (balance: number) => void;
  updateTradingSettings: (settings: TradingSettings) => void;

  // Auto strategy
  isAutoTrading: boolean;
  toggleAutoTrading: () => void;

  // UI
  loading: boolean;
  error: string | null;
  sidebarOpen: boolean;
  toggleSidebar: () => void;

  // Init
  initialize: () => Promise<void>;
  refreshPrices: () => Promise<void>;

  // Regime
  regime: RegimeData;
}

export const useDashboardStore = create<DashboardStore>((set, get) => ({
  prices: [],
  fearGreed: { value: 50, classification: "Neutral" },
  fearGreedHistory: [],
  btcDominance: 0,
  totalMarketCap: 0,
  btcChart: [],

  account: engine.getAccount(),
  equityHistory: engine.getEquityHistory(),

  tradingSettings: engine.getSettings(),
  performanceStats: engine.getPerformanceStats(),
  recentSignals: [],

  regime: { regime: "sideways", fearGreed: 50, btcDominance: 0 },

  isAutoTrading: false,
  loading: true,
  error: null,
  sidebarOpen: false,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  openPosition: (params) => {
    const pos = engine.openPosition(params);
    if (pos) {
      set({
        account: engine.getAccount(),
        equityHistory: engine.getEquityHistory(),
        performanceStats: engine.getPerformanceStats(),
      });
    }
    return pos;
  },

  closePosition: (id, price) => {
    const trade = engine.closePosition(id, price);
    if (trade) {
      set({
        account: engine.getAccount(),
        equityHistory: engine.getEquityHistory(),
        performanceStats: engine.getPerformanceStats(),
      });
    }
    return trade;
  },

  resetAccount: (balance) => {
    engine.reset(balance);
    set({
      account: engine.getAccount(),
      equityHistory: engine.getEquityHistory(),
      performanceStats: engine.getPerformanceStats(),
      recentSignals: [],
    });
  },

  updateTradingSettings: (settings: TradingSettings) => {
    engine.updateSettings(settings);
    if (strategyRunner) {
      strategyRunner.setSettings(settings);
    }
    set({ tradingSettings: engine.getSettings() });
  },

  toggleAutoTrading: () => {
    const { isAutoTrading } = get();
    if (isAutoTrading) {
      strategyRunner?.stop();
      strategyRunner = null;
      set({ isAutoTrading: false });
    } else {
      strategyRunner = new AutoStrategyRunner(engine);
      strategyRunner.setSettings(engine.getSettings());
      strategyRunner.start(
        () => get().prices,
        () => ({
          regime: get().regime.regime,
          fearGreed: get().regime.fearGreed,
        }),
      );
      set({ isAutoTrading: true });
    }
  },

  refreshPrices: async () => {
    try {
      const prices = await fetchPrices();
      const priceMap: Record<string, number> = {};
      for (const p of prices) priceMap[p.symbol] = p.price;
      engine.updatePrices(priceMap);
      engine.checkTriggers(priceMap);
      engine.snapshotEquity();

      const fg = get().fearGreed;
      const bd = get().btcDominance;
      const regime: RegimeData["regime"] =
        fg.value > 60 ? "bull" : fg.value < 40 ? "bear" : "sideways";

      const updatedState: Partial<DashboardStore> = {
        prices,
        account: engine.getAccount(),
        equityHistory: engine.getEquityHistory(),
        performanceStats: engine.getPerformanceStats(),
        regime: { regime, fearGreed: fg.value, btcDominance: bd },
      };

      if (strategyRunner) {
        updatedState.recentSignals = strategyRunner.getRecentSignals();
      }

      set(updatedState as DashboardStore);
    } catch (e) {
      set({ error: "가격 데이터 로딩 실패" });
    }
  },

  initialize: async () => {
    set({ loading: true, error: null });
    try {
      const [prices, fg, fgHistory, globalData, btcChart] = await Promise.all([
        fetchPrices(),
        fetchFearGreed(),
        fetchFearGreedHistory(),
        fetchGlobalData(),
        fetchMarketChart("bitcoin", 90),
      ]);

      const priceMap: Record<string, number> = {};
      for (const p of prices) priceMap[p.symbol] = p.price;
      engine.updatePrices(priceMap);
      engine.snapshotEquity();

      const regime: RegimeData["regime"] =
        fg.value > 60 ? "bull" : fg.value < 40 ? "bear" : "sideways";

      set({
        prices,
        fearGreed: fg,
        fearGreedHistory: fgHistory,
        btcDominance: globalData.btc_dominance,
        totalMarketCap: globalData.total_market_cap,
        btcChart,
        account: engine.getAccount(),
        equityHistory: engine.getEquityHistory(),
        performanceStats: engine.getPerformanceStats(),
        regime: {
          regime,
          fearGreed: fg.value,
          btcDominance: globalData.btc_dominance,
        },
        loading: false,
      });

      // Auto-refresh prices every 30s
      if (priceInterval) clearInterval(priceInterval);
      priceInterval = setInterval(() => get().refreshPrices(), 30_000);

      // Auto-refresh F&G every 5 min
      if (fngInterval) clearInterval(fngInterval);
      fngInterval = setInterval(async () => {
        try {
          const [fg2, fgH2, gd2] = await Promise.all([
            fetchFearGreed(),
            fetchFearGreedHistory(),
            fetchGlobalData(),
          ]);
          const r: RegimeData["regime"] =
            fg2.value > 60 ? "bull" : fg2.value < 40 ? "bear" : "sideways";
          set({
            fearGreed: fg2,
            fearGreedHistory: fgH2,
            btcDominance: gd2.btc_dominance,
            totalMarketCap: gd2.total_market_cap,
            regime: {
              regime: r,
              fearGreed: fg2.value,
              btcDominance: gd2.btc_dominance,
            },
          });
        } catch {}
      }, 300_000);
    } catch (e) {
      set({
        loading: false,
        error:
          "데이터를 불러오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
      });
    }
  },
}));
