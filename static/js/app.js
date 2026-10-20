/* IACity — interface web. Aucun innerHTML avec des données : tout passe par des nœuds texte (anti-injection). */
'use strict';

// ---------------------------------------------------------------- utilitaires
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
let toastTimer = null;
function toast(msg, bad) {
  const t = $('#toast');
  t.textContent = msg; t.style.display = 'block'; t.style.borderColor = bad ? 'var(--bad)' : 'var(--accent)';
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.style.display = 'none', 4500);
}
async function api(path, opts = {}) {
  const o = { method: opts.method || 'GET', headers: { 'X-IACity': '1' } };
  if (opts.body !== undefined) { o.body = JSON.stringify(opts.body); o.headers['Content-Type'] = 'application/json'; }
  if (opts.form) { o.body = opts.form; }
  const r = await fetch('/api' + path, o);
  let data = null;
  try { data = await r.json(); } catch (e) { /* non JSON */ }
  if (!r.ok) {
    const msg = (data && data.error) || ('Erreur ' + r.status);
    if (!opts.quiet) toast(msg, true);
    const e = new Error(msg); e.data = data; throw e;
  }
  return data;
}
const pct = v => Math.round(Math.max(0, Math.min(1, v)) * 100);
function bar(v, cls = '', max = 1) { return h('div', { class: 'bar ' + cls }, h('b', { style: { width: Math.round(Math.max(0, Math.min(1, v / max)) * 100) + '%' } })); }
const EMO_FR = { joy: 'joie', sadness: 'tristesse', anger: 'colère', fear: 'peur', frustration: 'frustration', curiosity: 'curiosité', trust: 'confiance', jealousy: 'jalousie' };
const NEED_FR = { social: 'social', fun: 'loisirs', comfort: 'confort', security: 'sécurité', curiosity: 'curiosité' };
const TRAIT_FR = { openness: 'ouverture', conscientiousness: 'rigueur', extraversion: 'extraversion', agreeableness: 'agréabilité', neuroticism: 'nervosité', honesty: 'honnêteté' };
const MOOD_COL = { joy: '#ffd84a', sadness: '#6ab0ff', anger: '#ff5b5b', fear: '#b07aff', frustration: '#ff9a3c', curiosity: '#4ae0e0', trust: '#6bd68a', jealousy: '#b6e04a' };
const TYPE_COL = { mairie: '#c9954a', police: '#4a74c9', hopital: '#e8e8f0', ecole: '#e0c94a', epicerie: '#58b866', atelier: '#d98a3a', restaurant: '#d65a5a',
  bar: '#9a5ad6', bureau: '#7e8aa6', habitation: '#c8a37a', boutique: '#3ab8b0', loisirs: '#e070b0', plaza: '#c9b99a', parc: '#4a8c46', rue: '#4a4e58', terrain: '#9c8a62' };
const TYPE_FR = { mairie: 'Mairie', police: 'Police', hopital: 'Hôpital', ecole: 'École', epicerie: 'Épicerie', atelier: 'Atelier', restaurant: 'Restaurant', bar: 'Bar',
  bureau: 'Bureaux', habitation: 'Habitation', boutique: 'Boutique', loisirs: 'Loisirs', plaza: 'Place', parc: 'Parc', rue: 'Rue', terrain: 'Terrain à bâtir' };

// ---------------------------------------------------------------- état
const S = {
  state: null, map: null, mapVersion: -1, selected: null, tab: 'agent', sub: 'overview', hover: null,
  prevPos: {}, arrived: {}, effects: [], bubbleSeen: {}, placeSig: '', staticCanvas: null, subState: {},
  focusPlace: null, lastPanelKey: '',
};

// ---------------------------------------------------------------- sondage de l'état
async function poll() {
  try {
    const st = await api('/state', { quiet: true });
    if (S.mapVersion !== st.map_version || !S.map) {
      const m = await api('/map', { quiet: true });
      S.map = m.rows; S.mapVersion = m.version; S.staticCanvas = null;
    }
    const now = performance.now();
    for (const a of st.agents) {
      const p = S.prevPos[a.id];
      if (p && (p.x !== a.x || p.y !== a.y)) {
        S.effects.push({ x: p.x, y: p.y, t: now, kind: 'out' }, { x: a.x, y: a.y, t: now, kind: 'in' });
        S.arrived[a.id] = now;
      }
      S.prevPos[a.id] = { x: a.x, y: a.y };
      if (a.say && !(a.say.seq in S.bubbleSeen)) S.bubbleSeen[a.say.seq] = now;
    }
    const sig = JSON.stringify(st.places.map(p => [p.id, p.name, p.type, p.owner_name]));
    if (sig !== S.placeSig) { S.placeSig = sig; S.staticCanvas = null; }
    const prevSession = S.state && S.state.session_id;
    S.state = st;
    if (prevSession && prevSession !== st.session_id) { S.selected = null; S.prevPos = {}; S.subState = {}; }
    if (!S.selected && st.agents.length) S.selected = (st.agents.find(a => !a.human) || st.agents[0]).id;
    if (S.selected && !st.agents.find(a => a.id === S.selected)) S.selected = st.agents.length ? st.agents[0].id : null;
    updateHeader();
  } catch (e) { $('#llm-badge').textContent = 'serveur injoignable'; $('#llm-badge').className = 'pill bad'; }
}

function updateHeader() {
  const st = S.state;
  $('#clock').textContent = st.time + (st.effects.length ? '' : '');
  $('#btn-play').textContent = st.paused ? '▶ Reprendre' : '⏸ Pause';
  $('#btn-step').disabled = !st.paused;
  if (document.activeElement !== $('#speed')) $('#speed').value = String(st.speed);
  const l = st.llm;
  const b = $('#llm-badge');
  b.textContent = 'IA : ' + (l.mode === 'ollama' ? l.model : 'démo') + (st.llm_pending ? ` (${st.llm_pending} en réflexion)` : '');
  b.className = 'pill ' + (l.mode === 'ollama' && l.available ? 'ok' : l.mode === 'ollama' ? 'bad' : '');
  b.title = l.last_error || (l.mode === 'demo' ? 'Mode démonstration : aucun modèle local utilisé' : 'Modèle local actif');
  const eff = $('#effects'); eff.textContent = '';
  const LBL = { fete: '🎉 fête', panne: '⚡ panne', penurie: '📉 pénurie' };
  st.effects.forEach(e => eff.append(h('span', null, LBL[e.key] || e.key)));
  eff.append(h('span', { class: 'muted' }, `trésor ville : ${st.treasury} · posts : ${st.posts} · conv. ouvertes : ${st.open_conversations}`));
  const chips = $('#agent-chips');
  const key = st.agents.map(a => a.id + a.name + (a.id === S.selected)).join('|');
  if (chips.dataset.key !== key) {
    chips.dataset.key = key; chips.textContent = '';
    st.agents.forEach(a => chips.append(h('span', { class: 'chip' + (a.id === S.selected ? ' sel' : ''), onclick: () => selectAgent(a.id) },
      h('i', { style: { background: `hsl(${a.hue},65%,55%)` } }), (a.human ? '★ ' : '') + a.name)));
  }
}

function selectAgent(id) {
  S.selected = id; S.subState = {};
  if (S.tab !== 'agent') setTab('agent'); else renderPanel(true);
  $('#agent-chips').dataset.key = '';
  updateHeader();
}

// ---------------------------------------------------------------- rendu de la ville
const T = 16;
const cv = $('#city'), ctx = cv.getContext('2d');
function hash(x, y) { let n = (x * 374761393 + y * 668265263) ^ 0x5bd1e995; n = (n ^ (n >> 13)) * 1274126177; return ((n ^ (n >> 16)) >>> 0) / 4294967295; }
function shade(hex, f) {
  const n = parseInt(hex.slice(1), 16); let r = n >> 16, g = (n >> 8) & 255, b = n & 255;
  r = Math.max(0, Math.min(255, Math.round(r * f))); g = Math.max(0, Math.min(255, Math.round(g * f))); b = Math.max(0, Math.min(255, Math.round(b * f)));
  return `rgb(${r},${g},${b})`;
}
function placeAtTile(x, y) {
  let best = null, area = 1e9;
  for (const p of S.state.places) {
    const [rx, ry, rw, rh] = p.rect;
    if (x >= rx && x < rx + rw && y >= ry && y < ry + rh && rw * rh < area) { best = p; area = rw * rh; }
  }
  return best;
}
function buildStatic() {
  const rows = S.map, H = rows.length, W = rows[0].length;
  const oc = document.createElement('canvas'); oc.width = W * T; oc.height = H * T;
  const c = oc.getContext('2d');
  const owner = {};
  for (const p of S.state.places) if (p.indoor || p.type === 'terrain') { const [x, y, w, hh] = p.rect; for (let j = y; j < y + hh; j++) for (let i = x; i < x + w; i++) owner[i + ',' + j] = p; }
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const t = rows[y][x], px = x * T, py = y * T, r = hash(x, y);
    const pl = owner[x + ',' + y];
    const col = pl ? (TYPE_COL[pl.type] || '#888') : null;
    switch (t) {
      case 'g': c.fillStyle = r > .5 ? '#5d9c4a' : '#58964a'; c.fillRect(px, py, T, T); c.fillStyle = '#4d8a40'; if (r < .3) c.fillRect(px + (r * 40 | 0) % 12, py + (r * 90 | 0) % 12, 2, 2); break;
      case 'k': c.fillStyle = '#4a8c46'; c.fillRect(px, py, T, T); if (r < .12) { c.fillStyle = r < .06 ? '#ffd84a' : '#ff8fd0'; c.fillRect(px + 5, py + 7, 2, 2); } break;
      case 'r': c.fillStyle = '#4a4e58'; c.fillRect(px, py, T, T); c.fillStyle = '#555a66'; if (r < .25) c.fillRect(px + (r * 50 | 0) % 12, py + 4, 3, 1);
        if ((rows[y][x - 1] === 'r' && rows[y][x + 1] === 'r') && (rows[y + 1] && rows[y + 1][x] !== 'r' || rows[y - 1] && rows[y - 1][x] !== 'r')) { c.fillStyle = '#d8c850'; c.fillRect(px + 2, y % 2 ? py + T - 2 : py, 5, 2); } break;
      case 's': c.fillStyle = '#b8b2a0'; c.fillRect(px, py, T, T); c.fillStyle = '#a49e8c'; c.fillRect(px, py + T - 1, T, 1); break;
      case 'p': c.fillStyle = (x + y) % 2 ? '#cdbd9e' : '#c3b393'; c.fillRect(px, py, T, T); break;
      case 'l': c.fillStyle = '#9c8a62'; c.fillRect(px, py, T, T); c.fillStyle = '#8a7a54'; if (r < .3) c.fillRect(px + 4, py + 6, 3, 2); break;
      case 'f': c.fillStyle = shade(col, ((x + y) % 2 ? 1.0 : 0.93) * 0.55 + 0.45); c.fillRect(px, py, T, T);
        c.fillStyle = shade(col, 0.55); if (r < .05) c.fillRect(px + 3, py + 3, 6, 4); break;
      case 'w': c.fillStyle = shade(col || '#666', 0.42); c.fillRect(px, py, T, T); c.fillStyle = shade(col || '#666', 0.3); c.fillRect(px, py + T - 3, T, 3);
        if (pl && rows[y - 1] && rows[y - 1][x] !== 'w' && rows[y - 1][x] !== 'f' && hash(x, y + 7) < .35 && x > pl.rect[0] && x < pl.rect[0] + pl.rect[2] - 1) { c.fillStyle = '#bfe6ff'; c.fillRect(px + 3, py + 4, 10, 6); } break;
      case 'd': c.fillStyle = '#7a4a22'; c.fillRect(px, py, T, T); c.fillStyle = '#e8c870'; c.fillRect(px + 11, py + 8, 2, 2); break;
      case 't': c.fillStyle = '#58964a'; c.fillRect(px, py, T, T); c.fillStyle = '#5a3a1e'; c.fillRect(px + 7, py + 10, 3, 6); c.fillStyle = '#2f6b32'; c.fillRect(px + 2, py + 1, 12, 10); c.fillStyle = '#3d8a40'; c.fillRect(px + 4, py + 2, 6, 4); break;
      case 'x': c.fillStyle = '#cdbd9e'; c.fillRect(px, py, T, T); c.fillStyle = '#8a8a96'; c.fillRect(px + 1, py + 1, 14, 14); c.fillStyle = '#5ab0f0'; c.fillRect(px + 3, py + 3, 10, 10); c.fillStyle = '#c8ecff'; c.fillRect(px + 7, py + 5, 2, 6); break;
      case 'o': c.fillStyle = '#3a78c0'; c.fillRect(px, py, T, T); c.fillStyle = '#5a98e0'; c.fillRect(px + 3, py + 5, 6, 1); break;
      default: c.fillStyle = '#222'; c.fillRect(px, py, T, T);
    }
  }
  // enseignes
  c.textBaseline = 'middle'; c.textAlign = 'center';
  for (const p of S.state.places) {
    const [x, y, w, hh] = p.rect;
    if (p.type === 'terrain') {
      c.fillStyle = '#e8d8a0'; c.font = 'bold 9px monospace'; c.fillText('À BÂTIR', (x + w / 2) * T, (y + hh / 2) * T);
      continue;
    }
    if (!p.indoor) continue;
    const label = p.name.length > 22 ? p.name.slice(0, 21) + '…' : p.name;
    c.font = 'bold 9px monospace';
    const tw = Math.min(w * T - 4, c.measureText(label).width + 8);
    c.fillStyle = shade(TYPE_COL[p.type] || '#888', 0.7); c.fillRect((x + w / 2) * T - tw / 2, y * T + 2, tw, 12);
    c.fillStyle = '#fff'; c.fillText(label, (x + w / 2) * T, y * T + 8.5, w * T - 6);
  }
  S.staticCanvas = oc;
  if (cv.width !== W * T || cv.height !== H * T) { cv.width = W * T; cv.height = H * T; }
}

function drawAgent(a, now) {
  const jit = (hash(a.id.length, a.id.charCodeAt(a.id.length - 1)) - .5) * 6;
  const px = a.x * T + T / 2 + jit, bob = Math.sin(now / 400 + a.hue) > .6 ? -1 : 0;
  const py = a.y * T + T - 2 + bob;
  const born = S.arrived[a.id]; const k = born ? Math.min(1, (now - born) / 350) : 1;
  ctx.globalAlpha = .25 + .75 * k;
  const col = `hsl(${a.hue},65%,55%)`, dark = `hsl(${a.hue},55%,30%)`;
  ctx.fillStyle = '#0005'; ctx.fillRect(px - 5, py - 1, 10, 2);
  ctx.fillStyle = '#2a2438'; ctx.fillRect(px - 3, py - 5, 2, 4); ctx.fillRect(px + 1, py - 5, 2, 4);
  ctx.fillStyle = col; ctx.fillRect(px - 4, py - 11, 8, 6);
  ctx.fillStyle = dark; ctx.fillRect(px - 5, py - 10, 1, 4); ctx.fillRect(px + 4, py - 10, 1, 4);
  ctx.fillStyle = '#f1c9a0'; ctx.fillRect(px - 3, py - 17, 6, 6);
  ctx.fillStyle = dark; ctx.fillRect(px - 3, py - 17, 6, 2);
  ctx.fillStyle = '#222'; ctx.fillRect(px - 2, py - 14, 1, 1); ctx.fillRect(px + 1, py - 14, 1, 1);
  ctx.globalAlpha = 1;
  ctx.fillStyle = MOOD_COL[a.mood] || '#fff'; ctx.fillRect(px - 1, py - 20, 3, 2);
  if (a.human) { ctx.fillStyle = '#ffcf4a'; ctx.font = 'bold 10px monospace'; ctx.textAlign = 'center'; ctx.fillText('★', px, py - 24); }
  if (a.activity === 'réfléchit…') { ctx.fillStyle = '#fff'; const n = ((now / 300) | 0) % 4; for (let i = 0; i < n; i++) ctx.fillRect(px - 5 + i * 4, py - 24, 2, 2); }
  if (a.id === S.selected) {
    ctx.strokeStyle = (now / 250 | 0) % 2 ? '#ffcf4a' : '#fff'; ctx.lineWidth = 1.5; ctx.strokeRect(px - 8.5, py - 21.5, 17, 24);
  }
  return { px, py };
}

function wrap(text, max) {
  const words = text.split(' '), lines = []; let cur = '';
  for (const w of words) { if ((cur + ' ' + w).trim().length > max) { if (cur) lines.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); }
  if (cur) lines.push(cur);
  return lines.slice(0, 4).map((l, i, arr) => i === 3 && lines.length > 4 ? l + '…' : l);
}

function drawBubble(text, px, py, vol) {
  ctx.font = '9px monospace'; ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  const lines = wrap(text, vol === 'whisper' ? 18 : 26), w = Math.max(...lines.map(l => ctx.measureText(l).width)) + 8, hh = lines.length * 11 + 6;
  let bx = Math.max(2, Math.min(cv.width - w - 2, px - w / 2)), by = Math.max(2, py - 26 - hh);
  ctx.fillStyle = vol === 'shout' ? '#fff3b0' : vol === 'whisper' ? '#d0d0e8' : '#ffffff'; ctx.fillRect(bx, by, w, hh);
  ctx.strokeStyle = '#222'; ctx.lineWidth = 1; ctx.strokeRect(bx + .5, by + .5, w - 1, hh - 1);
  ctx.beginPath(); ctx.moveTo(px - 3, by + hh); ctx.lineTo(px + 3, by + hh); ctx.lineTo(px, by + hh + 4); ctx.closePath(); ctx.fillStyle = ctx.fillStyle; ctx.fill();
  ctx.fillStyle = vol === 'whisper' ? '#666' : '#111'; lines.forEach((l, i) => ctx.fillText(vol === 'whisper' ? '(' + l + ')' : l, bx + 4, by + 11 + i * 11));
}

function frame(now) {
  requestAnimationFrame(frame);
  if (!S.state || !S.map) return;
  if (!S.staticCanvas) buildStatic();
  ctx.drawImage(S.staticCanvas, 0, 0);
  if (S.hover && S.hover.place) {
    const [x, y, w, hh] = S.hover.place.rect; ctx.strokeStyle = '#ffcf4a'; ctx.lineWidth = 2; ctx.strokeRect(x * T + 1, y * T + 1, w * T - 2, hh * T - 2);
  }
  // effets de téléportation
  S.effects = S.effects.filter(e => now - e.t < 700);
  for (const e of S.effects) {
    const k = (now - e.t) / 700, cx = e.x * T + T / 2, cy = e.y * T + T / 2;
    ctx.strokeStyle = e.kind === 'in' ? `rgba(120,255,255,${1 - k})` : `rgba(255,140,255,${1 - k})`; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, 3 + k * (e.kind === 'in' ? 14 : 9), 0, 6.3); ctx.stroke();
    for (let i = 0; i < 6; i++) { const ang = i * 1.047 + k * 3; ctx.fillStyle = e.kind === 'in' ? '#7ff' : '#f8f'; ctx.fillRect(cx + Math.cos(ang) * k * 18, cy + Math.sin(ang) * k * 18 * (e.kind === 'in' ? -1 : 1), 2, 2); }
  }
  const agents = [...S.state.agents].filter(a => a.x != null).sort((a, b) => a.y - b.y);
  const pos = {};
  for (const a of agents) pos[a.id] = drawAgent(a, now);
  if ($('#opt-names').checked) {
    ctx.font = '8px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    for (const a of agents) { const p = pos[a.id]; ctx.fillStyle = '#000b'; const w = ctx.measureText(a.name).width + 4; ctx.fillRect(p.px - w / 2, p.py + 1, w, 9); ctx.fillStyle = a.human ? '#ffcf4a' : '#fff'; ctx.fillText(a.name, p.px, p.py + 8.5); }
  }
  if ($('#opt-bubbles').checked) for (const a of agents) {
    if (a.say && now - (S.bubbleSeen[a.say.seq] || 0) < 6500) drawBubble(a.say.text, pos[a.id].px, pos[a.id].py - 16, a.say.volume);
  }
}
requestAnimationFrame(frame);

function canvasTile(ev) {
  const r = cv.getBoundingClientRect(), sx = cv.width / r.width, sy = cv.height / r.height;
  return { cx: (ev.clientX - r.left) * sx, cy: (ev.clientY - r.top) * sy };
}
function hitAgent(cx, cy) {
  let best = null, bd = 14;
  for (const a of S.state.agents) { if (a.x == null) continue; const d = Math.hypot(cx - (a.x * T + T / 2), cy - (a.y * T + T / 2 - 4)); if (d < bd) { bd = d; best = a; } }
  return best;
}
cv.addEventListener('mousemove', ev => {
  if (!S.state) return;
  const { cx, cy } = canvasTile(ev), tip = $('#map-tip');
  const a = hitAgent(cx, cy), pl = placeAtTile(Math.floor(cx / T), Math.floor(cy / T));
  S.hover = { agent: a, place: pl && pl.id !== 'p_outdoor' && (pl.indoor || pl.type === 'terrain') ? pl : null };
  let txt = null;
  if (a) txt = `${a.human ? '★ ' : ''}${a.name}\n${a.activity}\n${a.money} pièces` + (a.goal ? `\nobjectif : ${a.goal}` : '');
  else if (S.hover.place) { const p = S.hover.place; txt = `${p.name}\n${TYPE_FR[p.type] || p.type}${p.owner_name ? ' — ' + p.owner_name : ''}` + (p.wage ? `\nsalaire ${p.wage}` : ''); }
  if (txt) { tip.hidden = false; tip.textContent = txt; const sr = $('#stage').getBoundingClientRect(); tip.style.left = Math.min(ev.clientX - sr.left + 14, sr.width - 220) + 'px'; tip.style.top = (ev.clientY - sr.top + 14) + 'px'; }
  else tip.hidden = true;
});
cv.addEventListener('mouseleave', () => { $('#map-tip').hidden = true; S.hover = null; });
cv.addEventListener('click', ev => {
  const { cx, cy } = canvasTile(ev), a = hitAgent(cx, cy);
  if (a) { selectAgent(a.id); return; }
  const p = placeAtTile(Math.floor(cx / T), Math.floor(cy / T));
  if (p && p.id !== 'p_outdoor') { S.focusPlace = p.id; setTab('world'); }
});

// ---------------------------------------------------------------- onglets
function setTab(name) {
  S.tab = name; S.lastPanelKey = '';
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === name));
  renderPanel(true);
}
document.querySelectorAll('#tabs button').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
function typing() { const e = document.activeElement; return e && $('#panel').contains(e) && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.tagName); }
async function renderPanel(force) {
  if (!S.state) return;
  if (!force && typing()) return;
  const panel = $('#panel'), scroll = panel.scrollTop;
  const fn = { agent: panelAgent, iachat: panelIachat, journal: panelJournal, convs: panelConvs, human: panelHuman, world: panelWorld, system: panelSystem }[S.tab];
  try {
    const node = await fn();
    if (node) { panel.textContent = ''; panel.append(node); panel.scrollTop = force ? 0 : scroll; }
  } catch (e) { if (!panel.firstChild) panel.append(h('div', { class: 'notice bad' }, e.message)); }
}
setInterval(() => renderPanel(false), 2500);

function evRow(r) {
  return h('div', { class: 'ev ' + r.type }, h('div', { class: 't' }, `${r.sim_time} · ${r.type}${r.data && r.data.origin ? ' · ' + r.data.origin : ''}`), h('div', null, r.summary));
}
function loadMore(btn, fn) { btn.disabled = true; fn().finally(() => { btn.disabled = false; }); }

// ---- Agent
function nameOf(id) { const a = S.state.agents.find(x => x.id === id); return a ? a.name : id; }
async function panelAgent() {
  const id = S.selected; if (!id) return h('div', { class: 'muted' }, 'Aucun agent.');
  const wrap = h('div');
  const subs = [['overview', 'Aperçu'], ['thoughts', 'Pensées'], ['memory', 'Mémoire'], ['relations', 'Relations'], ['messages', 'Messages'], ['goals', 'Objectifs'], ['history', 'Historique'], ['convs', 'Conversations'], ['knowledge', 'Savoirs']];
  wrap.append(h('div', { class: 'subtabs' }, subs.map(([k, l]) => h('button', { class: S.sub === k ? 'on' : '', onclick: () => { S.sub = k; S.subState = {}; renderPanel(true); } }, l))));
  const body = h('div'); wrap.append(body);
  const o = await api('/agents/' + id);
  body.append(h('div', { class: 'row' }, h('h3', null, (o.human ? '★ ' : '') + o.name), o.thinking ? h('span', { class: 'tag' }, 'réfléchit…') : null,
    h('span', { class: 'muted' }, `${o.place.name} · ${o.money} pièces · ☎ ${o.number}`)));
  body.append(h('div', { class: 'notice small' }, 'Vue administrateur : ces informations ne sont pas connues des autres habitants. Les « pensées » sont des traces simulées générées par le modèle, pas une preuve de conscience.'));
  const view = { overview: () => subOverview(o), thoughts: () => subLog(id, 'thoughts', 'Aucune pensée enregistrée.'), memory: () => subMemory(id), relations: () => subRelations(id),
    messages: () => subMessages(id), goals: () => subGoals(id), history: () => subLog(id, 'history', 'Aucun événement.'), convs: () => subConvs(id), knowledge: () => subKnowledge(id) }[S.sub];
  body.append(await view());
  return wrap;
}
function needsBlock(o) {
  return h('div', { class: 'kv' }, Object.entries(o.needs).map(([k, v]) => [h('span', null, NEED_FR[k] || k), bar(v / 100, v > 70 ? 'n' : '')]));
}
async function subOverview(o) {
  const d = h('div');
  const convs = await api(`/agents/${o.id}/conversations?limit=3`);
  d.append(h('h3', null, 'Conversations en cours'));
  const open = convs.rows.filter(c => c.state === 'open');
  if (!open.length) d.append(h('div', { class: 'muted' }, 'Aucune conversation ouverte.'));
  open.forEach(c => d.append(convCard(c)));
  d.append(h('h3', null, 'État'), h('div', { class: 'kv' },
    h('span', null, 'Activité'), h('span', null, o.activity), h('span', null, 'Logement'), h('span', null, o.home || 'sans logement'),
    h('span', null, 'Réputation'), h('span', null, `générale ${o.reputation.general ?? '—'} (${o.reputation.opinions || 0} avis) · commerce ${o.reputation.commerce ?? '—'}`),
    h('span', null, 'Stats'), h('span', null, `travaillé ${o.stats.worked} · fabriqué ${o.stats.crafted} · vendu ${o.stats.sold} · acheté ${o.stats.bought}`)));
  d.append(h('h3', null, 'Besoins (0 = satisfait)'), needsBlock(o));
  d.append(h('h3', null, 'Émotions simulées'), h('div', { class: 'kv' }, Object.entries(o.emotions).map(([k, v]) => [h('span', null, EMO_FR[k] || k), bar(v, 'p')])));
  d.append(h('h3', null, 'Personnalité (évolutive)'), h('div', { class: 'kv' }, Object.entries(o.personality).map(([k, v]) => [h('span', null, TRAIT_FR[k] || k), bar(v, 'g')])));
  d.append(h('h3', null, 'Compétences'), Object.keys(o.skills).length ? h('div', null, Object.entries(o.skills).map(([k, v]) => h('span', { class: 'tag' }, `${k} ${v}`))) : h('div', { class: 'muted' }, 'aucune pour l\'instant'));
  d.append(h('h3', null, 'Valeurs & croyances'));
  if (!o.values.length && !o.beliefs.length) d.append(h('div', { class: 'muted' }, 'Rien de formé pour l\'instant.'));
  o.values.forEach(v => d.append(h('div', { class: 'card' }, h('span', { class: 'tag good' }, 'valeur'), v.text)));
  o.beliefs.forEach(b => d.append(h('div', { class: 'card' }, h('span', { class: 'tag' }, `croyance ${pct(b.confidence)}%`), b.text)));
  d.append(h('h3', null, 'Inventaire'));
  if (!o.inventory.length) d.append(h('div', { class: 'muted' }, 'vide'));
  o.inventory.forEach(i => d.append(h('div', { class: 'card' }, h('b', null, i.name), ` (${i.category}, q${i.quality}) `, i.price ? h('span', { class: 'tag good' }, `en vente ${i.price}`) : null, h('div', { class: 'muted small' }, i.description))));
  d.append(h('h3', null, 'Carnet de contacts'));
  if (!o.contacts.length) d.append(h('div', { class: 'muted' }, 'aucun numéro connu'));
  o.contacts.forEach(c => d.append(h('div', null, `${c.name} — ☎ ${c.number} `, h('span', { class: 'muted small' }, c.provenance))));
  d.append(h('h3', null, 'Plan en cours & habitudes'));
  d.append(h('div', { class: 'muted small' }, o.plan.length ? o.plan.map(p => p.type).join(' → ') : 'pas de plan'), h('div', { class: 'muted small' }, Object.keys(o.routines).length ? 'habitudes : ' + Object.entries(o.routines).map(([k, v]) => `${k}×${v.count}`).join(', ') : 'aucune habitude apprise'));
  return d;
}
async function subLog(id, kind, empty) {
  const st = S.subState;
  if (st.pages == null) { st.pages = 1; st.q = ''; }
  const d = h('div');
  d.append(h('input', { type: 'search', placeholder: 'rechercher…', value: st.q, onchange: e => { st.pages = 1; st.q = e.target.value; renderPanel(true); } }));
  const r = await api(`/agents/${id}/log?kind=${kind}&limit=${Math.min(300, 30 * st.pages)}&q=${encodeURIComponent(st.q)}`);
  d.append(h('div', { class: 'muted small' }, `${r.total} entrée(s)`));
  if (!r.rows.length) d.append(h('div', { class: 'muted' }, empty));
  r.rows.forEach(x => d.append(evRow(x)));
  if (r.has_more) d.append(h('button', { onclick: () => { st.pages++; renderPanel(true); } }, 'Charger plus'));
  return d;
}
async function subMemory(id) {
  const st = S.subState; st.page = st.page || 1; st.q = st.q || ''; st.kind = st.kind || '';
  const r = await api(`/agents/${id}/memory?page=${st.page}&per_page=20&q=${encodeURIComponent(st.q)}&kind=${st.kind}`);
  const d = h('div');
  const kinds = ['', 'experience', 'conversation', 'overheard', 'message', 'post', 'info', 'lesson', 'thought', 'event', 'transaction'];
  d.append(h('div', { class: 'row' }, h('input', { type: 'search', placeholder: 'rechercher…', value: st.q, onchange: e => { st.q = e.target.value; st.page = 1; renderPanel(true); } }),
    h('select', { onchange: e => { st.kind = e.target.value; st.page = 1; renderPanel(true); } }, kinds.map(k => h('option', { value: k, selected: k === st.kind }, k || 'tous types')))));
  d.append(h('div', { class: 'muted small' }, `${r.total} souvenir(s) — subjectifs : confiance et déformation possibles, le fait d'origine est dans le journal global`));
  r.rows.forEach(m => d.append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('span', { class: 'tag' }, m.kind), h('span', { class: 'muted small' }, `${m.time} · confiance ${pct(m.confidence)}%` + (m.source && m.source !== 'self' ? ` · source ${nameOf(m.source)}` : '') + (m.fact_seq ? ` · fait #${m.fact_seq}` : '')), m.distorted ? h('span', { class: 'tag bad' }, 'déformé') : null),
    h('div', null, m.recalled), m.recalled !== m.original ? h('div', { class: 'muted small' }, 'original : ' + m.original) : null)));
  d.append(pager(st, r.total, 20));
  return d;
}
function pager(st, total, per) {
  const pages = Math.max(1, Math.ceil(total / per));
  return h('div', { class: 'row' }, h('button', { disabled: st.page <= 1, onclick: () => { st.page--; renderPanel(true); } }, '← Préc.'), h('span', { class: 'muted' }, `page ${st.page}/${pages}`),
    h('button', { disabled: st.page >= pages, onclick: () => { st.page++; renderPanel(true); } }, 'Suiv. →'));
}
async function subRelations(id) {
  const r = await api(`/agents/${id}/relationships`), d = h('div');
  if (!r.rows.length) d.append(h('div', { class: 'muted' }, 'Aucune relation pour l\'instant : cet agent n\'a rencontré personne.'));
  r.rows.forEach(x => d.append(h('div', { class: 'card' },
    h('div', { class: 'row' }, h('b', { style: { cursor: 'pointer' }, onclick: () => selectAgent(x.id) }, x.name), x.types.map(t => h('span', { class: 'tag good' }, t)),
      h('span', { class: 'tag' }, x.has_number ? '☎ numéro connu' : 'sans numéro'), x.they_have_my_number ? h('span', { class: 'tag' }, 'a mon numéro') : null),
    h('div', { class: 'kv' }, h('span', null, 'confiance'), bar(x.trust, 'g'), h('span', null, 'amitié'), bar(x.friendship, 'p'), h('span', null, 'rivalité'), bar(x.rivalry, ''), h('span', null, 'hostilité'), bar(x.hostility, 'n')),
    h('div', { class: 'muted small' }, `${x.interactions} interactions`), x.history.slice(-4).map(hh => h('div', { class: 'muted small' }, `t${hh.tick} · ${hh.why}`)))));
  return d;
}
async function subMessages(id) {
  const st = S.subState, r = await api(`/agents/${id}/messages${st.with ? '?with=' + st.with : ''}`), d = h('div');
  d.append(h('div', { class: 'notice small' }, 'Accès superviseur aux messages privés. Ils ne sont pas visibles des autres agents ni sur IACHAT.'));
  if (!r.threads.length) d.append(h('div', { class: 'muted' }, 'Aucun message privé (il faut connaître un numéro pour écrire).'));
  r.threads.forEach(t => d.append(h('div', { class: 'card', style: { cursor: 'pointer', borderColor: st.with === t.with ? 'var(--accent)' : '' }, onclick: () => { st.with = t.with; renderPanel(true); } }, h('b', null, t.name), ` · ${t.count} message(s) · `, h('span', { class: 'muted' }, t.last.text.slice(0, 60)))));
  r.messages.forEach(m => d.append(h('div', { class: 'bubble' }, h('b', null, m.from_name), ' → ', m.to_name, ` (${m.status}) : `, m.text)));
  return d;
}
async function subGoals(id) {
  const r = await api(`/agents/${id}/goals`), d = h('div');
  if (!r.rows.length) d.append(h('div', { class: 'muted' }, 'Aucun objectif : l\'agent n\'en a pas encore défini (aucun n\'est imposé).'));
  r.rows.forEach(g => d.append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('span', { class: 'tag ' + (g.status === 'done' ? 'good' : g.status === 'active' ? '' : 'bad') }, g.status), h('b', null, g.description)),
    h('div', { class: 'row' }, bar(g.progress, 'g'), h('span', { class: 'muted small' }, `${pct(g.progress)}% · ${g.kind} · priorité ${g.priority.toFixed(1)} · origine : ${g.origin}`)))));
  return d;
}
function convCard(c) {
  return h('div', { class: 'card' }, h('div', { class: 'row' }, h('span', { class: 'tag' }, c.state === 'open' ? 'ouverte' : 'terminée'), h('b', null, c.participants.map(p => p.name).join(' & ')), h('span', { class: 'muted small' }, `${c.place} · ${c.total_turns} répliques`)),
    c.turns.slice(-12).map(t => h('div', { class: 'bubble' + (t.overheard ? ' over' : '') }, h('b', null, t.speaker), t.volume !== 'normal' ? ` (${t.volume})` : '', t.overheard ? ' [entendu de loin]' : '', ' : ', t.text)));
}
async function subConvs(id) { const r = await api(`/agents/${id}/conversations?limit=10`), d = h('div'); if (!r.rows.length) d.append(h('div', { class: 'muted' }, 'Aucune conversation entendue.')); r.rows.forEach(c => d.append(convCard(c))); return d; }
async function subKnowledge(id) {
  const r = await api(`/agents/${id}/knowledge?per_page=50`), d = h('div');
  d.append(h('div', { class: 'muted small' }, 'Informations reçues avec leur provenance. Une rumeur n\'est pas un fait vérifié.'));
  if (!r.rows.length) d.append(h('div', { class: 'muted' }, 'Aucune information reçue.'));
  r.rows.forEach(k => d.append(h('div', { class: 'card' }, h('span', { class: 'tag ' + (k.kind === 'rumor' ? 'bad' : '') }, k.kind), `confiance ${pct(k.confidence)}% · `, h('span', { class: 'muted small' }, `source ${k.source_name} · ${k.hops} saut(s)${k.chain_names.length ? ' · chaîne : ' + k.chain_names.join(' → ') : ''}`), h('div', null, k.claim))));
  return d;
}

// ---- IACHAT
let iachatState = { rows: [], more: false, author: '', openReply: null, loaded: false, humanName: '' };
async function panelIachat() {
  const st = iachatState;
  const r = await api('/iachat/feed?limit=30' + (st.author ? '&author=' + st.author : ''));
  st.rows = r.rows; st.more = r.has_more;
  const d = h('div');
  d.append(h('h3', null, 'IACHAT — réseau social fictif'));
  const ta = h('textarea', { rows: 2, maxlength: 280, placeholder: S.state.human ? 'Publier en tant que ' + nameOf(S.state.human) + '…' : 'Publier en tant qu\'humain…', id: 'pub-text' });
  const counter = h('span', { class: 'muted small' }, '0/280');
  ta.addEventListener('input', () => counter.textContent = ta.value.length + '/280');
  const nameIn = !S.state.human ? h('input', { type: 'text', placeholder: 'Pseudo (Humain)', maxlength: 24, value: st.humanName, onchange: e => st.humanName = e.target.value }) : null;
  d.append(ta, h('div', { class: 'row' }, nameIn, h('button', { onclick: async () => { if (!ta.value.trim()) return; await api('/iachat/post', { method: 'POST', body: { text: ta.value, name: st.humanName } }); ta.value = ''; renderPanel(true); } }, 'Publier'), counter));
  const sel = h('select', { onchange: e => { st.author = e.target.value; renderPanel(true); } }, h('option', { value: '' }, 'tous les auteurs'), ...S.state.agents.map(a => h('option', { value: a.id, selected: a.id === st.author }, a.name)));
  d.append(h('div', { class: 'row', style: { marginTop: '8px' } }, 'Filtrer :', sel, h('span', { class: 'muted small' }, `${r.total} publications`)));
  const top = r.rows.filter(p => !p.reply_to);
  const byParent = {};
  r.rows.filter(p => p.reply_to).forEach(p => (byParent[p.reply_to] = byParent[p.reply_to] || []).push(p));
  const list = h('div'); d.append(list);
  const shown = st.author ? r.rows : top;
  shown.forEach(p => { list.append(postNode(p)); (byParent[p.id] || []).slice().reverse().forEach(c => list.append(postNode(c, true))); });
  if (!shown.length) list.append(h('div', { class: 'muted' }, 'Aucune publication pour l\'instant. Les agents publient quand ils en ressentent le besoin.'));
  return d;
}
function postNode(p, reply) {
  const n = h('div', { class: 'post' + (reply ? ' reply' : '') + (p.human ? ' humanpost' : '') },
    h('div', { class: 'row' }, h('b', { style: { cursor: p.author.startsWith('a') ? 'pointer' : 'default' }, onclick: () => p.author.startsWith('a') && selectAgent(p.author) }, p.author_name),
      p.human ? h('span', { class: 'tag human' }, 'HUMAIN') : (p.author === 'city' ? h('span', { class: 'tag' }, 'officiel') : h('span', { class: 'tag' }, 'agent IA')), h('span', { class: 'muted small' }, p.time)),
    h('div', null, p.text),
    h('div', { class: 'row small' }, Object.entries(p.reactions).map(([k, v]) => h('span', { class: 'tag', title: (p.reactors[k] || []).join(', ') }, `${k} ${v}`)),
      !reply ? h('a', { onclick: () => replyBox(n, p) }, `répondre (${p.replies})`) : null,
      S.state.human ? ['like', 'love', 'laugh'].map(k => h('a', { onclick: async () => { await api('/iachat/react', { method: 'POST', body: { post_id: p.id, kind: k } }); renderPanel(true); } }, k)) : null));
  return n;
}
function replyBox(node, p) {
  if (node.querySelector('.rbox')) return;
  const ta = h('textarea', { rows: 1, maxlength: 280 });
  node.append(h('div', { class: 'rbox row' }, ta, h('button', { onclick: async () => { if (!ta.value.trim()) return; await api('/iachat/post', { method: 'POST', body: { text: ta.value, reply_to: p.id, name: iachatState.humanName } }); renderPanel(true); } }, 'Envoyer')));
  ta.focus();
}

// ---- Journal
let journal = { rows: [], more: false, types: '', q: '', actor: '', live: true };
async function panelJournal() {
  const j = journal;
  if (j.pages == null) j.pages = 1;
  const q = `/log?limit=${Math.min(500, 60 * j.pages)}${j.types ? '&types=' + j.types : ''}${j.actor ? '&actor=' + j.actor : ''}${j.q ? '&q=' + encodeURIComponent(j.q) : ''}`;
  const r = await api(q); j.rows = r.rows; j.more = r.has_more;
  const d = h('div');
  const TYPES = ['', 'thought', 'say', 'action', 'action_rejected', 'teleport', 'dm', 'post,reply', 'transaction', 'craft,build', 'work', 'relationship', 'info,lie', 'world_event', 'llm_error', 'system,restore'];
  const reset = () => { j.pages = 1; renderPanel(true); };
  d.append(h('h3', null, 'Journal global (administrateur)'), h('div', { class: 'row' },
    h('select', { onchange: e => { j.types = e.target.value; reset(); } }, TYPES.map(t => h('option', { value: t, selected: t === j.types }, t || 'tous les types'))),
    h('select', { onchange: e => { j.actor = e.target.value; reset(); } }, h('option', { value: '' }, 'tous les agents'), ...S.state.agents.map(a => h('option', { value: a.id, selected: a.id === j.actor }, a.name))),
    h('input', { type: 'search', placeholder: 'rechercher…', value: j.q, onchange: e => { j.q = e.target.value; reset(); } })));
  j.rows.forEach(x => d.append(evRow(x)));
  if (j.more) d.append(h('button', { onclick: () => { j.pages++; renderPanel(true); } }, 'Charger plus'));
  return d;
}

// ---- Conversations
async function panelConvs() {
  const r = await api('/conversations?state=open&per_page=30'), d = h('div');
  d.append(h('h3', null, `Conversations ouvertes (${r.total})`));
  if (!r.rows.length) d.append(h('div', { class: 'muted' }, 'Aucune conversation ouverte en ce moment.'));
  r.rows.forEach(c => d.append(convCard(c)));
  const old = await api('/conversations?state=closed&per_page=10');
  d.append(h('h3', null, 'Récemment terminées'));
  old.rows.forEach(c => d.append(convCard(c)));
  return d;
}

// ---- Mon personnage
async function panelHuman() {
  const v = await api('/human'), d = h('div');
  d.append(h('h3', null, 'Mon personnage'));
  d.append(h('div', { class: 'notice small' }, 'Ce panneau n\'affiche que ce que votre personnage a vu ou entendu dans le monde. Les pensées et messages des habitants, visibles dans les autres onglets, ne lui sont pas connus.'));
  if (!v.spawned) {
    const name = h('input', { type: 'text', placeholder: 'Votre nom ou pseudo', maxlength: 24 });
    d.append(h('div', { class: 'row' }, name, h('button', { onclick: async () => { if (!name.value.trim()) return; await api('/human/spawn', { method: 'POST', body: { name: name.value } }); renderPanel(true); } }, 'Entrer dans la ville')));
    return d;
  }
  const act = async (body, okMsg) => { try { const r = await api('/human/action', { method: 'POST', body }); toast(okMsg || r.message); } catch (e) { /* toast déjà affiché */ } renderPanel(true); };
  d.append(h('div', { class: 'kv' }, h('span', null, 'Nom'), h('span', null, v.name), h('span', null, 'Lieu'), h('span', null, v.place.name), h('span', null, 'Argent'), h('span', null, v.money), h('span', null, 'Mon numéro'), h('span', null, v.number)));
  const dest = h('select', null, v.places.map(p => h('option', { value: p.id, selected: p.id === v.place.id }, p.name)));
  d.append(h('h3', null, 'Se téléporter'), h('div', { class: 'row' }, dest, h('button', { onclick: () => act({ type: 'teleport', place: dest.value }) }, 'Y aller')));
  d.append(h('h3', null, 'Personnes à portée de vue'));
  if (!v.people.length) d.append(h('div', { class: 'muted' }, 'Personne autour de vous.'));
  v.people.forEach(p => d.append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('b', null, p.name), h('span', { class: 'muted small' }, `${p.known ? 'connu' : 'inconnu'} · ${p.doing} · audibilité ${Math.round(p.audible * 100)}%`)),
    h('div', { class: 'row' }, h('button', { onclick: () => act({ type: 'give_number', to: p.id }, 'Numéro donné') }, 'Donner mon numéro')))));
  const to = h('select', null, h('option', { value: '' }, 'à la cantonade'), ...v.people.map(p => h('option', { value: p.id }, p.name)));
  const vol = h('select', null, h('option', { value: 'normal' }, 'voix normale'), h('option', { value: 'whisper' }, 'chuchoter'), h('option', { value: 'shout' }, 'crier'));
  const say = h('input', { type: 'text', placeholder: 'Ce que vous dites…', maxlength: 240, style: { flex: 1 } });
  const send = () => { if (!say.value.trim()) return; const b = { type: 'say', text: say.value, volume: vol.value }; if (to.value) b.to = to.value; act(b, 'Dit'); };
  say.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
  d.append(h('h3', null, 'Parler'), h('div', { class: 'row' }, to, vol), h('div', { class: 'row' }, say, h('button', { onclick: send }, 'Dire')));
  const cs = h('select', null, v.contacts.map(c => h('option', { value: c.id }, `${c.name} (${c.number})`)));
  const sms = h('input', { type: 'text', placeholder: 'SMS…', maxlength: 280, style: { flex: 1 } });
  d.append(h('h3', null, 'Téléphone'), v.contacts.length ? h('div', { class: 'row' }, cs, sms, h('button', { onclick: () => { if (sms.value.trim()) act({ type: 'text', to: cs.value, text: sms.value }, 'SMS envoyé'); } }, 'Envoyer')) : h('div', { class: 'muted' }, 'Aucun contact : demandez leur numéro en personne.'));
  v.messages.slice().reverse().forEach(m => d.append(h('div', { class: 'bubble' }, h('b', null, m.from_name), ' → ', m.to_name, ' : ', m.text)));
  if (v.market.length) {
    d.append(h('h3', null, 'En vente ici'));
    v.market.forEach(m => d.append(h('div', { class: 'row' }, `${m.name} — ${m.price} (${m.seller})`, h('button', { onclick: () => act({ type: 'buy', item_id: m.item_id }, 'Acheté') }, 'Acheter'))));
  }
  if (v.inventory.length) { d.append(h('h3', null, 'Inventaire')); v.inventory.forEach(i => d.append(h('div', null, i.name + (i.price ? ` (en vente ${i.price})` : '')))); }
  d.append(h('h3', null, 'Ce que j\'ai vu et entendu'));
  v.memory.forEach(m => d.append(h('div', { class: 'bubble' + (m.kind === 'overheard' ? ' over' : '') }, h('span', { class: 'muted small' }, m.time + ' '), m.recalled)));
  return d;
}

// ---- Monde
async function panelWorld() {
  const d = h('div'), st = S.state;
  const cfg = await api('/config');
  d.append(h('h3', null, 'Déclencher un événement'));
  Object.entries(cfg.scenarios).forEach(([k, desc]) => d.append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('b', null, k), h('button', { onclick: async () => { const r = await api('/events/trigger', { method: 'POST', body: { key: k } }); toast(r.description); renderPanel(true); } }, 'Déclencher')), h('div', { class: 'muted small' }, desc))));
  d.append(h('h3', null, 'Économie'), h('div', { class: 'kv' }, h('span', null, 'Trésor de la Ville'), h('span', null, st.treasury), h('span', null, 'Multiplicateur prix'), h('span', null, st.flags.price_mult), h('span', null, 'Loyers / salaires'), h('span', null, `×${st.flags.rent_mult} / ×${st.flags.wage_mult}`)));
  d.append(h('h3', null, 'Lieux'));
  st.places.forEach(p => d.append(h('div', { class: 'card', style: { borderColor: S.focusPlace === p.id ? 'var(--accent)' : '' } }, h('div', { class: 'row' }, h('i', { style: { width: '10px', height: '10px', background: TYPE_COL[p.type] || '#888', display: 'inline-block' } }), h('b', null, p.name), h('span', { class: 'tag' }, TYPE_FR[p.type] || p.type), p.built ? h('span', { class: 'tag good' }, 'créé par un agent') : null),
    h('div', { class: 'muted small' }, `propriétaire : ${p.owner_name || '—'}${p.wage ? ' · salaire ' + p.wage : ''}${p.for_sale ? ' · à vendre ' + p.price : ''}${p.capacity ? ` · logements ${p.tenants}/${p.capacity}` : ''}`))));
  return d;
}

// ---- Système
async function panelSystem() {
  const d = h('div'), st = S.state;
  const l = await api('/llm'), sv = await api('/saves');
  d.append(h('h3', null, 'Modèle de langage local'));
  d.append(h('div', { class: 'card' }, h('div', { class: 'kv' }, h('span', null, 'Mode actif'), h('span', null, l.mode + (l.available ? '' : ' (indisponible)')), h('span', null, 'Modèle'), h('span', null, l.model), h('span', null, 'Appels'), h('span', null, `${l.stats.calls} · erreurs ${l.stats.errors} · invalides ${l.stats.invalid} · dernier ${l.stats.last_ms ?? '—'} ms`)),
    l.last_error ? h('div', { class: 'notice bad small' }, l.last_error) : null));
  const mode = h('select', null, ['auto', 'ollama', 'demo'].map(m => h('option', { value: m, selected: m === l.configured }, m === 'auto' ? 'auto (Ollama sinon démo)' : m === 'demo' ? 'démonstration (sans modèle)' : 'Ollama')));
  const model = h('input', { type: 'text', value: l.model.includes('démo') ? 'llama3.2:3b' : l.model, size: 16 });
  const url = h('input', { type: 'text', value: l.url, size: 26 });
  d.append(h('div', { class: 'row' }, mode, model, url, h('button', { onclick: async () => { await api('/llm/config', { method: 'POST', body: { mode: mode.value, model: model.value, url: url.value } }); toast('Configuration LLM appliquée'); renderPanel(true); } }, 'Appliquer / tester')),
    h('div', { class: 'muted small' }, 'Installation : « ollama pull llama3.2:3b » puis choisir le mode Ollama. Le modèle doit rester adapté à votre RAM/GPU.'));
  d.append(h('h3', null, 'Sauvegardes'));
  const nm = h('input', { type: 'text', placeholder: 'nom (optionnel)', maxlength: 60 });
  d.append(h('div', { class: 'row' }, nm, h('button', { onclick: async () => { const r = await api('/saves', { method: 'POST', body: { name: nm.value } }); toast('Sauvegardé : ' + r.name); renderPanel(true); } }, '💾 Sauvegarder')));
  const file = h('input', { type: 'file', accept: '.json' });
  d.append(h('div', { class: 'row' }, file, h('button', { onclick: async () => { if (!file.files[0]) return; if (!confirm('Importer et restaurer ce fichier remplace la simulation en cours.')) return; const fd = new FormData(); fd.append('file', file.files[0]); await api('/saves/import', { method: 'POST', form: fd }); toast('Sauvegarde importée'); S.subState = {}; renderPanel(true); } }, 'Importer')));
  if (!sv.length) d.append(h('div', { class: 'muted' }, 'Aucune sauvegarde.'));
  sv.forEach(s => d.append(h('div', { class: 'card' }, h('div', { class: 'row' }, h('b', null, s.name), h('span', { class: 'muted small' }, `${s.agents} agents · cycle ${s.tick}${s.auto ? ' · auto' : ''}`)),
    h('div', { class: 'row' }, h('button', { onclick: async () => { if (!confirm('Revenir à cet état ? Les événements ultérieurs seront masqués du journal.')) return; await api(`/saves/${s.id}/restore`, { method: 'POST', body: {} }); toast('État restauré'); S.subState = {}; iachatState.rows = []; renderPanel(true); } }, '↩ Restaurer'),
      h('a', { href: `/api/saves/${s.id}/download`, download: '' }, h('button', null, '⬇ Télécharger'))))));
  d.append(h('h3', null, 'Exporter les journaux'), h('div', { class: 'row' },
    ['jsonl', 'json', 'csv'].map(f => h('a', { href: '/api/export?format=' + f }, h('button', null, 'Journal .' + f))),
    ['agents', 'transactions', 'posts', 'messages', 'items'].map(t => h('a', { href: '/api/export/table/' + t }, h('button', null, t + '.csv')))));
  d.append(h('h3', null, 'Intégrité'));
  const out = h('div', { class: 'muted small' }, st.integrity_errors ? `${st.integrity_errors} anomalie(s) détectée(s)` : 'Aucune anomalie détectée.');
  d.append(h('button', { onclick: async () => { const r = await api('/integrity'); out.textContent = r.ok ? 'OK : monnaie conservée, références valides, positions valides.' : r.errors.join(' | '); } }, 'Vérifier maintenant'), out);
  return d;
}

// ---------------------------------------------------------------- contrôles d'en-tête
$('#btn-play').addEventListener('click', async () => { await api(S.state.paused ? '/sim/resume' : '/sim/pause', { method: 'POST', body: {} }); poll(); });
$('#btn-step').addEventListener('click', async () => { await api('/sim/step', { method: 'POST', body: { n: 1 } }); poll(); renderPanel(false); });
$('#speed').addEventListener('change', async e => { await api('/sim/speed', { method: 'POST', body: { speed: parseFloat(e.target.value) } }); poll(); });
$('#btn-new').addEventListener('click', async () => {
  const n = parseInt($('#new-n').value, 10);
  if (!(n >= 1 && n <= 20)) { toast('Le nombre d\'agents doit être entre 1 et 20', true); return; }
  if (!confirm('Créer une nouvelle simulation ? L\'état actuel sera perdu (pensez à sauvegarder).')) return;
  const body = { num_agents: n, human: $('#new-human').value.trim() || null, start: true };
  const seed = $('#new-seed').value.trim(); if (seed) body.seed = seed;
  await api('/sim/new', { method: 'POST', body });
  S.map = null; S.selected = null; S.subState = {}; S.prevPos = {}; iachatState.rows = [];
  await poll(); renderPanel(true); toast('Nouvelle simulation créée');
});

poll().then(() => renderPanel(true));
setInterval(poll, 800);
