# moomoo-dashboard

A free dashboard on GitHub Pages showing moomoo-style charts of the
**top 5 US swing-trade buys** from a four-stage model: market regime (SPY trend) → hard
filters (liquidity, rising 200-day, defined stop) → a 0-100 score (trend & relative strength,
entry location, reward-to-risk, catalyst, timing) → final rank by score × reward-to-risk,
with a sized trade plan per stock. The scoring rules are printed on the page.

- Live site: https://tmjolnir.github.io/moomoo-dashboard/
- Data: **moomoo only**, fetched through the moomoo MCP connector by the Claude scheduled
  task *moomoo MCP dashboard refresh*, which runs on demand and weekly
- Setup, refreshing and troubleshooting: **[GUIDE.md](GUIDE.md)**

```bash
python -m http.server 8000 -d site   # view locally
```

Not investment advice.
