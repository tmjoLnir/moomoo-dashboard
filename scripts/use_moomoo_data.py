"""Use the moomoo ranking from the `moomoo-data` branch if it is fresh enough.

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
    if age > max_age_min:
        return False, f"moomoo data is {age:.0f} min old (limit {max_age_min:.0f}); PC/OpenD probably offline"
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
