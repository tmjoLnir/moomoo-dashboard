"""Synthetic data so the site can be built and tested offline. Never used by the scheduled workflow."""
from __future__ import annotations

import numpy as np
import pandas as pd

NAMES = ["DEMOA", "DEMOB", "DEMOC", "DEMOD", "DEMOE", "DEMOF", "DEMOG", "DEMOH", "DEMOI", "DEMOJ"]


class DemoProvider:
    name = "demo"
    label = "DEMO synthetic data (not real prices)"
    shortlist_size = None

    def __init__(self):
        self.rng = np.random.default_rng(7)
        self._cache: dict[str, pd.DataFrame] = {}

    def close(self):
        pass

    def candidates(self, universe_size: int = 10) -> list[dict]:
        rows = []
        for t in NAMES:
            last = float(self.bars(t)["close"].iloc[-1])
            rows.append({"code": f"US.{t}", "ticker": t, "name": f"Demo Corp {t[-1]}", "price": last,
                         "market_cap": 50e9, "target_mean": last * self.rng.uniform(0.9, 1.6),
                         "analysts": int(self.rng.integers(5, 40)), "consensus01": self.rng.uniform(0.4, 1.0),
                         "rating_label": "buy"})
        return rows

    def bars(self, ticker: str, years: float = 5) -> pd.DataFrame:
        if ticker not in self._cache:
            idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=1260)
            r = self.rng.normal(0.0004, 0.02, len(idx))
            close = 100 * np.exp(np.cumsum(r))
            vol = self.rng.lognormal(17, 0.4, len(idx))
            self._cache[ticker] = pd.DataFrame({"open": close * (1 + self.rng.normal(0, .005, len(idx))),
                                                "high": close * 1.01, "low": close * 0.99,
                                                "close": close, "volume": vol}, index=idx)
        df = self._cache[ticker]
        return df.tail(int(252 * years))
