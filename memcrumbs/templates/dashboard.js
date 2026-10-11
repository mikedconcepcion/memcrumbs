(function () {
"use strict";
/* memcrumbs dashboard. Everything is built with textContent and setAttribute: wiki text is never parsed as HTML. */
const D = JSON.parse(document.getElementById("data").textContent);
const $ = id => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
/* a word in a command someone copies: bare when safe, else single-quoted (literal in bash and PowerShell); a word
   with a single quote cannot be quoted for both, so it is withheld (null): a page name must never run code */
const shq = w => /^[\w.+=/:-]+$/.test(String(w)) ? String(w) : (/['\n]/.test(String(w)) ? null : `'${w}'`);
const P = D.project, stale = P.stale_days, CLI = `memcrumbs -p ${shq(P.name) || "<project>"}`;
const H = D.history || [], pages = D.pages, items = D.plan.items;
let uid = 0;

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = String(text);
  if (cls) e.className = cls;
  return e;
}
function svg(tag, attrs) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  return e;
}
function add(parent, ...kids) { kids.forEach(k => k !== null && k !== undefined && parent.appendChild(typeof k === "string" ? document.createTextNode(k) : k)); return parent; }
const fmt = n => n === null || n === undefined ? "–" : Number(n).toLocaleString();
const plural = (n, word) => `${fmt(n)} ${word}${n === 1 ? "" : "s"}`;
const ago = m => m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
const short = day => day ? day.slice(5) : "";

/* theme */
const THEMES = ["auto", "light", "dark"];
function setTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  $("theme").textContent = "Theme: " + t; $("theme").dataset.t = t;
  try { localStorage.setItem("memcrumbs-theme", t); } catch (e) { /* private window: auto */ }
}
let saved = "auto";
try { saved = localStorage.getItem("memcrumbs-theme") || "auto"; } catch (e) { saved = "auto"; }
setTheme(THEMES.includes(saved) ? saved : "auto");
$("theme").onclick = () => setTheme(THEMES[(THEMES.indexOf($("theme").dataset.t) + 1) % THEMES.length]);

/* copy a command */
function copy(text, btn) {
  const label = btn.dataset.label || btn.textContent; btn.dataset.label = label;
  const done = () => { btn.textContent = "Copied"; setTimeout(() => { btn.textContent = label; }, 1200); };
  const fallback = () => {
    const ta = el("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch (e) { /* the text stays visible to copy by hand */ }
    ta.remove();
  };
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
}
function cmdChip(text) {
  const w = el("div", null, "cmd"), b = el("button", "Copy");
  b.type = "button"; b.onclick = () => copy(text, b);
  return add(w, el("code", text), b);
}

/* page classes and colours */
const KIND = {decision: "--k-decision", incident: "--k-incident", runbook: "--k-runbook", journal: "--k-journal"};
const kindColor = k => `var(${KIND[k] || "--k-component"})`;
const GROUP = {decisions: "--k-decision", incidents: "--k-incident", runbooks: "--k-runbook", journal: "--k-journal", "": "--accent"};
const SPARE = ["--k-component", "--k-other", "--k-pink", "--k-reference", "--k-lime", "--k-system"];
const groupColors = {};
let spare = 0;
[...new Set(pages.map(p => p.group))].sort().forEach(g => {
  groupColors[g] = `var(${GROUP[g.toLowerCase()] || SPARE[spare++ % SPARE.length]})`;
});
const isRecord = p => p.kind === "journal" || p.status === "superseded" || p.status === "rejected";
function fresh(p) {
  if (isRecord(p)) return "record";
  if (p.age === null) return "never";
  return p.age <= stale / 2 ? "fresh" : p.age <= stale ? "aging" : "stale";
}
const FRESH = {
  fresh: ["var(--ok)", `verified in the last ${Math.round(stale / 2)} days`],
  aging: ["var(--fresh2)", `verified ${Math.round(stale / 2)}–${stale} days ago`],
  stale: ["var(--warn)", `older than ${stale} days`],
  never: ["var(--faint)", "never verified"],
  record: ["var(--line)", "journal and retired pages"],
};
const ORDER = ["fresh", "aging", "stale", "never", "record"];
const byPath = new Map(pages.map(p => [p.path, p]));
const titleOf = path => (byPath.get(path) || {}).title || path;

/* header */
$("title").textContent = P.title;
$("meta").textContent = [P.name, `generated ${P.generated}`,
  `${fmt(D.index.docs)} docs · ${fmt(D.index.symbols)} symbols indexed`,
  D.index.refreshed_min_ago !== null ? `index refreshed ${ago(D.index.refreshed_min_ago)}` : "index not built yet",
  `memcrumbs ${P.version}`].join(" · ");
add($("regen"), "Regenerate it: ", cmdChip(`${CLI} dashboard --open`));

/* tabs */
const TABS = [...document.querySelectorAll("section[data-tab]")].map(s => s.dataset.tab);
function show(hash) {
  const cut = hash.indexOf("/");                            // #wiki/<page> opens a page in the reader
  let tab = cut < 0 ? hash : hash.slice(0, cut);
  if (!TABS.includes(tab)) tab = "overview";
  document.querySelectorAll("section[data-tab]").forEach(s => s.classList.toggle("on", s.dataset.tab === tab));
  document.querySelectorAll("#tabs a").forEach(a => {
    if (a.getAttribute("href") === "#" + tab) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  if (tab === "map") drawMap();
  if (tab === "wiki") {
    let name = "";
    try { name = cut < 0 ? "" : decodeURIComponent(hash.slice(cut + 1)); } catch (e) { name = ""; }
    openPage(name);
  }
}
window.addEventListener("hashchange", () => { show(location.hash.slice(1)); window.scrollTo(0, 0); });
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
    e.preventDefault();
    if (!location.hash.startsWith("#wiki")) location.hash = "wiki";
    $("wikisearch").focus();
  }
});
const pageHref = p => "#wiki/" + encodeURIComponent(p.page);
function pageLinkTo(p, text) { const a = el("a", text === undefined ? p.title : text, "wl"); a.href = pageHref(p); return a; }

/* small charts */
function ring(pct) {
  const s = svg("svg", {viewBox: "0 0 120 120", width: 136, height: 136, role: "img",
    "aria-label": pct === null ? "no pages" : `trust ${pct} percent`});
  const r = 50, C = 2 * Math.PI * r;
  const col = pct === null ? "var(--faint)" : D.check.errors ? "var(--bad)" : pct >= 80 ? "var(--ok)" : "var(--warn)";
  s.appendChild(svg("circle", {cx: 60, cy: 60, r, fill: "none", stroke: "var(--bg2)", "stroke-width": 12}));
  if (pct) {
    const arc = svg("circle", {cx: 60, cy: 60, r, fill: "none", stroke: col, "stroke-width": 12, "stroke-linecap": "round",
      transform: "rotate(-90 60 60)", "stroke-dasharray": `0 ${C}`});
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) arc.style.transition = "stroke-dasharray .9s cubic-bezier(.2,.8,.2,1)";
    s.appendChild(arc);
    requestAnimationFrame(() => requestAnimationFrame(() => arc.setAttribute("stroke-dasharray", `${C * Math.min(pct, 100) / 100} ${C}`)));
  }
  const a = 0.8 * 2 * Math.PI - Math.PI / 2;                      // the 80% target
  s.appendChild(svg("line", {x1: 60 + 41 * Math.cos(a), y1: 60 + 41 * Math.sin(a), x2: 60 + 59 * Math.cos(a),
    y2: 60 + 59 * Math.sin(a), stroke: "var(--ink)", "stroke-opacity": .35, "stroke-width": 2}));
  const t = svg("text", {x: 60, y: 63, "text-anchor": "middle", "font-size": 27, "font-weight": 650, fill: "var(--ink)"});
  t.textContent = pct === null ? "–" : pct + "%";
  const k = svg("text", {x: 60, y: 82, "text-anchor": "middle", "font-size": 10.5, fill: "var(--muted)"});
  k.textContent = "target 80%";
  return add(s, t, k);
}
function spark(vals, o) {
  o = o || {};
  const w = o.w || 300, h = o.h || 56, lo = o.min !== undefined ? o.min : Math.min(...vals),
    hi = o.max !== undefined ? o.max : Math.max(...vals), span = hi - lo || 1, col = o.color || "var(--accent)";
  const pts = vals.map((v, i) => [vals.length === 1 ? w / 2 : 3 + i * (w - 6) / (vals.length - 1), h - 4 - (v - lo) / span * (h - 10)]);
  const s = svg("svg", {viewBox: `0 0 ${w} ${h}`, class: "chart", "aria-hidden": "true"});
  const id = "sp" + (++uid), grad = svg("linearGradient", {id, x1: 0, y1: 0, x2: 0, y2: 1});
  add(grad, svg("stop", {offset: "0", "stop-color": col, "stop-opacity": .28}), svg("stop", {offset: "1", "stop-color": col, "stop-opacity": 0}));
  const defs = svg("defs"); defs.appendChild(grad); s.appendChild(defs);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  s.appendChild(svg("path", {d: `${line} L${pts[pts.length - 1][0].toFixed(1)} ${h} L${pts[0][0].toFixed(1)} ${h} Z`, fill: `url(#${id})`}));
  s.appendChild(svg("path", {d: line, fill: "none", stroke: col, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round"}));
  const last = pts[pts.length - 1];
  s.appendChild(svg("circle", {cx: last[0], cy: last[1], r: 3.5, fill: col, stroke: "var(--card)", "stroke-width": 1.5}));
  return s;
}
function dayBars(days, h) {
  const w = 600, max = Math.max(1, ...days.map(d => d.lookups)), bw = w / days.length;
  const s = svg("svg", {viewBox: `0 0 ${w} ${h + 18}`, class: "chart", role: "img", "aria-label": "lookups per day"});
  [0.5, 1].forEach(f => s.appendChild(svg("line", {x1: 0, x2: w, y1: h - f * (h - 4), y2: h - f * (h - 4), stroke: "var(--line)", "stroke-dasharray": "3 4"})));
  days.forEach((d, i) => {
    const g = svg("g"), x = i * bw + bw * 0.18, bwid = bw * 0.64, found = d.lookups - d.empty;
    const hf = found / max * (h - 4), he = d.empty / max * (h - 4);
    g.appendChild(svg("rect", {x, y: 0, width: bw * 0.64, height: h, fill: "transparent"}));
    if (found) g.appendChild(svg("rect", {x, y: h - hf, width: bwid, height: hf, rx: 2.5, fill: "var(--accent)"}));
    if (d.empty) g.appendChild(svg("rect", {x, y: h - hf - he, width: bwid, height: he, rx: 2.5, fill: "var(--warn)"}));
    if (!d.lookups) g.appendChild(svg("rect", {x, y: h - 2, width: bwid, height: 2, rx: 1, fill: "var(--line)"}));
    const tip = svg("title"); tip.textContent = `${d.day}: ${plural(d.lookups, "lookup")}, ${d.empty} found nothing, ${plural(d.sessions, "session")}`;
    g.appendChild(tip); s.appendChild(g);
  });
  [[0, "start"], [Math.floor(days.length / 2), "middle"], [days.length - 1, "end"]].forEach(([i, anchor]) => {
    const t = svg("text", {x: anchor === "start" ? 0 : anchor === "end" ? w : (i + 0.5) * bw, y: h + 15, "text-anchor": anchor, "font-size": 11, fill: "var(--muted)"});
    t.textContent = short(days[i].day); s.appendChild(t);
  });
  const top = svg("text", {x: 0, y: 10, "text-anchor": "start", "font-size": 11, fill: "var(--muted)"});
  top.textContent = `${max}/day`; s.appendChild(top);
  return s;
}
function empty(title, text, cmd) {
  const e = add(el("div", null, "empty"), el("b", title), el("div", text));
  if (cmd) e.appendChild(cmdChip(cmd));
  return e;
}

/* overview: trust */
const T = D.trust, errs = D.check.errors, nAttention = items.length;
$("ring").appendChild(ring(T));
const verdict = T === null ? ["No pages yet", ""] : errs ? ["Fix now", "bad"] : T >= 80 ? ["Healthy", "ok"]
  : T >= 60 ? ["Needs a little care", "warn"] : ["Needs attention", "warn"];
$("verdict").textContent = verdict[0]; $("verdict").className = "verdict " + verdict[1];
const prev = H.length > 1 ? H[H.length - 2] : null;
if (prev && prev.trust !== null && prev.trust !== undefined && T !== null) {
  const d = T - prev.trust;
  $("verdict").appendChild(el("span", d === 0 ? `no change since ${prev.day}` : `${d > 0 ? "+" : ""}${d} since ${prev.day}`,
    "delta " + (d >= 0 ? "up" : "down")));
}
$("verdictwhy").textContent = T === null ? "Write a first page, then run memcrumbs index."
  : (errs ? `${plural(errs, "check error")} to fix first. ` : "") +
    `${pages.length - nAttention} of ${plural(pages.length, "page")} need nothing; ${nAttention} need a refresh or a fix.`;
const trustVals = H.map(h => h.trust).filter(v => v !== null && v !== undefined);
if (trustVals.length > 1) {
  add($("trend"), spark(trustVals, {min: 0, max: 100, color: T >= 80 ? "var(--ok)" : "var(--warn)", h: 46}),
    el("div", `trust over the last ${plural(trustVals.length, "snapshot")} (one a day, when the dashboard is generated)`, "sub"));
} else {
  $("trend").appendChild(el("div", "The trend line starts once the dashboard has been generated on two different days.", "note"));
}

/* overview: KPIs */
function kpi(k, v, unit, foot) {
  const box = el("div", null, "kpi"), val = el("div", v, "v");
  if (unit) val.appendChild(el("small", " " + unit));
  add(box, el("div", k, "k"), val);
  (Array.isArray(foot) ? foot : [foot]).forEach(f => f && box.appendChild(typeof f === "string" ? el("div", f, "foot") : f));
  $("kpis").appendChild(box);
}
const kinds = {};
pages.forEach(p => { kinds[p.kind] = (kinds[p.kind] || 0) + 1; });
const kindBar = el("div", null, "meter");
Object.entries(kinds).sort((a, b) => b[1] - a[1]).forEach(([k, n]) => {
  const i = el("i"); i.style.width = (100 * n / pages.length) + "%"; i.style.background = kindColor(k); i.title = `${k}: ${n}`;
  kindBar.appendChild(i);
});
kpi("Wiki pages", fmt(pages.length), "", [kindBar, Object.entries(kinds).sort((a, b) => b[1] - a[1]).slice(0, 3)
  .map(([k, n]) => `${n} ${k}`).join(" · ")]);
const hdr = D.header, hdrBar = el("div", null, "meter"), hdrFill = el("i");
hdrFill.style.width = Math.min(100, 100 * hdr.tokens / hdr.budget) + "%";
hdrFill.style.background = hdr.cut ? "var(--warn)" : "var(--ok)"; hdrBar.appendChild(hdrFill);
kpi("Session header", fmt(hdr.tokens), `/ ${fmt(hdr.budget)} tokens`, [hdrBar,
  hdr.cut ? "cut to fit its budget" : "fits its budget, every session"]);
const days = D.daily || [], lookups = days.reduce((a, d) => a + d.lookups, 0),
  emptyN = days.reduce((a, d) => a + d.empty, 0), sessions = days.reduce((a, d) => a + d.sessions, 0);
kpi("Lookups, 30 days", fmt(lookups), "", [lookups ? spark(days.map(d => d.lookups), {h: 34, min: 0}) : null,
  lookups ? `${Math.round(100 * emptyN / lookups)}% found nothing · ${plural(sessions, "session")}` : "none counted yet"]);
kpi("Recall on your questions", D.bench ? Math.round(100 * D.bench.total.recall_at_3) + "%" : "–", D.bench ? "in top 3" : "",
  D.bench ? `${plural(D.bench.total.n, "question")} · ≈ ${fmt(D.bench.total.tokens_mean)} tokens per answer`
    : "add the questions you ask (Agent usage)");

/* overview: needs you */
const A = [];
const st = D.plan.state || {}, approved = new Set(st.approved || []), done = new Set(st.done || []);
const left = (st.approved || []).filter(p => !done.has(p));
const hot = items.filter(c => c.hits > 0).sort((a, b) => b.hits - a.hits);
const moved = items.filter(c => c.reasons.includes("sources-changed"));
const names = list => list.slice(0, 3).map(c => c.page).join(", ") + (list.length > 3 ? ` and ${list.length - 3} more` : "");
const header = new Set(["rules", "index", "gotchas"]);
const inbound = {};
pages.forEach(p => p.links.forEach(t => { inbound[t] = (inbound[t] || 0) + 1; }));
const orphans = pages.filter(p => !p.links.length && !inbound[p.page] && !header.has(p.page.toLowerCase()) && p.kind !== "journal");
const unread = orphans.filter(p => !p.hits);
const sg = D.suggest || {}, nsg = Object.values(sg).reduce((a, n) => a + n, 0);
if (nsg) A.push(["info", `${plural(nsg, "suggestion")} to look at`, Object.entries(sg).map(([k, n]) => `${n} ${k}`).join(" · ") +
  ". Each shows its evidence and a patch; nothing is applied without your yes.", "overview", `${CLI} suggest`]);
const rv = D.review || {lines: 0, pages: 0, kept: 0};
if (rv.lines || rv.pages) A.push(["warn", `${plural(rv.lines + rv.pages, "item")} wait for your review`,
  `${plural(rv.lines, "new rule/gotcha line")} (kept out of the session header until then) and ${plural(rv.pages, "agent-written page")}. Approve them in your own terminal, not through the agent.`, "overview", `${CLI} review`]);
if (errs) A.push(["bad", `${plural(errs, "check error")} in wiki pages`, "Secrets or instruction-like text. Agents read these pages, so fix them first.", "checks", `${CLI} check`]);
if (left.length) A.push(["info", `Refresh in progress: ${plural(left.length, "page")} left`, `You approved a budget of ≈ ${fmt(st.budget)} tokens; ≈ ${fmt(st.spent || 0)} used. Tell the agent:`, "refresh", "memcrumbs plan next"]);
if (hot.length) A.push(["warn", `${plural(hot.length, "page")} your agent reads need a refresh`, names(hot), "refresh"]);
if (moved.length) A.push(["warn", `${plural(moved.length, "page")} describe code that changed`, "Their sources changed after they were verified: " + names(moved), "refresh"]);
if (hdr.cut) {
  const want = hdr.sections.reduce((a, s) => a + s.tokens, 0);
  A.push(["warn", "The session header is over its budget", `Its sections ask for ≈ ${fmt(want)} tokens against ${fmt(hdr.budget)}, so some lines sit behind a command. Shorten rules or gotchas, or raise [status] max_tokens (at most 1500).`, "overview"]);
}
if (D.bench && D.bench.misses.length) A.push(["warn", `${plural(D.bench.misses.length, "question")} of yours missed the top 3`, "Content gaps: write or link the page that answers them, in the words people use.", "usage"]);
const zero = (D.usage.find || {}).zero_results_pct;
if (zero !== undefined && zero >= 15) A.push(["warn", `${zero}% of lookups found nothing`, "Agents asked about things the wiki does not cover yet. When you spot one, add it to your bench.", "usage"]);
if (unread.length) A.push(["info", `${plural(unread.length, "page")} no page links to and no agent has read`, "Link them from a related page or from the map in index.md, or retire them: " + names(unread), "map"]);
const rest = items.length - hot.length;
if (rest > 0) A.push(["info", `${plural(rest, "other page")} stale or unverified`, "Agents rarely read them, so refresh them when it suits you.", "refresh"]);
if (!D.bench) A.push(["info", "Measure recall on your own questions", "When a lookup misses, record the question and the page that answers it.", "usage", `${CLI} bench --add "<question>" --expect <page>`]);
if (!A.length || (A.length === 1 && A[0][0] === "info" && !errs && !items.length)) {
  $("actions").appendChild(add(el("li"), el("span", null, "dot ok"), add(el("div"), el("b", "All clear"),
    el("div", "Every page is verified, current and clean. Nothing needs you today.", "why")), el("span")));
}
A.forEach(([sev, title, why, tab, cmd]) => {
  const body = add(el("div"), el("b", title), el("div", why, "why"));
  if (cmd) body.appendChild(cmdChip(cmd));
  const go = el("a", "Open", "go"); go.href = "#" + tab;
  $("actions").appendChild(add(el("li"), el("span", null, "dot " + sev), body, tab === "overview" ? el("span") : go));
});

/* overview: freshness strip */
const counts = {};
pages.slice().sort((a, b) => ORDER.indexOf(fresh(a)) - ORDER.indexOf(fresh(b)) || (a.age || 0) - (b.age || 0)).forEach(p => {
  const f = fresh(p), sq = el("span"); counts[f] = (counts[f] || 0) + 1;
  sq.style.background = FRESH[f][0]; sq.title = `${p.title} · ${p.age === null ? "never verified" : p.age + " days"}`;
  $("strip").appendChild(sq);
});
ORDER.filter(f => counts[f]).forEach(f => {
  const i = el("i"); i.style.background = FRESH[f][0];
  $("striplegend").appendChild(add(el("span"), i, `${counts[f]} ${FRESH[f][1]}`));
});
if (!pages.length) $("strip").replaceWith(empty("No pages yet", "Write the first page in the wiki folder."));

/* overview: header composition */
const PAL = ["var(--accent)", "var(--k-runbook)", "var(--k-decision)", "var(--k-incident)", "var(--k-system)", "var(--k-other)"];
const want = hdr.sections.reduce((a, s) => a + s.tokens, 0), scale = Math.max(hdr.budget, want, 1);
hdr.sections.forEach((s, i) => {
  const seg = el("i"); seg.style.width = (100 * s.tokens / scale) + "%"; seg.style.background = PAL[i % PAL.length];
  seg.title = `${s.title}: ≈ ${s.tokens} tokens, ${plural(s.lines, "line")}`; $("hdrbar").appendChild(seg);
  const sw = el("i"); sw.style.background = PAL[i % PAL.length];
  $("hdrlegend").appendChild(add(el("span"), sw, `${s.title} ≈ ${fmt(s.tokens)}`));
});
$("hdrsub").textContent = `≈ ${fmt(hdr.tokens)} of ${fmt(hdr.budget)} tokens, injected at the start of every agent session.`;
$("hdrnote").textContent = want > hdr.budget
  ? `The sections ask for ≈ ${fmt(want)} tokens; each cut section ends with the command that shows the rest.`
  : "Everything fits. Keep rules and gotchas short: every line here is paid for in every session.";

/* overview: most read */
const mostRead = pages.filter(p => p.hits).sort((a, b) => b.hits - a.hits).slice(0, 8);
mostRead.forEach(p => {
  const bar = el("div", null, "b"), fill = el("i"); fill.style.width = (100 * p.hits / mostRead[0].hits) + "%";
  if (fresh(p) === "stale" || fresh(p) === "never") fill.style.background = "var(--warn)";
  bar.appendChild(fill);
  const t = add(el("div", null, "t"), pageLinkTo(p)); t.title = p.path;
  $("toppages").appendChild(add(el("li"), t, bar, el("div", fmt(p.hits), "n")));
});
if (!mostRead.length) $("toppages").replaceWith(empty("No reads counted yet", "Reads are counted when an agent runs find or page."));
else $("toppages").after(el("p", "Amber bars: read often, but stale or never verified. Those are the best pages to refresh.", "note"));

/* lookups */
$("lookupsub").textContent = lookups ? `${plural(lookups, "lookup")} · ${plural(sessions, "session")} · ${emptyN} found nothing (amber)` : "";
[["lookups", 110], ["lookups2", 150]].forEach(([id, h]) => $(id).appendChild(lookups ? dayBars(days, h)
  : empty("No lookups in the last 30 days", "They are counted when agents run find, page, sym or outline.")));

/* refresh control */
const planTok = items.reduce((a, c) => a + c.tokens, 0);
const reasonCls = {"secret": "bad", "injection": "bad", "sources-changed": "warn", "stale": "warn"};
$("b-refresh").textContent = items.length || "";
if (hot.length) $("b-refresh").className = "badge warn";
$("budget").value = st.budget || Math.min(planTok, 20000);
if ((st.approved || []).length) $("approved").textContent = `Approved ${st.approved_at || ""}: ${plural(st.approved.length, "page")} · ` +
  `budget ${fmt(st.budget || 0)} · used ≈ ${fmt(st.spent || 0)} · done ${done.size}`;
const boxes = [], SHOWN = 12;
items.forEach(c => {
  const cb = el("input"); cb.type = "checkbox"; cb.checked = approved.has(c.page) && !done.has(c.page);
  cb.dataset.page = c.page; cb.dataset.tokens = c.tokens; cb.setAttribute("aria-label", "select " + c.page);
  cb.addEventListener("change", update); boxes.push(cb);
  const why = el("div", null, "chips"); why.style.margin = "0";
  c.reasons.forEach(r => why.appendChild(el("span", r, "chip " + (reasonCls[r] || ""))));
  const target = byPath.get(c.path);
  const name = add(el("div"), add(el("div"), target ? pageLinkTo(target) : titleOf(c.path)), el("div", c.path, "sub"));
  if (c.sources.length) name.appendChild(el("div", "changed: " + c.sources.join(", "), "sub"));
  const state = done.has(c.page) ? el("span", "done", "chip ok") : approved.has(c.page) ? el("span", "approved", "chip") : "";
  const tr = el("tr");
  [cb, name, why].forEach(x => tr.appendChild(add(el("td"), x)));
  tr.appendChild(el("td", fmt(c.tokens), "n")); tr.appendChild(el("td", fmt(c.hits), "n")); tr.appendChild(add(el("td"), state));
  if (boxes.length > SHOWN) { tr.hidden = true; tr.dataset.more = "1"; }
  $("items").appendChild(tr);
});
if (boxes.length > SHOWN) {
  const more = $("more"); $("morebar").hidden = false; more.textContent = `Show all ${boxes.length}`;
  more.onclick = () => {
    const open = more.textContent.startsWith("Show all");
    document.querySelectorAll("tr[data-more]").forEach(r => { r.hidden = !open; });
    more.textContent = open ? `Show the top ${SHOWN}` : `Show all ${boxes.length}`;
  };
}
if (!items.length) {
  const td = el("td"); td.colSpan = 6; td.appendChild(empty("Nothing to refresh", "Every page is verified, current and clean."));
  $("items").appendChild(add(el("tr"), td));
}
function update() {
  const sel = boxes.filter(b => b.checked), tok = sel.reduce((a, b) => a + Number(b.dataset.tokens), 0);
  const budget = Number($("budget").value) || 0, over = budget && tok > budget;
  $("sum").textContent = `${plural(sel.length, "page")} selected · ≈ ${fmt(tok)} of ${fmt(budget || tok)} tokens` + (over ? " · over budget" : "");
  $("sum").className = "sub" + (over ? " over" : "");
  $("budgetfill").style.width = (budget ? Math.min(100, 100 * tok / budget) : tok ? 100 : 0) + "%";
  $("budgetfill").style.background = over ? "var(--bad)" : "var(--accent)";
  const names = sel.map(b => b.dataset.page), withheld = names.filter(n => shq(n) === null);
  const list = shq(names.filter(n => shq(n) !== null).join(","));
  $("cmd").textContent = (list ? `${CLI} plan --approve ${list} --budget ${budget || tok}` : `${CLI} plan --clear`) +
    (withheld.length ? `\n# left out ${withheld.length} page(s) whose names hold a quote: rename them` : "");
}
$("fit").onclick = () => {
  let room = Number($("budget").value) || 0;
  boxes.forEach(b => { const t = Number(b.dataset.tokens); b.checked = t <= room; if (b.checked) room -= t; });
  update();
};
$("all").onclick = () => { boxes.forEach(b => { b.checked = true; }); update(); };
$("none").onclick = () => { boxes.forEach(b => { b.checked = false; }); update(); };
$("budget").addEventListener("input", update);
$("copy").onclick = () => copy($("cmd").textContent, $("copy"));
update();

/* pages */
let kindFilter = "";
function renderPages() {
  const q = $("filter").value.toLowerCase(), body = $("pages"); body.textContent = "";
  const list = pages.filter(p => (!kindFilter || p.kind === kindFilter) &&
    (!q || (p.path + " " + p.title + " " + p.kind + " " + p.summary).toLowerCase().includes(q)))
    .sort((a, b) => (b.age === null ? 1e9 : b.age) - (a.age === null ? 1e9 : a.age));
  list.forEach(p => {
    const f = fresh(p), bar = el("div", null, "agebar"), fill = el("i");
    fill.style.width = (p.age === null ? 100 : Math.min(100, 100 * p.age / (2 * stale))) + "%"; fill.style.background = FRESH[f][0];
    bar.appendChild(fill);
    const kind = add(el("span", null, "chip"), (() => { const s = el("span", null, "sw"); s.style.background = kindColor(p.kind); return s; })(), p.kind);
    const status = p.status ? el("span", p.status, "chip " + (isRecord(p) ? "" : "ok")) : "";
    const tr = el("tr");
    [add(el("div"), add(el("div"), pageLinkTo(p)), el("div", p.path, "sub")), kind, p.verified || "–",
      add(el("div"), el("div", p.age === null ? "never" : p.age + " d"), bar), status].forEach(x => tr.appendChild(add(el("td"), x)));
    tr.appendChild(el("td", fmt(p.lines), "n")); tr.appendChild(el("td", fmt(p.hits), "n"));
    body.appendChild(tr);
  });
  if (!list.length) { const td = el("td"); td.colSpan = 7; td.appendChild(empty("No match", "Try fewer words or another kind.")); body.appendChild(add(el("tr"), td)); }
  const ok = pages.filter(p => p.age !== null && p.age <= stale).length;
  $("pagesub").textContent = `${plural(list.length, "page")} shown · ${ok} of ${pages.length} verified in the last ${stale} days · oldest first`;
}
[["", pages.length]].concat(Object.entries(kinds).sort((a, b) => b[1] - a[1])).forEach(([k, n]) => {
  const b = el("button", null, "chip"); b.type = "button"; b.setAttribute("aria-pressed", String(k === ""));
  if (k) { const s = el("span", null, "sw"); s.style.background = kindColor(k); b.appendChild(s); }
  b.appendChild(document.createTextNode(`${k || "all"} ${n}`));
  b.onclick = () => { kindFilter = k; document.querySelectorAll("#kindchips button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); renderPages(); };
  $("kindchips").appendChild(b);
});
$("filter").addEventListener("input", renderPages);
renderPages();

/* knowledge map */
let mapDrawn = false;
function drawMap() {
  if (mapDrawn) return;
  mapDrawn = true;
  const g = $("graph"), W = 800, Hh = 600;
  let list = pages.slice();
  if (list.length > 260) list = list.sort((a, b) => (b.hits + b.links.length + (inbound[b.page] || 0)) - (a.hits + a.links.length + (inbound[a.page] || 0))).slice(0, 260);
  const idx = new Map(list.map((p, i) => [p.page, i]));
  const seen = new Set(), edges = [];
  list.forEach((p, i) => p.links.forEach(t => {
    const j = idx.get(t), key = Math.min(i, j) + ":" + Math.max(i, j);
    if (j !== undefined && j !== i && !seen.has(key)) { seen.add(key); edges.push([i, j]); }
  }));
  const groups = [...new Set(list.map(p => p.group))].sort();
  const anchor = {};
  groups.forEach((gr, i) => {
    const a = 2 * Math.PI * i / Math.max(groups.length, 1) - Math.PI / 2, r = groups.length > 1 ? 190 : 0;
    anchor[gr] = [W / 2 + r * Math.cos(a), Hh / 2 + r * 0.8 * Math.sin(a)];
  });
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const deg = list.map((_, i) => edges.filter(e => e[0] === i || e[1] === i).length);
  const N = list.map(p => ({p, x: anchor[p.group][0] + (rnd() - 0.5) * 80, y: anchor[p.group][1] + (rnd() - 0.5) * 80,
    r: Math.min(16, 5 + 2.2 * Math.sqrt(p.hits || 0))}));
  for (let it = 0, temp = 9; it < 300; it++, temp = Math.max(0.4, temp * 0.985)) {
    const dx = new Float64Array(N.length), dy = new Float64Array(N.length);
    for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
      let ex = N[i].x - N[j].x, ey = N[i].y - N[j].y; const d2 = Math.max(ex * ex + ey * ey, 30), f = 2000 / d2;
      dx[i] += ex * f / Math.sqrt(d2); dy[i] += ey * f / Math.sqrt(d2); dx[j] -= ex * f / Math.sqrt(d2); dy[j] -= ey * f / Math.sqrt(d2);
    }
    edges.forEach(([i, j]) => {
      const ex = N[j].x - N[i].x, ey = N[j].y - N[i].y, d = Math.sqrt(ex * ex + ey * ey) || 1, f = (d - 80) * 0.03;
      dx[i] += ex / d * f; dy[i] += ey / d * f; dx[j] -= ex / d * f; dy[j] -= ey / d * f;
    });
    N.forEach((n, i) => {
      const a = anchor[n.p.group];
      const pull = deg[i] ? 0.02 : 0.08;               // an unlinked page stays near its group
      dx[i] += (a[0] - n.x) * pull + (W / 2 - n.x) * 0.002; dy[i] += (a[1] - n.y) * pull + (Hh / 2 - n.y) * 0.002;
      const m = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1, step = Math.min(m, temp);
      n.x += dx[i] / m * step; n.y += dy[i] / m * step;
    });
  }
  if (!N.length) { g.replaceWith(empty("No pages to map yet", "Pages appear here with their [[links]].")); return; }
  const bx = N.map(n => n.x), by = N.map(n => n.y), minX = Math.min(...bx), minY = Math.min(...by);
  const bw = Math.max(...bx) - minX || 1, bh = Math.max(...by) - minY || 1, aspect = 1.15;   // fill the 4:3 frame
  if (bw / bh < aspect) N.forEach(n => { n.x = minX + (n.x - minX) * Math.min(1.9, aspect * bh / bw); });
  else N.forEach(n => { n.y = minY + (n.y - minY) * Math.min(1.9, bw / (aspect * bh)); });
  const xs = N.map(n => n.x), ys = N.map(n => n.y), pad = 40;
  const x0 = Math.min(...xs) - pad, y0 = Math.min(...ys) - pad, w = Math.max(...xs) - x0 + pad + 80, h = Math.max(...ys) - y0 + pad;
  g.setAttribute("viewBox", `${x0} ${y0} ${Math.max(w, 200)} ${Math.max(h, 150)}`);
  const lines = edges.map(([i, j]) => { const l = svg("line", {x1: N[i].x, y1: N[i].y, x2: N[j].x, y2: N[j].y, class: "edge", "stroke-width": 1.2}); g.appendChild(l); return l; });
  const labelled = new Set(N.map((n, i) => [n.p.hits * 2 + deg[i], i]).sort((a, b) => b[0] - a[0]).slice(0, 8).map(x => x[1]));
  const dots = N.map((n, i) => {
    const f = fresh(n.p), c = svg("circle", {cx: n.x, cy: n.y, r: n.r, class: "node", fill: groupColors[n.p.group],
      stroke: f === "stale" || f === "never" ? "var(--warn)" : "var(--card)", "stroke-width": f === "stale" || f === "never" ? 2.5 : 1.5});
    const tip = svg("title"); tip.textContent = `${n.p.title} · ${n.p.path}`; c.appendChild(tip);
    c.addEventListener("click", e => { e.stopPropagation(); focus(i); });
    g.appendChild(c);
    return c;
  });
  const labels = N.map((n, i) => {                       // a few labels at rest, the neighbourhood's on focus
    const t = svg("text", {x: n.x + n.r + 3, y: n.y + 3.5, class: labelled.has(i) ? "show" : ""});
    t.textContent = n.p.title.length > 28 ? n.p.title.slice(0, 27) + "…" : n.p.title;
    g.appendChild(t);
    return t;
  });
  function focus(i) {
    g.classList.add("focus");
    const near = new Set([i]);
    edges.forEach(([a, b], k) => { const on = a === i || b === i; lines[k].classList.toggle("near", on); if (on) { near.add(a); near.add(b); } });
    dots.forEach((d, k) => d.classList.toggle("near", near.has(k)));
    labels.forEach((t, k) => t.classList.toggle("near", near.has(k)));
    const p = N[i].p, panel = $("mappanel"); panel.textContent = "";
    const open = el("a", "Read the page", "go"); open.href = pageHref(p);
    add(panel, el("h3", p.title), el("div", p.path, "sub mono"), add(el("div", null, "controls"), open));
    const chips = el("div", null, "chips");
    add(chips, el("span", p.group || "top level", "chip"), el("span", p.age === null ? "never verified" : `verified ${p.age} d ago`, "chip " + (fresh(p) === "stale" || fresh(p) === "never" ? "warn" : "ok")),
      el("span", plural(p.hits, "read"), "chip"));
    panel.appendChild(chips);
    if (p.summary) panel.appendChild(el("p", p.summary, "note"));
    const out = p.links.filter(t => idx.has(t)), inn = list.filter(q => q.links.includes(p.page));
    [["Links to", out.map(t => idx.get(t))], ["Linked from", inn.map(q => idx.get(q.page))]].forEach(([label, ids]) => {
      if (!ids.length) return;
      panel.appendChild(el("div", label, "sub"));
      const box = el("div", null, "chips");
      ids.forEach(k => { const b = el("button", N[k].p.title, "chip"); b.type = "button"; b.onclick = () => focus(k); box.appendChild(b); });
      panel.appendChild(box);
    });
    if (!out.length && !inn.length) panel.appendChild(el("p", "No links in or out. Link it from a related page so lookups can follow it.", "note"));
  }
  function overview() {
    g.classList.remove("focus");
    const panel = $("mappanel"); panel.textContent = "";
    add(panel, el("h3", `${plural(N.length, "page")} · ${plural(edges.length, "link")}`),
      el("p", "Click a page to see what it links to and what links to it. Click the background to come back here.", "note"));
    if (orphans.length) {
      panel.appendChild(el("div", `Unlinked (${orphans.length})`, "sub"));
      const box = el("div", null, "chips");
      orphans.slice(0, 16).forEach(p => { const k = idx.get(p.page); if (k === undefined) return; const b = el("button", p.title, "chip"); b.type = "button"; b.onclick = () => focus(k); box.appendChild(b); });
      panel.appendChild(box);
    }
  }
  g.addEventListener("click", overview);
  overview();
}
const gcount = {};
pages.forEach(p => { gcount[p.group] = (gcount[p.group] || 0) + 1; });
Object.keys(groupColors).forEach(gr => {
  const s = el("span", null, "sw"); s.style.background = groupColors[gr];
  $("maplegend").appendChild(add(el("span", null, "chip"), s, `${gr || "top level"} ${gcount[gr]}`));
});
$("maplegend").appendChild(add(el("span", null, "chip"), (() => { const s = el("span", null, "sw"); s.style.boxShadow = "0 0 0 2px var(--warn)"; return s; })(), "stale or never verified"));

/* decisions & incidents */
const story = pages.filter(p => p.kind === "decision" || p.kind === "incident").map(p => {
  const m = /^(\d{4}-\d{2}-\d{2})/.exec(p.page);
  return Object.assign({when: m ? m[1] : p.verified || ""}, p);
}).sort((a, b) => b.when.localeCompare(a.when) || a.title.localeCompare(b.title));
let storyKind = "";
function renderStory() {
  const ul = $("timeline"); ul.textContent = "";
  story.filter(s => !storyKind || s.kind === storyKind || s.status === storyKind).forEach(s => {
    const li = el("li"); li.style.setProperty("--tl", kindColor(s.kind));
    const what = add(el("div", null, "what"), pageLinkTo(s), " ");
    if (s.status) what.appendChild(el("span", s.status, "chip " + (s.status === "rejected" || s.status === "superseded" ? "warn" : s.status === "accepted" ? "ok" : "")));
    add(li, el("div", `${s.when || "undated"} · ${s.kind}`, "when"), what);
    if (s.summary) li.appendChild(el("div", s.summary, "note"));
    ul.appendChild(li);
  });
  if (!story.length) ul.replaceWith(empty("No decisions or incidents yet", "Record them as they happen; agents find them later.",
    `${CLI} decision "<title>" --status accepted`));
}
const tl = [["", "all", story.length], ["decision", "decisions", story.filter(s => s.kind === "decision").length],
  ["incident", "incidents", story.filter(s => s.kind === "incident").length]];
[...new Set(story.map(s => s.status).filter(Boolean))].sort().forEach(s => tl.push([s, s, story.filter(x => x.status === s).length]));
tl.filter(t => t[2] || !t[0]).forEach(([k, label, n]) => {
  const b = el("button", `${label} ${n}`, "chip"); b.type = "button"; b.setAttribute("aria-pressed", String(!k));
  b.onclick = () => { storyKind = k; document.querySelectorAll("#tlchips button").forEach(x => x.setAttribute("aria-pressed", String(x === b))); renderStory(); };
  $("tlchips").appendChild(b);
});
renderStory();

/* agent usage: recall, commands */
if (D.bench) {
  const t = D.bench.total, stats = el("div", null, "grid4");
  [["recall@1", Math.round(100 * t.recall_at_1) + "%"], ["recall@3", Math.round(100 * t.recall_at_3) + "%"],
    ["MRR", t.mrr.toFixed(2)], ["tokens / answer", fmt(t.tokens_mean)]].forEach(([k, v]) => stats.appendChild(add(el("div"), el("div", v, "v"), el("div", k, "sub"))));
  stats.querySelectorAll(".v").forEach(v => { v.style.fontSize = "22px"; v.style.fontWeight = "650"; });
  $("bench").appendChild(stats);
  if (D.bench.misses.length) {
    $("bench").appendChild(el("p", "Content gaps: your questions that missed the top 3", "sub"));
    const ul = el("ul", null, "rank");
    D.bench.misses.forEach(m => ul.appendChild(add(el("li"), el("div", m.q, "t"), el("div", m.id, "sub"), el("div", m.rank ? "#" + m.rank : "miss", "n"))));
    $("bench").appendChild(ul);
  } else $("bench").appendChild(el("p", `All ${plural(t.n, "question")} found in the top 3.`, "note"));
} else {
  $("bench").appendChild(empty("No questions yet", "When a lookup misses, record the question and the page that answers it.",
    `${CLI} bench --add "<question>" --expect <page>`));
}
Object.entries(D.usage).forEach(([cmd, u]) => {
  const tr = el("tr"); tr.appendChild(add(el("td"), el("code", cmd)));
  [u.n, u.p50_tokens, u.p95_tokens].forEach(v => tr.appendChild(el("td", fmt(v), "n")));
  tr.appendChild(el("td", u.truncated_pct + "%", "n")); tr.appendChild(el("td", fmt(u.p95_ms), "n"));
  tr.appendChild(el("td", u.zero_results_pct !== undefined ? u.zero_results_pct + "%" : "–", "n"));
  $("usagetbl").appendChild(tr);
});
if (!Object.keys(D.usage).length) { const td = el("td"); td.colSpan = 7; td.appendChild(empty("No usage logged yet", "Commands log their size and speed here, never their text.")); $("usagetbl").appendChild(add(el("tr"), td)); }

/* checks, journal */
const LV = {E: ["error", "bad"], W: ["warning", "warn"], I: ["to curate", ""]};
[["E", D.check.errors], ["W", D.check.warnings], ["I", D.check.info]].forEach(([k, n]) =>
  $("checkchips").appendChild(el("span", `${n} ${LV[k][0]}${n === 1 || k === "I" ? "" : "s"}`, "chip " + (n ? LV[k][1] : ""))));
$("b-checks").textContent = errs || D.check.warnings || "";
$("b-checks").className = "badge " + (errs ? "bad" : D.check.warnings ? "warn" : "");
D.check.findings.forEach(f => {
  const tr = el("tr");
  [el("span", LV[f.level] ? LV[f.level][0] : f.level, "chip " + (LV[f.level] ? LV[f.level][1] : "")), el("code", f.where), f.message]
    .forEach(x => tr.appendChild(add(el("td"), x)));
  $("findings").appendChild(tr);
});
if (!D.check.findings.length) $("findings").closest("table").replaceWith(empty("No findings", "Pages are clean."));
D.journal.slice().reverse().forEach(j => $("journal").appendChild(el("li", j.replace(/^- /, ""))));
if (!D.journal.length) $("journal").replaceWith(empty("The journal is empty", "Agents add a line when they learn something.", `${CLI} log "<note>"`));

/* wiki reader */
const texts = D.wiki || [];
const byName = new Map(pages.map((p, i) => [p.page.toLowerCase(), i]));
const hay = pages.map((p, i) => (p.title + " " + p.path + " " + p.summary + " " + (texts[i] || "")).toLowerCase());
const linkedFrom = {};
pages.forEach(p => p.links.forEach(t => { (linkedFrom[t] = linkedFrom[t] || []).push(p); }));
const attention = new Map(items.map(c => [c.path, c]));
const DATED = new Set(["decisions", "incidents", "journal"]);
let current = -1;
const mdContext = () => ({
  skipTitle: true,
  page(name, label) {
    const i = byName.get(name.toLowerCase().replace(/\.md$/i, ""));
    if (i === undefined) { const s = el("span", label, "broken"); s.title = `no page named ${name}`; return s; }
    return pageLinkTo(pages[i], label);
  },
});
function freshDot(p) {
  const d = el("span", null, "fd"); d.style.background = FRESH[fresh(p)][0]; d.title = FRESH[fresh(p)][1];
  return d;
}
function buildTree() {
  const q = $("wikisearch").value.trim().toLowerCase(), nav = $("wikitree"), groups = {};
  nav.textContent = "";
  pages.forEach((p, i) => { if (!q || hay[i].includes(q)) (groups[p.group] = groups[p.group] || []).push(i); });
  const order = Object.keys(groups).sort((a, b) => (a === "" ? -1 : b === "" ? 1 : a.localeCompare(b)));
  order.forEach(g => {
    const ids = groups[g].sort((a, b) => DATED.has(g.toLowerCase()) ? pages[b].page.localeCompare(pages[a].page)
      : pages[a].title.localeCompare(pages[b].title));
    nav.appendChild(add(el("div", null, "grp"), el("span", g || "Top level"), el("span", String(ids.length))));
    ids.forEach(i => {
      const a = add(el("a"), freshDot(pages[i]), el("span", pages[i].title, "tt"));
      a.href = pageHref(pages[i]); a.title = pages[i].path;
      if (i === current) a.setAttribute("aria-current", "page");
      nav.appendChild(a);
    });
  });
  const n = order.reduce((acc, g) => acc + groups[g].length, 0);
  $("wikicount").textContent = q ? `${n} of ${plural(pages.length, "page")} match` : plural(pages.length, "page");
  if (!n) nav.appendChild(empty("No match", "Try another word."));
}
function chipsFor(p) {
  const f = fresh(p), row = el("div", null, "chips"), sw = el("span", null, "sw");
  sw.style.background = kindColor(p.kind);
  add(row, add(el("span", null, "chip"), sw, p.kind),
    el("span", p.age === null ? (isRecord(p) ? "not verified (record)" : "never verified") : `verified ${p.verified} · ${p.age} d ago`,
      "chip " + (f === "stale" || f === "never" ? "warn" : f === "record" ? "" : "ok")));
  if (p.status) row.appendChild(el("span", p.status, "chip " + (isRecord(p) ? "warn" : "ok")));
  row.appendChild(el("span", plural(p.hits, "read"), "chip"));
  return row;
}
function openPage(name) {
  const art = $("wikipage");
  art.textContent = "";
  let i = name ? byName.get(name.toLowerCase()) : (byName.has("index") ? byName.get("index") : 0);
  if (!pages.length) i = undefined;
  current = i === undefined ? -1 : i;
  buildTree();
  if (!pages.length) { art.appendChild(empty("No pages yet", "Write the first page in the wiki folder.")); return; }
  if (i === undefined) {
    art.appendChild(empty(`No page named “${name}”`, "It may have been renamed or removed. Search the list on the left."));
    return;
  }
  const p = pages[i], head = el("div", null, "pagehead");
  add(head, el("h1", p.title), chipsFor(p));
  if (p.summary) head.appendChild(el("p", p.summary, "lead"));
  if (p.sources && p.sources.length) head.appendChild(el("div", "Sources: " + p.sources.join(", "), "sub mono"));
  head.appendChild(cmdChip(`${CLI} page ${shq(p.page) || "<rename the file: unsafe name>"}`));
  art.appendChild(head);
  const todo = attention.get(p.path);
  if (todo) {
    const go = el("a", "Plan a refresh", "go"); go.href = "#refresh"; go.style.marginLeft = "8px";
    art.appendChild(add(el("div", null, "callout"), `Needs a refresh: ${todo.reasons.join(", ")}.`, go));
  }
  if (texts[i] === null || texts[i] === undefined) {
    art.appendChild(empty("Too large to show here", "Read it in a terminal:", `${CLI} page ${shq(p.page) || "<rename the file>"}`));
  } else {
    art.appendChild(MD.render(texts[i], el("div", null, "md"), mdContext()));
  }
  const rel = el("div", null, "related");
  [["Links to", p.links.map(t => pages[byName.get(t.toLowerCase())]).filter(Boolean)], ["Linked from", linkedFrom[p.page] || []]]
    .forEach(([label, list]) => {
      if (!list.length) return;
      rel.appendChild(el("div", label, "sub"));
      const box = el("div", null, "chips");
      list.forEach(q => { const a = pageLinkTo(q); a.className = "chip"; box.appendChild(a); });
      rel.appendChild(box);
    });
  if (rel.childNodes.length) art.appendChild(rel);
  else art.appendChild(el("p", "No other page links here yet. Link it from a related page so lookups can follow it.", "note"));
}
$("wikisearch").addEventListener("input", buildTree);
$("wikisearch").addEventListener("keydown", e => {
  const first = $("wikitree").querySelector("a");
  if (e.key === "Enter" && first) { location.hash = first.getAttribute("href").slice(1); }
});

show(location.hash.slice(1));
})();
