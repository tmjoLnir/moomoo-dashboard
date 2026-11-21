"""Build the dashboard ranking from moomoo data fetched through the Claude moomoo MCP connector.

Used by the Claude scheduled task "moomoo MCP dashboard refresh" (GUIDE.md §5), the site's only
data source. The Claude session calls the
MCP tools; this script reads their raw JSON output (Claude Code saves large tool results
to files, so numbers never need to be copied by hand) and does all scaling and scoring
with scoring.py.

Steps (all paths default to the mcp/ folder):
  1. screen     <saved quote_stock_screen result>...     -> mcp/universe.json
  2. shortlist --check-listing                           -> codes to pass to quote_stock_basicinfo
     listing    <saved quote_stock_basicinfo result>     -> drops listings < 330 days old
     shortlist  [--n 15]                                 -> codes to fetch details for
  3. add-consensus <code> <file or inline JSON>          -> mcp/details.json
     add-kline     <code> <saved quote_history_kline result (num=370)>
  4. finalize                                            -> mcp/dashboard.json
  5. (task) publish_data_branch.py mcp/dashboard.json moomoo-data, then dispatch the deploy
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoring  # noqa: E402

DIR = Path("mcp")
UNIVERSE, DETAILS, OUT = DIR / "universe.json", DIR / "details.json", DIR / "dashboard.json"

# (result kind, factor name, indicator params) -> (field, divisor). Scaling per the screener docs.
FIELDS = {
    ("simple_property", 2201, None): ("price", 1e3),
    ("simple_property", 2301, None): ("market_cap", 1e3),
    ("featured_property", 5401, None): ("rating", 1e3),      # 1 sell .. 5 strong buy
    ("featured_property", 5403, None): ("target_mean", 1e9),
}
# Technicals (RSI14, 50/200-day MA, up-volume share) are computed from the K-lines with
# scoring.technicals(). The screener's MA factor ignored the
# requested period in testing, so it is not used.
SCREEN_RETRIEVE = [  # what the task passes as retrieve_queries
    {"simple_property": {"name": 2201}}, {"simple_property": {"name": 2301}},
    {"featured_property": {"name": 5401}}, {"featured_property": {"name": 5403}},
]
SCREEN_QUERIES = [  # what the task passes as screen_queries: US, market cap >= $10B, price >= $5
    {"simple_field_query": {"simple_field": 1, "screen_value_list": [2]}},
    {"simple_property_query": {"property": {"name": 2301}, "lower": {"value": 10_000_000_000_000, "includes": True}}},
    {"simple_property_query": {"property": {"name": 2201}, "lower": {"value": 5_000, "includes": True}}},
]


def read_json(arg: str):
    """A path to a saved tool result, or the JSON text itself.

    Inline JSON is detected first: a long JSON string passed to Path.exists() raises
    OSError "File name too long" (seen with basicinfo for 25 codes).
    """
    text = arg if arg.lstrip().startswith(("{", "[")) else Path(arg).read_text()
    d = json.loads(text)
    return d.get("data", d) if isinstance(d, dict) else d


def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")))


# -- 1. screener -> universe ---------------------------------------------------
def cmd_screen(files):
    uni = {}
    for f in files:
        for it in read_json(f)["items"]:
            row = {"code": it["code"], "ticker": it["code"].split(".", 1)[-1], "name": it.get("name")}
            for r in it["results"]:
                kind, body = next(iter(r.items()))
                prop = body.get("property", {})
                params = tuple(prop.get("indicator_params") or []) or None
                key = (kind.removesuffix("_result"), prop.get("name"), params)
                if key in FIELDS and body.get("value") not in (None, ""):
                    field, div = FIELDS[key]
                    row[field] = float(body["value"]) / div
            uni[row["code"]] = row
    save(UNIVERSE, list(uni.values()))
    print(f"universe: {len(uni)} stocks -> {UNIVERSE}")


def cmd_listing(arg):
    """Store listing dates from a quote_stock_basicinfo result, so shortlist skips new listings."""
    dates = {b["code"]: b.get("listing_date") for b in read_json(arg)["basic_list"]}
    uni = load(UNIVERSE, [])
    for u in uni:
        if u["code"] in dates:
            u["listing_ms"] = dates[u["code"]]
    save(UNIVERSE, uni)
    print(f"listing dates saved for {len(dates)} codes")


MIN_LISTED_DAYS = 330  # ~230 trading days: enough for the 200-day MA


def too_new(u) -> bool:
    ms = u.get("listing_ms")
    if not ms:
        return False
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)
    return age.days < MIN_LISTED_DAYS


def company_key(u) -> str:
    """'Alphabet-A' / 'Alphabet-C' -> 'alphabet', so dual share classes count once."""
    return (u.get("name") or u["code"]).rsplit("-", 1)[0].strip().lower()


def prerank_rows():
    rows, seen = [], set()
    for u in sorted(load(UNIVERSE, []), key=lambda x: -(x.get("market_cap") or 0)):
        if company_key(u) in seen:   # keep the larger share class only
            continue
        seen.add(company_key(u))
        if (u.get("price") or 0) < scoring.MIN_PRICE or (u.get("market_cap") or 0) < scoring.MIN_MARKET_CAP:
            continue
        r = dict(u, consensus01=(u["rating"] - 1) / 4 if u.get("rating") else 0.0, analysts=10)
        rows.append(r)
    return sorted(rows, key=scoring.fundamental_prescore, reverse=True)


# -- 2. shortlist --------------------------------------------------------------
def cmd_shortlist(n, with_unchecked: bool):
    rows = [r for r in prerank_rows() if not too_new(r)]
    if with_unchecked:  # step 2a: candidates to check listing dates for (a few extra)
        print(" ".join(r["code"] for r in rows[: n + 10] if "listing_ms" not in r))
    else:
        print(" ".join(r["code"] for r in rows[:n]))


# -- 3. details ----------------------------------------------------------------
def cmd_add_consensus(code, arg):
    det = load(DETAILS, {})
    det.setdefault(code, {})["consensus"] = read_json(arg)
    save(DETAILS, det)
    print(f"{code}: consensus saved")


def cmd_add_kline(code, arg):
    bars = sorted(read_json(arg)["kline_list"], key=lambda b: b["time_key"])
    packed = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for b in bars:
        d = str(b["date"])
        packed["t"].append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
        for k, src in (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close")):
            packed[k].append(round(float(b[src]), 4))
        packed["v"].append(int(b["volume"]))
    det = load(DETAILS, {})
    det.setdefault(code, {})["bars"] = packed
    save(DETAILS, det)
    print(f"{code}: {len(bars)} bars {packed['t'][0]} .. {packed['t'][-1]}")


# -- 4. finalize ---------------------------------------------------------------
def bars_df(b):
    import pandas as pd
    return pd.DataFrame({"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]},
                        index=pd.to_datetime(b["t"]))


def cmd_finalize():
    det = load(DETAILS, {})
    scored = []
    for u in prerank_rows():
        d = det.get(u["code"], {})
        b, cons = d.get("bars"), d.get("consensus")
        tech = scoring.technicals(bars_df(b)) if cons and b else None   # needs >= 220 bars
        if not tech:
            continue
        con, n, breakdown = scoring.normalize_consensus(cons)
        row = dict(u, consensus01=con, analysts=n, breakdown=breakdown, bars=b, rating_label=cons.get("rating"),
                   target_mean=cons.get("average") or u.get("target_mean"),
                   target_high=cons.get("highest"), target_low=cons.get("lowest"),
                   price=b["c"][-1], change_pct=round(100 * (b["c"][-1] / b["c"][-2] - 1), 2))
        row["tech"] = tech
        s = scoring.score(row)
        if s:
            row.update(s)
            scored.append(row)
    scored.sort(key=lambda r: r["score"], reverse=True)
    if len(scored) < 5:
        raise SystemExit(f"only {len(scored)} stocks scored; need 5. Add details for more shortlisted codes.")

    keep = ["ticker", "name", "price", "change_pct", "market_cap", "target_mean", "target_high", "target_low",
            "analysts", "consensus01", "rating_label", "breakdown", "score", "parts", "upside_pct", "tech", "bars"]
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "provider": "moomoo",
        "source": "mcp",
        "provider_label": "moomoo (Claude MCP snapshot)",
        "universe_size": len(load(UNIVERSE, [])),
        "shortlist_size": len(det),
        "scored_count": len(scored),
        "scoring": scoring.SCORING_DOC,
        "top": [{k: r.get(k) for k in keep} for r in scored[:5]],
        "runners_up": [{k: r.get(k) for k in ("ticker", "name", "score", "upside_pct")} for r in scored[5:15]],
    }
    save(OUT, data)
    print("top:", ", ".join(f"{r['ticker']} {r['score']}" for r in scored[:5]))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("screen").add_argument("files", nargs="+")
    sl = sub.add_parser("shortlist"); sl.add_argument("--n", type=int, default=15)
    sl.add_argument("--check-listing", action="store_true", help="print codes whose listing date is still unknown")
    sub.add_parser("listing").add_argument("src")
    sub.add_parser("screen-queries")
    c = sub.add_parser("add-consensus"); c.add_argument("code"); c.add_argument("src")
    k = sub.add_parser("add-kline"); k.add_argument("code"); k.add_argument("src")
    sub.add_parser("finalize")
    sub.add_parser("retrieve-queries")
    a = ap.parse_args()
    {"screen": lambda: cmd_screen(a.files), "shortlist": lambda: cmd_shortlist(a.n, a.check_listing),
     "listing": lambda: cmd_listing(a.src), "screen-queries": lambda: print(json.dumps(SCREEN_QUERIES)),
     "add-consensus": lambda: cmd_add_consensus(a.code, a.src), "add-kline": lambda: cmd_add_kline(a.code, a.src),
     "finalize": cmd_finalize, "retrieve-queries": lambda: print(json.dumps(SCREEN_RETRIEVE))}[a.cmd]()


if __name__ == "__main__":
    main()
