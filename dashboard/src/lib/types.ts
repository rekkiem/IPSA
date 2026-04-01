// types/ipsa.ts — Tipos para el IPSA Agent Dashboard

export interface StockEntry {
  ticker:            string;
  name:              string;
  score:             number;
  signal:            string;
  is_excluded:       boolean;
  kill_reasons:      string[];
  thesis:            string;
  current_price:     number | null;
  dividend_yield:    number | null;
  spread:            number | null;
  roe:               number | null;
  debt_to_equity:    number | null;
  payout_ratio:      number | null;
  momentum_3m:       number | null;
  momentum_6m:       number | null;
  rsi:               number | null;
  max_drawdown:      number | null;
  volatility_annual: number | null;
  sharpe_ratio:      number | null;
  above_sma50:       boolean | null;
  above_sma200:      boolean | null;
  factor_dividend:   number | null;
  factor_quality:    number | null;
  factor_momentum:   number | null;
  factor_risk:       number | null;
  entry_low:         number | null;
  entry_high:        number | null;
  stop_loss:         number | null;
  resistance:        number | null;
  weight_pct:        number | null;
  horizon:           string | null;
  market_cap:        number | null;
  pe_ratio:          number | null;
  pb_ratio:          number | null;
  bb_position:       number | null;
  macd_histogram:    number | null;
  rank:              number;
  // ML fields (optional)
  predicted_return_21d?: number;
  direction?:            string;
  confidence?:           string;
  signal_ml?:            string;
}

export interface MacroData {
  usdclp:         number | null;
  risk_free_rate: number;
  inflation:      number;
  timestamp:      string;
}

export interface RegimeData {
  regime:            'BULL' | 'BEAR' | 'NEUTRAL';
  confidence:        number;
  ipsa_momentum_3m:  number | null;
  ipsa_above_sma50:  boolean | null;
  ipsa_above_sma200: boolean | null;
  regime_ml?:        string;
  regime_prob_bull?: number;
}

export interface ChangesData {
  changed:     boolean;
  new_entries: string[];
  exits:       string[];
  alert:       string | null;
}

export interface DailyReport {
  date:        string;
  macro:       MacroData;
  regime:      RegimeData;
  changes:     ChangesData;
  top5:        StockEntry[];
  ranked_all:  StockEntry[];
}

export type SignalType = 'COMPRAR' | 'ESPERAR' | 'EVITAR';
export type RegimeType = 'BULL' | 'BEAR' | 'NEUTRAL';
