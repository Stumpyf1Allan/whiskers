/* Whiskers: the Retirement tab. A plan one row a year, from now to the end of the plan,
   in today's money; the pensions it rests on; and the State Pension.

   Nothing here is a forecast. Returns are steady assumptions the person can change, and
   the stress tests exist because real returns are not steady. */
'use strict';

VIEWS.retirement = { title: 'Retirement plan', navTitle: 'Year by year', sub: 'Each year to the end of the plan, in today’s money: what comes in, what goes out, and which pot pays the difference.', render: vRetirement };
VIEWS.pensions = { title: 'Pensions', sub: 'Every pension you have: final salary, pots, annuities and anything in South Africa.', render: vPensions };
VIEWS.statepension = { title: 'State Pension', sub: 'When it starts, roughly how much, and whether filling a gap in your record pays.', render: vStatePension };

const POT_COLOURS = { cash: '#4f8fd6', isa: 'var(--accent)', gia: '#3d9c8f', abroad: '#c98a3a', pensions: '#8a63c9' };
const IN_COLOURS = { salary: '#4f8fd6', state: 'var(--green)', db: '#8a63c9', annuity: '#b07fd6', other: '#7a8a99', lump: '#c9a53a',
  from_cash: '#9fc0e8', from_isa: 'var(--accent)', from_gia: '#3d9c8f', from_abroad: '#c98a3a', from_pension: '#c96a8a' };
const ageTip = rows => a => { const r = rows.find(x => Math.floor(x.age) === Math.floor(a)); return r ? `Age ${Math.floor(r.age)}, ${r.year}` : `Age ${a}`; };
const ageOf = a => Math.floor(a);

async function vRetirement(el) {
  const d = await api('/api/retirement');
  S.ret = d;
  if (!d.ready) { retBasics(el, d); return; }
  const p = d.plan, rows = p.rows, s = d.settings;
  setDot('retirement', p.lasts ? null : (p.runs_out_at || 0) >= 85 ? 'amber' : 'red');
  const fl = p.income_floor;
  const potSeries = [['cash', 'Cash'], ['isa', 'ISAs'], ['gia', 'General account'], ['abroad', 'Abroad'], ['pensions', 'Pensions']]
    .filter(([k]) => rows.some(r => r[k] > 0.5))
    .map(([k, l]) => ({ name: l, points: rows.map(r => [ageOf(r.age), Math.max(0, r[k])]), color: POT_COLOURS[k] }));
  const vlines = [{ at: ageOf(p.stop_age), label: 'stop work', color: 'var(--accent)' }];
  if (p.spa) vlines.push({ at: Math.ceil(p.spa), label: 'State Pension', color: 'var(--cyan)' });
  if (p.first_short) vlines.push({ at: ageOf(p.first_short), label: 'runs short', color: 'var(--red)' });
  const inParts = [['salary', 'Pay, after NI'], ['state', 'State Pension'], ['db', 'Final-salary pensions'], ['annuity', 'Annuities'], ['other', 'Other income'],
    ['lump', 'Tax-free cash'], ['from_cash', 'From cash'], ['from_isa', 'From ISAs'], ['from_gia', 'From the general account'], ['from_abroad', 'From abroad'], ['from_pension', 'From pension pots']]
    .filter(([k]) => rows.some(r => r[k] > 0.5));
  const outgoings = rows.map(r => r.spend + r.one_off + r.mortgage + r.tax);
  const atStop = rows.find(r => r.age >= p.stop_age) || rows[0];
  el.innerHTML = `<div class="stack-lg">
    <section class="panel">
      <div class="verdict">
        <div class="big ${p.lasts ? 'ok' : 'short'}">${p.lasts ? `Lasts to ${Math.round(p.horizon)}` : `Runs short at ${ageOf(p.runs_out_at)}`}</div>
        <p style="max-width:70ch">${p.lasts ? `On these assumptions the money lasts to the end of the plan, with ${money(rows.at(-1).liquid, { dp: 0 })} left at ${Math.round(p.horizon)} in today’s money.`
          : `On these assumptions the money runs out at about ${ageOf(p.runs_out_at)}, ${Math.round(p.horizon - p.runs_out_at)} years before the end of the plan. The levers below show what would change that.`}</p>
      </div>
      <div class="stat-row" style="margin-top:14px">
        <div class="stat"><span class="k">When you stop, at ${p.stop_age.toFixed(0)}</span><span class="v">${money(p.at_stop.liquid, { dp: 0 })}</span><span class="tiny muted">savings, investments and pension pots</span></div>
        <div class="stat"><span class="k">Guaranteed income from ${ageOf(fl.age)}</span><span class="v">${money(fl.guaranteed, { dp: 0 })}</span><span class="tiny muted">a year: ${known(fl.covers) ? `${pct(Math.min(fl.covers, 9.99), { dp: 0 })} of essential spending` : 'essentials not entered'}</span></div>
        <div class="stat"><span class="k">Mortgage</span><span class="v">${p.mortgage_free_age ? `Clear at ${ageOf(p.mortgage_free_age)}` : (S.ret.start.mortgages || []).length ? 'Not cleared' : 'None'}</span><span class="tiny muted">${s.clear_mortgage_at_stop ? 'cleared when you stop work' : 'runs to its end'}${(d.start.mortgages || []).some(m => m.fixed_until) && d.market ? `; after the deal ends, a new fix at ${(+d.market.avg_fix_5y).toFixed(2)}% (today’s average) is assumed` : ''}</span></div>
        <div class="stat"><span class="k">At the end of the plan</span><span class="v">${money(p.estate, { dp: 0 })}</span><span class="tiny muted">${p.iht.tax ? `inheritance tax about ${money(p.iht.tax, { dp: 0 })}` : 'no inheritance tax on these figures'}</span></div>
      </div>
      ${(d.start.missing_fx || []).length ? `<p class="warnline" style="margin-top:10px">No exchange rate yet for ${esc(d.start.missing_fx.join(', '))}, so ${d.start.missing_fx.length === 1 ? 'it is' : 'they are'} left out. Press Refresh.</p>` : ''}
    </section>

    <section class="panel"><div class="spread"><h2>What you’ll have, year by year</h2><span class="muted small">in today’s money</span></div>
      <div style="margin-top:10px">${Charts.line({ series: potSeries, stack: true, numericX: true, money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney,
        xtick: a => String(a), xtip: ageTip(rows), totalLabel: 'Altogether', vlines }, 280)}</div>
      <div class="legend" style="margin-top:6px">${potSeries.map(x => `<span><i style="background:${x.color}"></i>${esc(x.name)}</span>`).join('')}</div>
    </section>

    <section class="panel"><div class="spread"><h2>Where each year’s money comes from</h2><span class="muted small">bars: money coming in; line: spending, the mortgage and tax</span></div>
      <div style="margin-top:10px">${Charts.bars({ items: rows.map(r => ({ label: String(ageOf(r.age)), long: `Age ${ageOf(r.age)}, ${r.year}`,
          parts: inParts.map(([k, l]) => ({ name: l, value: r[k], color: IN_COLOURS[k] })),
          note: r.short ? 'Short this year' : r.saving > 1 ? `Saved ${moneyText(r.saving, 0)}` : '' })),
        overlay: [{ name: 'Spending, mortgage and tax', values: outgoings, color: 'var(--ink)' }],
        money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney }, 260)}</div>
      <div class="legend" style="margin-top:6px">${inParts.map(([k, l]) => `<span><i style="background:${IN_COLOURS[k]}"></i>${esc(l)}</span>`).join('')}<span><i style="background:var(--ink);height:2px;vertical-align:3px"></i>Spending, mortgage and tax</span></div>
      <p class="chart-note">Where the bars stand above the line, the difference is saved; where a pot pays, it shows in its own colour. Tax-free cash appears in the year it is taken.</p>
    </section>

    <div class="grid g2">
      <section class="panel"><h2>Try a change</h2>
        <p class="lede">Move one and see what it does. Nothing is saved unless you press Use these.</p>
        <div class="lever"><label for="lv-stop">Stop work at</label><input type="range" id="lv-stop" min="${Math.max(50, Math.ceil(p.age_now))}" max="75" step="0.5" value="${p.stop_age}"><output id="lv-stop-o">${p.stop_age}</output></div>
        <div class="lever"><label for="lv-spend">Spending on extras</label><input type="range" id="lv-spend" min="0" max="150" step="5" value="100"><output id="lv-spend-o">100%</output></div>
        <div class="lever"><label for="lv-save">Spend less now and invest it (a month)</label><input type="range" id="lv-save" min="0" max="1500" step="25" value="0"><output id="lv-save-o">£0</output></div>
        <div class="lever"><label for="lv-order">Which pots to spend first</label><select id="lv-order">${Object.entries(d.orders_available).map(([k, l]) => `<option value="${k}" ${k === s.withdrawal_order ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select><span></span></div>
        <div id="lv-out" class="plan-box" style="margin-top:10px"><span class="small">As it stands: ${p.lasts ? `lasts to ${Math.round(p.horizon)}` : `runs short at ${ageOf(p.runs_out_at)}`}.</span></div>
        <div class="row" style="margin-top:10px"><button class="btn" data-act="lv-use">Use these</button><button class="btn ghost" data-act="lv-reset">Put them back</button></div>
        ${(d.levers || []).length ? `<h3 style="margin-top:16px">To make it last, any one of these</h3><ul class="small" style="padding-left:18px;display:grid;gap:4px;margin-top:6px">${d.levers.map(l => `<li><b>${esc(l.label)}</b>: ${narr(l.words.replace(/£[\d,]+/g, m => `[[${m}]]`))}</li>`).join('')}</ul>` : ''}
      </section>
      <section class="panel"><h2>If things go badly</h2>
        <p class="lede">The same plan with one thing going wrong. A plan worth having survives most of these.</p>
        <div>${(d.stresses || []).map(x => `<div class="stress"><span class="lvl ${x.lasts ? 'green' : 'red'}"></span><b class="small">${esc(x.label)}</b>
          <span class="small nowrap ${x.lasts ? 'up' : 'down'}">${x.lasts ? `lasts to ${Math.round(x.horizon)}` : `short at ${ageOf(x.runs_out_at)}`}</span><span class="d">${esc(x.why)}</span></div>`).join('')}</div>
        ${d.need ? `<h3 style="margin-top:16px">The growth the plan needs</h3><p class="small" style="margin-top:4px">${esc(d.need.words)}</p>
          <p class="tiny muted" style="margin-top:4px">Your investments are set to grow at about ${(+d.start.mix.real).toFixed(1)}% a year above inflation after charges, from what they hold${d.start.mix.assumed ? ' (assumed: nothing invested yet)' : ''}.</p>` : ''}
      </section>
    </div>

    <section class="panel"><h2>Which pots to spend first</h2>
      <p class="lede">The order changes the tax paid along the way and what is left at the end. From April 2027 an unused pension counts towards inheritance tax, which changes the old advice to spend pensions last.</p>
      <div class="table-wrap"><table class="small"><thead><tr><th>Order</th><th>Lasts?</th><th class="r">Tax over the plan</th><th class="r">Left at the end</th><th class="r">Inheritance tax</th><th></th></tr></thead><tbody>
        ${(d.orders || []).map(o => `<tr><td>${esc(o.label)}${o.chosen ? ' <span class="chip green">your choice</span>' : ''}</td><td>${o.lasts ? '<span class="up">Yes</span>' : `<span class="down">Short at ${ageOf(o.runs_out_at)}</span>`}</td>
          <td class="r">${money(o.total_tax, { dp: 0 })}</td><td class="r">${money(o.estate, { dp: 0 })}</td><td class="r">${money(o.iht, { dp: 0 })}</td>
          <td class="r">${o.chosen ? '' : `<button class="btn small ghost" data-act="ret-order" data-v="${o.key}">Use this</button>`}</td></tr>`).join('')}</tbody></table></div>
      <p class="note" style="margin-top:8px">${esc(p.iht.note || '')} Rough figures in today’s money: a will, gifts and trusts can change them a great deal.</p>
    </section>

    <section class="panel"><details><summary><b>Every year, in full</b> <span class="muted small">${rows.length} rows</span></summary>
      <div class="yt-wrap" style="margin-top:10px"><table class="yt"><thead><tr><th>Age</th><th>Year</th><th class="r">Pay</th><th class="r">State</th><th class="r">Pensions</th><th class="r">Other</th><th class="r">Tax</th>
        <th class="r">Spending</th><th class="r">Mortgage</th><th class="r">One-offs</th><th class="r">From savings</th><th class="r">From pensions</th><th class="r">Saved</th>
        <th class="r">Cash</th><th class="r">ISAs</th><th class="r">General</th><th class="r">Abroad</th><th class="r">Pension pots</th><th class="r">Altogether</th><th class="r">Mortgage left</th></tr></thead><tbody>
        ${rows.map(r => `<tr class="${r === atStop ? 'stop' : ''} ${p.spa && ageOf(r.age) === Math.ceil(p.spa) ? 'spa' : ''} ${r.short ? 'short' : ''}"><td class="num">${ageOf(r.age)}</td><td class="num">${r.year}</td>
          ${[r.salary, r.state, r.db + r.annuity, r.other, r.tax, r.spend, r.mortgage, r.one_off, r.from_cash + r.from_isa + r.from_gia + r.from_abroad, r.from_pension, r.saving,
             r.cash, r.isa, r.gia, r.abroad, r.pensions, r.liquid, r.mortgage_left].map(v => `<td class="r">${Math.abs(v) < 0.5 ? '<span class="muted">–</span>' : money(v, { dp: 0 })}</td>`).join('')}</tr>`).join('')}
      </tbody></table></div>
      <p class="note" style="margin-top:6px">Blue line: the year you stop work. Cyan: State Pension age. Red rows: years the money ran short.</p></details></section>

    ${retFigures(d)}
    ${retStartsFrom(d)}
    <p class="note">In today’s money throughout: £20,000 in 2045 means what £20,000 buys now. Tax as it stood on ${fmtDate(d.checked)}, with frozen thresholds catching a little more each year until April 2031. A tool for seeing whether a plan hangs together; not a forecast, and not financial advice.</p>
  </div>`;
  setTimeout(wireLevers, 0);
}

// ---------------------------------------------------------------------------- levers

function wireLevers() {
  const ids = ['lv-stop', 'lv-spend', 'lv-save', 'lv-order'];
  if (!$('#lv-stop')) return;
  const show = () => {
    $('#lv-stop-o').textContent = (+$('#lv-stop').value).toFixed(1).replace('.0', '');
    $('#lv-spend-o').textContent = `${$('#lv-spend').value}%`;
    $('#lv-save-o').textContent = `£${(+$('#lv-save').value).toLocaleString('en-GB')}`;
  };
  let t;
  const run = () => {
    show();
    clearTimeout(t);
    t = setTimeout(async () => {
      try {
        const r = await api('/api/retirement/what-if', { method: 'POST', body: { stop_age: $('#lv-stop').value,
          spend_factor: +$('#lv-spend').value / 100, extra_saving: $('#lv-save').value, order: $('#lv-order').value } });
        const base = S.ret.plan;
        const end = r.rows.at(-1).liquid, baseEnd = base.rows.at(-1).liquid;
        $('#lv-out').innerHTML = `<b>${r.lasts ? `Lasts to ${Math.round(r.horizon)}` : `Runs short at ${ageOf(r.runs_out_at)}`}</b>
          <span class="small">(now ${base.lasts ? `lasts to ${Math.round(base.horizon)}` : `short at ${ageOf(base.runs_out_at)}`}). Left at the end: ${money(end, { dp: 0 })}, ${end >= baseEnd ? 'up' : 'down'} ${money(Math.abs(end - baseEnd), { dp: 0 })}. Tax over the plan: ${money(r.total_tax, { dp: 0 })}.</span>`;
      } catch (e) { $('#lv-out').innerHTML = `<span class="warnline">${esc(e.message)}</span>`; }
    }, 250);
  };
  ids.forEach(id => $(`#${id}`).addEventListener(id === 'lv-order' ? 'change' : 'input', run));
  show();
}
ACTS['lv-reset'] = () => render();
ACTS['lv-use'] = async b => {
  const s = S.ret.settings, f = +$('#lv-spend').value / 100;
  const body = { stop_age: $('#lv-stop').value, withdrawal_order: $('#lv-order').value };
  if (f !== 1 && known(s.spend_extra)) body.spend_extra = Math.round(s.spend_extra * f);
  if (+$('#lv-save').value) body.saving_monthly = (s.saving_monthly || 0) + +$('#lv-save').value;
  await busy(b, async () => {
    await api('/api/retirement', { method: 'PATCH', body });
    toast(+$('#lv-save').value ? 'Saved. The extra saving is now part of your monthly saving.' : 'Saved.');
    render();
  });
};
ACTS['ret-order'] = async b => {
  await api('/api/retirement', { method: 'PATCH', body: { withdrawal_order: b.dataset.v } }).catch(e => toast(e.message, true));
  render();
};

// ---------------------------------------------------------------------------- the basics

function retBasics(el, d) {
  const s = d.settings;
  el.dataset.sub = 'Three things and the plan can run: your date of birth, when you’d like to stop working, and what you spend.';
  el.innerHTML = `<div class="stack-lg" style="max-width:900px"><section class="panel"><h2>The basics</h2>
    <p class="lede">The plan review on the Overall tab asks these too, with everything else a plan needs. Your answers go to the same place, so neither can disagree.</p>
    <div class="form-grid">
      <label class="field">Date of birth<input type="date" id="rb-dob" value="${esc(s.dob || '')}" max="${new Date().toISOString().slice(0, 10)}"></label>
      <label class="field">Stop working at (age)<input type="number" id="rb-stop" min="40" max="85" step="0.5" value="${esc(s.stop_age ?? '')}" placeholder="60"></label>
      <label class="field">Essential spending, a month<input type="number" id="rb-ess" min="0" step="50" value="${esc(s.spend_essential ?? '')}" placeholder="1,800"><span class="help">Bills, food, transport, insurance, council tax. Not the mortgage: it comes from the Mortgage tab.</span></label>
      <label class="field">Extras, a month<input type="number" id="rb-extra" min="0" step="50" value="${esc(s.spend_extra ?? '')}" placeholder="800"><span class="help">Holidays, hobbies, eating out, gifts.</span></label>
      <label class="field">Where you live<select id="rb-nation">${Object.entries(d.nations).map(([k, l]) => `<option value="${k}" ${k === s.nation ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label>
      <label class="field">The plan runs to (age)<input type="number" id="rb-hz" min="70" max="110" value="${esc(s.horizon_age ?? 95)}"></label>
    </div>
    <div class="row" style="margin-top:14px"><button class="btn primary" data-act="rb-save">Run the plan</button><button class="btn ghost" data-go="plan">Do the full plan review instead</button></div>
    ${d.missing.length ? `<p class="small muted" style="margin-top:8px">Still needed: ${esc(d.missing.join(', '))}.</p>` : ''}</section></div>`;
}
ACTS['rb-save'] = async b => {
  await busy(b, async () => {
    await api('/api/retirement', { method: 'PATCH', body: { dob: $('#rb-dob').value, stop_age: $('#rb-stop').value, spend_essential: $('#rb-ess').value,
      spend_extra: $('#rb-extra').value, nation: $('#rb-nation').value, horizon_age: $('#rb-hz').value } });
    render();
  });
};

// ---------------------------------------------------------------------------- your figures

function retFigures(d) {
  const s = d.settings, a = s.assumptions, n = d.assumption_notes;
  const num = (id, v, o = {}) => `<input type="number" id="${id}" value="${esc(v ?? '')}" ${o.min !== undefined ? `min="${o.min}"` : ''} ${o.max !== undefined ? `max="${o.max}"` : ''} step="${o.step || 'any'}" ${o.ph ? `placeholder="${esc(o.ph)}"` : ''}>`;
  const sel = (id, opts, cur) => `<select id="${id}">${opts.map(([k, l]) => `<option value="${k}" ${String(k) === String(cur) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  const oneOffs = (s.one_offs || []).map((o, i) => listRow('oo', i, o)).join('');
  const others = (s.other_income || []).map((o, i) => listRow('oi', i, o)).join('');
  return `<section class="panel"><details ${S.retOpen ? 'open' : ''} id="ret-fig"><summary><b>Your figures and the assumptions</b> <span class="muted small">everything the plan runs on</span></summary>
    <div class="stack" style="margin-top:12px">
      <h3>You</h3><div class="form-grid">
        <label class="field">Date of birth<input type="date" id="rf-dob" value="${esc(s.dob || '')}"></label>
        <label class="field">Where you live${sel('rf-nation', Object.entries(d.nations), s.nation)}</label>
        <label class="field">Married or in a civil partnership${sel('rf-partner', [['false', 'No'], ['true', 'Yes']], String(!!s.partner))}<span class="help">A husband, wife or civil partner inherits free of inheritance tax.</span></label>
        <label class="field">Where you’ll live in retirement${sel('rf-country', [['uk', 'The UK'], ['za', 'South Africa'], ['both', 'Some of each']], s.retire_country)}<span class="help">A UK State Pension paid in South Africa is frozen: it never rises.</span></label>
        <label class="field">The plan runs to (age)${num('rf-hz', s.horizon_age, { min: 70, max: 110, step: 1 })}</label>
      </div>
      <h3>Work</h3><div class="form-grid">
        <label class="field">Stop working at (age)${num('rf-stop', s.stop_age, { min: 40, max: 85, step: 0.5 })}</label>
        <label class="field">Salary before tax, a year${num('rf-salary', s.salary, { min: 0, step: 500 })}</label>
        <label class="field">Pay rises above inflation (% a year)${num('rf-sg', s.salary_growth, { min: -5, max: 10, step: 0.5 })}</label>
        <label class="field">Cut your hours from (age)${num('rf-cba', s.cut_back_age, { min: 30, max: 85, step: 0.5, ph: 'not planned' })}</label>
        <label class="field">Earning then (% of pay now)${num('rf-cbp', s.cut_back_pct, { min: 0, max: 100, step: 5, ph: '60' })}</label>
        <label class="field">Into your workplace pension (% of salary)${num('rf-cp', s.contrib_pct, { min: 0, max: 100, step: 0.5 })}<span class="help">What comes out of your pay. Add the pension itself on the Pensions screen.</span></label>
        <label class="field">How it comes out of your pay${sel('rf-cm', [['net_pay', 'Before tax (most public-sector schemes)'], ['salary_sacrifice', 'Salary sacrifice'], ['relief_at_source', 'After tax, with relief added']], s.contrib_method)}</label>
        <label class="field">Into ISAs and investments, a month${num('rf-save', s.saving_monthly, { min: 0, step: 50, ph: 'whatever is left over' })}</label>
      </div>
      <h3>Spending, in today’s money</h3><div class="form-grid">
        <label class="field">Essentials, a month${num('rf-ess', s.spend_essential, { min: 0, step: 50 })}</label>
        <label class="field">Extras, a month${num('rf-extra', s.spend_extra, { min: 0, step: 50 })}</label>
        <label class="field">From 75, extras fall by (%)${num('rf-75', s.spend_less_from_75, { min: 0, max: 90, step: 5 })}</label>
        <label class="field">Emergency fund kept back (months of essentials)${num('rf-em', s.emergency_months, { min: 0, max: 60, step: 1 })}</label>
        <label class="field">The mortgage${sel('rf-clear', [['false', 'Runs to its end'], ['true', 'Cleared when I stop work']], String(!!s.clear_mortgage_at_stop))}</label>
        <label class="field">Tax-free cash from pension pots${sel('rf-tfc', [['upfront', 'A quarter at the start'], ['ufpls', 'A quarter of each withdrawal']], s.tax_free_cash)}</label>
        <label class="field">Home goes to children or grandchildren${sel('rf-home', [['true', 'Yes'], ['false', 'No']], String(s.home_to_children !== false))}</label>
      </div>
      <h3>Big costs ahead</h3><div class="listrows" id="oo-list">${oneOffs}</div>
      <div><button class="btn small" data-act="lr-add" data-kind="oo">Add one</button> <span class="tiny muted">A negative amount is money coming in, such as an inheritance or downsizing.</span></div>
      <h3>Other income</h3><div class="listrows" id="oi-list">${others}</div>
      <div><button class="btn small" data-act="lr-add" data-kind="oi">Add one</button> <span class="tiny muted">Rent, part-time work, a trust. Pensions go on the Pensions screen.</span></div>
      <h3>Assumptions, % a year above inflation</h3><div class="form-grid">
        ${Object.keys(n).map(k => `<label class="field">${esc({ inflation: 'Inflation (% a year)', shares: 'Shares', bonds: 'Bonds and gilts', cash: 'Cash', property: 'Property', gold: 'Gold',
          dc_default: 'A pension pot nobody has described', rand_drift: 'The rand against the pound', sp_real: 'State Pension above prices', annuity_rate: 'Annuity income, % of the pot' }[k] || k)}
          <input type="number" step="0.1" data-assume="${k}" value="${esc(a[k] ?? '')}"><span class="help">${esc(n[k])}</span></label>`).join('')}
      </div>
      <div class="row"><button class="btn primary" data-act="rf-save">Save and run again</button></div>
    </div></details></section>`;
}
function listRow(kind, i, o = {}) {
  return kind === 'oo'
    ? `<div class="lr" data-lr="oo"><input type="text" data-f="label" value="${esc(o.label || '')}" placeholder="New car" style="width:200px"><input type="number" data-f="amount" value="${esc(o.amount ?? '')}" placeholder="£" style="width:120px"><span class="small">at age</span><input type="number" data-f="age" value="${esc(o.age ?? '')}" style="width:80px"><button class="btn small ghost" data-act="lr-del">Remove</button></div>`
    : `<div class="lr" data-lr="oi"><input type="text" data-f="label" value="${esc(o.label || '')}" placeholder="Rent from the flat" style="width:200px"><input type="number" data-f="yearly" value="${esc(o.yearly ?? '')}" placeholder="£ a year" style="width:120px"><span class="small">from</span><input type="number" data-f="from_age" value="${esc(o.from_age ?? '')}" placeholder="now" style="width:70px"><span class="small">to</span><input type="number" data-f="to_age" value="${esc(o.to_age ?? '')}" placeholder="the end" style="width:80px"><label class="small row" style="gap:4px"><input type="checkbox" data-f="taxable" ${o.taxable !== false ? 'checked' : ''}>taxable</label><button class="btn small ghost" data-act="lr-del">Remove</button></div>`;
}
ACTS['lr-add'] = b => {
  const box = $(`#${b.dataset.kind}-list`);
  box.insertAdjacentHTML('beforeend', listRow(b.dataset.kind, box.children.length));
  wire(box);
};
ACTS['lr-del'] = b => b.closest('.lr').remove();
const readList = kind => $$(`[data-lr="${kind}"]`).map(r => Object.fromEntries($$('[data-f]', r).map(i => [i.dataset.f, i.type === 'checkbox' ? i.checked : i.value])))
  .filter(o => (o.label || '').trim());
ACTS['rf-save'] = async b => {
  const v = id => $(`#${id}`).value;
  const assumptions = Object.fromEntries($$('[data-assume]').map(i => [i.dataset.assume, i.value]));
  const body = { dob: v('rf-dob'), nation: v('rf-nation'), partner: v('rf-partner') === 'true', retire_country: v('rf-country'), horizon_age: v('rf-hz'),
    stop_age: v('rf-stop'), salary: v('rf-salary'), salary_growth: v('rf-sg'), cut_back_age: v('rf-cba'), cut_back_pct: v('rf-cbp'),
    contrib_pct: v('rf-cp'), contrib_method: v('rf-cm'), saving_monthly: v('rf-save'), spend_essential: v('rf-ess'), spend_extra: v('rf-extra'),
    spend_less_from_75: v('rf-75'), emergency_months: v('rf-em'), clear_mortgage_at_stop: v('rf-clear') === 'true', tax_free_cash: v('rf-tfc'),
    home_to_children: v('rf-home') === 'true', one_offs: readList('oo'), other_income: readList('oi'), assumptions };
  await busy(b, async () => {
    await api('/api/retirement', { method: 'PATCH', body });
    S.retOpen = true;
    toast('Saved. The plan has run again with your figures.');
    render();
  });
};

function retStartsFrom(d) {
  const st = d.start, pots = st.pots;
  const line = (label, v, go) => known(v) && Math.abs(v) > 0.5 ? `<tr><td>${label}</td><td class="r">${money(v, { dp: 0 })}</td><td class="r">${go ? `<a href="#" data-go="${go}">change</a>` : ''}</td></tr>` : '';
  return `<section class="panel"><details><summary><b>What the plan starts from</b> <span class="muted small">everything Whiskers knows about today</span></summary>
    <table class="small" style="margin-top:10px;max-width:640px"><tbody>
      ${line('Cash in the bank', pots.cash, 'settings')}${line('Owed on cards (cleared first)', -pots.owed, 'settings')}${line('ISAs', pots.isa, 'holdings')}${line('General investment accounts', pots.gia, 'holdings')}${line('Money abroad, at today’s rate', pots.abroad, 'settings')}
      ${st.dcs.map(x => line(`${esc(x.name)} <span class="tiny muted">pension pot, growing ${(+x.growth).toFixed(1)}% above inflation</span>`, x.value, x.kind === 'sipp' ? 'holdings' : 'pensions')).join('')}
      ${st.dbs.map(x => `<tr><td>${esc(x.name)} <span class="tiny muted">pays from ${x.start_age}</span></td><td class="r">${money(x.yearly, { dp: 0 })} a year</td><td class="r"><a href="#" data-go="pensions">change</a></td></tr>`).join('')}
      ${st.annuities.map(x => `<tr><td>${esc(x.name)} <span class="tiny muted">annuity</span></td><td class="r">${money(x.yearly, { dp: 0 })} a year</td><td class="r"><a href="#" data-go="pensions">change</a></td></tr>`).join('')}
      ${line('Property', st.property, 'settings')}
      ${(st.mortgages || []).map(m => line(`${esc(m.name || 'Mortgage')} still owed`, known(m.balance) ? -m.balance : null, 'mortgage')).join('')}
    </tbody></table>
    <p class="tiny muted" style="margin-top:6px">Your ISAs and general account are expected to grow at about ${(+st.mix.real).toFixed(1)}% a year above inflation: ${pct(st.mix.equity, { dp: 0 })} of them grows like shares, after about ${(+st.mix.charges).toFixed(2)}% a year in charges.</p>
    <details style="margin-top:10px"><summary class="small">The tax rules used</summary>
      <table class="small" style="margin-top:6px"><tbody>${(d.rules || []).map(r => `<tr><td>${esc(r.what)}</td><td>${esc(r.value)}<div class="tiny muted">${esc(r.note || '')}</div></td><td class="tiny">${r.source ? `<a href="${esc(r.source)}">source</a>` : ''}</td></tr>`).join('')}</tbody></table>
      <p class="tiny muted">Checked ${fmtDate(d.checked)}.</p></details>
  </details></section>`;
}

// ============================================================================ Pensions

const PENSION_ADD = { db: 'Add a final-salary or career-average pension', dc: 'Add a pension pot', annuity: 'Add an annuity', sa_ra: 'Add a South African retirement annuity' };
const PENSION_HELP = {
  db: 'A promise of so much a year for life, like the NHS, teachers’ or civil service schemes. Its yearly statement gives the pension built up so far.',
  dc: 'A pot of money invested for you: a workplace pension or a personal pension. Its statement gives the value of the pot.',
  annuity: 'An income already bought with a pension pot.',
  sa_ra: 'A South African retirement annuity, in rand. It counts at today’s exchange rate.',
};

async function vPensions(el) {
  const d = await api('/api/pensions');
  S.pens = d;
  const sp = d.state_pension;
  el.innerHTML = `<div class="stack-lg">
    <section class="panel"><div class="spread"><h2>Your pensions</h2>
      <div class="row wrap">${Object.entries(PENSION_ADD).map(([k, l]) => `<button class="btn small ${k === 'db' ? 'primary' : ''}" data-act="pen-add" data-kind="${k}">${esc(l)}</button>`).join('')}</div></div>
      <p class="lede">Each is shown as income from its own age on the Retirement plan. A promise of so much a year is never added to what you own as though it could be spent tomorrow.</p>
      ${d.items.length ? d.items.map(p => `<div class="pension"><div><b>${esc(p.name)}</b> <span class="kind">${esc(d.kinds[p.kind] || p.kind)}${p.provider ? `, ${esc(p.provider)}` : ''}</span>
          <div class="small"><span class="pv">${esc(p.describe)}</span>${p.kind === 'db' && p.accruing ? ', still building up' : ''}</div>
          <div class="tiny muted">${p.pot_as_of || p.yearly_as_of ? `From the statement of ${fmtDate(p.pot_as_of || p.yearly_as_of)}. ` : ''}${p.nominee ? `Nominated: ${esc(p.nominee)}.` : '<span class="warnline">No nomination recorded.</span>'}</div></div>
        <div class="row"><button class="btn small" data-act="pen-edit" data-id="${p.id}">Change</button><button class="btn small ghost danger" data-act="pen-del" data-id="${p.id}" data-name="${esc(p.name)}">Remove</button></div></div>`).join('')
        : '<p class="muted">None added yet. Start with the biggest; its latest statement has what’s needed.</p>'}
      ${d.sipps.length ? `<p class="small" style="margin-top:10px">Tracked on the Investments tab, not here (adding them again would count them twice): ${d.sipps.map(x => `${esc(x.name)} ${money(x.total, { dp: 0 })}`).join(', ')}.</p>` : ''}
    </section>
    <section class="panel"><h2>The State Pension</h2>
      ${sp && known(sp.weekly) ? `<p>${money(sp.weekly, { dp: 2 })} a week (${money(sp.yearly, { dp: 0 })} a year) from ${esc(d.spa.words)}, on ${fmtDate(d.spa.date)}: ${esc(sp.basis)}.</p>` : '<p class="muted">Not entered yet.</p>'}
      <div style="margin-top:8px"><button class="btn small" data-go="statepension">Look at the State Pension</button></div></section>
    <section class="panel"><h2>Worth knowing</h2><ul class="small" style="padding-left:18px;display:grid;gap:6px;margin-top:6px">
      <li>From 6 April 2027, money left in a pension pot when you die counts towards inheritance tax. A nomination tells each scheme who should receive it; a will doesn’t always reach a pension.</li>
      <li>Most people can take a quarter of a pot tax-free, up to £268,275 across all of them. The rest is taxed as income when it comes out.</li>
      <li>The earliest age a pot can be touched rises from 55 to 57 on 6 April 2028.</li>
      <li>Pension Wise gives free, impartial guidance to anyone 50 or over: <a href="https://www.moneyhelper.org.uk/en/pensions-and-retirement/pension-wise">moneyhelper.org.uk</a>. Lost track of an old workplace pension? <a href="https://www.gov.uk/find-pension-contact-details">gov.uk’s Pension Tracing Service</a> finds it.</li>
    </ul></section>
  </div>`;
}

function pensionForm(kind, p) {
  p = p || {};
  const d = S.pens;
  const v = (k, dflt = '') => (p[k] === null || p[k] === undefined ? dflt : p[k]);
  const f = (id, label, val, o = {}) => `<label class="field ${o.full ? 'full' : ''}">${label}<input type="${o.type || 'number'}" id="${id}" value="${esc(val)}" ${o.step ? `step="${o.step}"` : 'step="any"'} ${o.ph ? `placeholder="${esc(o.ph)}"` : ''}>${o.help ? `<span class="help">${o.help}</span>` : ''}</label>`;
  const sel = (id, label, opts, cur, help) => `<label class="field">${label}<select id="${id}">${Object.entries(opts).map(([k, l]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>${help ? `<span class="help">${help}</span>` : ''}</label>`;
  const ccy = kind === 'sa_ra' ? 'R' : '£';
  let fields = f('pf-name', 'Name', v('name'), { type: 'text', ph: kind === 'db' ? 'NHS Pension' : kind === 'sa_ra' ? 'Allan Gray RA' : 'Aviva workplace pension' }) +
    f('pf-provider', 'Provider (optional)', v('provider'), { type: 'text' });
  if (kind === 'db') {
    fields += f('pf-yearly', 'Pension a year built up so far (£)', v('yearly'), { step: 100, help: 'From the latest statement or the scheme’s online portal. In today’s money.' }) +
      f('pf-yearly-on', 'As at', String(v('yearly_as_of')).slice(0, 10), { type: 'date' }) +
      f('pf-normal', 'The scheme’s pension age', v('normal_age'), { step: 1, ph: '67', help: 'NHS 2015 scheme: your State Pension age. 1995 section: 60.' }) +
      f('pf-start', 'When you’ll take it (age)', v('start_age'), { step: 0.5, ph: 'the scheme’s age' }) +
      f('pf-early', 'Reduction for each year taken early (%)', v('early_reduction'), { step: 0.1, ph: '5', help: 'Often about 5% a year. The scheme’s own figures win.' }) +
      f('pf-lump', 'Automatic lump sum (£)', v('lump_sum'), { step: 100, ph: '0', help: 'Some older schemes (the NHS 1995 section) pay one as well as the pension.' }) +
      f('pf-commute', 'Pension swapped for cash (%)', v('commute_pct'), { step: 1, ph: '0' }) +
      f('pf-factor', 'Cash for each £1 a year given up', v('commute_factor'), { step: 0.5, ph: '12', help: 'The NHS pays £12.' }) +
      sel('pf-index', 'How it rises once paid', d.indexation, v('indexation', 'cpi')) +
      f('pf-cap', 'Cap or fixed rise (% a year)', v('index_cap'), { step: 0.1, ph: '5' }) +
      sel('pf-accruing', 'Still building up while you work?', { 0: 'No', 1: 'Yes' }, String(v('accruing', 0) ? 1 : 0)) +
      f('pf-accrual', 'Extra pension a year for each year worked (£)', v('accrual_yearly'), { step: 50, help: 'NHS 2015 scheme: 1/54 of each year’s pensionable pay.' }) +
      f('pf-spouse', 'For a husband, wife or partner after you (%)', v('spouse_pct'), { step: 5, ph: '50' });
  } else if (kind === 'annuity') {
    fields += f('pf-yearly', 'Income a year (£)', v('yearly'), { step: 100 }) +
      f('pf-start', 'Paid from (age)', v('start_age'), { step: 0.5, ph: 'now' }) +
      sel('pf-index', 'How it rises', d.indexation, v('indexation', 'none')) +
      f('pf-cap', 'Cap or fixed rise (% a year)', v('index_cap'), { step: 0.1 }) +
      f('pf-spouse', 'For a husband, wife or partner after you (%)', v('spouse_pct'), { step: 5 });
  } else {
    fields += f('pf-pot', `Value of the pot (${ccy})`, v('pot'), { step: 100 }) +
      f('pf-pot-on', 'As at', String(v('pot_as_of')).slice(0, 10), { type: 'date' }) +
      f('pf-contrib', `Going in each month, you and any employer (${ccy})`, v('contrib_monthly'), { step: 10, ph: '0' }) +
      f('pf-start', 'Start taking it at (age)', v('start_age'), { step: 0.5, ph: 'when you stop work', help: kind === 'sa_ra' ? 'In South Africa, from 55.' : 'From 55, or 57 from April 2028.' }) +
      (kind === 'dc' ? sel('pf-take', 'How you’ll take it', d.take, v('take', 'drawdown')) : '') +
      f('pf-growth', 'Growth above inflation (% a year)', v('growth'), { step: 0.1, ph: 'the plan’s default', help: 'Blank uses the plan’s figure for a typical balanced fund.' }) +
      f('pf-charges', 'Charges (% a year)', v('charges'), { step: 0.05, ph: '0.5' });
  }
  fields += f('pf-nominee', 'Nominated to receive it', v('nominee'), { type: 'text', ph: 'Who the scheme should pay', full: kind !== 'db' }) +
    `<label class="field full">Notes (optional)<input type="text" id="pf-notes" value="${esc(v('notes'))}"></label>`;
  openModal({ title: p.id ? `Change ${p.name}` : PENSION_ADD[kind], wide: true,
    body: `<p class="small muted" style="max-width:80ch">${esc(PENSION_HELP[kind])}${kind === 'sa_ra' ? ' South African tax on it is not modelled.' : ''}</p><div class="form-grid" style="margin-top:12px">${fields}</div>`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="pen-save" data-id="${p.id || ''}" data-kind="${kind}">Save</button>` });
}
ACTS['pen-add'] = b => pensionForm(b.dataset.kind, null);
ACTS['pen-edit'] = b => { const p = S.pens.items.find(x => x.id === +b.dataset.id); if (p) pensionForm(p.kind, p); };
ACTS['pen-save'] = async b => {
  const kind = b.dataset.kind;
  const val = id => $(`#${id}`) ? $(`#${id}`).value : undefined;
  const body = { kind, name: val('pf-name'), provider: val('pf-provider'), nominee: val('pf-nominee'), notes: val('pf-notes') };
  const map = { 'pf-yearly': 'yearly', 'pf-yearly-on': 'yearly_as_of', 'pf-normal': 'normal_age', 'pf-start': 'start_age', 'pf-early': 'early_reduction',
    'pf-lump': 'lump_sum', 'pf-commute': 'commute_pct', 'pf-factor': 'commute_factor', 'pf-index': 'indexation', 'pf-cap': 'index_cap',
    'pf-accruing': 'accruing', 'pf-accrual': 'accrual_yearly', 'pf-spouse': 'spouse_pct', 'pf-pot': 'pot', 'pf-pot-on': 'pot_as_of',
    'pf-contrib': 'contrib_monthly', 'pf-take': 'take', 'pf-growth': 'growth', 'pf-charges': 'charges' };
  for (const [id, k] of Object.entries(map)) if ($(`#${id}`)) body[k] = val(id);
  if (body.accruing !== undefined) body.accruing = body.accruing === '1';
  if (kind === 'sa_ra') body.currency = 'ZAR';
  await busy(b, async () => {
    if (b.dataset.id) await api(`/api/pensions/${b.dataset.id}`, { method: 'PATCH', body });
    else await api('/api/pensions', { method: 'POST', body });
    closeModal(); toast('Saved.'); render();
  });
};
ACTS['pen-del'] = async b => {
  if (!await confirmBox(`Remove ${b.dataset.name}?`, 'It comes out of the retirement plan and the Overall picture. The pension itself is not touched.', 'Remove', true)) return;
  await api(`/api/pensions/${b.dataset.id}`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  render();
};

// ============================================================================ State Pension

async function vStatePension(el) {
  const d = await api('/api/pensions');
  const s = d.settings, sp = d.state_pension, spa = d.spa;
  const stored = s.state_pension || {};
  el.innerHTML = `<div class="stack-lg">
    <div class="grid g2">
      <section class="panel"><h2>When</h2>
        ${spa ? `<div class="fig" style="font-size:2rem">${esc(spa.words)}</div><p>On ${fmtDate(spa.date)}.</p>${spa.note ? `<p class="small muted" style="margin-top:6px">${esc(spa.note)}</p>` : ''}`
          : `<p class="muted">Add your date of birth first.</p><div class="row" style="margin-top:8px"><input type="date" id="sp-dob"><button class="btn small" data-act="sp-dob">Save</button></div>`}
      </section>
      <section class="panel"><h2>How much</h2>
        ${sp && known(sp.weekly) ? `<div class="fig" style="font-size:2rem">${money(sp.weekly, { dp: 2 })} <span class="muted" style="font-size:1rem">a week</span></div>
          <p>${money(sp.yearly, { dp: 0 })} a year in today’s money: ${esc(sp.basis)}. The full new State Pension is ${money(sp.full_weekly, { dp: 2 })} a week in 2026–27.</p>`
          : '<p class="muted">Not known yet. Your forecast from gov.uk is the best figure; failing that, the years on your record give a rough one.</p>'}
        ${sp && known(sp.years_at_pension_age) ? `<p class="small" style="margin-top:6px">About ${sp.years_at_pension_age} qualifying years by State Pension age, counting the years you plan to keep working. ${sp.short_by ? `That is ${sp.short_by} short of the 35 for the full amount.` : 'Enough for the full amount.'}</p>` : ''}
      </section>
    </div>
    ${sp && sp.top_up ? `<section class="plan-box"><h2>Filling a gap might pay</h2>
      <p style="margin-top:6px">Each year bought costs about ${money(sp.top_up.cost_each, { dp: 0 })} (voluntary Class 3 contributions) and adds about ${money(sp.top_up.adds_each, { dp: 0 })} a year to the State Pension for life, so it pays for itself in about ${sp.top_up.pays_back_years} years of drawing it.
        You could fill up to ${plural(sp.top_up.years, 'year')}. The ${esc(sp.top_up.oldest_year)} year can only be filled until <b>${esc(sp.top_up.oldest_deadline)}</b>.</p>
      <p class="small" style="margin-top:6px">Check first: years you’ll work anyway, and credits, may already fill the gap. The Future Pension Centre (0800 731 0175) confirms whether a year would add anything before you pay. <a href="${esc(sp.top_up.source)}">More on topping up</a>.</p></section>` : ''}
    <section class="panel"><h2>Your record</h2>
      <p class="lede">Your forecast and National Insurance record are on gov.uk: search for <a href="https://www.gov.uk/check-state-pension">“Check your State Pension forecast”</a>. It takes a Government Gateway or GOV.UK One Login account.</p>
      <div class="form-grid">
        <label class="field">Your forecast (£ a week)<input type="number" id="sp-weekly" step="0.01" min="0" max="1000" value="${esc(stored.weekly ?? '')}"><span class="help">The forecast already assumes you keep working to State Pension age.</span></label>
        <label class="field">Qualifying years so far<input type="number" id="sp-years" step="1" min="0" max="60" value="${esc(stored.years ?? '')}"><span class="help">35 for the full amount, at least 10 for any. Years worked in South Africa don’t count.</span></label>
        <label class="field">Gaps your record says you could fill<input type="number" id="sp-gaps" step="1" min="0" max="20" value="${esc(stored.gaps ?? '')}"><span class="help">Usually only the last six tax years can be filled.</span></label>
      </div>
      <div class="row" style="margin-top:10px"><button class="btn primary" data-act="sp-save">Save</button></div>
    </section>
    ${s.retire_country !== 'uk' ? `<section class="panel"><h2>Living in South Africa</h2><p class="small">A UK State Pension can be paid to someone living in South Africa, but it is frozen: it stays at the amount first paid and never rises, so it buys a little less each year. The retirement plan allows for that because you said you’ll live there${s.retire_country === 'both' ? ' some of the time (it assumes frozen only if you choose South Africa alone)' : ''}.</p></section>` : ''}
  </div>`;
}
ACTS['sp-save'] = async b => {
  await busy(b, async () => {
    await api('/api/retirement', { method: 'PATCH', body: { state_pension: { weekly: $('#sp-weekly').value, years: $('#sp-years').value, gaps: $('#sp-gaps').value } } });
    toast('Saved.'); render();
  });
};
ACTS['sp-dob'] = async b => {
  await busy(b, async () => { await api('/api/retirement', { method: 'PATCH', body: { dob: $('#sp-dob').value } }); render(); });
};
