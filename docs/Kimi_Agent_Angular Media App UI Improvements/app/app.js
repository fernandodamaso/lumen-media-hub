/* ============================================================
   Media Manager — dashboard mockup behavior
   ============================================================ */
"use strict";

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

/* ------------------------------------------------------------
   Toasts
------------------------------------------------------------ */
const toastIcons = {
  success: '<svg class="icon" viewBox="0 0 24 24"><path d="m4.5 12.5 5 5 10-11"/></svg>',
  info: '<svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M12 11v5"/></svg>',
  warning: '<svg class="icon" viewBox="0 0 24 24"><path d="M12 3 2.5 20h19L12 3zM12 10v4m0 3h.01"/></svg>',
};

function showToast(type, title, msg, timeout = 4200) {
  const host = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast toast--${type}`;
  el.innerHTML = `
    <span class="toast__icon">${toastIcons[type] || toastIcons.info}</span>
    <div><p class="toast__title"></p><p class="toast__msg"></p></div>`;
  el.querySelector(".toast__title").textContent = title;
  el.querySelector(".toast__msg").textContent = msg;
  host.appendChild(el);
  setTimeout(() => {
    el.classList.add("is-leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, timeout);
}

/* ------------------------------------------------------------
   Downloads — count-up, live ticker, pause / resume
------------------------------------------------------------ */
const dlState = {
  paused: false,
  down: 5.7,
  up: 0.5,
  items: [
    { key: "afterlight", pct: 68, done: 4.7, total: 6.9, rate: 4.0, etaMin: 9 },
    { key: "bluehour", pct: 31, done: 0.6, total: 2.0, rate: 1.7, etaMin: 13 },
  ],
};

function countUp(el, target, decimals = 1, duration = 1100) {
  const start = performance.now();
  function frame(now) {
    const t = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = (target * eased).toFixed(decimals);
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function renderSpeeds() {
  $("#statDown").textContent = dlState.down.toFixed(1);
  $("#statUp").textContent = dlState.up.toFixed(1);
}

function renderItems() {
  dlState.items.forEach((it) => {
    const row = $(`.dl-item[data-item="${it.key}"]`);
    if (!row) return;
    row.querySelector("[data-pct-label]").textContent = `${Math.floor(it.pct)}%`;
    row.querySelector("[data-bar]").style.setProperty("--p", `${it.pct}%`);
    row.querySelector("[data-done]").textContent = it.done.toFixed(1);
    row.querySelector("[data-rate-down]").textContent = dlState.paused ? "0.0" : it.rate.toFixed(1);
    row.querySelector("[data-eta]").textContent = `${it.etaMin}m`;
  });
}

function setPaused(paused) {
  dlState.paused = paused;
  $("#pauseAllBtn").disabled = paused;
  $("#resumeAllBtn").disabled = !paused;
  $("#queueSummary").textContent = paused ? "queue paused" : "2 downloads active";

  $$(".dl-item[data-item]").forEach((row) => {
    row.classList.toggle("is-paused", paused);
    const pill = row.querySelector("[data-state-pill]");
    pill.textContent = paused ? "Paused" : "Downloading";
    pill.classList.toggle("pill--accent", !paused);
    pill.classList.toggle("pill--amber", paused);
    row.querySelector("[data-bar]").classList.toggle("is-live", !paused);
  });

  if (paused) {
    dlState.down = 0; dlState.up = 0;
    renderSpeeds(); renderItems();
    showToast("info", "Queue paused", "All downloads and uploads are on hold.");
  } else {
    dlState.down = 5.4; dlState.up = 0.5;
    renderSpeeds(); renderItems();
    showToast("success", "Queue resumed", "Downloads are back to full speed.");
  }
}

$("#pauseAllBtn").addEventListener("click", () => setPaused(true));
$("#resumeAllBtn").addEventListener("click", () => setPaused(false));

// Live jitter — simulates a WebSocket feed
setInterval(() => {
  if (dlState.paused) return;
  dlState.down = Math.max(3.2, Math.min(7.8, dlState.down + (Math.random() - 0.5) * 1.4));
  dlState.up = Math.max(0.2, Math.min(0.9, dlState.up + (Math.random() - 0.5) * 0.2));
  dlState.items.forEach((it) => {
    if (it.pct >= 100) return;
    it.pct = Math.min(99, it.pct + Math.random() * 0.6);
    it.done = (it.total * it.pct) / 100;
    it.rate = Math.max(0.8, it.rate + (Math.random() - 0.5) * 0.5);
    it.etaMin = Math.max(1, Math.round(((it.total - it.done) / it.rate) * 60 / 60 * 10));
  });
  renderSpeeds();
  renderItems();
}, 2200);

/* ------------------------------------------------------------
   Library tabs
------------------------------------------------------------ */
$$(".segmented__btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".segmented__btn").forEach((b) => {
      b.classList.toggle("is-active", b === btn);
      b.setAttribute("aria-selected", b === btn);
    });
    const tab = btn.dataset.tab;
    const movies = $("#postersMovies");
    const series = $("#postersSeries");
    movies.classList.toggle("is-hidden", tab !== "movies");
    series.classList.toggle("is-hidden", tab !== "series");
    // retrigger pane animation
    [movies, series].forEach((p) => {
      p.style.animation = "none";
      void p.offsetWidth;
      p.style.animation = "";
    });
    $("#libraryCount").textContent = tab === "movies" ? "4 movies · 2 watched" : "4 series · 1 monitored";
  });
});

/* ------------------------------------------------------------
   Poster quick actions
------------------------------------------------------------ */
const posterActionHandlers = {
  play: (title) => showToast("info", "Opening in Jellyfin", `${title} will start playing on your TV.`),
  refresh: (title) => showToast("success", "Metadata refreshed", `${title} · artwork and info updated.`),
  search: (title) => showToast("info", "Searching indexers", `Looking for releases of ${title}…`),
};
$$(".poster__action").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    posterActionHandlers[btn.dataset.action]?.(btn.dataset.title);
  });
});

/* ------------------------------------------------------------
   Command palette
------------------------------------------------------------ */
const palette = $("#palette");
const paletteInput = $("#paletteInput");
const paletteResults = $("#paletteResults");
let paletteIndex = 0;
let paletteFlat = [];

const paletteData = [
  { group: "Media", items: [
    { title: "Dune", meta: "2021 · Movie · 4K", kind: "Movie", thumb: "assets/posters/dune.jpg", run: () => showToast("info", "Opening Dune", "Movie detail page would open here.") },
    { title: "Afterlight", meta: "2026 · Movie · Downloading 68%", kind: "Movie", thumb: "assets/posters/afterlight.jpg", run: () => showToast("info", "Opening Afterlight", "Movie detail page would open here.") },
    { title: "Orbit Station", meta: "2024 · Movie · 61% watched", kind: "Movie", thumb: "assets/posters/orbit-station.jpg", run: () => showToast("info", "Opening Orbit Station", "Movie detail page would open here.") },
    { title: "Night Transit", meta: "2026 · Movie · Missing", kind: "Movie", thumb: "assets/posters/night-transit.jpg", run: () => showToast("info", "Opening Night Transit", "Movie detail page would open here.") },
    { title: "Cowboy Bebop", meta: "Series · S1 E5 today", kind: "Series", thumb: "assets/posters/cowboy-bebop.jpg", run: () => showToast("info", "Opening Cowboy Bebop", "Series detail page would open here.") },
    { title: "The Blue Hour", meta: "Series · S2 E3 today", kind: "Series", thumb: "assets/posters/blue-hour.jpg", run: () => showToast("info", "Opening The Blue Hour", "Series detail page would open here.") },
    { title: "The Expanse", meta: "Series · S4 E2 Saturday", kind: "Series", thumb: "assets/posters/expanse.jpg", run: () => showToast("info", "Opening The Expanse", "Series detail page would open here.") },
    { title: "Dark Signal", meta: "Series · Monitoring", kind: "Series", thumb: "assets/posters/dark-signal.jpg", run: () => showToast("info", "Opening Dark Signal", "Series detail page would open here.") },
  ]},
  { group: "Actions", items: [
    { title: "Pause all downloads", meta: "Queue · 2 active", kind: "Action", glyph: '<svg class="icon" viewBox="0 0 24 24"><path d="M9 5v14M15 5v14"/></svg>', run: () => setPaused(true) },
    { title: "Resume all downloads", meta: "Queue", kind: "Action", glyph: '<svg class="icon" viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg>', run: () => setPaused(false) },
    { title: "Refresh all metadata", meta: "Library · 8 items", kind: "Action", glyph: '<svg class="icon" viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/></svg>', run: () => showToast("success", "Metadata refresh queued", "8 items will be refreshed in the background.") },
    { title: "Open Jellyfin", meta: "Media server", kind: "Action", glyph: '<svg class="icon" viewBox="0 0 24 24"><path d="M7 4.5v15l13-7.5z"/></svg>', run: () => showToast("info", "Opening Jellyfin", "Launching your media server…") },
  ]},
  { group: "Services", items: [
    { title: "Sonarr", meta: "Healthy · Series management", kind: "Service", glyph: '<span class="dot dot--green"></span>', run: () => showToast("info", "Opening Sonarr", "Service page would open here.") },
    { title: "Radarr", meta: "Healthy · Movie management", kind: "Service", glyph: '<span class="dot dot--green"></span>', run: () => showToast("info", "Opening Radarr", "Service page would open here.") },
    { title: "Prowlarr", meta: "Degraded · Indexer manager", kind: "Service", glyph: '<span class="dot dot--amber"></span>', run: () => showToast("warning", "Prowlarr degraded", "2 of 6 indexers are failing health checks.") },
    { title: "SABnzbd", meta: "Down · Usenet client", kind: "Service", glyph: '<span class="dot dot--red"></span>', run: () => showToast("warning", "SABnzbd unreachable", "Connection refused · retrying in 5 minutes.") },
  ]},
];

function fuzzyScore(query, text) {
  query = query.toLowerCase();
  text = text.toLowerCase();
  let qi = 0, score = 0, streak = 0;
  for (let ti = 0; ti < text.length && qi < query.length; ti++) {
    if (text[ti] === query[qi]) {
      qi++; streak++;
      score += 1 + streak * 2;
      if (ti === 0 || text[ti - 1] === " ") score += 6;
    } else streak = 0;
  }
  return qi === query.length ? score : -1;
}

function renderPalette(query = "") {
  paletteResults.innerHTML = "";
  paletteFlat = [];
  paletteIndex = 0;

  paletteData.forEach(({ group, items }) => {
    const matched = items
      .map((it) => ({ it, s: query ? fuzzyScore(query, `${it.title} ${it.meta}`) : 0 }))
      .filter(({ s }) => s >= 0)
      .sort((a, b) => b.s - a.s)
      .map(({ it }) => it);
    if (!matched.length) return;

    const label = document.createElement("p");
    label.className = "palette__group";
    label.textContent = group;
    paletteResults.appendChild(label);

    matched.forEach((it) => {
      const btn = document.createElement("button");
      btn.className = "palette__item";
      btn.innerHTML = `
        ${it.thumb ? `<img class="palette__thumb" src="${it.thumb}" alt="" />` : `<span class="palette__glyph">${it.glyph}</span>`}
        <span><p class="palette__item-title"></p><p class="palette__item-meta"></p></span>
        <span class="palette__item-kind">${it.kind}</span>`;
      btn.querySelector(".palette__item-title").textContent = it.title;
      btn.querySelector(".palette__item-meta").textContent = it.meta;
      btn.addEventListener("click", () => { closePalette(); it.run(); });
      paletteResults.appendChild(btn);
      paletteFlat.push({ el: btn, run: it.run });
    });
  });

  if (!paletteFlat.length) {
    paletteResults.innerHTML = `<p class="palette__empty">No results for “${query}”</p>`;
    return;
  }
  markActive();
}

function markActive() {
  paletteFlat.forEach(({ el }, i) => el.classList.toggle("is-active", i === paletteIndex));
  paletteFlat[paletteIndex]?.el.scrollIntoView({ block: "nearest" });
}

function openPalette() {
  palette.hidden = false;
  paletteInput.value = "";
  renderPalette();
  requestAnimationFrame(() => paletteInput.focus());
}
function closePalette() { palette.hidden = true; }

paletteInput.addEventListener("input", () => renderPalette(paletteInput.value.trim()));
paletteInput.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") { e.preventDefault(); paletteIndex = Math.min(paletteIndex + 1, paletteFlat.length - 1); markActive(); }
  if (e.key === "ArrowUp") { e.preventDefault(); paletteIndex = Math.max(paletteIndex - 1, 0); markActive(); }
  if (e.key === "Enter") { e.preventDefault(); const item = paletteFlat[paletteIndex]; if (item) { closePalette(); item.run(); } }
});
palette.addEventListener("click", (e) => { if (e.target.hasAttribute("data-close-palette")) closePalette(); });

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    palette.hidden ? openPalette() : closePalette();
  }
  if (e.key === "Escape" && !palette.hidden) closePalette();
});

$("#searchTrigger").addEventListener("click", openPalette);
$("#addMediaBtn").addEventListener("click", openPalette);

/* ------------------------------------------------------------
   Theme switcher
------------------------------------------------------------ */
const themeButtons = $$("[data-theme-value]");
function applyTheme(name) {
  document.documentElement.dataset.theme = name;
  themeButtons.forEach((b) => b.classList.toggle("is-active", b.dataset.themeValue === name));
  try { localStorage.setItem("mm-theme", name); } catch {}
}
themeButtons.forEach((b) => b.addEventListener("click", () => {
  applyTheme(b.dataset.themeValue);
  showToast("info", "Theme changed", `Now showing the ${b.textContent.trim()} theme.`, 2600);
}));
try {
  const saved = localStorage.getItem("mm-theme");
  if (saved) applyTheme(saved);
} catch {}

/* ------------------------------------------------------------
   Misc triggers
------------------------------------------------------------ */
$("#bellBtn").addEventListener("click", () =>
  showToast("info", "3 notifications", "Episode grabbed · Watchdog failed · SABnzbd down."));
$("#statusPill").addEventListener("click", () =>
  showToast("warning", "2 services need attention", "SABnzbd is down · Prowlarr is degraded."));

/* ------------------------------------------------------------
   Boot — skeletons, count-ups, demo toasts
------------------------------------------------------------ */
window.addEventListener("DOMContentLoaded", () => {
  setTimeout(() => {
    document.body.classList.remove("is-loading");
    countUp($("#statDown"), dlState.down);
    countUp($("#statUp"), dlState.up);
    $$(".dl-item[data-item] .bar__fill").forEach((bar) => bar.classList.add("is-live"));
    renderItems();

    setTimeout(() => showToast("success", "Episode grabbed", "The Blue Hour S2E3 · 1080p · 1.4 GB"), 2600);
    setTimeout(() => showToast("warning", "SABnzbd connection lost", "Usenet client unreachable · retrying in 5m"), 6800);
  }, 1150);
});
