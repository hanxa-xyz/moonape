/* moonape dashboard — Coinbase layout, Robinhood chart aesthetics. Reads site/data/*.json; renders with Plotly 3. */
(() => {
  // ------------------------------------------------------------ theme + tokens
  const root = document.documentElement;
  const stored = (() => { try { return localStorage.getItem('moonape-theme'); } catch (e) { return null; } })();
  if (stored) root.dataset.theme = stored;
  const isDark = () => root.dataset.theme === 'dark' || (!root.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  const T = () => ({ fg: css('--fg'), fg2: css('--fg2'), muted: css('--muted'), line: css('--line'), line2: css('--line2'), card: css('--card'),
    accent: css('--accent'), up: css('--up'), down: css('--down'), s2: css('--series2'), dark: isDark() });

  const $ = (s) => document.querySelector(s);
  const fmt = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
  const fmt0 = (v) => (v == null) ? '—' : Number(v).toLocaleString();
  const money = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : '$' + fmt(v, d);
  const compact = (v) => (v == null || Number.isNaN(v)) ? '—' : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : fmt(v, 0);
  const pct = (v, d = 2) => (v == null || Number.isNaN(v)) ? '—' : `${v >= 0 ? '+' : ''}${Number(v).toFixed(d)}%`;
  const ago = (iso) => { if (!iso) return '—'; const m = (Date.now() - new Date(iso)) / 60000; if (m < 1) return 'now'; if (m < 60) return `${Math.round(m)}m ago`; if (m < 2880) return `${Math.round(m / 60)}h ago`; return `${Math.round(m / 1440)}d ago`; };
  const dstr = (iso) => iso ? new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  // intraday points are rendered on the New York clock (market time), as naive strings Plotly keeps as given
  const etFmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  const toET = (iso) => { const p = Object.fromEntries(etFmt.formatToParts(new Date(iso)).map(x => [x.type, x.value])); return `${p.year}-${p.month}-${p.day} ${p.hour === '24' ? '00' : p.hour}:${p.minute}`; };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const empty = (id, msg = 'No data yet') => { const el = $(id); if (el) el.innerHTML = `<div class="empty">${msg}</div>`; };

  // ------------------------------------------------------------ plotly helpers (Robinhood: no grid, no axis lines, thin marks)
  const CFG = { displayModeBar: false, responsive: true };
  const base = (extra = {}) => {
    const t = T();
    return Object.assign({
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { family: 'Inter, system-ui, sans-serif', color: t.fg2, size: 12 },
      margin: { l: 44, r: 12, t: 10, b: 36 },
      xaxis: { showgrid: false, zeroline: false, showline: false, tickfont: { size: 11, color: t.muted }, ticks: '' },
      yaxis: { showgrid: false, zeroline: false, showline: false, tickfont: { size: 11, color: t.muted }, ticks: '' },
      legend: { orientation: 'h', y: 1.14, x: 0, font: { size: 11, color: t.fg2 }, bgcolor: 'rgba(0,0,0,0)' },
      hovermode: 'x unified',
      hoverlabel: { bgcolor: t.card, bordercolor: t.line2, font: { family: 'Inter, system-ui, sans-serif', size: 12, color: t.fg } },
    }, extra);
  };
  const plot = (id, traces, layout) => { const el = $(id); if (!el) return; if (!traces.length || traces.every(tr => !((tr.x || tr.z || [])).length)) return empty(id); el.innerHTML = ''; Plotly.newPlot(el, traces, Object.assign(base(), layout || {}), CFG); };
  const vline = (x, color, dash = 'dash') => ({ type: 'line', x0: x, x1: x, y0: 0, y1: 1, yref: 'paper', line: { color, width: 1, dash } });
  const hline = (y, color, dash = 'dash') => ({ type: 'line', x0: 0, x1: 1, xref: 'paper', y0: y, y1: y, line: { color, width: 1, dash } });
  const note = (x, text, color, y = 1.04) => ({ x, y, yref: 'paper', text, showarrow: false, font: { color, size: 11, family: 'Inter, system-ui, sans-serif' }, xanchor: 'left', xshift: 4 });

  /** Robinhood-style single-series line: color by polarity, hidden y axis, crosshair, optional dashed baseline. */
  function rhLine(id, pts, { baseline = null, hoverFmt = null, intraday = false } = {}) {
    const el = $(id); if (!el) return;
    if (!pts || pts.length < 2) return empty(id, 'Not enough points yet');
    const t = T(); const first = baseline ?? pts[0][1], last = pts[pts.length - 1][1];
    const color = last >= first ? t.up : t.down;
    const ys = pts.map(p => p[1]); const lo = Math.min(...ys, first), hi = Math.max(...ys, first), pad = (hi - lo || 1) * 0.08;
    const shapes = baseline != null ? [hline(baseline, t.line2, 'dot')] : [];
    el.innerHTML = '';
    Plotly.newPlot(el, [{ x: pts.map(p => p[0]), y: ys, mode: 'lines', line: { color, width: 2, shape: 'linear' },
      hovertemplate: (hoverFmt ? hoverFmt : '%{y:,.2f}') + '<extra></extra>' }],
      base({ margin: { l: 4, r: 4, t: 6, b: 24 }, showlegend: false, hovermode: 'x',
        xaxis: { showgrid: false, zeroline: false, showline: false, tickfont: { size: 11, color: t.muted }, nticks: 6, showspikes: true, spikemode: 'across', spikesnap: 'cursor', spikecolor: t.line2, spikethickness: 1, spikedash: 'solid', tickformat: intraday === '1D' ? '%H:%M' : intraday ? '%b %d' : undefined, hoverformat: intraday ? '%b %d, %H:%M ET' : '%b %d, %Y' },
        yaxis: { visible: false, range: [lo - pad, hi + pad], fixedrange: true }, shapes,
        hoverlabel: { bgcolor: t.card, bordercolor: t.line2, font: { size: 13, color: t.fg, family: 'Inter, system-ui, sans-serif' } } }), CFG);
    return color === t.up;
  }

  /** inline SVG sparkline for watchlist rows */
  function spark(pts, up) {
    if (!pts || pts.length < 2) return '<svg viewBox="0 0 110 34"></svg>';
    const ys = pts.map(p => p[1]); const lo = Math.min(...ys), hi = Math.max(...ys); const r = hi - lo || 1;
    const d = pts.map((p, i) => `${(i / (pts.length - 1) * 108 + 1).toFixed(1)},${(32 - (p[1] - lo) / r * 28 - 2).toFixed(1)}`).join(' ');
    return `<svg viewBox="0 0 110 34" aria-hidden="true"><polyline fill="none" stroke="${up ? 'var(--up)' : 'var(--down)'}" stroke-width="1.75" stroke-linejoin="round" stroke-linecap="round" points="${d}"/></svg>`;
  }

  // ------------------------------------------------------------ data
  const D = {};
  async function load() {
    const names = ['meta', 'tiles', 'price_macro', 'options', 'iv', 'reddit', 'sec', 'socials', 'library'];
    await Promise.all(names.map(async (n) => { try { const r = await fetch(`data/${n}.json?v=${Date.now() >> 16}`); D[n] = r.ok ? await r.json() : null; } catch (e) { D[n] = null; } }));
  }

  // ------------------------------------------------------------ nav + theme
  document.querySelectorAll('.nav button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('.nav button').forEach((x) => x.classList.toggle('active', x === b));
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.id === `tab-${b.dataset.tab}`));
    try { history.replaceState(null, '', `#${b.dataset.tab}`); } catch (e) { location.hash = b.dataset.tab; } window.dispatchEvent(new Event('resize'));
  }));
  const hashTab = () => { const b = document.querySelector(`.nav button[data-tab="${(location.hash || '#home').slice(1)}"]`); if (b) b.click(); };
  $('#theme-toggle').onclick = () => { root.dataset.theme = isDark() ? 'light' : 'dark'; try { localStorage.setItem('moonape-theme', root.dataset.theme); } catch (e) {} renderAll(); };

  // ------------------------------------------------------------ status
  function status() {
    const m = D.meta; if (!m) { $('#status').innerHTML = '<span class="dot"></span>no data'; return; }
    const t = m.datasets?.option_chain?.latest_fetch; const minutes = t ? (Date.now() - new Date(t)) / 60000 : Infinity;
    const cls = minutes < (m.stale_after?.intraday_min || 45) ? 'fresh' : 'stale';
    $('#status').innerHTML = `<span class="dot ${cls}"></span>chain ${t ? ago(t) : 'never'}`;
    document.querySelectorAll('.banner').forEach(b => b.remove());
    if (m.fixture) { const b = document.createElement('div'); b.className = 'banner'; b.textContent = 'Synthetic fixture data — collectors have not run with real keys.'; $('.main').prepend(b); }
  }

  // ------------------------------------------------------------ home: hero
  let heroRange = '1D';
  function heroSeries(range) {
    const P = D.price_macro || {}; const g = (D.tiles?.stocks || {}).GME || {};
    const daily = (P.daily || {}).GME || []; const b15 = (P.bars15 || {}).GME || [];
    const dayOf = (iso) => new Date(iso).toLocaleDateString('en-US', { timeZone: 'America/New_York' });
    const regular = (p) => { const hm = toET(p[0]).slice(11); return hm >= '09:30' && hm < '16:00'; };  // regular session only, like the 1D view people expect
    if (range === '1D') {
      const last = b15.length ? dayOf(b15[b15.length - 1][0]) : null;
      const pts = b15.filter(p => dayOf(p[0]) === last && regular(p)).map(p => [toET(p[0]), p[1]]);
      return { pts, baseline: g.prev_close ?? null, label: 'Today', intraday: '1D' };
    }
    if (range === '1W') { const days = [...new Set(b15.map(p => dayOf(p[0])))].slice(-5); return { pts: b15.filter(p => days.includes(dayOf(p[0])) && regular(p)).map(p => [toET(p[0]), p[1]]), baseline: null, label: 'Past week', intraday: '1W' }; }
    const n = { '1M': 21, '3M': 63, '1Y': 252, 'ALL': Infinity }[range];
    const pts = (n === Infinity ? daily : daily.slice(-n)).map(p => [p[0], p[1]]);
    return { pts, baseline: null, label: { '1M': 'Past month', '3M': 'Past 3 months', '1Y': 'Past year', 'ALL': 'All time' }[range] };
  }
  function hero() {
    const g = (D.tiles?.stocks || {}).GME || {};
    const { pts, baseline, label, intraday } = heroSeries(heroRange);
    const last = g.price ?? (pts.length ? pts[pts.length - 1][1] : null);
    const first = baseline ?? (pts.length ? pts[0][1] : null);
    $('#hero-price').textContent = money(last);
    const d = (last != null && first != null) ? last - first : null;
    const up = d == null ? true : d >= 0;
    $('#hero-delta').className = `delta ${d == null ? '' : up ? 'up' : 'down'}`;
    $('#hero-delta').innerHTML = d == null ? '' : `${d >= 0 ? '+' : '−'}${money(Math.abs(d))} (${pct(d / first * 100)}) <span class="period">${label}</span>`;
    $('#hero-asof').textContent = g.ts ? `Last trade ${dstr(g.ts)} · ${(g.feed || 'iex').toUpperCase()}` : '';
    const pills = $('#hero-ranges'); pills.className = `pills ${up ? 'up' : 'down'}`;
    pills.querySelectorAll('button').forEach(b => { b.classList.toggle('active', b.dataset.r === heroRange); b.onclick = () => { heroRange = b.dataset.r; hero(); }; });
    rhLine('#hero-chart', pts, { baseline, intraday });
  }

  // ------------------------------------------------------------ home: stats, watchlist, macro, latest
  function stat(k, v, s, cls = '') { return `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div><div class="s ${cls}">${s || ''}</div></div>`; }
  function stats() {
    const O = D.tiles?.options || {}; const out = [];
    const vs = (mp) => (mp != null && O.spot) ? `${pct((mp / O.spot - 1) * 100, 1)} vs spot` : '';
    out.push(stat(`Max pain · ${O.front_expiry || 'front'}`, money(O.front_max_pain), O.front_dte != null ? `${O.front_dte}d · ${vs(O.front_max_pain)}` : ''));
    out.push(stat(`Monthly · ${O.monthly_expiry || ''}`, money(O.monthly_max_pain), vs(O.monthly_max_pain)));
    out.push(stat('Walls (front)', `${money(O.front_call_wall, 0)} / ${money(O.front_put_wall, 0)}`, 'call / put, largest OI'));
    out.push(stat('IV30', O.iv30 != null ? `${(O.iv30 * 100).toFixed(1)}%` : '—', O.iv_rank != null ? `rank ${fmt(O.iv_rank, 0)} · pctile ${fmt(O.iv_pct, 0)}` : `rank needs ${Math.max(0, 5 - (O.iv_history_days || 0))} more days`));
    out.push(stat('Put/call', `${fmt(O.pc_oi)} <span class="muted">OI</span>`, `${fmt(O.pc_vol)} by volume`));
    out.push(stat('Net GEX', O.net_gex != null ? `${(O.net_gex / 1e6).toFixed(1)}M` : '—', O.zero_gamma != null ? `zero-gamma ≈ ${money(O.zero_gamma, 1)}` : '$ per 1% move'));
    out.push(stat('Contracts', fmt0(O.n_contracts), O.oi_date ? `OI as of ${O.oi_date}` : ''));
    $('#stats').innerHTML = out.join('');
  }
  function watchlist() {
    const P = D.price_macro || {}; const S = D.tiles?.stocks || {}; const Y = D.tiles?.yields || {}; const M = D.tiles?.macro || {}; const boj = D.tiles?.boj;
    const yd = P.yields_daily || []; const yser = (k) => yd.filter(r => r[k] != null).map(r => [r.date, r[k]]);
    const spyD = ((P.daily || {}).SPY || []).map(p => [p[0], p[1]]);
    const jpy = (P.macro_daily || {})['JPY=X'] || [];
    const rows = [
      { nm: 'SPY', sub: 'S&P 500 ETF', pts: spyD, val: S.SPY?.price, chg: S.SPY?.change_pct, f: (v) => money(v) },
      { nm: '10Y', sub: 'US Treasury par yield', pts: yser('10Y'), val: Y['10Y'], f: (v) => fmt(v) + '%', abs: true },
      { nm: '2Y', sub: 'US Treasury par yield', pts: yser('2Y'), val: Y['2Y'], f: (v) => fmt(v) + '%', abs: true },
      { nm: '30Y', sub: 'US Treasury par yield', pts: yser('30Y'), val: Y['30Y'], f: (v) => fmt(v) + '%', abs: true },
      { nm: '10Y − 2Y', sub: 'Curve spread', pts: yser('spread_10y2y'), val: Y.spread_10y2y, f: (v) => fmt(v) + ' pp', abs: true },
      { nm: 'USD/JPY', sub: 'ECB reference rate', pts: jpy, val: M['JPY=X']?.value ?? (jpy.length ? jpy[jpy.length - 1][1] : null), f: (v) => fmt(v) },
      { nm: 'BOJ policy rate', sub: boj ? `since ${boj.asof}` : '', pts: [], val: boj?.rate, f: (v) => fmt(v) + '%', fixed: true },
    ];
    $('#watchlist').innerHTML = rows.map(r => {
      const last30 = r.pts.slice(-30);
      let chg = r.chg, abs = null;
      if (chg == null && last30.length > 1) { const a = last30[0][1], b = last30[last30.length - 1][1]; abs = b - a; chg = r.abs ? null : (b / a - 1) * 100; }
      const up = (chg ?? abs ?? 0) >= 0;
      const badge = r.fixed ? '<span class="badge flat">fixed</span>' : chg != null ? `<span class="badge ${up ? 'up' : 'down'}">${pct(chg)}</span>` : abs != null ? `<span class="badge ${up ? 'up' : 'down'}">${abs >= 0 ? '+' : ''}${fmt(abs)}</span>` : '<span class="badge flat">—</span>';
      const sub = r.chg == null && last30.length > 1 && !r.fixed ? `${r.sub} · 30d` : r.sub;
      return `<div class="wrow"><div><div class="nm">${r.nm}</div><div class="sub">${esc(sub)}</div></div>${spark(last30, up)}<div class="val">${r.f(r.val)}</div>${badge}</div>`;
    }).join('');
  }
  let macroKey = '10Y', macroRange = '1Y';
  function macro() {
    const P = D.price_macro || {}; const yd = P.yields_daily || [];
    const series = {
      '10Y': { title: '10-year Treasury yield', pts: yd.filter(r => r['10Y'] != null).map(r => [r.date, r['10Y']]), f: (v) => fmt(v) + '%', h: '%{y:.2f}%' },
      '2Y': { title: '2-year Treasury yield', pts: yd.filter(r => r['2Y'] != null).map(r => [r.date, r['2Y']]), f: (v) => fmt(v) + '%', h: '%{y:.2f}%' },
      '30Y': { title: '30-year Treasury yield', pts: yd.filter(r => r['30Y'] != null).map(r => [r.date, r['30Y']]), f: (v) => fmt(v) + '%', h: '%{y:.2f}%' },
      'spread': { title: '10Y − 2Y spread', pts: yd.filter(r => r.spread_10y2y != null).map(r => [r.date, r.spread_10y2y]), f: (v) => fmt(v) + ' pp', h: '%{y:.2f} pp' },
      'JPY': { title: 'USD/JPY', pts: (P.macro_daily || {})['JPY=X'] || [], f: (v) => fmt(v), h: '%{y:.2f}' },
      'SPY': { title: 'SPY', pts: ((P.daily || {}).SPY || []).map(p => [p[0], p[1]]), f: (v) => money(v), h: '$%{y:,.2f}' },
    };
    const sel = $('#macro-series');
    if (!sel.options.length) { sel.innerHTML = Object.entries(series).map(([k, s]) => `<option value="${k}">${s.title}</option>`).join(''); sel.onchange = () => { macroKey = sel.value; macro(); }; }
    sel.value = macroKey;
    const s = series[macroKey]; const n = { '1M': 21, '3M': 63, '1Y': 252, 'ALL': Infinity }[macroRange];
    const pts = n === Infinity ? s.pts : s.pts.slice(-n);
    $('#macro-title').textContent = s.title;
    const last = pts.length ? pts[pts.length - 1][1] : null, first = pts.length ? pts[0][1] : null;
    $('#macro-value').textContent = last != null ? s.f(last) : '—';
    const d = (last != null && first != null) ? last - first : null; const up = d == null || d >= 0;
    $('#macro-delta').className = `delta sm ${d == null ? '' : up ? 'up' : 'down'}`;
    $('#macro-delta').innerHTML = d == null ? '' : `${d >= 0 ? '+' : '−'}${s.f(Math.abs(d)).replace('$', '$')} <span class="period">${{ '1M': 'past month', '3M': 'past 3 months', '1Y': 'past year', 'ALL': 'all time' }[macroRange]}</span>`;
    const pills = $('#macro-ranges'); pills.className = `pills small ${up ? 'up' : 'down'}`;
    pills.querySelectorAll('button').forEach(b => { b.classList.toggle('active', b.dataset.r === macroRange); b.onclick = () => { macroRange = b.dataset.r; macro(); }; });
    rhLine('#macro-chart', pts, { hoverFmt: s.h });
  }
  function latest() {
    const t = D.tiles || {}; const sec = t.sec || {}; const r = t.reddit || {}; const s = (D.socials?.posts || [])[0];
    const cards = [];
    if (sec.form) cards.push(`<div class="card"><div class="k">Latest SEC filing</div><div class="t"><span class="form">${esc(sec.form)}</span> ${esc(sec.description || '')}</div><div class="m">${esc(sec.entity)} · ${sec.filing_date} · <a href="${esc(sec.url || '#')}" target="_blank" rel="noopener">open ↗</a></div></div>`);
    if (r.title) cards.push(`<div class="card"><div class="k">Latest Due Diligence · ${fmt0(r.n_dd_7d)} this week</div><div class="t"><a href="${esc(r.permalink)}" target="_blank" rel="noopener">${esc(r.title)}</a></div><div class="m">r/Superstonk · ${ago(r.created_utc)}</div></div>`);
    if (s) cards.push(`<div class="card"><div class="k">Latest post · ${esc(s.account_name)}</div><div class="t">${esc((s.text || '').slice(0, 160))}${(s.text || '').length > 160 ? '…' : ''}</div><div class="m">${s.platform === 'x' ? 'X' : 'Truth Social'} · ${ago(s.created_at)} · <a href="${esc(s.url)}" target="_blank" rel="noopener">open ↗</a></div></div>`);
    $('#latest').innerHTML = cards.join('') || '<div class="empty">Nothing collected yet</div>';
  }

  // ------------------------------------------------------------ options
  let curExp = null;
  function options() {
    const O = D.options || {}; const exps = Object.keys(O.expirations || {}).sort();
    const sel = $('#exp-select'); sel.innerHTML = exps.map(e => `<option value="${e}">${e} · ${O.expirations[e].dte}d · ${O.expirations[e].n} contracts</option>`).join('');
    if (!exps.length) { ['#ch-oi', '#ch-vol', '#ch-pain', '#ch-gex', '#ch-smile'].forEach(id => empty(id)); empty('#tbl-maxpain'); }
    const live = exps.filter(e => O.expirations[e].dte > 0);
    curExp = curExp && exps.includes(curExp) ? curExp : (live[0] || exps[0] || null);
    if (curExp) sel.value = curExp;
    sel.onchange = () => { curExp = sel.value; expiry(); smile(); };
    $('#opt-meta').textContent = O.snapshot_ts ? `Snapshot ${dstr(O.snapshot_ts)} · spot ${money(O.spot)} · OI as of ${O.oi_date || '—'}` : '';
    expiry(); maxpainTable(); history(); flows();
  }
  function expiry() {
    const O = D.options || {}; const E = (O.expirations || {})[curExp]; if (!E) return; const t = T();
    const s = E.strikes || []; const K = s.map(r => r.strike);
    const shapes = [vline(O.spot, t.muted, 'solid'), E.max_pain != null ? vline(E.max_pain, t.accent, 'dash') : null].filter(Boolean);
    const ann = [note(O.spot, `spot ${money(O.spot)}`, t.muted, 1.0), E.max_pain != null ? note(E.max_pain, `max pain ${money(E.max_pain)}`, t.accent, 1.07) : null].filter(Boolean);
    const bar = (y, name, color, cd) => ({ x: K, y, name, type: 'bar', marker: { color, line: { width: 0 } }, customdata: cd, hovertemplate: '%{customdata:,}<extra>' + name + '</extra>' });
    plot('#ch-oi', [bar(s.map(r => r.call_oi), 'Calls', t.up, s.map(r => r.call_oi)), bar(s.map(r => -(r.put_oi || 0)), 'Puts', t.down, s.map(r => r.put_oi))],
      { barmode: 'relative', bargap: 0.25, shapes, annotations: ann, yaxis: { showgrid: false, zeroline: true, zerolinecolor: t.line2, tickformat: '~s', tickfont: { size: 11, color: t.muted } }, margin: { l: 44, r: 12, t: 26, b: 36 } });
    plot('#ch-vol', [bar(s.map(r => r.call_vol), 'Calls', t.up, s.map(r => r.call_vol)), bar(s.map(r => -(r.put_vol || 0)), 'Puts', t.down, s.map(r => r.put_vol))],
      { barmode: 'relative', bargap: 0.25, shapes, yaxis: { showgrid: false, zeroline: true, zerolinecolor: t.line2, tickformat: '~s', tickfont: { size: 11, color: t.muted } }, margin: { l: 44, r: 12, t: 26, b: 36 } });
    plot('#ch-pain', [
      { x: K, y: s.map(r => r.call_pain), name: 'Call payout', stackgroup: 'p', line: { color: t.up, width: 0 }, fillcolor: t.dark ? 'rgba(0,200,5,.25)' : 'rgba(0,200,5,.18)', hovertemplate: '%{y:,.0f}<extra>calls</extra>' },
      { x: K, y: s.map(r => r.put_pain), name: 'Put payout', stackgroup: 'p', line: { color: t.down, width: 0 }, fillcolor: t.dark ? 'rgba(255,80,0,.25)' : 'rgba(255,80,0,.18)', hovertemplate: '%{y:,.0f}<extra>puts</extra>' },
      { x: K, y: s.map(r => r.pain), name: 'Total', line: { color: t.accent, width: 2 }, hovertemplate: '%{y:,.0f}<extra>total</extra>' }],
      { shapes, yaxis: { showgrid: false, zeroline: false, tickformat: '~s', tickfont: { size: 11, color: t.muted } }, margin: { l: 48, r: 12, t: 26, b: 36 } });
    const gs = s.filter(r => r.net_gex != null);
    plot('#ch-gex', [{ x: gs.map(r => r.strike), y: gs.map(r => r.net_gex), type: 'bar', name: 'Net GEX', marker: { color: gs.map(r => r.net_gex >= 0 ? t.accent : t.s2), line: { width: 0 } }, hovertemplate: '$%{y:,.0f}<extra></extra>' }],
      { bargap: 0.25, shapes: [vline(O.spot, t.muted, 'solid'), E.zero_gamma != null ? vline(E.zero_gamma, t.s2, 'dash') : null].filter(Boolean),
        annotations: E.zero_gamma != null ? [note(E.zero_gamma, `zero-gamma ${money(E.zero_gamma, 1)}`, t.s2)] : [], showlegend: false,
        yaxis: { showgrid: false, zeroline: true, zerolinecolor: t.line2, tickformat: '~s', tickfont: { size: 11, color: t.muted } }, margin: { l: 48, r: 12, t: 26, b: 36 } });
  }
  function maxpainTable() {
    const O = D.options || {}; const rows = O.maxpain || []; if (!rows.length) return empty('#tbl-maxpain');
    const isMonthly = (e) => { const d = new Date(e + 'T12:00:00'); return d.getDay() === 5 && d.getDate() >= 15 && d.getDate() <= 21; };
    const front = rows.find(r => r.dte > 0)?.expiration;
    const h = ['Expiration', 'DTE', 'Max pain', 'vs spot', 'Call wall', 'Put wall', 'Call OI', 'Put OI', 'P/C OI', 'Call vol', 'Put vol', 'P/C vol'];
    const body = rows.map(r => `<tr class="${r.expiration === front ? 'front' : ''} ${isMonthly(r.expiration) ? 'monthly' : ''}"><td>${r.expiration}</td>
      <td class="num">${r.dte}</td><td class="num">${money(r.max_pain)}</td><td class="num ${r.max_pain_vs_spot_pct >= 0 ? 'up' : 'down'}">${pct(r.max_pain_vs_spot_pct, 1)}</td><td class="num">${money(r.call_wall, 1)}</td><td class="num">${money(r.put_wall, 1)}</td>
      <td class="num">${fmt0(r.call_oi)}</td><td class="num">${fmt0(r.put_oi)}</td><td class="num">${fmt(r.pc_oi)}</td><td class="num">${fmt0(r.call_vol)}</td><td class="num">${fmt0(r.put_vol)}</td><td class="num">${fmt(r.pc_vol)}</td></tr>`).join('');
    $('#tbl-maxpain').innerHTML = `<table><thead><tr>${h.map((x, i) => `<th class="${i ? 'num' : ''}">${x}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
  }
  function history() {
    const H = (D.options || {}).history || []; const t = T();
    plot('#ch-mp-hist', [
      { x: H.map(r => r.ts), y: H.map(r => r.spot), name: 'Spot', line: { color: t.fg, width: 2 }, hovertemplate: '$%{y:.2f}<extra>spot</extra>' },
      { x: H.map(r => r.ts), y: H.map(r => r.front_max_pain), name: 'Front max pain', line: { color: t.accent, width: 2, shape: 'hv' }, hovertemplate: '$%{y:.2f}<extra>front</extra>' },
      { x: H.map(r => r.ts), y: H.map(r => r.monthly_max_pain), name: 'Monthly max pain', line: { color: t.s2, width: 2, shape: 'hv', dash: 'dot' }, hovertemplate: '$%{y:.2f}<extra>monthly</extra>' }],
      { yaxis: { showgrid: false, zeroline: false, tickprefix: '$', tickfont: { size: 11, color: t.muted } } });
    plot('#ch-pc-hist', [
      { x: H.map(r => r.ts), y: H.map(r => r.pc_oi), name: 'P/C open interest', line: { color: t.accent, width: 2 }, hovertemplate: '%{y:.2f}<extra>OI</extra>' },
      { x: H.map(r => r.ts), y: H.map(r => r.pc_vol), name: 'P/C day volume', line: { color: t.s2, width: 2 }, hovertemplate: '%{y:.2f}<extra>volume</extra>' }]);
  }
  function flows() {
    const O = D.options || {}; const F = O.finra || []; const t = T();
    plot('#ch-finra', [{ x: F.map(r => r.date), y: F.map(r => r.short_share * 100), name: 'Short share', type: 'bar', marker: { color: t.accent, line: { width: 0 } },
      customdata: F.map(r => [r.short_volume, r.total_volume]), hovertemplate: '%{y:.1f}% short<br>%{customdata[0]:,} of %{customdata[1]:,} shares<extra></extra>' }],
      { showlegend: false, bargap: 0.3, yaxis: { showgrid: false, zeroline: false, ticksuffix: '%', range: [0, 100], tickfont: { size: 11, color: t.muted } } });
    const X = O.occ_by_exchange || [];
    plot('#ch-occ', [
      { x: X.map(r => r.exchange), y: X.map(r => r.call), name: 'Calls', type: 'bar', marker: { color: t.up, line: { width: 0 } }, hovertemplate: '%{y:,}<extra>calls</extra>' },
      { x: X.map(r => r.exchange), y: X.map(r => r.put), name: 'Puts', type: 'bar', marker: { color: t.down, line: { width: 0 } }, hovertemplate: '%{y:,}<extra>puts</extra>' }],
      { barmode: 'stack', bargap: 0.3, yaxis: { showgrid: false, zeroline: false, tickformat: '~s', tickfont: { size: 11, color: t.muted } } });
  }

  // ------------------------------------------------------------ volatility
  function iv() {
    const V = D.iv || {}; const Tm = V.term || [], S = V.skew || []; const t = T();
    // direct labels only where there is room: skip a point whose neighbour sits within ~4% of the x span
    const span = Tm.length ? (Tm[Tm.length - 1].dte - Tm[0].dte) || 1 : 1; let lastLabelled = -Infinity;
    const labels = Tm.map(r => { if (r.dte - lastLabelled < span * 0.045) return ''; lastLabelled = r.dte; return `${(r.atm_iv * 100).toFixed(0)}%`; });
    plot('#ch-term', [{ x: Tm.map(r => r.dte), y: Tm.map(r => r.atm_iv * 100), text: labels, customdata: Tm.map(r => `${r.expiration} · K ${r.atm_strike}`), mode: 'lines+markers+text', textposition: 'top center',
      textfont: { size: 10, color: t.fg2 }, name: 'ATM IV', line: { color: t.accent, width: 2 }, marker: { color: t.accent, size: 8, line: { color: t.card, width: 2 } },
      hovertemplate: '%{customdata}<br><b>%{y:.1f}%</b><extra></extra>' }],
      { xaxis: { showgrid: false, zeroline: false, title: { text: 'days to expiration', font: { size: 11, color: t.muted } }, tickfont: { size: 11, color: t.muted } },
        yaxis: { showgrid: false, zeroline: false, ticksuffix: '%', tickfont: { size: 11, color: t.muted } }, hovermode: 'closest', showlegend: false, margin: { l: 44, r: 12, t: 24, b: 44 } });
    plot('#ch-skew', [{ x: S.map(r => r.expiration), y: S.map(r => r.skew25 * 100), type: 'bar', name: '25Δ skew', marker: { color: S.map(r => r.skew25 >= 0 ? t.accent : t.s2), line: { width: 0 } },
      customdata: S.map(r => [r.put25_iv * 100, r.call25_iv * 100]), hovertemplate: '<b>%{y:.1f} pp</b><br>put %{customdata[0]:.1f}% · call %{customdata[1]:.1f}%<extra></extra>' }],
      { xaxis: { type: 'category', showgrid: false, tickfont: { size: 10, color: t.muted } }, yaxis: { showgrid: false, zeroline: true, zerolinecolor: t.line2, ticksuffix: ' pp', tickfont: { size: 11, color: t.muted } }, hovermode: 'closest', showlegend: false, bargap: 0.3 });
    const H = V.iv30_history || [];
    const upIv = rhLine('#ch-iv30', H.map(p => [p[0], p[1] * 100]), { hoverFmt: '%{y:.1f}%' });
    void upIv;
    const U = V.surface || {};
    if (U.z && U.z.length) {
      plot('#ch-surface', [{ z: U.z.map(r => r.map(v => v == null ? null : v * 100)), x: U.buckets, y: U.expirations, type: 'heatmap',
        colorscale: t.dark ? [[0, '#15213d'], [1, '#7faaff']] : [[0, '#eaf0ff'], [1, '#0a46d6']], xgap: 2, ygap: 2,
        colorbar: { ticksuffix: '%', thickness: 10, outlinewidth: 0, tickfont: { size: 10, color: t.muted } }, hovertemplate: 'K/S %{x}<br>%{y}<br><b>%{z:.1f}%</b><extra></extra>', hoverongaps: false }],
        { xaxis: { title: { text: 'moneyness K/S', font: { size: 11, color: t.muted } }, type: 'category', tickfont: { size: 10, color: t.muted } }, yaxis: { type: 'category', autorange: 'reversed', tickfont: { size: 10, color: t.muted } }, hovermode: 'closest', margin: { l: 84, r: 12, t: 8, b: 48 } });
    } else empty('#ch-surface');
    smile();
  }
  function smile() {
    const O = D.options || {}; const E = (O.expirations || {})[curExp]; if (!E) return empty('#ch-smile'); const t = T();
    $('#smile-sub').textContent = `IV by strike · ${curExp}`;
    const s = (E.strikes || []).filter(r => r.call_iv != null || r.put_iv != null);
    plot('#ch-smile', [
      { x: s.map(r => r.strike), y: s.map(r => r.call_iv == null ? null : r.call_iv * 100), name: 'Calls', mode: 'lines+markers', line: { color: t.accent, width: 2 }, marker: { size: 5 }, connectgaps: true, hovertemplate: '%{y:.1f}%<extra>calls</extra>' },
      { x: s.map(r => r.strike), y: s.map(r => r.put_iv == null ? null : r.put_iv * 100), name: 'Puts', mode: 'lines+markers', line: { color: t.s2, width: 2 }, marker: { size: 5 }, connectgaps: true, hovertemplate: '%{y:.1f}%<extra>puts</extra>' }],
      { shapes: [vline(O.spot, t.muted, 'solid')], yaxis: { showgrid: false, zeroline: false, ticksuffix: '%', tickfont: { size: 11, color: t.muted } }, xaxis: { showgrid: false, zeroline: false, tickprefix: '$', tickfont: { size: 11, color: t.muted } } });
  }

  // ------------------------------------------------------------ Reddit
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
      if (!rows.length) return empty('#posts', posts.length ? 'No posts match' : 'No posts yet');
      $('#posts').innerHTML = rows.slice(0, 150).map(p => `<div class="post"><div class="avatar reddit">${esc((p.author || '?').slice(0, 1).toUpperCase())}</div><div>
        <div class="who"><span class="n">u/${esc(p.author)}</span><span class="h">r/${esc(p.subreddit || 'Superstonk')} · ${ago(p.created_utc)}</span><span class="tag ${/due diligence|\bDD\b/i.test(p.flair || '') ? 'dd' : ''}">${esc(p.flair || '—')}</span></div>
        <div class="t"><a href="${esc(p.permalink)}" target="_blank" rel="noopener">${esc(p.title)}</a></div>
        ${p.preview ? `<div class="p">${esc(p.preview)}${p.selftext_len > 320 ? '…' : ''}</div>` : ''}
        <div class="m"><span>▲ ${fmt0(p.score)}</span><span>💬 ${fmt0(p.num_comments)}</span>${p.url && !/reddit\.com/.test(p.url) ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">link ↗</a>` : ''}</div></div></div>`).join('');
    }
    render();
  }

  // ------------------------------------------------------------ Socials
  let acct = 'All';
  function socials() {
    const S = D.socials || {}; const posts = S.posts || []; const conf = S.configured || [];
    const chips = $('#acct-chips');
    chips.innerHTML = [`<span class="chip ${acct === 'All' ? 'active' : ''}" data-a="All">All</span>`, ...conf.map(c => `<span class="chip ${acct === c.account ? 'active' : ''}" data-a="${esc(c.account)}">${esc(c.account_name)}</span>`)].join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { acct = c.dataset.a; socials(); });
    const counts = (S.accounts || []).reduce((m, a) => { m[a.account] = a; return m; }, {});
    $('#social-meta').textContent = S.x_enabled ? `${posts.length} posts` : 'X accounts need a twitterapi.io key; Truth Social is live';
    $('#social-search').oninput = render;
    function render() {
      const qs = ($('#social-search').value || '').toLowerCase();
      const rows = posts.filter(p => (acct === 'All' || p.account === acct) && (!qs || (p.text || '').toLowerCase().includes(qs)));
      if (!rows.length) {
        const c = conf.find(x => x.account === acct);
        return empty('#social-feed', c && !counts[acct] ? `No posts collected yet for ${esc(c.account_name)} — <a href="${esc(c.url)}" target="_blank" rel="noopener">open on ${c.platform === 'x' ? 'X' : 'Truth Social'} ↗</a>` : 'No posts match');
      }
      $('#social-feed').innerHTML = rows.slice(0, 200).map(p => `<div class="post"><div class="avatar ${p.platform}">${esc((p.account_name || '?').slice(0, 1))}</div><div>
        <div class="who"><span class="n">${esc(p.account_name)}</span><span class="h">@${esc(p.account)} · ${ago(p.created_at)}</span><span class="tag ${p.platform}">${p.platform === 'x' ? 'X' : 'Truth'}</span>
          ${p.is_repost ? '<span class="tag">repost</span>' : ''}${p.is_quote ? '<span class="tag">quote</span>' : ''}${p.is_reply ? '<span class="tag">reply</span>' : ''}</div>
        <div class="body">${esc(p.text)}</div>
        ${p.quoted_text ? `<div class="quote">${esc(p.quoted_text)}${p.quoted_url ? ` <a href="${esc(p.quoted_url)}" target="_blank" rel="noopener">↗</a>` : ''}</div>` : ''}
        ${p.media_url ? `<img class="media" loading="lazy" src="${esc(p.media_url)}" alt="">` : ''}
        <div class="m">${p.likes != null ? `<span>♥ ${compact(p.likes)}</span><span>↻ ${compact(p.reposts)}</span><span>💬 ${compact(p.replies)}</span>${p.views != null ? `<span>👁 ${compact(p.views)}</span>` : ''}` : ''}<a href="${esc(p.url)}" target="_blank" rel="noopener">open ↗</a></div></div></div>`).join('');
    }
    render();
  }

  // ------------------------------------------------------------ SEC
  let secEntity = 'All';
  function sec() {
    const S = D.sec || {}; const F = S.filings || []; const ents = ['All', ...new Set(F.map(f => f.entity))];
    const chips = $('#sec-chips'); chips.innerHTML = ents.map(e => `<span class="chip ${e === secEntity ? 'active' : ''}" data-e="${esc(e)}">${esc(e)}</span>`).join('');
    chips.querySelectorAll('.chip').forEach(c => c.onclick = () => { secEntity = c.dataset.e; sec(); });
    $('#sec-search').oninput = render;
    function render() {
      const qs = ($('#sec-search').value || '').toLowerCase();
      const rows = F.filter(f => (secEntity === 'All' || f.entity === secEntity) && (!qs || `${f.form} ${f.description || ''} ${f.items || ''}`.toLowerCase().includes(qs)));
      if (!rows.length) return empty('#filings', F.length ? 'No filings match' : 'No filings yet');
      $('#filings').innerHTML = `<table><thead><tr><th>Filed</th><th>Entity</th><th>Form</th><th>Period</th><th>Description</th><th></th></tr></thead><tbody>${rows.slice(0, 250).map(f =>
        `<tr><td>${f.filing_date}</td><td>${esc(f.entity)}</td><td><span class="form">${esc(f.form)}</span></td><td>${f.report_date || ''}</td><td>${esc(f.description || '')}${f.items ? ` <span class="muted">items ${esc(f.items)}</span>` : ''}</td>
        <td>${f.url ? `<a href="${esc(f.url)}" target="_blank" rel="noopener">doc</a> · ` : ''}<a href="${esc(f.index_url)}" target="_blank" rel="noopener">index</a></td></tr>`).join('')}</tbody></table>`;
    }
    render();
    const H = S.holders_13f || [];
    $('#holders').innerHTML = H.length ? `<table><thead><tr><th>Filed</th><th>Filer</th><th>CIK</th><th>Period</th><th>Form</th><th></th></tr></thead><tbody>${H.map(h =>
      `<tr><td>${h.file_date}</td><td>${esc(h.filer)}</td><td>${h.cik}</td><td>${h.period_ending || ''}</td><td><span class="form">${esc(h.form)}</span></td><td><a href="${esc(h.url)}" target="_blank" rel="noopener">filing</a></td></tr>`).join('')}</tbody></table>
      <p class="muted">${fmt0(H[0]?.total_hits)} matching filings in the search window; showing the newest ${H.length}. Holding sizes need the information-table XML (follow-up).</p>` : '<div class="empty">No 13F search yet</div>';
  }

  // ------------------------------------------------------------ Library
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
      $('#lib-grid').innerHTML = rest.length ? rest.map(card).join('') : (books.length ? '<div class="empty">No books match</div>' : '<div class="empty">No catalog yet</div>');
      document.querySelectorAll('[data-more]').forEach(m => m.onclick = () => { const bx = m.previousElementSibling; bx.classList.toggle('open'); m.textContent = bx.classList.contains('open') ? 'less' : 'more'; });
    }
    render();
  }

  // ------------------------------------------------------------ About
  function about() {
    const m = D.meta || {}; const ds = m.datasets || {};
    const rows = Object.entries(ds).map(([k, v]) => `<tr><td>${k}</td><td class="num">${fmt0(v.rows)}</td><td>${v.latest_fetch ? `${dstr(v.latest_fetch)} (${ago(v.latest_fetch)})` : '—'}</td><td class="num">${v.mb}</td></tr>`).join('');
    $('#about').innerHTML = `
      <p><strong>moonape</strong> collects public data about GME on a schedule (GitHub Actions) and renders it here. Built ${dstr(m.built_at)}.</p>
      <h3>How to read it</h3>
      <ul>
        <li><strong>Max pain</strong> is the strike where option holders in aggregate would be paid the least at expiration (sum of open interest × intrinsic value). Open interest is published once a day by OCC, so that leg moves daily; intraday it moves only through price and volume.</li>
        <li><strong>Walls</strong> are the strikes with the largest call and put open interest for that expiration.</li>
        <li><strong>IV30</strong> interpolates ATM implied volatility to a constant 30 days in variance. <strong>IV rank</strong> is where today sits between the trailing-year min and max; <strong>percentile</strong> is the share of days below today. Both need history and switch on after five trading days.</li>
        <li><strong>GEX</strong> uses the dealer convention (long calls, short puts), $ per 1% move; zero-gamma is where per-strike net GEX turns positive. A convention, not a measurement.</li>
        <li><strong>Options feed</strong>: ${esc(m.feeds?.options || 'indicative')} (free plan: derived quotes, trades 15 minutes delayed). Stocks: ${esc(m.feeds?.stocks || 'iex')}.</li>
        <li><strong>Rates</strong>: US Treasury daily par curve (same-day close). <strong>USD/JPY</strong>: ECB reference rate via Frankfurter. <strong>BOJ</strong> policy rate is a dated constant (${m.boj?.rate}% since ${m.boj?.asof}).</li>
        <li><strong>FINRA short volume</strong> covers off-exchange prints only, regular hours. <strong>OCC</strong> volume is per exchange and account type.</li>
      </ul>
      <h3>Datasets</h3>
      <div class="tablewrap"><table><thead><tr><th>dataset</th><th class="num">rows</th><th>latest fetch</th><th class="num">MB</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="muted">Raw parquet lives in <code>data/</code> of the repo; query it with DuckDB: <code>moonape db --sql "select … from option_chain"</code>.</p>`;
  }

  function renderAll() { status(); hero(); stats(); watchlist(); macro(); latest(); options(); iv(); reddit(); socials(); sec(); library(); about(); }
  load().then(() => { renderAll(); hashTab(); });
})();
