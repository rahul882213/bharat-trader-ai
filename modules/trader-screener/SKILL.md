---
name: trader-screener
description: Imports Screener.in CSV stock screens and Excel (.xlsx) company financial workbooks into Bharat Trader AI with deduplication, ISIN mapping, business/order-book notes, and missing-data auditing.
---

# Screener.in Integration Skill
1. Use `import_screener_xlsx()` for full company workbooks (`Data Sheet`, `Profit & Loss`, `Quarters`, `Balance Sheet`, `Cash Flow`).
2. Use `import_screener_csv()` for single or multi-company Screener.in exported CSV tables.
3. Use `update_business_notes()` to record order book, order inflow, execution timelines, customer concentration, and competitive positioning.
4. Always surface `source`, `statement_scope`, `reporting_period`, `imported_at`, and `missing_fields`.
