"""Use the moomoo ranking from the `moomoo-data` branch if it is fresh enough.

Freshness: the data's own `valid_minutes` if present (on-demand MCP snapshots set 24h),
otherwise --max-age-min. If the ranking carries no price bars (MCP snapshots don't, to
keep Claude token use low), chart bars for the 5 tickers are added from Yahoo here.

Writes site/data/dashboard.json and prints used=true|false to $GITHUB_OUTPUT.
Never fails the job: any problem just means "not used", and the workflow runs Yahoo.

  python scripts/use_moomoo_data.py [--branch moomoo-data] [--max-age-min 45]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "dashboard.json"


def add_bars(data: dict, tickers: list[str]) -> None:
    """Fill top[i]['bars'] with 5y daily OHLCV from Yahoo for tickers that lack them."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from providers.yahoo_provider import YahooProvider
    from refresh import CHART_YEARS, pack_bars

    bars = YahooProvider().bars_many(tickers, CHART_YEARS)
    for t in data["top"]:
        df = bars.get(t["ticker"])
        if t["ticker"] in tickers:
            if df is None or df.empty:
                raise RuntimeError(f"no Yahoo bars for {t['ticker']}")
            t["bars"] = pack_bars(df)


def decide(branch: str, max_age_min: float) -> tuple[bool, str]:
    try:
        subprocess.run(["git", "fetch", "--depth", "1", "origin", branch], check=True, capture_output=True)
        raw = subprocess.run(["git", "show", "FETCH_HEAD:dashboard.json"], check=True,
                             capture_output=True, text=True).stdout
    except subprocess.CalledProcessError:
        return False, f"no {branch} branch yet"
    try:
        data = json.loads(raw)
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["generated_at"])).total_seconds() / 60
    except (ValueError, KeyError) as e:
        return False, f"unreadable data on {branch}: {e}"
    if data.get("provider") != "moomoo" or len(data.get("top", [])) < 5:
        return False, "data on branch is not a complete moomoo ranking"
    limit = float(data.get("valid_minutes") or max_age_min)
    if age > limit:
        return False, f"moomoo data is {age:.0f} min old (limit {limit:.0f}); refresh source probably offline"
    missing = [t["ticker"] for t in data["top"] if not t.get("bars")]
    if missing:
        try:
            add_bars(data, missing)
        except Exception as e:
            return False, f"moomoo ranking found but chart bars could not be added: {e}"
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    return True, f"using moomoo data from {data['generated_at']} ({age:.0f} min old)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="moomoo-data")
    ap.add_argument("--max-age-min", type=float, default=45)
    a = ap.parse_args()
    used, why = decide(a.branch, a.max_age_min)
    print(why)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"used={'true' if used else 'false'}\n")


if __name__ == "__main__":
    main()
