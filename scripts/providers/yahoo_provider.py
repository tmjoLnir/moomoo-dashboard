"""Yahoo Finance fallback provider (free, no account, runs on GitHub-hosted runners).

Used when your PC (with moomoo OpenD) is off, so the dashboard keeps refreshing.
The page labels which provider produced the data.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

UNIVERSE_FILE = Path(__file__).resolve().parent.parent / "universe_us_large.txt"


class YahooProvider:
    name = "yahoo"
    label = "Yahoo Finance (fallback)"
    shortlist_size = None  # price history is cheap in bulk, so score the whole universe

    def __init__(self):
        import yfinance as yf

        self.yf = yf
        self._bars: dict[str, pd.DataFrame] = {}

    def close(self):
        pass

    def candidates(self, universe_size: int = 120) -> list[dict]:
        # strip "# comment" text per line *before* splitting, so comment words never become tickers
        lines = (ln.split("#", 1)[0] for ln in UNIVERSE_FILE.read_text().splitlines())
        tickers = list(dict.fromkeys(t for ln in lines for t in ln.split()))
        tickers = tickers[:universe_size]
        rows = []
        for t in tickers:
            try:
                info = self.yf.Ticker(t.replace(".", "-")).info
            except Exception as e:  # rate limits / delisted symbols
                print(f"  ! info {t}: {e}")
                time.sleep(2)
                continue
            rec = info.get("recommendationMean")  # 1 = strong buy ... 5 = sell
            rows.append({
                "code": f"US.{t}", "ticker": t, "name": info.get("shortName") or t,
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "market_cap": info.get("marketCap"),
                "target_mean": info.get("targetMeanPrice"), "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "analysts": info.get("numberOfAnalystOpinions") or 0,
                "consensus01": (5 - rec) / 4 if rec else 0.0,
                "rating_label": info.get("recommendationKey"),
            })
            time.sleep(0.3)
        return rows

    def bars_many(self, tickers: list[str], years: float = 2) -> dict[str, pd.DataFrame]:
        period = "5y" if years > 2 else "2y"
        raw = self.yf.download([t.replace(".", "-") for t in tickers], period=period, interval="1d",
                               auto_adjust=True, group_by="ticker", progress=False, threads=False)
        out = {}
        for t in tickers:
            try:
                sym = t.replace(".", "-")
                # group_by="ticker" gives (ticker, field) columns, even for one ticker in recent yfinance
                df = raw[sym] if getattr(raw.columns, "nlevels", 1) > 1 else raw
                df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
                out[t] = df
            except KeyError:
                continue
        return out

    def bars(self, ticker: str, years: float = 2) -> pd.DataFrame | None:
        return self.bars_many([ticker], years).get(ticker)
