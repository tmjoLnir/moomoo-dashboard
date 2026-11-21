"""Blended "buy potential" score.

Every provider (moomoo, yahoo) hands this module the same raw inputs:
  - price, market cap
  - analyst average target price, analyst count, a 0..1 consensus rating
  - daily OHLCV bars (pandas DataFrame, >= ~220 rows for the 200-day average)

The logic below is ALSO exported as plain text (SCORING_DOC) and written into
the dashboard JSON, so the web page always prints exactly the rules that
produced the ranking. Change a weight here and the page updates itself.
"""
from __future__ import annotations

import math

import pandas as pd

# ---- weights (must sum to 1.0) ---------------------------------------------
WEIGHTS = {
    "upside": 0.35,     # analyst target-price upside
    "consensus": 0.20,  # analyst buy/hold/sell mix, scaled by coverage
    "trend": 0.15,      # price vs 200-day MA, 50-day vs 200-day MA
    "rsi": 0.15,        # RSI(14) "pullback, not free-fall" sweet spot
    "volume": 0.15,     # share of last 20 days' volume traded on up days
}

# ---- eligibility filters -----------------------------------------------------
MIN_PRICE = 5.0
MIN_MARKET_CAP = 10e9
MIN_ANALYSTS = 5

SCORING_DOC = {
    "summary": "Score 0-100 = weighted blend of five sub-scores, each scaled 0-1. "
               "Analyst data says where the price could go; technicals say whether now is a sensible entry.",
    "filters": [
        f"Price >= ${MIN_PRICE:.0f}",
        f"Market cap >= ${MIN_MARKET_CAP / 1e9:.0f}B",
        f"At least {MIN_ANALYSTS} analysts covering the stock",
        "At least 220 trading days of price history",
    ],
    "components": [
        {"key": "upside", "name": "Analyst upside", "weight": WEIGHTS["upside"],
         "rule": "Upside = average analyst target / price - 1. 0% or less scores 0; 50% or more scores 1; linear in between."},
        {"key": "consensus", "name": "Analyst consensus", "weight": WEIGHTS["consensus"],
         "rule": "Mean rating on a 1 (sell) to 5 (strong buy) scale, rescaled to 0-1, then multiplied by "
                 "min(1, analysts/10) so thinly covered stocks are discounted."},
        {"key": "trend", "name": "Trend", "weight": WEIGHTS["trend"],
         "rule": "0.5 if price > 200-day MA, plus 0.5 if 50-day MA > 200-day MA."},
        {"key": "rsi", "name": "RSI(14) setup", "weight": WEIGHTS["rsi"],
         "rule": "Peaks at RSI 45 (a pullback that isn't a free-fall): score = 1 - |RSI - 45| / 35, floored at 0. "
                 "So RSI 10 or RSI 80 scores 0."},
        {"key": "volume", "name": "Volume accumulation", "weight": WEIGHTS["volume"],
         "rule": "Share of the last 20 days' volume traded on up-days. 30% or less scores 0, 70% or more scores 1."},
    ],
    "caveat": "A screen, not advice. It ranks large caps by a transparent rule; it does not know about news, "
              "earnings dates or your risk tolerance.",
}


def clip01(x: float) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    return max(0.0, min(1.0, float(x)))


def rsi(close: pd.Series, period: int = 14) -> float:
    """Wilder's RSI on the latest bar."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] else math.inf
    return 100 - 100 / (1 + rs)


def technicals(bars: pd.DataFrame) -> dict | None:
    """Features from daily bars (columns: open, high, low, close, volume)."""
    if bars is None or len(bars) < 220:
        return None
    close, vol = bars["close"], bars["volume"]
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1]
    last20 = bars.tail(21)
    up = last20["close"].diff() > 0
    vol20 = last20["volume"].iloc[1:]
    up_share = float(vol20[up.iloc[1:]].sum() / vol20.sum()) if vol20.sum() else 0.5
    return {
        "sma50": float(sma50),
        "sma200": float(sma200),
        "rsi14": float(rsi(close)),
        "up_volume_share": up_share,
        "last_close": float(close.iloc[-1]),
        "avg_vol_5": float(vol.tail(5).mean()),
        "avg_vol_50": float(vol.tail(50).mean()),
    }


def score(row: dict) -> dict | None:
    """row needs: price, market_cap, target_mean, analysts, consensus01, tech (dict from technicals)."""
    price, tech = row.get("price"), row.get("tech")
    if not price or not tech:
        return None
    if price < MIN_PRICE or (row.get("market_cap") or 0) < MIN_MARKET_CAP:
        return None
    if (row.get("analysts") or 0) < MIN_ANALYSTS or not row.get("target_mean"):
        return None

    upside = row["target_mean"] / price - 1
    parts = {
        "upside": clip01(upside / 0.50),
        "consensus": clip01(row.get("consensus01", 0)) * min(1.0, row["analysts"] / 10),
        "trend": 0.5 * (price > tech["sma200"]) + 0.5 * (tech["sma50"] > tech["sma200"]),
        "rsi": clip01(1 - abs(tech["rsi14"] - 45) / 35),
        "volume": clip01((tech["up_volume_share"] - 0.30) / 0.40),
    }
    total = 100 * sum(WEIGHTS[k] * v for k, v in parts.items())
    return {"score": round(total, 1), "parts": {k: round(v, 3) for k, v in parts.items()},
            "upside_pct": round(100 * upside, 1)}


def fundamental_prescore(row: dict) -> float:
    """Cheap pre-rank (analyst data only) used to shortlist before pulling price history."""
    if not row.get("price") or not row.get("target_mean"):
        return -1
    up = clip01((row["target_mean"] / row["price"] - 1) / 0.50)
    con = clip01(row.get("consensus01", 0)) * min(1.0, (row.get("analysts") or 0) / 10)
    return WEIGHTS["upside"] * up + WEIGHTS["consensus"] * con


def consensus_from_counts(strong_buy=0, buy=0, hold=0, underperform=0, sell=0) -> tuple[float, int]:
    """moomoo style counts -> (0..1 score, analyst count)."""
    n = (strong_buy or 0) + (buy or 0) + (hold or 0) + (underperform or 0) + (sell or 0)
    if not n:
        return 0.0, 0
    mean = (5 * (strong_buy or 0) + 4 * (buy or 0) + 3 * (hold or 0) + 2 * (underperform or 0) + (sell or 0)) / n
    return (mean - 1) / 4, n


def normalize_consensus(c: dict) -> tuple[float, int, dict]:
    """moomoo analyst consensus (SDK or MCP) -> (0..1 score, analyst count, breakdown in analyst counts).

    moomoo may report the strong_buy/buy/hold/underperform/sell mix as *percentages*
    (e.g. strong_buy=100 with total=14), so the analyst count comes from `total`,
    and percentages are converted back to approximate counts for display.
    """
    keys = ("strong_buy", "buy", "hold", "underperform", "sell")
    mix = {k: float(c.get(k) or 0) for k in keys}
    con, n_from_mix = consensus_from_counts(**mix)
    total = int(c.get("total") or c.get("num_of_target_analysts") or 0)
    if not n_from_mix and c.get("rating"):           # no mix at all: fall back to the 1-5 rating
        con = (float(c["rating"]) - 1) / 4
    looks_pct = total and abs(sum(mix.values()) - 100) < 1.5 and sum(mix.values()) != total
    if looks_pct:
        breakdown = {k: round(v / 100 * total) for k, v in mix.items()}
    else:
        breakdown = {k: int(v) for k, v in mix.items()}
    return con, (total or int(n_from_mix)), breakdown
