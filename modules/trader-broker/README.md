# Module 8: Indian Broker Integration (`trader-broker`)

Provides unified adapter interface for **Zerodha Kite Connect**, **Upstox API v2**, **Angel One SmartAPI**, **DhanHQ**, and **Paper Trading Engine** (default).

## Live Order Safety Gate
Live orders cannot execute without:
1. Complete order summary
2. Quantity
3. Entry price
4. Stop-loss
5. Target
6. Maximum estimated loss (INR)
7. Explicit user confirmation

## Unit Tests
```bash
python3 -m unittest modules/trader-broker/tests/test_broker.py
```
