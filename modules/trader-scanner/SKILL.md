---
name: trader-scanner
description: Multi-timeframe NSE/BSE stock scanner identifying ORB, VWAP, EMA, RSI, MACD, Bollinger Squeeze, Volume, Relative Strength, 52W High, S/R, Chart Patterns, Gaps, and Momentum setups.
---

# Trader Scanner Skill (India — NSE / BSE)

## Supported Strategies
- `orb` (Opening Range Breakout)
- `vwap-breakout`
- `ema-crossover`
- `rsi-oversold`
- `macd-crossover`
- `bb-squeeze`
- `volume-breakout`
- `relative-strength` (Outperformance vs NIFTY 50)
- `52w-high`
- `sr-breakout`
- `chart-patterns`
- `gap`
- `momentum`
- `unusual-volume`

## Usage
```bash
python3 main.py scanner daily
python3 main.py scanner orb --timeframe 5m --universe banknifty
python3 main.py scanner volume-breakout --timeframe 15m
```

## Output
Writes structured ranked opportunities in INR to `trader/signals.json`.
