"""Rank US stocks by blended buy-potential score and write site/data/dashboard.json.

Usage:
  python scripts/refresh.py --provider moomoo   # needs OpenD running locally
  python scripts/refresh.py --provider yahoo    # free fallback
  python scripts/refresh.py --provider auto     # moomoo if OpenD answers, else yahoo
  python scripts/refresh.py --provider demo     # offline synthetic data for testing
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scoring  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "dashboard.json"
TOP_N = 5
CHART_YEARS = 5


def make_provider(name: str):
    if name in ("moomoo", "auto"):
        try:
            from providers.moomoo_provider import MoomooProvider
            return MoomooProvider()
        except Exception as e:
            if name == "moomoo":
                raise
            print(f"moomoo unavailable ({e}); falling back to Yahoo")
    if name in ("yahoo", "auto"):
        from providers.yahoo_provider import YahooProvider
        return YahooProvider()
    if name == "demo":
        from providers.demo_provider import DemoProvider
        return DemoProvider()
    raise SystemExit(f"unknown provider {name}")


def get_bars(p, tickers, years):
    if hasattr(p, "bars_many"):
        return p.bars_many(tickers, years)
    out = {}
    for t in tickers:
        try:
            out[t] = p.bars(t, years)
        except Exception as e:
            print(f"  ! bars {t}: {e}")
    return out


def pack_bars(df):
    return {
        "t": [d.strftime("%Y-%m-%d") for d in df.index],
        "o": [round(x, 4) for x in df["open"]], "h": [round(x, 4) for x in df["high"]],
        "l": [round(x, 4) for x in df["low"]], "c": [round(x, 4) for x in df["close"]],
        "v": [int(x) for x in df["volume"]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="auto", choices=["auto", "moomoo", "yahoo", "demo"])
    ap.add_argument("--universe", type=int, default=120)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    t0 = time.time()
    p = make_provider(a.provider)
    print(f"provider: {p.label}")
    try:
        cands = p.candidates(a.universe)
        print(f"universe: {len(cands)} stocks with quote data")

        # Stage 1: shortlist on analyst data (cheap) when the provider rations price-history calls.
        cands.sort(key=scoring.fundamental_prescore, reverse=True)
        short = cands[: p.shortlist_size] if p.shortlist_size else cands
        print(f"shortlist for technicals: {len(short)}")

        # Stage 2: technicals + full blended score.
        bars = get_bars(p, [c["ticker"] for c in short], 2)
        scored = []
        for c in short:
            c["tech"] = scoring.technicals(bars.get(c["ticker"]))
            if c["tech"]:
                c["price"] = c.get("price") or c["tech"]["last_close"]
            s = scoring.score(c)
            if s:
                c.update(s)
                scored.append(c)
        scored.sort(key=lambda c: c["score"], reverse=True)
        if len(scored) < TOP_N:
            raise SystemExit(f"only {len(scored)} stocks passed the filters; refusing to publish")
        top = scored[:TOP_N]
        print("top:", ", ".join(f"{c['ticker']} {c['score']}" for c in top))

        # Stage 3: long history for the charts (1M ... 5Y tabs).
        long = get_bars(p, [c["ticker"] for c in top], CHART_YEARS)
        for c in top:
            df = long.get(c["ticker"])
            if df is None or df.empty:
                df = bars[c["ticker"]]
            c["bars"] = pack_bars(df)
            prev, last = df["close"].iloc[-2], df["close"].iloc[-1]
            c["change_pct"] = round(100 * (last / prev - 1), 2)
    finally:
        p.close()

    keep = ["ticker", "name", "price", "change_pct", "market_cap", "target_mean", "target_high", "target_low",
            "analysts", "consensus01", "rating_label", "breakdown", "score", "parts", "upside_pct", "tech", "bars"]
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "provider": p.name,
        "provider_label": p.label,
        "universe_size": len(cands),
        "shortlist_size": len(short),
        "scored_count": len(scored),
        "elapsed_sec": round(time.time() - t0, 1),
        "scoring": scoring.SCORING_DOC,
        "top": [{k: c.get(k) for k in keep} for c in top],
        "runners_up": [{k: c.get(k) for k in ("ticker", "name", "score", "upside_pct")} for c in scored[TOP_N:TOP_N + 10]],
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, separators=(",", ":"), default=float))
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB) in {data['elapsed_sec']}s")


if __name__ == "__main__":
    main()
