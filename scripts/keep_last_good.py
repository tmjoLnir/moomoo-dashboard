"""If the moomoo snapshot couldn't be loaded, re-publish the data that is live right now instead of the repo's seed file."""
import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "dashboard.json"

try:
    with urllib.request.urlopen(sys.argv[1], timeout=30) as r:
        data = json.loads(r.read())
    assert data.get("top"), "no ranking in live data"
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    print(f"snapshot not loaded; kept live data from {data.get('generated_at')}")
except Exception as e:  # first deploy, or site not reachable: keep the committed seed
    print(f"snapshot not loaded and live data unavailable ({e}); publishing committed seed")
