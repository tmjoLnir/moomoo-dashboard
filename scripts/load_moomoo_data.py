"""Copy the latest moomoo MCP snapshot from the `moomoo-data` branch into the site.

The site has a single data source: the on-demand Claude task that publishes moomoo
MCP data to `moomoo-data`. There is no age limit; the page shows the snapshot's date
and warns when it gets old.

Exit code 0 = site/data/dashboard.json written; 1 = nothing usable on the branch
(the workflow then keeps whatever is live, or the committed seed).

  python scripts/load_moomoo_data.py [--branch moomoo-data]
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "dashboard.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="moomoo-data")
    a = ap.parse_args()
    try:
        subprocess.run(["git", "fetch", "--depth", "1", "origin", a.branch], check=True, capture_output=True)
        raw = subprocess.run(["git", "show", "FETCH_HEAD:dashboard.json"], check=True,
                             capture_output=True, text=True).stdout
        data = json.loads(raw)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"no usable data on {a.branch}: {e}")
        return 1
    top = data.get("top", [])
    if len(top) < 1 or not all(t.get("bars") for t in top):
        print(f"data on {a.branch} is incomplete (needs at least 1 stock with chart bars)")
        return 1
    age_h = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["generated_at"])).total_seconds() / 3600
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"using moomoo data from {data['generated_at']} ({age_h:.1f} h old)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
