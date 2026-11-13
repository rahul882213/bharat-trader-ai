# Module 12: Screener.in Data Integration

## Purpose
Integrates Screener.in company financial exports (`.xlsx` workbooks and `.csv` stock screens) into the central Bharat Trader AI database, linking records cleanly via ISIN / NSE symbol / BSE code.

## Compliance Rules
- Never assumes an official public Screener.in API.
- Never invents endpoints or bypasses login/paywalls.
- Supports direct user-exported CSV and Excel (`.xlsx`) import as the primary data source.
- Provides a pluggable `FundamentalExternalAdapter` for authorized providers and an optional, explicitly labelled `ScreenerPublicPageAdapter` for public pages.
- Explicitly audits and surfaces missing financial fields rather than fabricating numbers.
