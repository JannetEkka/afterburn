// Afterburn site: the scar map, the demo pact read live from Monad testnet, and per-field evidence.
const RPC = "https://testnet-rpc.monad.xyz";
const EXPLORER = "https://testnet.monadvision.com";
const STATUS = ["none", "enrolled", "in challenge window", "disputed", "clean", "burnt"];
const ABI = [
  "function plots(uint256) view returns (address farmer, bytes32 village, uint32 ares, uint8 status, uint16 burntBps, uint64 deadline, bool bonusDone, bytes32 polygonHash, bytes32 evidenceHash)",
  "function villages(bytes32) view returns (uint32 plots, uint32 settled, uint32 clean, bool bonusUnlocked)",
  "function available() view returns (uint256)",
  "function reserved() view returns (uint256)",
  "function plotCount() view returns (uint256)",
  "function burntThresholdBps() view returns (uint16)",
];

const $ = (s) => document.querySelector(s);
const fmt = (n) => n.toLocaleString("en-IN");
const short = (h) => (h ? h.slice(0, 10) + "…" + h.slice(-6) : "");
const getJSON = (u) => fetch(u, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);

const state = { chain: {}, villages: {} };

async function main() {
  const [plots, layers, notices, val, dep, snap, chips] = await Promise.all([
    getJSON("data/plots.json"), getJSON("data/layers.json"), getJSON("data/notices.json"), getJSON("data/validation.json"), getJSON("data/deployment.json"), getJSON("data/chain.json"), getJSON("data/chips.json"),
  ]);
  Object.assign(state, { plots, layers, notices, val, dep, chips });
  if (snap && dep && snap.pact === dep.pact) {
    // render from the last snapshot straight away, then refresh from the chain
    state.chain = Object.fromEntries(Object.entries(snap.plots).map(([k, v]) => [Number(k), v]));
    state.villages = snap.villages;
    state.pool = { available: BigInt(snap.available), reserved: BigInt(snap.reserved) };
    state.snapshot = snap;
  }
  stats();
  drawMap();
  pactSection();
  if (dep && dep.pact) {
    await readChain();
    pactSection();
  }
}

function stats() {
  const { layers, val } = state;
  if (layers) $("#st-season").textContent = fmt(layers.season_burnt_ha) + " ha";
  if (val) {
    $("#st-flames").textContent = val.s2_fires_at_after_pass;
    $("#st-flames-viirs").textContent = Math.round(val.s2_fires_with_viirs_same_day_within_1km * 100) + "%";
    $("#v-in").textContent = (val.burnt_share_in_viirs_footprints * 100).toFixed(1) + "%";
    $("#v-rand").textContent = (val.burnt_share_random_harvested * 100).toFixed(1) + "%";
    $("#v-lift").textContent = val.lift + "×";
    $("#v-scars").textContent = fmt(val.scars);
    $("#v-375").textContent = (val.scars_with_viirs_within_375m * 100).toFixed(1) + "%";
  }
}

// ------------------------------------------------------------------ map
let map, plotLayers = {};
function drawMap() {
  const { layers, plots } = state;
  map = L.map("leaflet", { zoomControl: true, preferCanvas: true });
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 18, attribution: "Imagery © Esri, Maxar, Earthstar Geographics · Scars: Copernicus Sentinel-2 · Fires: NASA FIRMS",
  }).addTo(map);
  const b = layers.overlay_bounds;
  map.fitBounds(b);

  const scars = L.imageOverlay("data/scars.png", b, { opacity: 0.85, interactive: false }).addTo(map);
  const viirs = L.layerGroup(layers.viirs.map((d) => L.circleMarker([d.lat, d.lon], { radius: 2.6, color: "#141210", weight: 0.6, fillColor: "#ffd60a", fillOpacity: 0.95 })
    .bindTooltip(`VIIRS ${d.sat.replace("VIIRS ", "")}<br>${d.date} ${d.time.slice(0, 2)}:${d.time.slice(2)} UTC`))).addTo(map);
  const flames = L.layerGroup(layers.flames.map((d) => L.circleMarker([d.lat, d.lon], { radius: 3, color: "#fff", weight: 0.8, fillColor: "#ff3b30", fillOpacity: 1 })
    .bindTooltip(`In flames at the Sentinel-2 pass<br>${d.date}, 11:20 IST`))).addTo(map);
  const pact = L.layerGroup().addTo(map);
  for (const p of plots.plots) {
    const poly = L.geoJSON(p.polygon, { style: plotStyle(p) }).on("click", () => openPlot(p.plot));
    poly.bindTooltip(`Plot ${p.plot}`, { sticky: true });
    plotLayers[p.plot] = poly;
    pact.addLayer(poly);
  }
  // village labels
  const byV = groupVillages();
  for (const [v, ps] of Object.entries(byV)) {
    const bb = L.featureGroup(ps.map((p) => plotLayers[p.plot])).getBounds();
    L.marker(bb.getNorthWest(), { icon: L.divIcon({ className: "", html: `<span class="vlabel">Village ${v}</span>`, iconAnchor: [0, 18] }) }).addTo(pact);
  }

  const legend = $("#legend");
  const row = (label, sw, layer, on = true) => {
    const el = document.createElement("label");
    el.className = "legend-row";
    el.innerHTML = `<input type="checkbox" ${on ? "checked" : ""}>${sw}<span>${label}</span>`;
    el.querySelector("input").addEventListener("change", (e) => (e.target.checked ? layer.addTo(map) : map.removeLayer(layer)));
    legend.appendChild(el);
  };
  row(`Burn scars this season, ${fmt(layers.season_burnt_ha)} ha<span class="ints">${layers.intervals.map((i) => `<span><i class="sw" style="background:${i.colour}"></i>${i.from.slice(5).replace("-", "/")} → ${i.to.slice(5).replace("-", "/")}: ${fmt(i.burnt_ha)} ha</span>`).join("")}</span>`,
    `<span class="sw" style="background:linear-gradient(90deg,${layers.intervals.map((i) => i.colour).join(",")})"></span>`, scars);
  row(`VIIRS fire detections (official count), ${fmt(layers.viirs.length)}`, `<span class="sw dot" style="background:#ffd60a"></span>`, viirs);
  row(`Fields in flames at the Sentinel-2 pass, ${fmt(layers.flames.length)}`, `<span class="sw dot" style="background:#ff3b30"></span>`, flames);
  row("Demo pact fields", `<span class="sw" style="border:2px solid #3dd6c3"></span>`, pact);

  const vb = $("#vbuttons");
  for (const [v, ps] of Object.entries(byV)) {
    const burnt = ps.filter(isBurnt).length;
    const btn = document.createElement("button");
    btn.className = "vbtn";
    btn.innerHTML = `${ps[0].village_name}<small>${ps.length} fields · ${burnt ? burnt + " burnt" : "all clean"}</small>`;
    btn.onclick = () => map.flyToBounds(L.featureGroup(ps.map((p) => plotLayers[p.plot])).getBounds().pad(0.4), { duration: 1.2 });
    vb.appendChild(btn);
  }
}

function groupVillages() {
  const out = {};
  for (const p of state.plots.plots) (out[p.village] ||= []).push(p);
  return out;
}

function isBurnt(p) {
  const c = state.chain[p.plot];
  if (c && c.status >= 4) return c.status === 5;
  return p.burnt_bps >= 2000;
}

function verdictClass(p) {
  const c = state.chain[p.plot];
  if (c && c.status < 4 && c.status > 0) return c.status === 1 ? "pending" : isBurnt(p) ? "burnt" : "clean";
  return isBurnt(p) ? "burnt" : "clean";
}

function plotStyle(p) {
  const col = { clean: "#3dd6c3", burnt: "#ff5a36", pending: "#a89f95" }[verdictClass(p)];
  return { color: col, weight: 2.5, fillColor: col, fillOpacity: 0.18 };
}

// ------------------------------------------------------------------ chain
async function readChain() {
  try {
    // the public RPC drops bursts, so read a few at a time and retry
    const provider = new ethers.JsonRpcProvider(RPC, 10143, { staticNetwork: true, batchMaxCount: 1 });
    const c = new ethers.Contract(state.dep.pact, ABI, provider);
    const retry = async (fn, n = 4) => { for (let i = 0; ; i++) { try { return await fn(); } catch (e) { if (i >= n) throw e; await new Promise((r) => setTimeout(r, 400 * (i + 1))); } } };
    const avail = await retry(() => c.available());
    const res = await retry(() => c.reserved());
    state.pool = { available: avail, reserved: res };
    const ps = state.plots.plots;
    for (let i = 0; i < ps.length; i += 4) {
      await Promise.all(ps.slice(i, i + 4).map(async (p) => {
        const r = await retry(() => c.plots(p.plot));
        state.chain[p.plot] = { farmer: r.farmer, status: Number(r.status), burntBps: Number(r.burntBps), deadline: Number(r.deadline), bonusDone: r.bonusDone, evidenceHash: r.evidenceHash, polygonHash: r.polygonHash };
      }));
    }
    for (const [v, vps] of Object.entries(groupVillages())) {
      const r = await retry(() => c.villages(vps[0].village_id));
      state.villages[v] = { plots: Number(r.plots), settled: Number(r.settled), clean: Number(r.clean), bonusUnlocked: r.bonusUnlocked };
    }
    for (const p of state.plots.plots) plotLayers[p.plot].setStyle(plotStyle(p));
    state.live = true;
    state.snapshot = null;
  } catch (e) {
    console.warn("chain read failed", e);
    state.live = false;
  }
}

// ------------------------------------------------------------------ plot panel
function openPlot(n) {
  const p = state.plots.plots.find((q) => q.plot === n);
  const c = state.chain[n];
  const cls = verdictClass(p);
  const label = c && c.status ? STATUS[c.status] : isBurnt(p) ? "burnt" : "clean";
  const win = p.burnt_between || [];
  // one image pixel per 10 m Sentinel-2 pixel, scaled up as crisp squares; the outline is a vector on top
  const cm = state.chips && state.chips[n];
  const outline = cm ? `<svg viewBox="0 0 ${cm.w} ${cm.h}" preserveAspectRatio="none" aria-hidden="true"><polygon points="${cm.ring.map((q) => q.join(",")).join(" ")}"/></svg>` : "";
  const chips = state.plots.season.map((d) => `<figure class="chip ${win.includes(d) ? "burnwin" : ""}"><div class="chipbox" style="aspect-ratio:${cm ? cm.w + "/" + cm.h : "1"}"><img src="chips/plot-${n}-${d}.png" alt="Plot ${n} on ${d}" loading="lazy">${outline}</div><figcaption>${d}${d === win[1] ? " · scar" : ""}</figcaption></figure>`).join("");
  const dep = state.dep;
  const tx = (k) => (dep && dep.txs && dep.txs[k] ? `<a href="${EXPLORER}/tx/${dep.txs[k]}" target="_blank" rel="noopener">${short(dep.txs[k])}</a>` : "—");
  const match = c && c.evidenceHash && c.evidenceHash.toLowerCase() === p.evidence_hash.toLowerCase();
  const note = state.notices && state.notices[n];
  const amount = (bps) => (dep ? `${ethers.formatEther((BigInt(dep.terms.ratePerHa) * BigInt(p.ares) / 100n) * BigInt(bps) / 10000n)} MON` : "");
  $("#plot").innerHTML = `
    <button class="back" onclick="closePlot()">← all fields</button>
    <h2>Plot ${n}</h2>
    <div class="meta">${p.village_name} · ${(p.ares / 100).toFixed(2)} ha · ${p.cells.length} land cells</div>
    <span class="badge ${cls}">${label}</span>
    <div class="verdict"><b>${(p.burnt_bps / 100).toFixed(0)}%</b><span>of the field scarred${win.length ? `, between ${win[0]} and ${win[1]}` : " this season"}</span></div>
    <div class="chips">${chips}</div>
    <p class="chipnote">Sentinel-2 true colour, the same 10 m pixels the verdict is computed from.</p>
    <dl class="kv">
      <dt>Rule</dt><dd>burn scar v${state.plots.rule.version} (<span class="mono">${state.plots.rule_id}</span>)</dd>
      <dt>Evidence</dt><dd><a href="${p.evidence_uri}" target="_blank">${p.evidence_uri}</a></dd>
      <dt>Evidence hash</dt><dd class="mono">${short(p.evidence_hash)}${c ? (match ? ' <span style="color:var(--clean)">✓ matches chain</span>' : ' <span style="color:var(--burnt)">≠ chain</span>') : ""}</dd>
      <dt>Polygon hash</dt><dd class="mono">${short(p.polygon_hash)}</dd>
      ${c ? `<dt>On-chain</dt><dd>${STATUS[c.status]}${c.status === 2 ? `, window closes ${new Date(c.deadline * 1000).toLocaleString()}` : ""}</dd>` : `<dt>On-chain</dt><dd>${dep ? "reading…" : "not deployed yet"}</dd>`}
      ${dep ? `<dt>Paid at sign-up</dt><dd>${amount(dep.terms.upfrontBps)} · ${tx("enrol:" + n)}</dd>
      <dt>Verdict tx</dt><dd>${tx("verdict:" + n)}</dd>
      <dt>Settled</dt><dd>${c && c.status === 4 ? amount(10000 - dep.terms.upfrontBps) + " paid · " : c && c.status === 5 ? "nothing more paid · " : ""}${tx("finalize:" + n) !== "—" ? tx("finalize:" + n) : tx("resolve:" + n)}</dd>` : ""}
    </dl>
    ${note ? `<div class="notice"><div class="tabs"><button class="on" data-l="pa">ਪੰਜਾਬੀ</button><button data-l="en">English</button></div><p id="note-text" lang="pa">${note.pa}</p><small>The farmer's message, written by Gemini from the verdict's facts. Punjabi not yet checked by a native speaker.</small></div>` : ""}
    <div class="cmd">python pipeline/recheck.py docs/evidence/plot-${n}.json${dep ? ` --pact ${dep.pact} --plot ${n}` : ""}</div>`;
  if (note) {
    $("#plot").querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
      $("#plot").querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
      $("#note-text").textContent = note[b.dataset.l];
      $("#note-text").lang = b.dataset.l;
    }));
  }
  $("#panel-empty").hidden = true;
  $("#plot").hidden = false;
  $("#panel").scrollTop = 0;
  map.flyToBounds(plotLayers[n].getBounds().pad(2.5), { duration: 0.9, maxZoom: 16 });
}

function closePlot() {
  $("#plot").hidden = true;
  $("#panel-empty").hidden = false;
}

// ------------------------------------------------------------------ pact section
function pactSection() {
  const { dep, pool, plots } = state;
  const byV = groupVillages();
  if (dep && dep.pact) $("#pact-addr").textContent = dep.pact;
  const settled = Object.values(state.chain).filter((c) => c.status >= 4).length;
  const clean = Object.values(state.chain).filter((c) => c.status === 4).length;
  $("#chain").innerHTML = dep && dep.pact
    ? `<div class="stat"><b><a href="${EXPLORER}/address/${dep.pact}" target="_blank" rel="noopener">${short(dep.pact)}</a></b><span>AfterburnPact on Monad testnet (chain 10143)${state.live ? " · read live" : state.snapshot ? ` · snapshot at block ${fmt(state.snapshot.block)}` : ". Couldn't reach the RPC just now; showing the computed verdicts"}</span></div>
       <div class="stat"><b>${plots.plots.length}</b><span>fields enrolled in 3 villages</span></div>
       <div class="stat"><b>${settled ? `${clean} clean · ${settled - clean} burnt` : "in window"}</b><span>${settled} of ${plots.plots.length} settled</span></div>
       <div class="stat"><b>${pool ? Number(ethers.formatEther(pool.available)).toFixed(4) : "—"} MON</b><span>in the pool and owed to no one${pool ? `; ${Number(ethers.formatEther(pool.reserved)).toFixed(4)} MON still reserved for farmers` : ""}</span></div>`
    : `<div class="stat"><b>Not deployed yet</b><span>The verdicts below are computed; they go on-chain once the testnet deployer is funded.</span></div>`;

  $("#villages").innerHTML = Object.entries(byV).map(([v, ps]) => {
    const vs = state.villages[v];
    const burnt = ps.filter(isBurnt).length;
    const bonus = vs && vs.settled === vs.plots ? (vs.bonusUnlocked ? `<span class="bonus on">Bonus paid to all ${vs.clean} fields</span>` : `<span class="bonus off">No bonus: ${vs.plots - vs.clean} field${vs.plots - vs.clean > 1 ? "s" : ""} burned</span>`)
      : `<span class="bonus ${burnt ? "off" : "on"}">${burnt ? `Bonus will be lost: ${burnt} burnt` : "On track for the bonus"}</span>`;
    return `<div class="village"><h3>${ps[0].village_name}</h3>
      <div class="row">${ps.map((p) => `<div class="cell ${verdictClass(p)}" title="Plot ${p.plot}: ${(p.burnt_bps / 100).toFixed(0)}% scarred" onclick="document.getElementById('map').scrollIntoView({behavior:'smooth'});openPlot(${p.plot})">${p.plot}</div>`).join("")}</div>
      ${bonus}</div>`;
  }).join("");

  const t = dep && dep.txs ? dep.txs : {};
  const count = (pre) => Object.keys(t).filter((k) => k.startsWith(pre)).length;
  const first = (pre) => Object.entries(t).find(([k]) => k.startsWith(pre));
  const item = (title, body, pre) => {
    const f = first(pre);
    return `<li><b>${title}</b><span>${body}${f ? ` · <a href="${EXPLORER}/tx/${f[1]}" target="_blank" rel="noopener">tx</a>` : ""}</span></li>`;
  };
  const ch = dep && dep.challenged;
  $("#timeline").innerHTML = dep && dep.pact ? [
    `<li><b>Deployed and funded</b><span>roles fixed at deploy: funder, cooperative, verifier, arbiter · <a href="${EXPLORER}/tx/${dep.deployTx}" target="_blank" rel="noopener">tx</a></span></li>`,
    item(`${count("enrol:")} fields enrolled`, "25% paid to each farmer at sign-up; 50 m land cells claimed", "enrol:"),
    item("Enrolment closed", "village sizes fixed", "close"),
    item(`${count("verdict:")} verdicts posted`, "share scarred + evidence hash; window opens", "verdict:"),
    ch ? item(`Challenge on plot ${ch}`, "a watcher claimed it was clean and staked a bond", "challenge:") : "",
    ch ? item("Challenge rejected", "the imagery shows the scar; the bond went to the pool", "resolve:") : "",
    item(`${count("finalize:")} plots settled`, "clean fields got the other 75%", "finalize:"),
    item(`${count("bonus:")} village bonuses paid`, `${count("release:")} bonus shares returned to the pool`, "bonus:"),
  ].join("") : "<li><b>Waiting for deployment</b><span>see the repo for the script</span></li>";
}

main();
