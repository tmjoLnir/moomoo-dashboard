# Build and deploy guide: Top 5 buy-potential dashboard on GitHub Pages

This guide goes from an empty repo to a live, self-refreshing dashboard. Every
step lists what to do and why.

---

## 0. How it fits together

```
 ┌──────────────── GitHub Actions (scheduled every 30 min in US hours, or "Run workflow") ───────────────┐
 │                                                                                                       │
 │  scripts/refresh.py ──► provider ──► scoring.py ──► site/data/dashboard.json ──► deploy to Pages      │
 │                         │                                                                             │
 │                         ├─ moomoo  (self-hosted runner on YOUR PC, talks to moomoo OpenD)             │
 │                         └─ yahoo   (GitHub's servers, free fallback when your PC is off)              │
 └───────────────────────────────────────────────────────────────────────────────────────────────────────┘
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
.github/workflows/refresh-and-deploy.yml   # schedule + build + deploy
scripts/refresh.py                         # pipeline entry point
scripts/scoring.py                         # the blended score (weights, rules, filters)
scripts/providers/moomoo_provider.py       # moomoo OpenAPI via OpenD
scripts/providers/yahoo_provider.py        # free fallback
scripts/providers/demo_provider.py         # synthetic data for offline testing
scripts/universe_us_large.txt              # ticker universe for the Yahoo path
scripts/keep_last_good.py                  # if a refresh fails, keep yesterday's ranking live
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

1. **Actions → Refresh data & deploy → Run workflow** (branch `main`, provider `auto`).
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
4. **Tell the workflow to use it.** Repo → **Settings → Secrets and variables → Actions →
   Variables → New variable**: `DATA_PROVIDER` = `moomoo`.
5. Run the workflow again. The header should now say *source: moomoo OpenAPI (via OpenD)*.

**Trade-offs to know about**

- The PC (and OpenD) has to be **on and logged in** during market hours. If it's off,
  scheduled jobs wait in the queue. To use moomoo only some of the time, leave
  `DATA_PROVIDER` unset (Yahoo on schedule) and pick `moomoo` manually in
  *Run workflow*.
- moomoo limits **historical K-line quota** by the number of *distinct* symbols per
  30 days. The pipeline shortlists on analyst data first, so only about 25 symbols get
  history per run. Lower `shortlist_size` in `moomoo_provider.py` if you hit the quota.
- Screener and analyst calls are rate-limited per 30 s. The provider backs off
  automatically, and a run takes about 2–5 minutes.

## 8. Customise

| What | Where |
|---|---|
| Score weights and rules | `scripts/scoring.py` → `WEIGHTS`, `score()`, and `SCORING_DOC` (the page prints this text) |
| Filters (price, market cap, analyst count) | `scripts/scoring.py` top constants |
| Universe size | `--universe` in the workflow (default 120) |
| Yahoo tickers | `scripts/universe_us_large.txt` |
| Refresh schedule | `cron:` lines in the workflow (UTC) |
| Chart ranges/colours | `site/assets/app.js` (`RANGES`), `site/assets/style.css` (`--up`, `--down`) |

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Pages URL shows 404 | Step 5 not done, or the first deploy hasn't finished. Check the Actions tab. |
| Deploy job: "Branch … is not allowed to deploy" | You ran it from a non-default branch. Merge to `main` first. |
| Banner: "ranking is N days old" | Refreshes are failing. Open the latest run's log. The page keeps the last good data meanwhile. |
| Yahoo errors / 429 in log | Yahoo throttles shared runner IPs sometimes. The next run usually succeeds, and the old data stays live. |
| `OpenD not reachable` | OpenD isn't running or logged in on the runner PC, or it's on a different port. Set `MOOMOO_OPEND_HOST`/`PORT`. |
| Scheduled runs stopped | GitHub pauses schedules on public repos after 60 days without commits. Re-enable in Actions. |
| Cron runs late | GitHub's scheduler can be 5–20 min late at busy times. That's normal. |

---

*Not investment advice: the score is a transparent screen, not a recommendation.*
