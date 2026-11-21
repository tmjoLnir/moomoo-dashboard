# moomoo-dashboard

Free, self-refreshing dashboard on GitHub Pages showing moomoo-style charts of the
**top 5 US stocks by blended buy-potential score** (analyst upside + consensus + trend +
RSI setup + volume accumulation). The scoring rules are printed on the page.

- Live site (after setup): https://tmjolnir.github.io/moomoo-dashboard/
- Data: moomoo OpenAPI via OpenD on your PC (self-hosted runner, separate workflow), with Yahoo Finance as an automatic fallback whenever the moomoo ranking is over 45 min old
- Step-by-step build & deploy walkthrough: **[GUIDE.md](GUIDE.md)**

```bash
pip install -r requirements.txt
python scripts/refresh.py --provider demo   # or yahoo / moomoo
python -m http.server 8000 -d site
```

Not investment advice.
