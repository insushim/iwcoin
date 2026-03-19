-- CryptoNexus Ultra Schema

CREATE TABLE trades (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy','sell')),
  order_type TEXT NOT NULL,
  amount DECIMAL NOT NULL,
  price DECIMAL NOT NULL,
  cost DECIMAL NOT NULL,
  fee DECIMAL DEFAULT 0,
  strategy TEXT NOT NULL,
  regime TEXT,
  signal_confidence DECIMAL,
  pnl DECIMAL,
  pnl_pct DECIMAL,
  hold_duration_minutes INT,
  exit_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE positions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  exchange TEXT NOT NULL,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  amount DECIMAL NOT NULL,
  entry_price DECIMAL NOT NULL,
  current_price DECIMAL,
  unrealized_pnl DECIMAL,
  unrealized_pnl_pct DECIMAL,
  stop_loss DECIMAL,
  take_profit_1 DECIMAL,
  take_profit_2 DECIMAL,
  take_profit_3 DECIMAL,
  trailing_stop DECIMAL,
  strategy TEXT NOT NULL,
  regime TEXT,
  status TEXT DEFAULT 'open',
  tp1_hit BOOLEAN DEFAULT false,
  tp2_hit BOOLEAN DEFAULT false,
  opened_at TIMESTAMPTZ DEFAULT NOW(),
  closed_at TIMESTAMPTZ,
  close_reason TEXT
);

CREATE TABLE regime_history (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  regime TEXT NOT NULL,
  confidence DECIMAL NOT NULL,
  fear_greed INT,
  adx DECIMAL,
  btc_price DECIMAL,
  details JSONB,
  detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE strategy_performance (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  strategy TEXT NOT NULL UNIQUE,
  total_trades INT DEFAULT 0,
  wins INT DEFAULT 0,
  losses INT DEFAULT 0,
  total_pnl DECIMAL DEFAULT 0,
  win_rate DECIMAL DEFAULT 0,
  avg_profit DECIMAL DEFAULT 0,
  avg_loss DECIMAL DEFAULT 0,
  profit_factor DECIMAL DEFAULT 0,
  sharpe_ratio DECIMAL DEFAULT 0,
  max_drawdown DECIMAL DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE balance_snapshots (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  exchange TEXT NOT NULL,
  total_usdt DECIMAL NOT NULL,
  free_usdt DECIMAL NOT NULL,
  used_usdt DECIMAL NOT NULL,
  total_btc_value DECIMAL,
  snapshot_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ml_predictions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  symbol TEXT NOT NULL,
  predicted TEXT NOT NULL,
  confidence DECIMAL NOT NULL,
  actual TEXT,
  is_correct BOOLEAN,
  model_version TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE ensemble_votes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  symbol TEXT NOT NULL,
  regime TEXT NOT NULL,
  votes JSONB NOT NULL,
  final_action TEXT NOT NULL,
  final_confidence DECIMAL NOT NULL,
  executed BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_trades_created ON trades(created_at DESC);
CREATE INDEX idx_trades_strategy ON trades(strategy);
CREATE INDEX idx_positions_status ON positions(status);
CREATE INDEX idx_regime_detected ON regime_history(detected_at DESC);
CREATE INDEX idx_balance_snapshot ON balance_snapshots(snapshot_at DESC);
