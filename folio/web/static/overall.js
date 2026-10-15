/* Whiskers: the Overall tab.

   Net worth is what is owned less what is owed. A final-salary pension is not a pot and is
   never added in as though it could be spent tomorrow: it is shown beside the total as the
   income it is. Every amount goes through money() or narr(), so "Hide amounts" blurs it. */
'use strict';

VIEWS.overall = { title: 'Overall', sub: 'Everything you own and owe, how each part is doing, and what’s coming up.', render: vOverall };

const OWN_COLOURS = { Investments: 'var(--accent)', Cash: '#4f8fd6', Pensions: '#8a63c9', Property: '#c98a3a', Other: 'var(--grey)' };
const OWE_COLOURS = { Mortgage: 'var(--red)', Cards: 'var(--amber)' };

async function vOverall(el) {
  const d = await api('/api/overall');
  const b = d.balance;
  if (!b.total_own && !b.total_owe && !S.boot.platforms) { renderSetup(el, d); return; }
  const h = d.history;
  const monthAgo = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10);
  const then = h.filter(p => p[0] <= monthAgo).at(-1);
  const change = then ? b.net - then[1] : null;
  const promised = b.promised.reduce((a, p) => a + (p.yearly || 0), 0);
  const reds = d.tiles.filter(t => t.level === 'red').length;
  setDot('overall', reds ? 'red' : d.tiles.some(t => t.level === 'amber') ? 'amber' : null);
  el.innerHTML = `<div class="stack-lg">
    <div class="figures">
      <div class="hero"><div class="k">Net worth</div><div class="v">${money(b.net, { dp: 0 })}</div>
        <div class="s">${known(change) ? `<span class="${signCls(change)}">${money(change, { sign: true, dp: 0 })}</span> on a month ago` : 'Recorded each day Whiskers is open'}</div></div>
      <div><div class="k">You own</div><div class="v">${money(b.total_own, { dp: 0 })}</div>
        <div class="s">${Object.keys(b.own).length ? Object.keys(b.own).map(k => k.toLowerCase()).join(', ') : 'Nothing added yet'}</div></div>
      <div><div class="k">You owe</div><div class="v">${money(b.total_owe, { dp: 0 })}</div>
        <div class="s">${Object.keys(b.owe).length ? Object.keys(b.owe).map(k => k === 'Cards' ? 'credit cards' : k.toLowerCase()).join(' and ') : 'Nothing owed'}</div></div>
      <div><div class="k">Pensions promise</div><div class="v">${promised ? `${money(promised, { dp: 0 })}<span class="muted" style="font-size:1rem"> a year</span>` : '—'}</div>
        <div class="s">${promised ? 'Income for life, not counted in what you own' : 'No final-salary pension or annuity added'}</div></div>
    </div>
    ${b.unconverted.length ? `<div class="panel warnline">No exchange rate yet for ${esc(b.unconverted.join(', '))}, so ${b.unconverted.length === 1 ? 'it is' : 'they are'} left out of these totals. Press Refresh to fetch one.</div>` : ''}

    <div class="grid g-main">
      <section class="panel">
        <div class="spread"><h2>What you own and owe</h2><button class="btn small ghost" data-act="asset-add">Add your home or something else you own</button></div>
        ${balanceBlock(b)}
      </section>
      <div class="stack">${miniMonitor(d.market, d.exposure, d.playbook, d.watch_exposure)}
        <section class="panel"><h2>Coming up</h2>
          <p class="lede">Dates worth knowing over the next year, soonest first.</p>
          ${timelineHtml(d.this_year)}</section></div>
    </div>

    <section><h2 style="margin-bottom:8px">How each part is doing</h2>
      <div class="tiles">${d.tiles.map(tileHtml).join('')}</div></section>

    <div class="grid g2">
      <section class="panel"><h2>The big picture</h2>
        <h3 style="margin-top:10px">Your money</h3><p class="small">${narr(d.big_picture.you)}</p>
        <h3 style="margin-top:12px">${esc(d.big_picture.theme_title || 'The AI trade')}</h3><p class="small">${narr(d.big_picture.theme || d.big_picture.ai)}</p>
        <h3 style="margin-top:12px">Markets and the economy</h3><p class="small">${narr(d.big_picture.markets)}</p>
        <h3 style="margin-top:12px">What it means for your investments</h3><p class="small">${narr(d.big_picture.portfolio)}</p>
        <p class="note" style="margin-top:10px">Written from today’s figures by fixed rules. Not advice.</p>
      </section>
      <section class="panel"><h2>Things to look at</h2>
        <div class="alerts" style="margin-top:4px">${d.warnings.length ? d.warnings.map(alertRow).join('') : '<p class="none-state">Nothing needs a look in your investments.</p>'}</div></section>
    </div>

    <section class="panel"><h2>Net worth over time</h2>
      ${h.length >= 2 ? Charts.line({ series: [{ name: 'Net worth', points: h, color: 'var(--accent)', area: true }], money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney }, 220)
        : `<p class="muted" style="max-width:70ch">Whiskers writes down your net worth once a day whenever it’s open, so this line starts ${h.length ? `on ${fmtDate(h[0][0])}` : 'today'} and grows from there.</p>`}
    </section>
    ${d.setup.done < d.setup.of ? setupPanel(d.setup) : ''}
  </div>`;
}

function balanceBlock(b) {
  const own = Object.entries(b.own).map(([k, v]) => ({ name: k, value: v, color: OWN_COLOURS[k] || 'var(--grey)' }));
  if (!own.length && !Object.keys(b.owe).length) return '<p class="muted">Nothing added yet.</p>';
  const top = Math.max(b.total_own, b.total_owe, 1);
  return `<div class="balance">
      <div>${Charts.donut(own.map(o => ({ value: o.value, color: o.color })), { size: 170, thick: 22, centre: b.total_own ? compactMoney(b.total_own) : '', sub: 'owned' })}</div>
      <div class="legend-rows small">${own.map(o => `<div class="row"><span class="lvl" style="background:${o.color}"></span><span>${esc(o.name)}</span>
        <span class="num">${money(o.value, { dp: 0 })}</span><span class="muted num" style="width:44px;text-align:right">${pct(o.value / (b.total_own || 1), { dp: 0 })}</span></div>`).join('')}</div>
    </div>
    ${Object.keys(b.owe).length ? `<h3 style="margin-top:14px">What you owe</h3><div class="owe-bars">${Object.entries(b.owe).map(([k, v]) => `
      <div class="owe-bar"><span>${k === 'Cards' ? 'Credit cards' : esc(k)}</span><div class="track"><i style="width:${Math.max(1, v / top * 100)}%;background:${OWE_COLOURS[k] || 'var(--red)'}"></i></div><span class="num">${money(v, { dp: 0 })}</span></div>`).join('')}
      <div class="owe-bar"><span class="muted">Against owned</span><div class="track"><i style="width:${Math.max(1, b.total_own / top * 100)}%;background:var(--accent);opacity:.45"></i></div><span class="num muted">${money(b.total_own, { dp: 0 })}</span></div></div>` : ''}
    ${b.promised.length ? `<p class="small" style="margin-top:12px">Pensions that pay an income: ${b.promised.map(p => `${esc(p.name)} ${money(p.yearly, { dp: 0 })} a year${p.from ? ` from ${p.from}` : ''}`).join('; ')}. Shown as income on the Retirement tab, not as money you own.</p>` : ''}
    ${known(b.cash_abroad) && b.cash_abroad ? `<p class="small muted" style="margin-top:6px">Cash includes ${money(b.cash_abroad, { dp: 0 })} held in other currencies, at today’s rate.</p>` : ''}`;
}

function tileHtml(t) {
  const lvl = t.level === 'none' ? '' : t.level;
  const dial = t.watch ? `<div class="mini-dial" title="${esc(t.watch.title)}: ${esc(t.watch.label)}">${Charts.gauge(needle({ regime: t.watch.regime, gauge: t.watch.gauge }), { zones: GAUGE_ZONES, size: 120, label: t.watch.label })}</div>` : '';
  return `<button type="button" class="tile ${lvl}" data-go="${esc(t.go)}">
    ${dial}<div class="head"><span class="lvl ${lvl}"></span><b>${esc(t.title)}</b></div>
    <div class="val">${known(t.value) ? money(t.value, { dp: 0 }) : '<span class="muted">—</span>'}${t.value_label ? ` <small>${esc(t.value_label)}</small>` : ''}</div>
    ${t.lines.map(l => `<div class="ln">${narr(l)}</div>`).join('')}
    ${t.watch ? `<div class="ln muted">${esc(t.watch.title)}: ${esc(t.watch.label.toLowerCase())}</div>` : ''}
  </button>`;
}

function timelineHtml(items) {
  if (!items || !items.length) return '<p class="muted">Nothing dated in the next year.</p>';
  const soon = new Date(Date.now() + 60 * 864e5).toISOString().slice(0, 10);
  return `<div class="timeline">${items.slice(0, 10).map(e => `<div class="ev ${e.when <= soon ? 'soon' : ''}">
      <span class="when">${fmtDate(e.when)}</span>
      <div>${e.go ? `<button type="button" data-go="${esc(e.go)}"><b>${narr(e.what)}</b></button>` : `<b>${narr(e.what)}</b>`}<div class="small muted">${narr(e.detail || '')}</div></div></div>`).join('')}</div>`;
}

function setupPanel(st, big = false) {
  return `<section class="${big ? '' : 'panel'}">${big ? '' : `<div class="spread"><h2>Getting set up</h2><span class="chip">${st.done} of ${st.of} done</span></div>
    <p class="lede">Each one adds a part of the picture. They can be done in any order, over several sittings.</p>`}
    <div class="setup">${st.steps.map((x, i) => `<div class="card ${x.done ? 'done' : ''}">
      <h3><span class="lvl ${x.done ? 'green' : ''}"></span>${i + 1}. ${esc(x.title)}</h3>
      <p class="small muted">${esc(x.detail)}</p>
      <div><button class="btn small ${x.done ? '' : 'primary'}" data-go="${esc(x.go)}">${x.done ? 'Look again' : 'Start'}</button></div></div>`).join('')}</div></section>`;
}

// A new copy: nothing to add up yet, so the screen is the list of things to set up.
function renderSetup(el, d) {
  el.dataset.title = 'Welcome to Whiskers';
  el.dataset.sub = 'A few things to set up. Each one fills in part of the picture; none of them takes long.';
  el.innerHTML = `<div class="stack-lg" style="max-width:1100px">
    <section class="panel"><h2>Where to start</h2>
      <p class="lede" style="max-width:80ch">The plan review is the best first step: eight short sets of questions about you, your goals and how you feel about risk, saved as you go. Then add where you invest and save, your mortgage and your pensions, and Whiskers puts it all together.</p>
      ${setupPanel(d.setup, true)}
    </section>
    <section class="panel"><h3>Just looking?</h3><p class="muted" style="margin:4px 0 10px">Load a made-up household to see every screen working: investments, a mortgage, pensions and a little money in South Africa. It comes out again in one click.</p>
      <button class="btn" data-act="sample-load">Load the sample household</button></section>
  </div>`;
}

// ---------------------------------------------------------------------------- your home and other assets

function assetForm(a) {
  a = a || {};
  openModal({ title: a.id ? `Change ${a.name}` : 'Something you own', body: `<div class="form-grid">
      <label class="field">Name<input type="text" id="as-name" value="${esc(a.name || '')}" placeholder="Home"></label>
      <label class="field">Kind<select id="as-kind">${[['property', 'Property'], ['vehicle', 'A car or other vehicle'], ['other', 'Something else']].map(([k, l]) => `<option value="${k}" ${(a.kind || 'property') === k ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      <label class="field">What it’s worth<input type="number" id="as-value" step="1000" min="0" value="${known(a.value) ? a.value : ''}"><span class="help">A rough figure is fine: an online valuation, or what similar homes nearby sold for.</span></label>
      <label class="field">Currency<select id="as-ccy">${['GBP', 'ZAR', 'EUR', 'USD'].map(c => `<option ${(a.currency || 'GBP') === c ? 'selected' : ''}>${c}</option>`).join('')}</select></label>
      <label class="full row small"><input type="checkbox" id="as-home" ${a.is_home || (!a.id && (a.kind || 'property') === 'property') ? 'checked' : ''}> This is my main home <span class="muted">(for inheritance tax’s residence allowance)</span></label>
      <label class="field full">Notes (optional)<input type="text" id="as-notes" value="${esc(a.notes || '')}"></label>
    </div>`,
    foot: `${a.id ? `<button class="btn ghost danger" data-act="asset-del" data-id="${a.id}" data-name="${esc(a.name)}">Remove</button>` : ''}<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="asset-save" data-id="${a.id || ''}">Save</button>` });
}
ACTS['asset-add'] = () => assetForm(null);
ACTS['asset-edit'] = async b => {
  const d = await api('/api/assets');
  assetForm(d.items.find(x => x.id === +b.dataset.id));
};
ACTS['asset-save'] = async b => {
  const body = { name: $('#as-name').value, kind: $('#as-kind').value, value: $('#as-value').value,
    currency: $('#as-ccy').value, is_home: $('#as-home').checked, notes: $('#as-notes').value };
  await busy(b, async () => {
    if (b.dataset.id) await api(`/api/assets/${b.dataset.id}`, { method: 'PATCH', body });
    else await api('/api/assets', { method: 'POST', body });
    closeModal();
    toast('Saved.');
    render();
  });
};
ACTS['asset-del'] = async b => {
  if (!await confirmBox(`Remove ${b.dataset.name}?`, 'It comes off what you own. A mortgage linked to it keeps its own figure for the property, if it has one.', 'Remove', true)) return;
  await api(`/api/assets/${b.dataset.id}`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  render();
};

SETTINGS_PANELS.middle.push(() => `<section class="panel" id="assets-panel"><div class="spread"><h2>Your home and other things you own</h2><button class="btn" data-act="asset-add">Add one</button></div>
  <p class="lede">Counted in your net worth on the Overall tab. A mortgage can take the home’s value from here, so there is one figure for the house, not two that can disagree.</p>
  <div id="assets-list"><div class="spinner"></div></div></section>`);
document.addEventListener('whiskers:rendered', async () => {
  const box = $('#assets-list');
  if (!box) return;
  try {
    const d = await api('/api/assets');
    box.innerHTML = d.items.length ? `<table class="small"><tbody>${d.items.map(a => `<tr><td><b>${esc(a.name)}</b>${a.is_home ? ' <span class="chip">main home</span>' : ''}<div class="tiny muted">${esc(d.kinds[a.kind] || a.kind)}${a.valued_on ? `, valued ${fmtDate(a.valued_on)}` : ''}</div></td>
      <td class="r">${known(a.value) ? (a.currency && a.currency !== 'GBP' ? `<span class="pv">${esc(a.currency)} ${Math.round(a.value).toLocaleString('en-GB')}</span>` : money(a.value, { dp: 0 })) : '<span class="muted">no value</span>'}</td>
      <td class="r"><button class="btn small ghost" data-act="asset-edit" data-id="${a.id}">Change</button></td></tr>`).join('')}</tbody></table>`
      : '<p class="muted">Nothing yet.</p>';
    wire(box);
  } catch (e) { box.innerHTML = `<p class="warnline">${esc(e.message)}</p>`; }
});
