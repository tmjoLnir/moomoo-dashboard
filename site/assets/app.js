/* Top-5 buy-potential dashboard. Reads data/dashboard.json (written by scripts/refresh.py). */
(() => {
  "use strict";
  const LWC = window.LightweightCharts;
  const DATA_URL = "data/dashboard.json";
  const WORKFLOW_FILE = "refresh-and-deploy.yml";
  const RANGES = ["1M", "3M", "YTD", "1Y", "5Y"];
  const charts = []; // {chart, series..., rerender}

  const $ = (sel, el = document) => el.querySelector(sel);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtPx = (x) => x == null ? "–" : x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtPct = (x, d = 2) => x == null ? "–" : `${x > 0 ? "+" : ""}${x.toFixed(d)}%`;
  const fmtBig = (x) => {
    if (x == null) return "–";
    const a = Math.abs(x);
    if (a >= 1e12) return (x / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return (x / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return (x / 1e6).toFixed(2) + "M";
    if (a >= 1e3) return (x / 1e3).toFixed(1) + "K";
    return String(Math.round(x));
  };

  // ---- link to the GitHub Actions "Run workflow" page ----------------------
  function workflowUrl() {
    const m = location.hostname.match(/^([^.]+)\.github\.io$/);
    if (!m) return "https://github.com";
    const repo = location.pathname.split("/").filter(Boolean)[0] || `${m[1]}.github.io`;
    return `https://github.com/${m[1]}/${repo}/actions/workflows/${WORKFLOW_FILE}`;
  }

  // ---- data ----------------------------------------------------------------
  async function load() {
    const r = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status} loading ${DATA_URL}`);
    return r.json();
  }

  function ago(iso) {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const h = Math.round(mins / 60);
    return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
  }

  function render(d) {
    charts.splice(0).forEach((c) => c.chart.remove());
    const when = new Date(d.generated_at);
    $("#meta").textContent =
      `Ranked ${when.toLocaleString()} (${ago(d.generated_at)}) · source: ${d.provider_label} · ` +
      `${d.universe_size} stocks screened, ${d.scored_count} scored`;

    const banner = $("#banner");
    const stale = (Date.now() - when.getTime()) / 36e5 > 72;
    if (d.provider === "demo") {
      banner.hidden = false;
      banner.textContent = "DEMO DATA: synthetic prices for layout testing. The first scheduled refresh replaces it with real data.";
    } else if (stale) {
      banner.hidden = false;
      banner.textContent = `This ranking is ${ago(d.generated_at)}: the scheduled refresh may be failing. Check the Actions tab.`;
    } else banner.hidden = true;

    // ranking strip
    $("#ranking").replaceChildren(...d.top.map((s, i) => {
      const li = document.createElement("li");
      li.innerHTML = `<a href="#s-${s.ticker}"><span class="r">#${i + 1}</span><span class="t"></span><span class="s">Score ${s.score.toFixed(1)}</span></a>`;
      $(".t", li).textContent = s.ticker;
      return li;
    }));

    // stock panels
    const host = $("#stocks");
    host.replaceChildren();
    const partName = Object.fromEntries(d.scoring.components.map((c) => [c.key, c]));
    d.top.forEach((s, i) => host.appendChild(stockPanel(s, i, partName)));

    // scoring logic, printed from the same JSON the ranking came from
    const sc = d.scoring;
    $("#logic-summary").textContent = sc.summary;
    $("#logic-rows").replaceChildren(...sc.components.map((c) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td></td><td class="num"></td><td></td>`;
      tr.children[0].textContent = c.name;
      tr.children[1].textContent = `${Math.round(c.weight * 100)}%`;
      tr.children[2].textContent = c.rule;
      return tr;
    }));
    $("#logic-filters").replaceChildren(...sc.filters.map((f) => Object.assign(document.createElement("li"), { textContent: f })));
    $("#logic-pipeline").textContent =
      d.shortlist_size < d.universe_size
        ? `Pipeline: ${d.universe_size} stocks screened on analyst data first; the best ${d.shortlist_size} had price history pulled for the technical sub-scores; top 5 by total score shown.`
        : `Pipeline: all ${d.universe_size} stocks in the universe were fully scored; top 5 by total score shown.`;
    $("#logic-caveat").textContent = sc.caveat;

    $("#runners").replaceChildren(...(d.runners_up || []).map((r, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${i + 6}</td><td><b></b></td><td></td><td class="num">${r.score.toFixed(1)}</td><td class="num">${fmtPct(r.upside_pct, 1)}</td>`;
      tr.children[1].firstChild.textContent = r.ticker;
      tr.children[2].textContent = r.name || "";
      return tr;
    }));
  }

  function stockPanel(s, i, partName) {
    const el = $("#stock-tpl").content.firstElementChild.cloneNode(true);
    el.id = `s-${s.ticker}`;
    $(".rank", el).textContent = i + 1;
    $(".ticker", el).textContent = s.ticker;
    $(".name", el).textContent = s.name || "";
    $(".price", el).textContent = fmtPx(s.price);
    const chg = $(".chg", el);
    chg.textContent = `${s.change_pct >= 0 ? "▲" : "▼"} ${fmtPct(s.change_pct)}`;
    chg.classList.add(s.change_pct >= 0 ? "up" : "down");
    $(".score", el).textContent = s.score.toFixed(1);

    $(".parts", el).replaceChildren(...Object.entries(s.parts).map(([k, v]) => {
      const meta = partName[k];
      const li = document.createElement("li");
      li.innerHTML = `<span></span><span class="w"></span><div class="track"><div class="fill"></div></div>`;
      li.children[0].textContent = meta.name;
      li.children[1].textContent = `${(v * meta.weight * 100).toFixed(1)} / ${Math.round(meta.weight * 100)}`;
      li.title = meta.rule;
      $(".fill", li).style.width = `${Math.round(v * 100)}%`;
      return li;
    }));

    const b = s.breakdown;
    const rows = [
      ["Avg analyst target", s.target_mean ? `$${fmtPx(s.target_mean)}` : "–"],
      ["Upside to target", fmtPct(s.upside_pct, 1)],
      ["Target range", s.target_low && s.target_high ? `$${fmtPx(s.target_low)} – $${fmtPx(s.target_high)}` : "–"],
      ["Analysts", b ? `${s.analysts} (${b.strong_buy + b.buy} buy · ${b.hold} hold · ${b.underperform + b.sell} sell)` : String(s.analysts ?? "–")],
      ["RSI(14)", s.tech.rsi14.toFixed(1)],
      ["50 / 200-day MA", `${fmtPx(s.tech.sma50)} / ${fmtPx(s.tech.sma200)}`],
      ["Up-day volume (20d)", `${Math.round(s.tech.up_volume_share * 100)}%`],
      ["Market cap", s.market_cap ? `$${fmtBig(s.market_cap)}` : "–"],
    ];
    $(".stats", el).replaceChildren(...rows.flatMap(([k, v]) => {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v;
      return [dt, dd];
    }));

    // chart needs to be in the DOM to size itself
    requestAnimationFrame(() => buildChart(el, s));
    return el;
  }

  // ---- chart (moomoo-style: price on the left, % change on the right, volume + MAVOL5 below)
  function themeOpts() {
    return {
      layout: { background: { type: "solid", color: css("--surface") }, textColor: css("--muted"), fontSize: 11, attributionLogo: false }, // attribution is in the footer
      grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
      leftPriceScale: { borderVisible: false },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    };
  }

  function sliceRange(bars, range) {
    const n = bars.t.length;
    const last = new Date(bars.t[n - 1] + "T00:00:00Z");
    const from = new Date(last);
    if (range === "1M") from.setUTCMonth(from.getUTCMonth() - 1);
    else if (range === "3M") from.setUTCMonth(from.getUTCMonth() - 3);
    else if (range === "YTD") from.setUTCMonth(0, 1), from.setUTCDate(1);
    else if (range === "1Y") from.setUTCFullYear(from.getUTCFullYear() - 1);
    else from.setUTCFullYear(from.getUTCFullYear() - 5);
    const iso = from.toISOString().slice(0, 10);
    let i0 = bars.t.findIndex((t) => t >= iso);
    if (i0 < 0) i0 = 0;
    return i0;
  }

  function buildChart(el, s) {
    const box = $(".chart", el);
    const chart = LWC.createChart(box, {
      autoSize: true,
      ...themeOpts(),
      leftPriceScale: { visible: true, borderVisible: false, scaleMargins: { top: 0.06, bottom: 0.28 } },
      rightPriceScale: { visible: true, borderVisible: false, mode: LWC.PriceScaleMode.Percentage, scaleMargins: { top: 0.06, bottom: 0.28 } },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      timeScale: { borderVisible: false, rightOffset: 2 },
      handleScroll: false, handleScale: false,
    });
    // visible series on the right (percentage) scale; an invisible twin drives the left price labels
    const pctLine = chart.addLineSeries({ priceScaleId: "right", lineWidth: 2, priceLineStyle: LWC.LineStyle.Dashed, lastValueVisible: true });
    const pctCandle = chart.addCandlestickSeries({ priceScaleId: "right", visible: false, priceLineStyle: LWC.LineStyle.Dashed, borderVisible: false });
    const pxTwin = chart.addLineSeries({ priceScaleId: "left", color: "rgba(0,0,0,0)", lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
    const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    const mavol = chart.addLineSeries({ priceScaleId: "vol", lineWidth: 1.5, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 }, visible: false });

    const st = { range: "YTD", candles: false };
    const b = s.bars;
    const legend = $(".legend", el), vlv = $(".vl-v", el), vlm = $(".vl-ma", el);
    let view = null;

    function draw() {
      const i0 = sliceRange(b, st.range);
      const up = css("--up"), down = css("--down");
      const line = [], twin = [], candle = [], v = [], ma = [];
      for (let i = i0; i < b.t.length; i++) {
        const time = b.t[i];
        line.push({ time, value: b.c[i] });
        twin.push({ time, value: b.c[i] });
        candle.push({ time, open: b.o[i], high: b.h[i], low: b.l[i], close: b.c[i] });
        const isUp = i === 0 ? b.c[i] >= b.o[i] : b.c[i] >= b.c[i - 1];
        v.push({ time, value: b.v[i], color: isUp ? up : down });
        if (i >= 4) {
          let sum = 0; for (let k = i - 4; k <= i; k++) sum += b.v[k];
          ma.push({ time, value: sum / 5 });
        }
      }
      const first = b.c[i0], last = b.c[b.c.length - 1];
      const color = last >= first ? up : down;
      pctLine.applyOptions({ color, priceLineColor: color, visible: !st.candles });
      pctCandle.applyOptions({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, priceLineColor: color, visible: st.candles });
      mavol.applyOptions({ color: css("--mavol") });
      pctLine.setData(line); pctCandle.setData(candle); pxTwin.setData(twin); vol.setData(v); mavol.setData(ma);
      chart.timeScale().fitContent();
      view = { i0, first, color };
      showLegend(null);
    }

    function showLegend(time) {
      const idx = time ? b.t.indexOf(time) : b.t.length - 1;
      if (idx < 0) return;
      const pct = (b.c[idx] / view.first - 1) * 100;
      legend.textContent = `${b.t[idx]}  O ${fmtPx(b.o[idx])}  H ${fmtPx(b.h[idx])}  L ${fmtPx(b.l[idx])}  C ${fmtPx(b.c[idx])}  ${fmtPct(pct)} vs ${st.range} start`;
      const isUp = idx === 0 ? true : b.c[idx] >= b.c[idx - 1];
      vlv.textContent = `VOL: ${fmtBig(b.v[idx])}`;
      vlv.style.color = isUp ? css("--up") : css("--down");
      let sum = 0, n = 0; for (let k = Math.max(0, idx - 4); k <= idx; k++) { sum += b.v[k]; n++; }
      vlm.textContent = `MAVOL5: ${fmtBig(sum / n)}`;
    }
    chart.subscribeCrosshairMove((p) => showLegend(p && p.time ? (typeof p.time === "string" ? p.time : null) : null));

    // range tabs
    const tabs = $(".ranges", el);
    RANGES.forEach((r) => {
      const btn = document.createElement("button");
      btn.type = "button"; btn.role = "tab"; btn.textContent = r;
      btn.setAttribute("aria-selected", String(r === st.range));
      btn.onclick = () => {
        st.range = r;
        tabs.querySelectorAll("button").forEach((x) => x.setAttribute("aria-selected", String(x === btn)));
        draw();
      };
      tabs.appendChild(btn);
    });
    const ct = $(".ctype", el);
    ct.onclick = () => { st.candles = !st.candles; ct.textContent = st.candles ? "Line" : "Candles"; draw(); };

    draw();
    charts.push({ chart, rerender: () => { chart.applyOptions(themeOpts()); draw(); } });
  }

  // re-colour charts when the OS theme flips
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => charts.forEach((c) => c.rerender()));

  let shown = null; // generated_at of what's on screen
  async function refresh(force = true) {
    const btn = $("#reload");
    btn.disabled = true; btn.textContent = "Loading…";
    try {
      const d = await load();
      if (force || d.generated_at !== shown) { render(d); shown = d.generated_at; }
    }
    catch (e) { $("#meta").textContent = `Could not load data: ${e.message}`; }
    finally { btn.disabled = false; btn.textContent = "Reload data"; }
  }

  $("#run-refresh").href = workflowUrl();
  $("#reload").addEventListener("click", () => refresh(true));
  refresh(true);
  // pick up new data automatically if the tab is left open (only redraws when the ranking changed)
  setInterval(() => refresh(false), 15 * 60 * 1000);
})();
