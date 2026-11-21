# Build and deploy guide: Top 5 swing-trade dashboard on GitHub Pages

The site shows moomoo-style charts of the top 5 US swing-trade candidates from a four-stage ranking model (see `scripts/scoring.py`).
Its only data source is **moomoo, fetched through the moomoo MCP connector in Claude**.

---

## 0. How it fits together

```
 CLAUDE (cloud session, moomoo MCP connector)          GITHUB
 ┌─────────────────────────────────────────┐          ┌───────────────────────────────────┐
 │ Scheduled task "moomoo MCP dashboard    │  pushes  │ moomoo-data branch                │
 │ refresh" (on demand + weekly)           │ ───────► │   dashboard.json (one commit)     │
 │  screener ─► shortlist ─► consensus +   │          │                                   │
 │  K-lines ─► scripts/mcp_build.py score  │ triggers │ "Deploy dashboard" workflow       │
 │                                         │ ───────► │   copies it into site/ ─► Pages   │
 └─────────────────────────────────────────┘          └───────────────────────────────────┘
                                                          │
                       browser ──► https://<user>.github.io/moomoo-dashboard/
```

**Why it's built this way**

1. **GitHub Pages only serves static files.** The ranking is computed ahead of time,
   and the page just draws the JSON it's given.
2. **The moomoo MCP connector only exists inside a Claude session.** A website or
   GitHub workflow can't call it, so a Claude scheduled task fetches the data and
   publishes it to the `moomoo-data` branch.
3. **The ranking only changes when the task runs.** There is no fallback source.
   - The page always shows the latest snapshot with its date.
   - It warns once the snapshot is more than 8 days old (`STALE_DAYS` in
     `site/assets/app.js`).

---

## 1. Create the repository

Already done: `tmjoLnir/moomoo-dashboard` (public). If you were starting from scratch:

```bash
# on github.com: New repository -> name "moomoo-dashboard" -> Public -> Create
git clone https://github.com/<you>/moomoo-dashboard.git
```

GitHub Pages is free for public repos. A private repo needs a paid plan.

## 2. What's in the repo

```
.github/workflows/refresh-and-deploy.yml   # "Deploy dashboard": moomoo-data -> GitHub Pages
scripts/mcp_build.py                       # turns raw moomoo MCP output into dashboard.json
scripts/scoring.py                         # the 4-stage model (regime, filters, weights, sizing)
scripts/publish_data_branch.py             # pushes dashboard.json to moomoo-data
scripts/load_moomoo_data.py                # deploy side: copy the snapshot into site/
scripts/keep_last_good.py                  # deploy side: if loading fails, keep what's live
site/index.html, site/assets/*             # the dashboard (vanilla JS + Lightweight Charts, vendored)
site/data/dashboard.json                   # seed copy of a real moomoo snapshot
requirements.txt                           # pandas, numpy (used by mcp_build.py)
```

## 3. View it locally (optional)

```bash
python -m http.server 8000 -d site      # open http://localhost:8000
```

Use a local server rather than double-clicking `index.html`: browsers block `fetch()` of
local files.

## 4. Turn on GitHub Pages (one-time)

1. Repo → **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Repo → **Actions**: enable workflows if asked.

The workflow uploads `site/` straight to Pages, so refreshes never add commits to `main`.

**When the site deploys**
- On every push to `main`, using the latest snapshot on the `moomoo-data` branch.
- When the moomoo task finishes, because the task dispatches the workflow.
- From **Actions → Deploy dashboard → Run workflow**, to redeploy the current snapshot by hand.
  This doesn't fetch new data; only the task does.

**The `moomoo-data` branch** holds just `dashboard.json`, as a single force-pushed commit.
It's data, not code: don't merge it or open PRs from it.

## 5. How to refresh the ranking

The ranking is refreshed by the Claude scheduled task **moomoo MCP dashboard refresh**.

**Run it**
- **On demand:** claude.ai → **Scheduled tasks** → *moomoo MCP dashboard refresh* →
  **Run now**. Or ask Claude in any session: "fire the moomoo MCP dashboard refresh task".
- **Weekly:** it also runs every Saturday at 09:00 Singapore time, using Friday's US close.
- **Requirement:** the task must have the **moomoo connector** attached (claude.ai →
  Scheduled tasks → the task → connectors).

About 5–10 minutes later the site updates, and you get a push notification.

**What a run does**
1. Screens the top 200 US stocks by market cap (≥ $10B, price ≥ $10) with
   `quote_stock_screen`, which returns price, market cap, analyst rating and target,
   and 126-day and 21-day returns.
2. Drops stocks listed less than 330 days ago (`quote_stock_basicinfo`): they can't have
   a 200-day average yet.
3. Pre-ranks on 6-month momentum (skipping the last month) and keeps the best 20.
4. For those 20, fetches analyst consensus and about 370 daily K-lines, plus SPY's K-lines
   for the market regime and relative strength.
5. Runs the four stages in `scripts/scoring.py`: regime, hard filters, 0-100 score,
   final rank by score × reward-to-risk with position sizing.
6. Publishes to the `moomoo-data` branch and dispatches **Deploy dashboard**.

All number handling happens in `scripts/mcp_build.py`, which reads the raw tool output.
Claude Code saves large tool results to files, so nothing is copied by hand.

**Things to know**
- **Cost:** each run uses Claude usage, roughly 50–100k tokens.
- **Charts:** they use moomoo's daily K-lines, about 370 trading days (~1.5 years).
  So the 5Y tab shows that full span.
- **New listings are skipped:** their short history would also come back inline in the
  session instead of in a file, which costs far more tokens.

## 6. Customise

| What | Where |
|---|---|
| Score weights and rules | `scripts/scoring.py` → `WEIGHTS`, `score()`, `SCORING_DOC` (the page prints this text) |
| Filters (price, market cap, analyst count) | `scripts/scoring.py` top constants; screener filters in `mcp_build.py` (`SCREEN_QUERIES`) |
| Shortlist size | `--n` in the task's instructions (default 15) |
| When the stale warning appears | `STALE_DAYS` in `site/assets/app.js` |
| Weekly schedule | claude.ai → Scheduled tasks → the task's schedule |
| Chart ranges/colours | `site/assets/app.js` (`RANGES`), `site/assets/style.css` (`--up`, `--down`) |

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Task report: "moomoo connector not available" | Attach the moomoo connector to the task in claude.ai. |
| Banner: "This ranking is N days old" | The weekly run failed or was skipped. Run the task on demand and read its report. |
| Site didn't change after a run | Check that the task's report shows the deploy run, and that its log has "using moomoo data from …". |
| Pages URL shows 404 | Step 4 isn't done, or the first deploy hasn't finished. Check the Actions tab. |
| Deploy: "Branch … is not allowed to deploy" | The workflow was run from a non-default branch. Run it from `main`. |
| Deploy log: "no usable data on moomoo-data" | The branch is missing or incomplete. Run the task once. The site keeps showing what was live. |
| Task fails at "dispatch the workflow" | Check that `refresh-and-deploy.yml` exists on `main` and that the task dispatches it with no inputs. |

---

*Not investment advice: the score is a transparent screen, not a recommendation.*
