"""Four-stage swing-trade ranking.

Goal: rank stocks by expected return per unit of risk for a 1-3 week swing trade,
not by raw upside or by how many indicators fired.

  Stage 1  Market regime     SPY trend decides HOW MUCH to trade (position count, risk per trade).
  Stage 2  Hard filters      pass/fail; no score can override a failed filter.
  Stage 3  Score 0-100       five weighted parts, strongest-evidence factors weighted most.
  Stage 4  Final rank        score x reward-to-risk (capped), then position sizing by risk.

scripts/mcp_build.py hands this module moomoo daily bars (>= 260 rows), analyst
consensus and SPY bars. The rules are ALSO exported as text (SCORING_DOC) into the
dashboard JSON, so the web page always prints exactly the rules that produced the ranking.
Change a number here and the page updates itself.
"""
from __future__ import annotations

import math
import sys

try:
    import pandas as pd
except ModuleNotFoundError:  # `pip` may belong to a different Python than `python`
    sys.exit(
        f"pandas is not installed for this Python ({sys.executable}).\n"
        "Install the requirements with the same interpreter:\n"
        "    python -m pip install -r requirements.txt"
    )

# ---- Stage 3 weights (must sum to 1.0) ----------------------------------------
WEIGHTS = {
    "trend": 0.30,     # nearness to 52-week high + 6-month strength vs SPY
    "entry": 0.25,     # where price sits vs a rising 20-day average, in ATR units
    "rr": 0.20,        # reward-to-risk from structural stop to next resistance
    "catalyst": 0.15,  # up-day volume, analyst support, recent gap-up on volume
    "timing": 0.10,    # MACD / RSI / 10-day MA crossovers (timing aid only)
}

# ---- Stage 2 hard filters --------------------------------------------------------
MIN_PRICE = 10.0
MIN_MARKET_CAP = 10e9
MIN_DOLLAR_VOL = 20e6     # 20-day average daily dollar volume
MAX_STOP_PCT = 0.10       # if the structural stop is >10% away, there is no tight setup
MIN_BARS = 260

# ---- Stage 4 ------------------------------------------------------------------------
ACTION_SCORE = 70.0       # only scores at or above this are flagged actionable
RR_FULL = 3.0             # in the final rank, R:R at or above this counts in full; below it scales the score down
MAX_TARGET_ATR = 4.0      # a 1-3 week swing rarely travels more than ~4 ATR: cap the target there
MAX_ALLOC = 0.25          # never put more than 25% of the account in one position
REGIMES = {
    "risk-on": {"risk_pct": 0.01, "max_positions": 5},
    "risk-off": {"risk_pct": 0.005, "max_positions": 3},
}

SCORING_DOC = {
    "summary": "Four stages, run in order. Stage 1 reads the market to set how much to trade. "
               "Stage 2 removes anything that fails a hard filter. Stage 3 scores survivors 0-100 on "
               "factors weighted by research strength. Stage 4 ranks by score x reward-to-risk and sizes "
               "each trade so a stop-out costs a fixed slice of the account.",
    "stages": [
        "1. Regime: SPY above its 50- and 200-day averages = risk-on (up to 5 positions, 1% account risk each). "
        "Otherwise risk-off (up to 3 positions, 0.5% risk each).",
        "2. Hard filters (below). A stock failing any one is excluded, whatever its score.",
        "3. Score 0-100 from the five weighted parts in the table.",
        f"4. Final rank = score x min(R:R, {RR_FULL:.0f}) / {RR_FULL:.0f}: setups at {RR_FULL:.0f}R or better rank on score alone, "
        f"weaker R:R scales the score down. Flagged actionable only if score >= {ACTION_SCORE:.0f} "
        "and within the regime's position count. Allocation = risk per trade / stop distance, capped at "
        f"{MAX_ALLOC:.0%} of the account.",
    ],
    "filters": [
        f"Price >= ${MIN_PRICE:.0f} and market cap >= ${MIN_MARKET_CAP / 1e9:.0f}B",
        f"20-day average dollar volume >= ${MIN_DOLLAR_VOL / 1e6:.0f}M",
        "Price above a RISING 200-day average (200-day MA higher than 20 sessions ago)",
        f"A defined stop: structural stop no more than {MAX_STOP_PCT:.0%} below price",
        f"At least {MIN_BARS} trading days of history",
    ],
    "components": [
        {"key": "trend", "name": "Trend & relative strength", "weight": WEIGHTS["trend"],
         "rule": "Half: price / 52-week high (75% or less scores 0, at the high scores 1). Half: 6-month return "
                 "skipping the last month, minus SPY's (-10% or worse scores 0, +30% or better scores 1)."},
        {"key": "entry", "name": "Entry location", "weight": WEIGHTS["entry"],
         "rule": "Distance from the 20-day MA in ATR(14) units. -0.5 to +1.0 ATR scores 1 (a pullback or tight base); "
                 "fades to 0 at -1.5 ATR (breaking down) and at +3 ATR (stretched). Halved if the 20-day MA is falling."},
        {"key": "rr", "name": "Reward-to-risk", "weight": WEIGHTS["rr"],
         "rule": "Stop = lowest low of 10 sessions minus 0.25 ATR (at least 1 ATR below price). Target = 52-week high "
                 "if it is 1.5-4 ATR above price; capped at price + 4 ATR if further (a swing rarely travels more); "
                 "price + 3 ATR if the high is closer than 1.5 ATR. R:R of 1.5 or less scores 0; 3 or more scores 1."},
        {"key": "catalyst", "name": "Catalyst & confirmation", "weight": WEIGHTS["catalyst"],
         "rule": "40%: share of the last 20 days' volume on up-days (30% scores 0, 70% scores 1). 30%: analyst consensus "
                 "scaled by coverage, halved if the average target is below price. 30%: a gap-up of 3%+ on 1.5x volume in "
                 "the last 20 sessions that price still holds."},
        {"key": "timing", "name": "Timing signal", "weight": WEIGHTS["timing"],
         "rule": "One third each, if within the last 3 sessions: MACD histogram crossed above 0; RSI(14) crossed above 50; "
                 "close crossed above the 10-day MA. Lowest weight: these time an entry, they don't predict returns."},
    ],
    "caveat": "A screen, not advice. Earnings dates and sector concentration are NOT checked: confirm no earnings report "
              "falls inside your holding period and hold at most two names per sector. Prices are end-of-day; recheck "
              "levels before placing orders. Weights are a research-informed starting point, not backtested settings.",
}


def clip01(x: float) -> float:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    return max(0.0, min(1.0, float(x)))


def ramp(x: float, lo: float, hi: float) -> float:
    """0 at lo, 1 at hi, linear between (works for lo > hi too)."""
    return clip01((x - lo) / (hi - lo))


def rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, math.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def atr_series(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = bars["close"].shift()
    tr = pd.concat([bars["high"] - bars["low"], (bars["high"] - prev).abs(), (bars["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def crossed_up(series: pd.Series, level, lookback: int = 3) -> bool:
    """True if series moved from <= level to > level within the last `lookback` bars."""
    lvl = level if isinstance(level, pd.Series) else pd.Series(level, index=series.index)
    above = series > lvl
    tail = above.tail(lookback + 1)
    return bool(tail.iloc[-1]) and not bool(tail.iloc[:-1].all())


def momentum_6_1(close: pd.Series) -> float:
    """Return from ~6 months ago to ~1 month ago (skips the short-term reversal month)."""
    return float(close.iloc[-22] / close.iloc[-127] - 1)


def regime(spy: pd.DataFrame) -> dict:
    """Stage 1 from SPY daily bars."""
    c = spy["close"]
    last, sma50, sma200 = float(c.iloc[-1]), float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1])
    label = "risk-on" if last > sma50 and last > sma200 else "risk-off"
    return {"label": label, **REGIMES[label], "spy": round(last, 2), "spy_sma50": round(sma50, 2),
            "spy_sma200": round(sma200, 2), "spy_mom_6_1": momentum_6_1(c),
            "spy_off_high_pct": round(100 * (last / float(spy["high"].tail(252).max()) - 1), 1)}


def technicals(bars: pd.DataFrame) -> dict | None:
    """Features from daily bars (columns: open, high, low, close, volume)."""
    if bars is None or len(bars) < MIN_BARS:
        return None
    o, h, l, c, v = (bars[k] for k in ("open", "high", "low", "close", "volume"))
    last = float(c.iloc[-1])
    sma10, sma20, sma50, sma200 = (c.rolling(n).mean() for n in (10, 20, 50, 200))
    atr = atr_series(bars)
    a = float(atr.iloc[-1])
    rsi = rsi_series(c)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    hist = macd - macd.ewm(span=9, adjust=False).mean()

    hi252 = float(h.tail(252).max())
    stop = float(l.tail(10).min()) - 0.25 * a
    stop = min(stop, last - a)                      # at least 1 ATR of room
    if hi252 < last + 1.5 * a:          # at/near highs: no overhead resistance, assume a 3 ATR swing
        target = last + 3 * a
    else:                                # next resistance, but no further than a realistic swing
        target = min(hi252, last + MAX_TARGET_ATR * a)
    rr = (target - last) / (last - stop) if last > stop else 0.0

    last20 = bars.tail(21)
    up = last20["close"].diff() > 0
    vol20 = last20["volume"].iloc[1:]
    up_share = float(vol20[up.iloc[1:]].sum() / vol20.sum()) if vol20.sum() else 0.5

    vol50 = v.rolling(50).mean().shift()
    gap = False
    for i in range(len(bars) - 20, len(bars)):
        if o.iloc[i] >= c.iloc[i - 1] * 1.03 and v.iloc[i] >= 1.5 * vol50.iloc[i] and last >= l.iloc[i]:
            gap = True

    return {
        "last_close": last,
        "sma20": float(sma20.iloc[-1]), "sma50": float(sma50.iloc[-1]), "sma200": float(sma200.iloc[-1]),
        "sma200_rising": bool(sma200.iloc[-1] > sma200.iloc[-21]),
        "sma20_rising": bool(sma20.iloc[-1] > sma20.iloc[-6]),
        "atr14": a,
        "rsi14": float(rsi.iloc[-1]),
        "pct_of_52w_high": last / hi252,
        "high_52w": hi252,
        "mom_6_1": momentum_6_1(c),
        "dist20_atr": (last - float(sma20.iloc[-1])) / a if a else 0.0,
        "dollar_vol20": float((c * v).tail(20).mean()),
        "up_volume_share": up_share,
        "gap_up_held": gap,
        "sig_macd": crossed_up(hist, 0.0),
        "sig_rsi50": crossed_up(rsi, 50.0),
        "sig_ma10": crossed_up(c, sma10),
        "stop": stop, "target": target, "rr": rr, "stop_pct": (last - stop) / last,
    }


def hard_filters(row: dict) -> list[str]:
    """Stage 2. Returns the list of failed filters (empty = pass)."""
    t, fails = row["tech"], []
    if row["price"] < MIN_PRICE or (row.get("market_cap") or 0) < MIN_MARKET_CAP:
        fails.append("size/price")
    if t["dollar_vol20"] < MIN_DOLLAR_VOL:
        fails.append("liquidity")
    if not (t["last_close"] > t["sma200"] and t["sma200_rising"]):
        fails.append("below or falling 200-day")
    if t["stop_pct"] > MAX_STOP_PCT:
        fails.append("no tight stop")
    return fails


def entry_score(d: float) -> float:
    if d < -0.5:
        return ramp(d, -1.5, -0.5)
    if d <= 1.0:
        return 1.0
    return ramp(d, 3.0, 1.0)


def score(row: dict, reg: dict) -> dict:
    """Stage 3 + 4 for a row that passed Stage 2.

    row needs: price, tech (from technicals), consensus01, analysts, target_mean (optional).
    """
    t = row["tech"]
    rs = t["mom_6_1"] - reg["spy_mom_6_1"]
    upside = (row["target_mean"] / row["price"] - 1) if row.get("target_mean") else None
    analyst = clip01(row.get("consensus01", 0)) * min(1.0, (row.get("analysts") or 0) / 10)
    if upside is not None and upside < 0:
        analyst *= 0.5
    parts = {
        "trend": 0.5 * ramp(t["pct_of_52w_high"], 0.75, 1.0) + 0.5 * ramp(rs, -0.10, 0.30),
        "entry": entry_score(t["dist20_atr"]) * (1.0 if t["sma20_rising"] else 0.5),
        "rr": ramp(t["rr"], 1.5, 3.0),
        "catalyst": 0.4 * ramp(t["up_volume_share"], 0.30, 0.70) + 0.3 * analyst + 0.3 * float(t["gap_up_held"]),
        "timing": (t["sig_macd"] + t["sig_rsi50"] + t["sig_ma10"]) / 3,
    }
    total = 100 * sum(WEIGHTS[k] * v for k, v in parts.items())
    alloc = min(MAX_ALLOC, reg["risk_pct"] / t["stop_pct"]) if t["stop_pct"] > 0 else 0.0
    return {
        "score": round(total, 1),
        "parts": {k: round(v, 3) for k, v in parts.items()},
        "final_rank": round(total * min(t["rr"], RR_FULL) / RR_FULL, 1),
        "upside_pct": round(100 * upside, 1) if upside is not None else None,
        "rs_vs_spy_pct": round(100 * rs, 1),
        "plan": {"entry": round(t["last_close"], 2), "stop": round(t["stop"], 2), "target": round(t["target"], 2),
                 "rr": round(t["rr"], 2), "stop_pct": round(100 * t["stop_pct"], 1),
                 "alloc_pct": round(100 * alloc, 1), "risk_pct": round(100 * reg["risk_pct"], 2)},
    }


def momentum_prescore(row: dict) -> float:
    """Cheap pre-rank from screener fields (6-month return excluding the last month) to pick
    which stocks get daily bars pulled. Missing data sorts last."""
    r126, r21 = row.get("ret_126d"), row.get("ret_21d")
    if r126 is None or r21 is None:
        return -math.inf
    return (1 + r126) / (1 + r21) - 1


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
