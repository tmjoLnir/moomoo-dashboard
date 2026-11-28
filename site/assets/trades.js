/* "My trades" panel. Reads data/trades.json: the daily swing-trade check's snapshot
   (Claude scheduled task "Daily post-US-close swing-trade check", published to the
   trades-data branch). Independent of the top-5 ranking in app.js. */
(() => {
  "use strict";
  const LWC = window.LightweightCharts;
  const URL_ = "data/trades.json";
  const STALE_DAYS = 4; // runs Tue-Sat; Sat -> Tue is the longest normal gap
  let charts = [];

  const $ = (sel, el = document) => el.querySelector(sel);
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmtPct = (x) => x == null ? "–" : `${x > 0 ? "+" : ""}${x.toFixed(2)}%`;
  const money = (x) => x == null ? "–" : "$" + x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: Math.abs(x) < 10 ? 3 : 2 });
  const slug = (x) => String(x || "").toLowerCase().replace(/[^a-z]+/g, "-");
  const pill = (txt) => Object.assign(document.createElement("span"), { className: `pill ${slug(txt)}`, textContent: txt });
  const ago = (iso) => {
    const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (mins < 60) return `${Math.max(mins, 0)} min ago`;
    const h = Math.round(mins / 60);
    return h < 48 ? `${h} h ago` : `${Math.round(h / 24)} days ago`;
  };
  const themeOpts = () => ({
    layout: { background: { type: "solid", color: css("--surface") }, textColor: css("--muted"), fontSize: 10, attributionLogo: false },
    grid: { vertLines: { color: css("--grid") }, horzLines: { color: css("--grid") } },
  });

  async function load() {
    try {
      const r = await fetch(`${URL_}?t=${Date.now()}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      render(await r.json());
    } catch (e) { $("#trades").hidden = true; }
  }

  function render(d) {
    charts.forEach((c) => c.chart.remove());
    charts = [];
    $("#trades").hidden = false;
    $("#trades-meta").textContent =
      `US session ${d.session_date}${d.session_note ? ` (${d.session_note})` : ""} · checked ${new Date(d.generated_at).toLocaleString()} (${ago(d.generated_at)})`;
    const ban = $("#trades-banner");
    ban.hidden = (Date.now() - new Date(d.generated_at).getTime()) / 864e5 <= STALE_DAYS;
    ban.textContent = `This trade check is from ${ago(d.generated_at)}. The daily swing-trade check may have failed; run it in Claude.`;

    const T = d.tickers;
    const close = (t) => {
      const sp = document.createElement("span");
      sp.textContent = `${money(t.close)} `;
      sp.append(Object.assign(document.createElement("span"), { className: `chg ${t.change_pct >= 0 ? "up" : "down"}`, textContent: fmtPct(t.change_pct) }));
      return sp;
    };
    const rows = [
      ["Close", close],
      ["Range", (t) => t.day_low != null ? `${money(t.day_low)}–${money(t.day_high)}` : "–"],
      ["Pre / AH", (t) => t.extended || "–"],
      ["Vol vs avg", (t) => t.volume_ratio != null ? `${t.volume_ratio.toFixed(2)}x` : "–"],
      ["Candle", (t) => t.candle || "–", true],
      ["Status", (t) => pill(t.status)],
      ["Entry", (t) => money(t.entry)],
      ["Stop", (t) => money(t.stop)],
      ["Targets", (t) => (t.targets || []).map((x) => `${money(x.price)} (${x.rr.toFixed(1)}R)`).join(" / ") || "–", true],
      ["Size", (t) => t.shares ? `${t.shares.toLocaleString()} sh` : "–"],
      ["Verdict", (t) => pill(t.verdict)],
    ];
    const hr = document.createElement("tr");
    hr.append(document.createElement("th"), ...T.map((t) => Object.assign(document.createElement("th"), { textContent: t.ticker })));
    const thead = document.createElement("thead");
    thead.append(hr);
    const tbody = document.createElement("tbody");
    rows.forEach(([label, fn, wrap]) => {
      const tr = document.createElement("tr");
      tr.append(Object.assign(document.createElement("th"), { textContent: label, scope: "row" }));
      T.forEach((t) => {
        const td = document.createElement("td");
        if (wrap) td.className = "tw";
        const v = fn(t);
        if (v instanceof Node) td.append(v); else td.textContent = v;
        tr.append(td);
      });
      tbody.append(tr);
    });
    $("#trades-cmp").replaceChildren(thead, tbody);

    $("#trades-cards").replaceChildren(...T.map((t) => {
      const c = document.createElement("article");
      c.className = "tcard";
      c.innerHTML = `<div class="tcard-head"><span><b></b> <span class="muted"></span></span></div><div class="tchart"></div><p class="tplan"></p>`;
      $("b", c).textContent = t.ticker;
      $(".muted", c).textContent = t.name || "";
      $(".tcard-head", c).append(pill(t.verdict));
      $(".tplan", c).textContent = t.plan;
      if (t.note) c.append(Object.assign(document.createElement("p"), { className: "tnote", textContent: t.note }));
      if (t.bars && t.bars.t && t.bars.t.length > 1) requestAnimationFrame(() => chart($(".tchart", c), t));
      else $(".tchart", c).hidden = true;
      return c;
    }));

    const li = (date, text) => {
      const el = document.createElement("li");
      if (date) el.append(Object.assign(document.createElement("time"), { textContent: date }));
      el.append(document.createTextNode(text));
      return el;
    };
    $("#trades-events").replaceChildren(...(d.events || []).map((e) => li(e.date, e.text)));
    $("#trades-news").replaceChildren(...(d.news || []).map((n) => li(null, n)));
    $("#trades-log").replaceChildren(...(d.log || []).slice(-8).reverse().map((e) => li(e.date, e.text)));
    const a = d.account;
    $("#trades-note").textContent =
      (a ? `Sizing: example $${a.size.toLocaleString()} account, ${a.risk_pct}% ($${a.risk_usd}) risk per trade. ` : "") +
      "Claude can't see your moomoo account or fills: confirm positions and stops in moomoo. Read-only analysis, not investment advice.";
  }

  function chart(box, t) {
    const ch = LWC.createChart(box, {
      autoSize: true, ...themeOpts(),
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { borderVisible: false, rightOffset: 1 },
      handleScroll: false, handleScale: false,
    });
    const up = css("--up"), down = css("--down");
    const s = ch.addCandlestickSeries({ upColor: up, downColor: down, wickUpColor: up, wickDownColor: down, borderVisible: false, priceLineVisible: false });
    const b = t.bars;
    s.setData(b.t.map((time, i) => ({ time, open: b.o[i], high: b.h[i], low: b.l[i], close: b.c[i] })));
    const line = (price, color, title, lineStyle) => {
      if (price != null) s.createPriceLine({ price, color, title, lineWidth: 1, lineStyle, axisLabelVisible: true });
    };
    line(t.entry, css("--accent"), "entry", LWC.LineStyle.Solid);
    line(t.stop, down, "stop", LWC.LineStyle.Dashed);
    (t.targets || []).forEach((x, i) => line(x.price, up, `T${i + 1}`, LWC.LineStyle.Dotted));
    ch.timeScale().fitContent();
    charts.push({ chart: ch });
  }

  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", load);
  document.getElementById("reload").addEventListener("click", load);
  load();
  setInterval(load, 15 * 60 * 1000);
})();
