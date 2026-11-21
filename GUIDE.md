# Build and deploy guide: Top 5 buy-potential dashboard on GitHub Pages

This guide goes from an empty repo to a live, self-refreshing dashboard. Every
step lists what to do and why.

---

## 0. How it fits together

```
 YOUR PC (optional)                                   GITHUB'S SERVERS
 ┌─────────────────────────────────────┐              ┌──────────────────────────────────────────────────┐
 │ "Refresh moomoo data (self-hosted)" │   pushes     │ "Refresh data & deploy" (every 30 min, US hours) │
 │  OpenD ─► refresh.py --provider     │ ──────────►  │  1. moomoo-data < 45 min old?  use it            │
 │           moomoo                    │ moomoo-data  │  2. else recompute with Yahoo                    │
 │  (if the PC is off it just waits;   │   branch     │  3. else re-publish what's live now              │
 │   it can't block the site)          │ + triggers   │  ─► deploy site/ to GitHub Pages                 │
 └─────────────────────────────────────┘   deploy     └──────────────────────────────────────────────────┘
                                             │
        browser ──► https://<user>.github.io/moomoo-dashboard/  (static HTML + JS reads dashboard.json)
```

**Why it's built this way**

1. **GitHub Pages only serves static files.** It can't run Python or keep an API key
   secret, so the scoring runs ahead of time in GitHub Actions and the page just
   draws the JSON it's given.
2. **"At the moment of refresh"** means each workflow run recomputes the ranking from
   scratch. The page reloads the JSON every 15 minutes, and the *Recompute ranking*
   button opens the workflow so you can trigger a fresh run yourself.
3. **moomoo data needs OpenD.** The moomoo OpenAPI SDK doesn't call moomoo's servers
   directly. It talks to the **OpenD** gateway, which runs on a machine where
   you're logged in to moomoo. GitHub's cloud runners can't do that, so the moomoo
   path runs on your PC as a self-hosted runner. Yahoo is the free fallback that
   needs no account.
   - The two halves are **separate workflows**. Your PC only publishes data to the
     `moomoo-data` branch; the site is always deployed from GitHub's servers.
   - So when your PC is off, its job waits in its own queue, and the site falls back
     to Yahoo after 45 minutes instead of freezing.
4. **The moomoo MCP connector** (the one Claude uses in chat) is for interactive
   questions. It can't be called from a website or a CI job, so the pipeline uses
   the same data through the official API instead.

---

## 1. Create the repository

Already done for you: `tmjoLnir/moomoo-dashboard` (public). If you were starting from scratch:

```bash
# on github.com: New repository -> name "moomoo-dashboard" -> Public -> Create
git clone https://github.com/<you>/moomoo-dashboard.git
cd moomoo-dashboard
```

**Public vs. private:** GitHub Pages is free for public repos. A private repo needs a
paid plan (Pro/Team) to publish Pages.

## 2. What's in the repo

```
.github/workflows/refresh-and-deploy.yml   # schedule + build + deploy (GitHub-hosted only)
.github/workflows/refresh-moomoo.yml       # moomoo refresh on your PC -> moomoo-data branch
scripts/refresh.py                         # pipeline entry point
scripts/scoring.py                         # the blended score (weights, rules, filters)
scripts/providers/moomoo_provider.py       # moomoo OpenAPI via OpenD
scripts/providers/yahoo_provider.py        # free fallback
scripts/providers/demo_provider.py         # synthetic data for offline testing
scripts/universe_us_large.txt              # ticker universe for the Yahoo path
scripts/keep_last_good.py                  # if a refresh fails, keep yesterday's ranking live
scripts/publish_data_branch.py             # PC side: push dashboard.json to moomoo-data
scripts/use_moomoo_data.py                 # deploy side: use moomoo data if < 45 min old
site/index.html, site/assets/*             # the dashboard (vanilla JS + Lightweight Charts, vendored)
site/data/dashboard.json                   # generated data (committed copy is a demo seed)
requirements.txt / requirements-moomoo.txt
```

## 3. Run it locally (optional, about 5 min)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/refresh.py --provider yahoo             # or --provider demo (offline)
python -m http.server 8000 -d site                     # open http://localhost:8000
```

**Why use a local server instead of double-clicking `index.html`:** browsers block
`fetch()` of local files, so the page can't load `dashboard.json` from `file://`.

## 4. Get the code onto `main`

Claude pushed the code to the branch `claude/stock-dashboard-github-pages-6yqeva`.
Open a pull request into `main` and merge it, either on github.com (Pull requests →
New) or by asking Claude to open one.

**Why this matters:** the `github-pages` deployment environment only accepts deploys
from the default branch, so the site can't go live from a feature branch.

## 5. Turn on GitHub Pages

1. Repo → **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**. Don't pick
   "Deploy from a branch".
3. Repo → **Actions** tab. If you're asked to enable workflows, enable them.

**Why "GitHub Actions" as the source:** the workflow builds fresh data and uploads
the `site/` folder straight to Pages. Nothing gets committed back on each refresh,
so there's no commit spam.

## 6. First deploy

1. **Actions → Refresh data & deploy → Run workflow** (branch `main`, source `auto`).
2. Wait about 3–6 minutes. The Yahoo path pulls analyst data for about 120 tickers.
3. Open `https://tmjolnir.github.io/moomoo-dashboard/`.

The repo ships with demo data, so the page shows a yellow **DEMO DATA** banner until
the first successful run replaces it.

## 7. Switch the data source to moomoo (your PC)

1. **Install OpenD.** Download "OpenD" from moomoo's OpenAPI page, start it, and log in
   with your moomoo ID. It listens on `127.0.0.1:11111`. Confirm your account has
   **US stock quote rights for OpenAPI**: without them, screener and K-line calls
   return permission errors.
2. **Install Python 3.12** on that PC. The `moomoo-api` package doesn't build on
   Python 3.13 yet.
3. **Register the PC as a self-hosted runner.** Repo → **Settings → Actions → Runners →
   New self-hosted runner**, choose your OS, and run the commands it shows.
   Install it as a service (`./svc.sh install` on macOS/Linux, or say yes to "run as
   service" on Windows) so it survives reboots.
4. **Turn on the scheduled moomoo refresh.** Repo → **Settings → Secrets and variables → Actions →
   Variables → New variable**: `DATA_PROVIDER` = `moomoo`.
   - Without this variable, *Refresh moomoo data (self-hosted)* only runs when you start
     it by hand, so nothing queues before your runner exists.
5. **Test it.** Actions → **Refresh moomoo data (self-hosted)** → Run workflow.
   - It pushes `dashboard.json` to the `moomoo-data` branch, which triggers a deploy.
   - The page header should then say *source: moomoo OpenAPI (via OpenD)*.

**Trade-offs to know about**

- The PC (and OpenD) has to be **on and logged in** for moomoo data. When it's off,
  the site switches to Yahoo once the last moomoo ranking is 45 minutes old, and
  switches back on the next moomoo refresh.
  - A moomoo job waiting for an offline PC is replaced by the next scheduled one, so
    stale jobs don't pile up.
  - Change the 45-minute limit with `--max-age-min` in `refresh-and-deploy.yml`.
- moomoo limits **historical K-line quota** by the number of *distinct* symbols per
  30 days. The pipeline shortlists on analyst data first, so only about 25 symbols get
  history per run. Lower `shortlist_size` in `moomoo_provider.py` if you hit the quota.
- Screener and analyst calls are rate-limited per 30 s. The provider backs off
  automatically, and a run takes about 2–5 minutes.

## 7b. moomoo data via the Claude MCP connector (on demand, no PC needed)

If you have the **moomoo connector** in Claude, a Claude cloud session can fetch the data
instead of OpenD on your PC. It runs as an **on-demand scheduled task** called
*moomoo MCP dashboard refresh*.

**How to run it**
1. Open claude.ai → **Scheduled tasks** → *moomoo MCP dashboard refresh* → **Run now**,
   or ask Claude in any session: "fire the moomoo MCP dashboard refresh task".
2. About 5–10 minutes later the site shows *source: moomoo (Claude MCP snapshot)*.
   You get a notification when the run finishes.

**What a run does**
1. Screens the top 200 US stocks by market cap (≥ $10B, price ≥ $5) with
   `quote_stock_screen`, which returns price, market cap, rating and target.
2. Drops stocks listed less than 330 days ago (`quote_stock_basicinfo`): they can't
   have a 200-day average yet.
3. Pre-ranks on analyst data and takes the best 15.
4. For those 15, fetches analyst consensus and about 370 daily K-lines.
5. Scores them with `scripts/scoring.py`, the same rules as every other source.
6. Publishes to the `moomoo-data` branch and triggers *Refresh data & deploy*.

All number handling happens in `scripts/mcp_build.py`, which reads the raw tool output.
Claude Code saves large tool results to files, so nothing is copied by hand.

**Things to know**
- **Cost:** each run uses Claude usage, roughly 50–100k tokens. That's why it's
  on demand rather than every 30 minutes.
- **How long a snapshot lasts:** 24 hours (`valid_minutes` in the data). After that,
  the site goes back to Yahoo until the next run.
- **Charts:** they use moomoo's daily K-lines, about 370 trading days (~1.5 years).
  So the 5Y tab shows that full span, not 5 years.
- **Pre-listing filter:** recent listings (e.g. SPCX, SKHY, ANT in Nov 2026) are
  skipped. Their short history would also land inline in the session instead of in
  a file, which costs far more tokens.

## 8. Customise

| What | Where |
|---|---|
| Score weights and rules | `scripts/scoring.py` → `WEIGHTS`, `score()`, and `SCORING_DOC` (the page prints this text) |
| Filters (price, market cap, analyst count) | `scripts/scoring.py` top constants |
| Universe size | `--universe` in the workflow (default 120) |
| Yahoo tickers | `scripts/universe_us_large.txt` |
| Refresh schedule | `cron:` lines in both workflows (UTC) |
| How long moomoo data counts as fresh | `--max-age-min` in `refresh-and-deploy.yml` (default 45) |
| Chart ranges/colours | `site/assets/app.js` (`RANGES`), `site/assets/style.css` (`--up`, `--down`) |

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Pages URL shows 404 | Step 5 not done, or the first deploy hasn't finished. Check the Actions tab. |
| Deploy job: "Branch … is not allowed to deploy" | You ran it from a non-default branch. Merge to `main` first. |
| Banner: "ranking is N days old" | Refreshes are failing. Open the latest run's log. The page keeps the last good data meanwhile. |
| Yahoo errors / 429 in log | Yahoo throttles shared runner IPs sometimes. The next run usually succeeds, and the old data stays live. |
| MCP task: site still says Yahoo | Check the task run's transcript. The snapshot must be < 24 h old, and PR #3 (workflow split) must be merged into `main`. |
| `OpenD not reachable` | OpenD isn't running or logged in on the runner PC, or it's on a different port. Set `MOOMOO_OPEND_HOST`/`PORT`. |
| Site says Yahoo though `DATA_PROVIDER=moomoo` | The moomoo ranking is over 45 min old: check that the PC is on and that *Refresh moomoo data* runs are green. |
| Moomoo run stuck in "Queued" | No self-hosted runner is online. That's harmless now (the site keeps deploying with Yahoo), but start the runner on your PC. |
| Scheduled runs stopped | GitHub pauses schedules on public repos after 60 days without commits. Re-enable in Actions. |
| Cron runs late | GitHub's scheduler can be 5–20 min late at busy times. That's normal. |

---

*Not investment advice: the score is a transparent screen, not a recommendation.*
