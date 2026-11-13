---
name: trader-entry
description: Evaluates completed candles for VWAP position, EMA alignment, volume confirmation, S/R, and R:R; outputs WAIT, WATCH, ENTRY TRIGGERED, or SETUP INVALIDATED.
---

# Trader Entry Timing Engine Skill

Never declares a breakout on an incomplete forming candle.

## Usage
```bash
python3 main.py entry RELIANCE --timeframe 15m
```
