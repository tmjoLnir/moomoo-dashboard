# moomoo-dashboard

A free dashboard on GitHub Pages showing moomoo-style charts of the
**top 5 US stocks by blended buy-potential score**: analyst upside + consensus + trend +
RSI setup + volume accumulation. The scoring rules are printed on the page.

- Live site: https://tmjolnir.github.io/moomoo-dashboard/
- Data: **moomoo only**, fetched through the moomoo MCP connector by the Claude scheduled
  task *moomoo MCP dashboard refresh*, which runs on demand and weekly
- Setup, refreshing and troubleshooting: **[GUIDE.md](GUIDE.md)**

```bash
python -m http.server 8000 -d site   # view locally
```

Not investment advice.
