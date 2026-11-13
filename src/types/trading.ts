export type NavSection =
  | 'overview'
  | 'scanner'
  | 'technical'
  | 'fundamental'
  | 'news'
  | 'backtest'
  | 'portfolio'
  | 'alerts';

export interface CandleBar {
  timestamp: number;
  time: number | string;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SearchSymbolResult {
  symbol: string;
  name: string;
  series: string;
  isin: string;
  exchange: string;
  sector: string;
}

export interface RiskConfig {
  total_capital_inr: number;
  max_risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  min_risk_reward_ratio: number;
  max_trades_per_day: number;
  max_open_positions: number;
  max_sector_exposure_pct: number;
  max_portfolio_exposure_pct: number;
  paper_trading_enabled: boolean;
  fno_enabled: boolean;
}
