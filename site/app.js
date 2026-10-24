/* moonape dashboard: reads site/data/*.json, renders with Plotly. House grammar: black + one orange ramp; grey for reference lines. */
(() => {
  const C = { black: '#1a1a1a', oDark: '#b34212', oMid: '#eb6834', oLight: '#f4a06f', oPale: '#fbd9c4', grey: '#9a9a9a' };
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const FG = dark ? '#f2efe9' : '#1a1a1a', MUTED = dark ? '#a09a90' : '#6b6b6b', LINE = dark ? '#2e2c28' : '#e6e2dc';
  const INK = dark ? '#f2efe9' : C.black;
  const base = () => ({ paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: FG, size: 12 },
    margin: { l: 52, r: 16, t: 8, b: 40 }, xaxis: { gridcolor: LINE, zeroline: false }, yaxis: { gridcolor: LINE, zeroline: false },
    legend: { orientation: 'h', y: 1.12, x: 0, font: { size: 11 } }, hovermode: 'x unified' });
  const CFG = { displayModeBar: false, responsive: true };
  const $ = (s) => document.querySelector(s);
  const fmt = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
  const fmt0 = (v) => (v == null) ? '—' : Number(v).toLocaleString();
  const pct = (v, d = 1) => (v == null || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(d)}%`;
  const ago = (iso) => { if (!iso) return '—'; const m = (Date.now() - new Date(iso)) / 60000; if (m < 60) return `${Math.round(m)}m ago`; if (m < 2880) return `${Math.round(m / 60)}h ago`; return `${Math.round(m / 1440)}d ago`; };
  const dstr = (iso) => iso ? new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  const empty = (id, msg = 'no data yet — run a collector') => { const el = $(id); el.innerHTML = `<div class="empty">${msg}</div>`; };
  const plot = (id, traces, layout) => { const el = $(id); if (!traces.length || traces.every(t => !(t.x || []).length)) return empty(id); el.innerHTML = ''; Plotly.newPlot(el, traces, Object.assign(base(), layout || {}), CFG); };
  const vline = (x, color, dash, name) => ({ type: 'line', x0: x, x1: x, y0: 0, y1: 1, yref: 'paper', line: { color, width: 1.5, dash } , name });
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const D = {};
  async function load() {
    const names = ['meta', 'tiles', 'price_macro', 'options', 'iv', 'reddit', 'sec', 'socials', 'library'];
    await Promise.all(names.map(async (n) => { try { const r = await fetch(`data/${n}.json?v=${Date.now() >> 16}`); D[n] = r.ok ? await r.json() : null; } catch (e) { D[n] = null; } }));
  }

  // ---------------------------------------------------------------- tabs
  document.querySelectorAll('.tabs button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('.tabs button').forEach((x) => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.id === `tab-${b.dataset.tab}`));
    location.hash = b.dataset.tab; window.dispatchEvent(new Event('resize'));
  }));
  if (location.hash) { const b = document.querySelector(`.tabs button[data-tab="${location.hash.slice(1)}"]`); if (b) b.click(); }

  // ---------------------------------------------------------------- status + tiles
  function status() {
    const m = D.meta; if (!m) { $('#status').textContent = 'no data'; return; }
    const ds = m.datasets || {}; const t = ds.option_chain?.latest_fetch; const minutes = t ? (Date.now() - new Date(t)) / 60000 : Infinity;
    const cls = minutes < (m.stale_after?.intraday_min || 45) ? 'fresh' : 'stale';
    $('#status').innerHTML = `<span class="dot ${cls}"></span>chain ${t ? ago(t) : 'never'} · built ${ago(m.built_at)}`;
    if (m.fixture) { const b = document.createElement('div'); b.className = 'banner'; b.textContent = 'Synthetic fixture data — the collectors have not run with real keys yet. Prices, chain and IV here are generated, not market data.'; document.querySelector('main').prepend(b); }
  }
  function tile(k, v, s, cls = '') { return `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s ${cls}">${s || ''}</div></div>`; }
  function tiles() {
    const T = D.tiles || {}; const S = T.stocks || {}, O = T.options || {}, Y = T.yields || {}, M = T.macro || {};
    const g = S.GME, sp = S.SPY; const out = [];
    out.push(tile('GME', g ? fmt(g.price) : '—', g ? `${pct(g.change_pct)} · ${ago(g.ts)}` : 'no snapshot', g?.change_pct >= 0 ? 'up' : 'down'));
    out.push(tile('SPY', sp ? fmt(sp.price) : '—', sp ? `${pct(sp.change_pct)}` : '', sp?.change_pct >= 0 ? 'up' : 'down'));
    out.push(tile(`Max pain ${O.front_expiry || ''}`, fmt(O.front_max_pain), O.spot ? `spot ${fmt(O.spot)} · ${O.front_dte}d · OI ${O.oi_date || ''}` : ''));
    out.push(tile(`Monthly ${O.monthly_expiry || ''}`, fmt(O.monthly_max_pain), O.front_call_wall ? `walls C ${fmt(O.front_call_wall, 1)} / P ${fmt(O.front_put_wall, 1)}` : ''));
    out.push(tile('IV30', O.iv30 != null ? `${(O.iv30 * 100).toFixed(1)}%` : '—', O.iv_rank != null ? `rank ${fmt(O.iv_rank, 0)} · pct ${fmt(O.iv_pct, 0)} (${O.iv_history_days}d)` : 'rank needs history'));
    out.push(tile('P/C (OI · vol)', `${fmt(O.pc_oi)} · ${fmt(O.pc_vol)}`, O.n_contracts ? `${fmt0(O.n_contracts)} contracts` : ''));
    out.push(tile('Net GEX', O.net_gex != null ? `${(O.net_gex / 1e6).toFixed(1)}M` : '—', O.zero_gamma != null ? `zero-gamma ≈ ${fmt(O.zero_gamma, 1)}` : '$ per 1% move'));
    out.push(tile('10Y', Y['10Y'] != null ? `${fmt(Y['10Y'])}%` : '—', Y.date ? `2Y ${fmt(Y['2Y'])} · 30Y ${fmt(Y['30Y'])} · ${Y.date}` : ''));
    out.push(tile('10Y−2Y', Y.spread_10y2y != null ? `${fmt(Y.spread_10y2y)}` : '—', 'Treasury par curve'));
    out.push(tile('USD/JPY', M['JPY=X'] ? fmt(M['JPY=X'].value) : '—', M['JPY=X'] ? ago(M['JPY=X'].ts) : 'Yahoo'));
    out.push(tile('BOJ rate', T.boj ? `${T.boj.rate.toFixed(2)}%` : '—', T.boj ? `since ${T.boj.asof}` : ''));
    out.push(tile('DXY', M['DX-Y.NYB'] ? fmt(M['DX-Y.NYB'].value) : '—', M['DX-Y.NYB'] ? ago(M['DX-Y.NYB'].ts) : 'Yahoo'));
    const sec = T.sec || {}; out.push(tile('Latest filing', sec.form || '—', sec.filing_date ? `${esc(sec.entity)} · ${sec.filing_date}` : ''));
    const r = T.reddit || {}; out.push(tile('DD posts, 7d', fmt0(r.n_dd_7d), r.title ? `latest ${ago(r.created_utc)}` : ''));
    $('#tiles').innerHTML = out.join('');
  }

  // ---------------------------------------------------------------- overview charts
  function overview() {
    const P = D.price_macro || {};
    const idx = (arr) => arr && arr.length ? arr.map(([t, v]) => [t, v / arr[0][1] * 100]) : [];
    const gi = idx((P.intraday || {}).GME || (P.bars15 || {}).GME), si = idx((P.intraday || {}).SPY || (P.bars15 || {}).SPY);
    plot('#ch-intraday', [
      { x: gi.map(p => p[0]), y: gi.map(p => p[1]), name: 'GME', line: { color: C.oMid, width: 2 } },
      { x: si.map(p => p[0]), y: si.map(p => p[1]), name: 'SPY', line: { color: INK, width: 1.5 } }], { yaxis: { gridcolor: LINE, ticksuffix: '' } });
    const gd = ((P.daily || {}).GME || []).slice(-260);
    plot('#ch-gme-daily', [{ x: gd.map(r => r.t), y: gd.map(r => r.close), name: 'GME close', line: { color: INK, width: 1.5 }, fill: 'tozeroy', fillcolor: dark ? 'rgba(235,104,52,.12)' : 'rgba(235,104,52,.10)' }],
      { yaxis: { gridcolor: LINE, tickprefix: '$', rangemode: 'tozero' } });
    const yd = (P.yields_daily || []).slice(-520);
    plot('#ch-yields', [
      { x: yd.map(r => r.date), y: yd.map(r => r['2Y']), name: '2Y', line: { color: C.oLight, width: 1.5 } },
      { x: yd.map(r => r.date), y: yd.map(r => r['10Y']), name: '10Y', line: { color: C.oMid, width: 2 } },
      { x: yd.map(r => r.date), y: yd.map(r => r['30Y']), name: '30Y', line: { color: C.oDark, width: 1.5 } },
      { x: yd.map(r => r.date), y: yd.map(r => r.spread_10y2y), name: '10Y−2Y', yaxis: 'y2', line: { color: INK, width: 1.2, dash: 'dot' } }],
      { yaxis: { gridcolor: LINE, ticksuffix: '%' }, yaxis2: { overlaying: 'y', side: 'right', showgrid: false, ticksuffix: 'pp' }, margin: { l: 52, r: 48, t: 8, b: 40 } });
    const jpy = (P.macro_daily || {})['JPY=X'] || (P.macro_intraday || {})['JPY=X'] || [], dxy = (P.macro_daily || {})['DX-Y.NYB'] || (P.macro_intraday || {})['DX-Y.NYB'] || [];
    const fredj = (P.fred || {}).DEXJPUS || [];
    plot('#ch-fx', [
      { x: jpy.map(p => p[0]), y: jpy.map(p => p[1]), name: 'USD/JPY (Yahoo)', line: { color: C.oMid, width: 2 } },
      { x: fredj.map(p => p[0]), y: fredj.map(p => p[1]), name: 'USD/JPY (FRED, weekly release)', line: { color: C.grey, width: 1, dash: 'dot' } },
      { x: dxy.map(p => p[0]), y: dxy.map(p => p[1]), name: 'DXY', yaxis: 'y2', line: { color: INK, width: 1.5 } }],
      { yaxis2: { overlaying: 'y', side: 'right', showgrid: false }, margin: { l: 52, r: 48, t: 8, b: 40 } });
  }

  // ---------------------------------------------------------------- options
  let curExp = null;
  function options() {
    const O = D.options || {}; const exps = Object.keys(O.expirations || {}).sort();
    const sel = $('#exp-select'); sel.innerHTML = exps.map(e => `<option value="${e}">${e} (${O.expirations[e].dte}d · n=${O.expirations[e].n})</option>`).join('');
    if (!exps.length) { ['#ch-oi', '#ch-vol', '#ch-pain', '#ch-gex', '#ch-smile'].forEach(id => empty(id)); empty('#tbl-maxpain'); }
    const live = exps.filter(e => O.expirations[e].dte > 0);
    curExp = curExp && exps.includes(curExp) ? curExp : (live[0] || exps[0] || null);
    if (curExp) sel.value = curExp;
    sel.onchange = () => { curExp = sel.value; expiry(); smile(); };
    $('#opt-meta').textContent = O.snapshot_ts ? `snapshot ${dstr(O.snapshot_ts)} · spot ${fmt(O.spot)} · OI as of ${O.oi_date || '—'}` : '';
    expiry(); maxpainTable(); history(); flows();
  }
  function expiry() {
    const O = D.options || {}; const E = (O.expirations || {})[curExp]; if (!E) return;
    const s = E.strikes || []; const K = s.map(r => r.strike);
    const shapes = [vline(O.spot, C.grey, 'solid'), E.max_pain != null ? vline(E.max_pain, C.oMid, 'dash') : null].filter(Boolean);
    const ann = [{ x: O.spot, y: 1.02, yref: 'paper', text: `spot ${fmt(O.spot)}`, showarrow: false, font: { color: MUTED, size: 11 } },
      E.max_pain != null ? { x: E.max_pain, y: 1.08, yref: 'paper', text: `max pain ${fmt(E.max_pain)}`, showarrow: false, font: { color: C.oMid, size: 11 } } : null].filter(Boolean);
    plot('#ch-oi', [
      { x: K, y: s.map(r => r.call_oi), name: 'calls OI', type: 'bar', marker: { color: C.oMid } },
      { x: K, y: s.map(r => -(r.put_oi || 0)), name: 'puts OI', type: 'bar', marker: { color: INK }, customdata: s.map(r => r.put_oi), hovertemplate: '%{customdata:,}<extra>puts</extra>' }],
      { barmode: 'relative', shapes, annotations: ann, yaxis: { gridcolor: LINE, tickformat: ',' }, margin: { l: 60, r: 16, t: 28, b: 40 } });
    plot('#ch-vol', [
      { x: K, y: s.map(r => r.call_vol), name: 'calls vol', type: 'bar', marker: { color: C.oLight } },
      { x: K, y: s.map(r => -(r.put_vol || 0)), name: 'puts vol', type: 'bar', marker: { color: C.grey }, customdata: s.map(r => r.put_vol), hovertemplate: '%{customdata:,}<extra>puts</extra>' }],
      { barmode: 'relative', shapes, yaxis: { gridcolor: LINE, tickformat: ',' }, margin: { l: 60, r: 16, t: 28, b: 40 } });
    plot('#ch-pain', [
      { x: K, y: s.map(r => r.call_pain), name: 'call payout', stackgroup: 'p', line: { color: C.oLight, width: 0 } },
      { x: K, y: s.map(r => r.put_pain), name: 'put payout', stackgroup: 'p', line: { color: C.grey, width: 0 } },
      { x: K, y: s.map(r => r.pain), name: 'total', line: { color: INK, width: 2 } }],
      { shapes, yaxis: { gridcolor: LINE, tickformat: ',.0f', title: 'OI × intrinsic' }, margin: { l: 70, r: 16, t: 28, b: 40 } });
    const gs = s.filter(r => r.net_gex != null);
    plot('#ch-gex', [{ x: gs.map(r => r.strike), y: gs.map(r => r.net_gex), type: 'bar', name: 'net GEX', marker: { color: gs.map(r => r.net_gex >= 0 ? C.oMid : INK) } }],
      { shapes: [vline(O.spot, C.grey, 'solid'), E.zero_gamma != null ? vline(E.zero_gamma, C.oDark, 'dash') : null].filter(Boolean),
        annotations: E.zero_gamma != null ? [{ x: E.zero_gamma, y: 1.04, yref: 'paper', text: `zero-gamma ${fmt(E.zero_gamma, 1)}`, showarrow: false, font: { color: C.oDark, size: 11 } }] : [],
        yaxis: { gridcolor: LINE, tickformat: '~s' }, margin: { l: 60, r: 16, t: 28, b: 40 } });
  }
  function maxpainTable() {
    const O = D.options || {}; const rows = O.maxpain || []; if (!rows.length) return empty('#tbl-maxpain');
    const isMonthly = (e) => { const d = new Date(e + 'T12:00:00'); return d.getDay() === 5 && d.getDate() >= 15 && d.getDate() <= 21; };
    const front = rows.find(r => r.dte > 0)?.expiration;
    const h = ['Expiration', 'DTE', 'Max pain', 'vs spot', 'Call wall', 'Put wall', 'Call OI', 'Put OI', 'P/C OI', 'Call vol', 'Put vol', 'P/C vol', 'n'];
    const body = rows.map(r => `<tr class="${r.expiration === front ? 'front' : ''} ${isMonthly(r.expiration) ? 'monthly' : ''}"><td>${r.expiration}${isMonthly(r.expiration) ? ' <span class="muted">monthly</span>' : ''}</td>
      <td class="num">${r.dte}</td><td class="num">${fmt(r.max_pain)}</td><td class="num">${pct(r.max_pain_vs_spot_pct)}</td><td class="num">${fmt(r.call_wall, 1)}</td><td class="num">${fmt(r.put_wall, 1)}</td>
      <td class="num">${fmt0(r.call_oi)}</td><td class="num">${fmt0(r.put_oi)}</td><td class="num">${fmt(r.pc_oi)}</td><td class="num">${fmt0(r.call_vol)}</td><td class="num">${fmt0(r.put_vol)}</td><td class="num">${fmt(r.pc_vol)}</td><td class="num">${r.n_contracts}</td></tr>`).join('');
    $('#tbl-maxpain').innerHTML = `<table><thead><tr>${h.map((x, i) => `<th class="${i ? 'num' : ''}">${x}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
  }
  function history() {
    const H = (D.options || {}).history || [];
    plot('#ch-mp-hist', [
      { x: H.map(r => r.ts), y: H.map(r => r.spot), name: 'spot', line: { color: INK, width: 1.5 } },
      { x: H.map(r => r.ts), y: H.map(r => r.front_max_pain), name: 'front max pain', line: { color: C.oMid, width: 2, shape: 'hv' } },
      { x: H.map(r => r.ts), y: H.map(r => r.monthly_max_pain), name: 'monthly max pain', line: { color: C.oLight, width: 1.5, shape: 'hv', dash: 'dot' } },
      { x: H.map(r => r.ts), y: H.map(r => r.zero_gamma), name: 'zero-gamma', line: { color: C.grey, width: 1, dash: 'dash' } }], { yaxis: { gridcolor: LINE, tickprefix: '$' } });
    plot('#ch-pc-hist', [
      { x: H.map(r => r.ts), y: H.map(r => r.pc_oi), name: 'P/C open interest', line: { color: INK, width: 1.5 } },
      { x: H.map(r => r.ts), y: H.map(r => r.pc_vol), name: 'P/C day volume', line: { color: C.oMid, width: 1.5 } }], { yaxis: { gridcolor: LINE } });
  }
  function flows() {
    const O = D.options || {}; const F = O.finra || [];
    plot('#ch-finra', [
      { x: F.map(r => r.date), y: F.map(r => r.short_share * 100), name: 'short share %', type: 'bar', marker: { color: C.oMid } },
      { x: F.map(r => r.date), y: F.map(r => r.total_volume), name: 'off-exchange volume', yaxis: 'y2', line: { color: INK, width: 1.5 } }],
      { yaxis: { gridcolor: LINE, ticksuffix: '%', range: [0, 100] }, yaxis2: { overlaying: 'y', side: 'right', showgrid: false, tickformat: '~s' }, margin: { l: 52, r: 48, t: 8, b: 40 } });
    const X = O.occ_by_exchange || [];
    plot('#ch-occ', [
      { x: X.map(r => r.exchange), y: X.map(r => r.call), name: 'calls', type: 'bar', marker: { color: C.oMid } },
      { x: X.map(r => r.exchange), y: X.map(r => r.put), name: 'puts', type: 'bar', marker: { color: INK } }], { barmode: 'stack', yaxis: { gridcolor: LINE, tickformat: ',' } });
  }

  // ---------------------------------------------------------------- IV
  function iv() {
    const V = D.iv || {}; const T = V.term || [], S = V.skew || [];
    plot('#ch-term', [{ x: T.map(r => r.dte), y: T.map(r => r.atm_iv * 100), text: T.map(r => `${r.expiration} · K=${r.atm_strike}`), mode: 'lines+markers+text', textposition: 'top center',
      texttemplate: '%{y:.0f}%', name: 'ATM IV', line: { color: C.oMid, width: 2 }, marker: { color: INK, size: 7 }, hovertemplate: '%{text}<br>%{y:.1f}%<extra></extra>' }],
      { xaxis: { gridcolor: LINE, title: 'days to expiration', zeroline: false }, yaxis: { gridcolor: LINE, ticksuffix: '%' }, hovermode: 'closest' });
    plot('#ch-skew', [{ x: S.map(r => r.expiration), y: S.map(r => r.skew25 * 100), type: 'bar', name: '25Δ skew', marker: { color: S.map(r => r.skew25 >= 0 ? C.oMid : INK) },
      text: S.map(r => `${(r.skew25 * 100).toFixed(1)}pp`), textposition: 'outside', hovertemplate: 'put %{customdata[0]:.1f}% · call %{customdata[1]:.1f}%<extra></extra>',
      customdata: S.map(r => [r.put25_iv * 100, r.call25_iv * 100]) }], { xaxis: { type: 'category', gridcolor: LINE }, yaxis: { gridcolor: LINE, ticksuffix: 'pp' }, hovermode: 'closest' });
    const H = V.iv30_history || [];
    plot('#ch-iv30', [{ x: H.map(p => p[0]), y: H.map(p => p[1] * 100), name: 'IV30', line: { color: C.oMid, width: 2 } }], { yaxis: { gridcolor: LINE, ticksuffix: '%' } });
    const U = V.surface || {};
    if (U.z && U.z.length) {
      plot('#ch-surface', [{ z: U.z.map(r => r.map(v => v == null ? null : v * 100)), x: U.buckets, y: U.expirations, type: 'heatmap', colorscale: [[0, dark ? '#2a1a12' : C.oPale], [1, C.oDark]],
        colorbar: { ticksuffix: '%', thickness: 12 }, hovertemplate: 'K/S %{x}<br>%{y}<br>IV %{z:.1f}%<extra></extra>', hoverongaps: false }],
        { xaxis: { title: 'moneyness K/S', type: 'category' }, yaxis: { type: 'category', autorange: 'reversed' }, hovermode: 'closest', margin: { l: 90, r: 16, t: 8, b: 48 } });
    } else empty('#ch-surface');
    smile();
  }
  function smile() {
    const O = D.options || {}; const E = (O.expirations || {})[curExp]; if (!E) return empty('#ch-smile');
    const s = (E.strikes || []).filter(r => r.call_iv != null || r.put_iv != null);
    plot('#ch-smile', [
      { x: s.map(r => r.strike), y: s.map(r => r.call_iv == null ? null : r.call_iv * 100), name: 'calls', mode: 'lines+markers', line: { color: C.oMid }, marker: { size: 5 }, connectgaps: true },
      { x: s.map(r => r.strike), y: s.map(r => r.put_iv == null ? null : r.put_iv * 100), name: 'puts', mode: 'lines+markers', line: { color: INK }, marker: { size: 5 }, connectgaps: true }],
      { shapes: [vline(O.spot, C.grey, 'solid')], yaxis: { gridcolor: LINE, ticksuffix: '%' }, xaxis: { gridcolor: LINE, title: `strike · ${curExp}` } });
  }

  // ---------------------------------------------------------------- Reddit
  let flair = 'Due Diligence', sub = 'All';
  const flairMatch = (f, g) => g === 'Due Diligence' ? /due diligence|\bDD\b/i.test(f || '') : (f || '').toLowerCase().includes(g.toLowerCase());
  function reddit() {
    const R = D.reddit || {}; const posts = R.posts || [];
    const groups = ['All', 'Due Diligence', 'Data', 'News', 'Discussion', 'Technical Analysis', 'Speculation', 'Education'];
    const subs = ['All', ...new Set(posts.map(p => p.subreddit).filter(Boolean))];
    const sc = $('#sub-chips'); sc.innerHTML = subs.map(g => `<span class="chip ${g === sub ? 'active' : ''}" data-s="${esc(g)}">${g === 'All' ? 'All subreddits' : 'r/' + esc(g)}</span>`).join('');
    sc.querySelectorAll('.chip').forEach(c => c.onclick = () => { sub = c.dataset.s; reddit(); });
    const chips = $('#flair-chips'); chips.innerHTML = groups.map(g => `<span class="chip ${g === flair ? 'active' : ''}" data-f="${g}">${g}</span>`).join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { flair = c.dataset.f; reddit(); });
    $('#post-search').oninput = render;
    function render() {
      const qs = ($('#post-search').value || '').toLowerCase();
      const rows = posts.filter(p => (sub === 'All' || p.subreddit === sub) && (flair === 'All' || flairMatch(p.flair, flair)) && (!qs || (p.title || '').toLowerCase().includes(qs)));
      if (!rows.length) return empty('#posts', posts.length ? 'no posts match' : 'no posts yet — run `moonape collect reddit`');
      $('#posts').innerHTML = rows.slice(0, 150).map(p => `<div class="post"><div class="t"><a href="${esc(p.permalink)}" target="_blank" rel="noopener">${esc(p.title)}</a></div>
        <div class="m"><span class="muted">r/${esc(p.subreddit || 'Superstonk')}</span><span class="flair ${/due diligence|\bDD\b/i.test(p.flair || '') ? 'dd' : ''}">${esc(p.flair || '—')}</span><span>▲ ${fmt0(p.score)}</span><span>💬 ${fmt0(p.num_comments)}</span>
        <span>u/${esc(p.author)}</span><span>${ago(p.created_utc)}</span>${p.url && !/reddit\.com/.test(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">link ↗</a>` : ''}<span class="muted">${esc(p.source)}</span></div>
        ${p.preview ? `<div class="p">${esc(p.preview)}${p.selftext_len > 320 ? '…' : ''}</div>` : ''}</div>`).join('');
    }
    render();
  }

  // ---------------------------------------------------------------- Socials
  let acct = 'All';
  function socials() {
    const S = D.socials || {}; const posts = S.posts || []; const conf = S.configured || [];
    const chips = $('#acct-chips');
    chips.innerHTML = [`<span class="chip ${acct === 'All' ? 'active' : ''}" data-a="All">All</span>`, ...conf.map(c =>
      `<span class="chip ${acct === c.account ? 'active' : ''}" data-a="${esc(c.account)}">${esc(c.account_name)}</span>`)].join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { acct = c.dataset.a; socials(); });
    const counts = (S.accounts || []).reduce((m, a) => { m[a.account] = a; return m; }, {});
    $('#social-meta').textContent = S.x_enabled ? `${posts.length} posts` : 'X accounts need TWITTERAPI_IO_KEY; Truth Social is live';
    $('#social-search').oninput = render;
    function render() {
      const qs = ($('#social-search').value || '').toLowerCase();
      const rows = posts.filter(p => (acct === 'All' || p.account === acct) && (!qs || (p.text || '').toLowerCase().includes(qs)));
      if (!rows.length) {
        const c = conf.find(x => x.account === acct);
        return empty('#social-feed', c && !counts[acct] ? `no posts collected yet for ${c.account_name} — <a href="${c.url}" target="_blank" rel="noopener">open on ${c.platform === 'x' ? 'X' : 'Truth Social'} ↗</a>` : 'no posts match');
      }
      $('#social-feed').innerHTML = rows.slice(0, 200).map(p => `<div class="post">
        <div class="avatar ${p.platform}">${esc((p.account_name || '?').slice(0, 1))}</div>
        <div><div class="who"><span class="n">${esc(p.account_name)}</span><span class="h">@${esc(p.account)}</span><span class="badge ${p.platform}">${p.platform === 'x' ? 'X' : 'Truth'}</span>
          ${p.is_repost ? '<span class="badge">repost</span>' : ''}${p.is_quote ? '<span class="badge">quote</span>' : ''}${p.is_reply ? '<span class="badge">reply</span>' : ''}
          <a class="h" href="${esc(p.url)}" target="_blank" rel="noopener" title="${esc(p.created_at)}">${ago(p.created_at)} ↗</a></div>
        <div class="body">${esc(p.text)}</div>
        ${p.quoted_text ? `<div class="quote">${esc(p.quoted_text)}${p.quoted_url ? ` <a href="${esc(p.quoted_url)}" target="_blank" rel="noopener">↗</a>` : ''}</div>` : ''}
        ${p.media_url ? `<img class="media" loading="lazy" src="${esc(p.media_url)}" alt="">` : ''}
        ${p.likes != null ? `<div class="m"><span>♥ ${fmt0(p.likes)}</span><span>↻ ${fmt0(p.reposts)}</span><span>💬 ${fmt0(p.replies)}</span>${p.views != null ? `<span>👁 ${fmt0(p.views)}</span>` : ''}</div>` : ''}
        </div></div>`).join('');
    }
    render();
  }

  // ---------------------------------------------------------------- Library
  let libFilter = 'All';
  function library() {
    const L = D.library || {}; const books = L.books || []; const curated = new Set(L.curated || []);
    const kinds = ['All', 'DD', 'Guides', 'Art & memes', 'Periodicals', 'Macro'];
    const kind = (b) => { const t = (b.title || '').toLowerCase(); if (/superstonk guide|geographic|digest|gmedd/.test(t)) return 'Periodicals'; if (/artwork|collection|meme|pixel|stonker deck|lego|saga|christmas|stonks on the moon/.test(t)) return 'Art & memes'; if (/guide|faq|dictionary|how to|step-by-step|preparation|attorneys|financial advisors|rich/.test(t)) return 'Guides'; if (/fed|dollar|inflation|repo|treasury|liquidity|stagflation|evergrande|macro|2008|bubble|loan/.test(t)) return 'Macro'; return 'DD'; };
    const chips = $('#lib-chips'); chips.innerHTML = kinds.map(k => `<span class="chip ${k === libFilter ? 'active' : ''}" data-k="${k}">${k}</span>`).join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { libFilter = c.dataset.k; library(); });
    const st = L.stats || {};
    $('#lib-meta').innerHTML = st.books ? `${fmt0(st.books)} books · ${fmt0(st.pages)} pages · text indexed for ${fmt0(st.with_text)} · <a href="${esc(L.source)}" target="_blank" rel="noopener">bookcase ↗</a>` : '';
    const card = (b) => `<div class="book"><a href="${esc(b.url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(b.cover)}" alt=""></a>
      <div class="bt"><a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.title)}</a></div>
      <div class="bm">${esc(b.description || '')}${b.description ? ' · ' : ''}${fmt0(b.pages)} pp · ${b.added}</div>
      ${b.excerpt ? `<div class="bx">${esc(b.excerpt)}</div><div class="more" data-more>more</div>` : ''}</div>`;
    $('#lib-search').oninput = render;
    function render() {
      const qs = ($('#lib-search').value || '').toLowerCase();
      const match = (b) => (libFilter === 'All' || kind(b) === libFilter) && (!qs || `${b.title} ${b.description || ''} ${b.excerpt || ''}`.toLowerCase().includes(qs));
      const shelf = books.filter(b => curated.has(b.blink) && match(b));
      $('#lib-shelf-title').style.display = shelf.length ? '' : 'none';
      $('#lib-shelf').innerHTML = shelf.map(card).join('');
      const rest = books.filter(b => !curated.has(b.blink) && match(b)).sort((x, y) => (y.added > x.added ? 1 : -1));
      $('#lib-grid').innerHTML = rest.length ? rest.map(card).join('') : (books.length ? '<div class="empty">no books match</div>' : '<div class="empty">no catalog yet — library/bookcase.json missing</div>');
      document.querySelectorAll('[data-more]').forEach(m => m.onclick = () => { const bx = m.previousElementSibling; bx.classList.toggle('open'); m.textContent = bx.classList.contains('open') ? 'less' : 'more'; });
    }
    render();
  }

  // ---------------------------------------------------------------- SEC
  let secEntity = 'All';
  function sec() {
    const S = D.sec || {}; const F = S.filings || []; const ents = ['All', ...new Set(F.map(f => f.entity))];
    const chips = $('#sec-chips'); chips.innerHTML = ents.map(e => `<span class="chip ${e === secEntity ? 'active' : ''}" data-e="${esc(e)}">${esc(e)}</span>`).join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { secEntity = c.dataset.e; sec(); });
    $('#sec-search').oninput = render;
    function render() {
      const qs = ($('#sec-search').value || '').toLowerCase();
      const rows = F.filter(f => (secEntity === 'All' || f.entity === secEntity) && (!qs || `${f.form} ${f.description || ''} ${f.items || ''}`.toLowerCase().includes(qs)));
      if (!rows.length) return empty('#filings', F.length ? 'no filings match' : 'no filings yet — run `moonape collect daily`');
      $('#filings').innerHTML = `<table><thead><tr><th>Filed</th><th>Entity</th><th>Form</th><th>Period</th><th>Description / items</th><th></th></tr></thead><tbody>${rows.slice(0, 250).map(f =>
        `<tr><td>${f.filing_date}</td><td>${esc(f.entity)}</td><td><strong>${esc(f.form)}</strong></td><td>${f.report_date || ''}</td><td>${esc(f.description || '')}${f.items ? ` <span class="muted">items ${esc(f.items)}</span>` : ''}</td>
        <td>${f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">doc</a> · ` : ''}<a href="${esc(f.index_url)}" target="_blank" rel="noopener">index</a></td></tr>`).join('')}</tbody></table>`;
    }
    render();
    const H = S.holders_13f || [];
    $('#holders').innerHTML = H.length ? `<table><thead><tr><th>Filed</th><th>Filer</th><th>CIK</th><th>Period</th><th>Form</th><th></th></tr></thead><tbody>${H.map(h =>
      `<tr><td>${h.file_date}</td><td>${esc(h.filer)}</td><td>${h.cik}</td><td>${h.period_ending || ''}</td><td>${h.form}</td><td><a href="${esc(h.url)}" target="_blank" rel="noopener">filing</a></td></tr>`).join('')}</tbody></table>
      <p class="muted">${fmt0(H[0]?.total_hits)} matching filings in the search window; showing the newest ${H.length}. Holding sizes need the information-table XML (follow-up).</p>` : '<div class="empty">no 13F search yet</div>';
  }

  // ---------------------------------------------------------------- About
  function about() {
    const m = D.meta || {}; const ds = m.datasets || {};
    const rows = Object.entries(ds).map(([k, v]) => `<tr><td>${k}</td><td class="num">${fmt0(v.rows)}</td><td>${v.latest_fetch ? `${dstr(v.latest_fetch)} (${ago(v.latest_fetch)})` : '—'}</td><td class="num">${v.mb}</td></tr>`).join('');
    $('#about').innerHTML = `
      <p><strong>moonape</strong> collects public data about GME on a schedule (GitHub Actions) and renders it here. Built ${dstr(m.built_at)}${m.fixture ? ' from <strong>fixture data</strong> (synthetic Alpaca chain + recorded keyless sources)' : ''}.</p>
      <h3>How to read it</h3>
      <ul>
        <li><strong>Max pain</strong> is the strike where option holders in aggregate would be paid the least at expiration (sum of open interest × intrinsic value). Open interest is published once a day by OCC, so the OI leg moves daily and the chart moves intraday only through price and volume.</li>
        <li><strong>Walls</strong> are the strikes with the largest call and put open interest for that expiration.</li>
        <li><strong>IV30</strong> interpolates ATM implied volatility to a constant 30 days in variance. <strong>IV rank</strong> is where today sits between the trailing-year min and max; <strong>percentile</strong> is the share of days below today. Both need history and start meaningful after a few weeks.</li>
        <li><strong>GEX</strong> uses the dealer convention (long calls, short puts), $ per 1% move; zero-gamma is where per-strike net GEX turns positive. A convention, not a measurement.</li>
        <li><strong>Options feed</strong>: ${esc(m.feeds?.options || 'indicative')} (free plan: derived quotes, trades 15-min delayed). Stocks: ${esc(m.feeds?.stocks || 'iex')}.</li>
        <li><strong>Yields</strong>: US Treasury daily par curve (same-day close) with FRED history; intraday yields and USD/JPY from Yahoo. <strong>BOJ</strong> rate is a dated constant (${m.boj?.rate}% since ${m.boj?.asof}).</li>
        <li><strong>FINRA short volume</strong> covers off-exchange (TRF/ADF) prints only, regular hours. <strong>OCC</strong> volume is per exchange and account type (customer / market-maker / firm).</li>
      </ul>
      <h3>Datasets</h3>
      <div class="tablewrap"><table><thead><tr><th>dataset</th><th class="num">rows</th><th>latest fetch</th><th class="num">MB</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="muted">Raw parquet lives in <code>data/</code> of the repo; query it with DuckDB: <code>moonape db --sql "select … from option_chain"</code>.</p>`;
  }

  load().then(() => { status(); tiles(); overview(); options(); iv(); reddit(); socials(); sec(); library(); about(); });
})();
