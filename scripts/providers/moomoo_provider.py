"""moomoo OpenAPI provider.

Needs the moomoo OpenD gateway running and logged in (default 127.0.0.1:11111)
on the same machine, plus the `moomoo-api` Python SDK. In this project that
machine is your own PC registered as a GitHub *self-hosted runner*, so the
scheduled workflow can reach OpenD. See GUIDE.md, step 6.

Calls used (all in the official SDK):
  get_stock_filter               -> US universe by market cap (price, market cap)
  get_research_analyst_consensus -> average target, strong-buy/buy/hold/... counts
  request_history_kline          -> daily bars for shortlisted names and charts
"""
from __future__ import annotations

import datetime as dt
import os
import time

import pandas as pd

from scoring import MIN_MARKET_CAP, MIN_PRICE, normalize_consensus

HOST = os.environ.get("MOOMOO_OPEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("MOOMOO_OPEND_PORT", "11111"))


class MoomooProvider:
    name = "moomoo"
    label = "moomoo OpenAPI (via OpenD)"
    shortlist_size = 25  # analyst data is pre-ranked; only these get price history pulled

    def __init__(self):
        import moomoo as mm  # imported lazily so the yahoo path never needs the SDK

        self.mm = mm
        self.ctx = mm.OpenQuoteContext(host=HOST, port=PORT)
        ret, state = self.ctx.get_global_state()
        if ret != mm.RET_OK:
            self.ctx.close()
            raise RuntimeError(f"OpenD not reachable at {HOST}:{PORT}: {state}")

    def close(self):
        self.ctx.close()

    # -- helpers ---------------------------------------------------------------
    def _call(self, fn, *args, retries=4, **kwargs):
        """Call an SDK function, backing off when moomoo's rate limit kicks in."""
        for attempt in range(retries):
            out = fn(*args, **kwargs)
            ret, data = out[0], out[1]
            if ret == self.mm.RET_OK:
                return out
            msg = str(data)
            if "freq" in msg.lower() or "频率" in msg or "too many" in msg.lower():
                time.sleep(31)  # limits are per rolling 30s window
                continue
            raise RuntimeError(f"{fn.__name__} failed: {msg}")
        raise RuntimeError(f"{fn.__name__} still rate-limited after {retries} tries")

    # -- provider interface ----------------------------------------------------
    def candidates(self, universe_size: int = 120) -> list[dict]:
        mm = self.mm
        cap = mm.SimpleFilter()
        cap.stock_field = mm.StockField.MARKET_VAL
        cap.filter_min = MIN_MARKET_CAP
        cap.is_no_filter = False
        cap.sort = mm.SortDir.DESCEND

        px = mm.SimpleFilter()
        px.stock_field = mm.StockField.CUR_PRICE
        px.filter_min = MIN_PRICE
        px.is_no_filter = False

        rows, begin = [], 0
        while len(rows) < universe_size:
            _, (last_page, _all, items) = self._call(
                self.ctx.get_stock_filter, mm.Market.US, [cap, px], begin=begin, num=200)
            for it in items:
                rows.append({"code": it.stock_code, "ticker": it.stock_code.split(".", 1)[1],
                             "name": it.stock_name, "market_cap": float(it[cap]), "price": float(it[px])})
            if last_page or not items:
                break
            begin += len(items)
        rows = rows[:universe_size]

        for r in rows:
            try:
                _, c = self._call(self.ctx.get_research_analyst_consensus, r["code"])
            except RuntimeError as e:
                print(f"  ! consensus {r['ticker']}: {e}")
                continue
            c = c if isinstance(c, dict) else {}
            con, n, breakdown = normalize_consensus(c)
            r.update(target_mean=c.get("average"), target_high=c.get("highest"), target_low=c.get("lowest"),
                     analysts=n, consensus01=con, rating_label=c.get("rating"), breakdown=breakdown)
            time.sleep(0.4)
        return rows

    def bars(self, ticker: str, years: float = 2) -> pd.DataFrame | None:
        mm = self.mm
        code = f"US.{ticker}"
        end = dt.date.today()
        start = end - dt.timedelta(days=int(365 * years) + 5)
        frames, key = [], None
        while True:
            _, df, key = self._call(self.ctx.request_history_kline, code, start=str(start), end=str(end),
                                    ktype=mm.KLType.K_DAY, autype=mm.AuType.QFQ, max_count=1000,
                                    page_req_key=key)
            frames.append(df)
            if key is None:
                break
        df = pd.concat(frames)
        if df.empty:
            return None
        df.index = pd.to_datetime(df["time_key"]).dt.normalize()
        return df[["open", "high", "low", "close", "volume"]].astype(float)
