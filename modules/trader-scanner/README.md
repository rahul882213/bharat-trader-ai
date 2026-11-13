# Module 1: Indian Stock Scanner (`trader-scanner`)

Scans NSE and BSE equity universes (`nifty50`, `banknifty`, `finnifty`, `niftynext50`, `nifty100`, `midcap_smallcap`, `all`) across `1m`, `5m`, `15m`, `30m`, `1h`, and `1d` timeframes.

## Features
- 14 quantitative breakout, mean-reversion, pattern, and relative-strength scans
- Real market data with explicit provider attribution (`Yahoo Finance (Unofficial)` or Broker API)
- Ranked setup scoring with human-readable reasons
- Writes pipeline output to `trader/signals.json`

## Configuration
See `config.example.json` for default timeframe, universe, and volume thresholds.

## Running Unit Tests
```bash
python3 -m unittest modules/trader-scanner/tests/test_scanner.py
```
