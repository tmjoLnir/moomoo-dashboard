"""Daily swing-trade watchlist data ("My trades" panel): validate, publish, load.

The Claude scheduled task "Daily post-US-close swing-trade check" writes trades.json and
publishes it to the `trades-data` branch (one force-pushed commit, like `moomoo-data`).
The branch is also the task's memory: each run starts by reading the previous trades.json
(`show`) so stops, open trades and the log carry over from day to day.

  python scripts/trades_data.py show [--branch trades-data]       # print the last published state
  python scripts/trades_data.py check <trades.json>                # validate only
  python scripts/trades_data.py publish <trades.json> [--branch trades-data]
  python scripts/trades_data.py load [--branch trades-data]        # deploy side -> site/data/trades.json

Exit code 1 = invalid data or nothing on the branch (deploy then keeps what's live).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "trades.json"
STATUSES = {"watching", "triggered", "stopped", "target hit", "cancelled", "closed"}
VERDICTS = {"hold", "exit", "watch", "stand aside", "trim"}


def git(*args, stdin=None):
    return subprocess.run(["git", *args], input=stdin, capture_output=True, text=True, check=True).stdout.strip()


def validate(d: dict) -> list[str]:
    errs = []
    for k in ("generated_at", "session_date", "tickers"):
        if k not in d:
            errs.append(f"missing {k}")
    try:
        dt.datetime.fromisoformat(d.get("generated_at", ""))
    except ValueError:
        errs.append("generated_at is not ISO 8601 with offset")
    tickers = d.get("tickers") or []
    if not tickers:
        errs.append("no tickers")
    for t in tickers:
        name = t.get("ticker", "?")
        for k in ("ticker", "close", "change_pct", "status", "verdict", "plan"):
            if t.get(k) is None:
                errs.append(f"{name}: missing {k}")
        if t.get("status") not in STATUSES:
            errs.append(f"{name}: status must be one of {sorted(STATUSES)}")
        if t.get("verdict") not in VERDICTS:
            errs.append(f"{name}: verdict must be one of {sorted(VERDICTS)}")
        b = t.get("bars")
        if b and len({len(b.get(k, [])) for k in "tohlcv"}) != 1:
            errs.append(f"{name}: bars arrays differ in length")
    return errs


def fetch(branch: str) -> dict:
    git("fetch", "--depth", "1", "origin", branch)
    return json.loads(git("show", "FETCH_HEAD:trades.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["show", "check", "publish", "load"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--branch", default="trades-data")
    ap.add_argument("--remote", default="origin")
    a = ap.parse_args()

    if a.cmd in ("show", "load"):
        try:
            d = fetch(a.branch)
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"no usable data on {a.branch}: {e}")
            return 1
        errs = validate(d)
        if errs:
            print(f"data on {a.branch} is invalid: {errs}")
            return 1
        if a.cmd == "show":
            print(json.dumps({k: v for k, v in d.items()} | {
                "tickers": [{k: v for k, v in t.items() if k != "bars"} for t in d["tickers"]]}, indent=1))
        else:
            OUT.write_text(json.dumps(d, separators=(",", ":")))
            print(f"using trades data for session {d['session_date']} (generated {d['generated_at']})")
        return 0

    d = json.loads(Path(a.file).read_text(encoding="utf-8"))
    errs = validate(d)
    if errs:
        print("invalid trades.json:\n  " + "\n  ".join(errs))
        return 1
    if a.cmd == "check":
        print(f"ok: {len(d['tickers'])} tickers, session {d['session_date']}")
        return 0

    os.environ.update({"GIT_AUTHOR_NAME": "trades-check", "GIT_AUTHOR_EMAIL": "actions@users.noreply.github.com",
                       "GIT_COMMITTER_NAME": "trades-check", "GIT_COMMITTER_EMAIL": "actions@users.noreply.github.com"})
    blob = git("hash-object", "-w", a.file)
    tree = git("mktree", stdin=f"100644 blob {blob}\ttrades.json\n")
    commit = git("commit-tree", tree, "-m", f"trades data {d['session_date']}")
    git("push", "--force", a.remote, f"{commit}:refs/heads/{a.branch}")
    print(f"published session {d['session_date']} -> {a.remote}/{a.branch} ({commit[:8]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
