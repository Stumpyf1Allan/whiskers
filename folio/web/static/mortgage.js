/* Whiskers: the Mortgage section, brought from Mittens & Pence. Off unless switched on in
   Settings, Sections; off, it shows nothing and counts towards nothing.

   A mortgage balance alone answers nothing. The four things worth knowing are the split of
   each payment between interest and capital, the date the fixed rate ends, what an
   overpayment is really worth, and the equity. Between statements the balance is
   projected from the last one, and the screen says so rather than showing a year-old
   figure as today's. */
'use strict';

VIEWS.mortgage = { title: 'Mortgage', section: 'mortgage', sub: 'The balance running down, when the fixed rate ends, and what paying more would save.', render: vMortgage };

const monthYear = iso => { if (!iso) return '—'; const [y, m] = String(iso).slice(0, 10).split('-').map(Number); return `${MONTHS[m - 1]} ${y}`; };
const KIND_WORD = { repayment: 'Repayment', interest_only: 'Interest only', part_and_part: 'Part and part' };

async function vMortgage(el) {
  const d = await api('/api/mortgages');
  S.mortMarket = d.market;
  S.mortAssets = d.assets;
  if (!d.items.length) {
    el.innerHTML = `<div class="stack-lg" style="max-width:900px"><section class="panel"><h2>Add your mortgage</h2>
      <p class="lede">Only the lender and the balance are needed to start. Every extra figure unlocks something: a rate and a payment give the split between interest and capital and the date it clears; the date the fixed rate ends gives a warning months before it does; the home’s value gives your equity.</p>
      <p class="small" style="max-width:75ch">Most of it is on the yearly statement, or in the lender’s app: the balance, the rate, the monthly payment, and the date the deal ends.</p>
      <div class="row" style="margin-top:12px"><button class="btn primary" data-act="mort-new">Add your mortgage</button></div></section>
      <p class="note">No mortgage? Switch this section off in Settings, Sections.</p></div>`;
    return;
  }
  const details = await Promise.all(d.items.map(s => api(`/api/mortgages/${s.id}`).catch(() => null)));
  const soon = d.items.find(s => known(s.days_to_rate_change) && s.days_to_rate_change <= 200);
  setDot('mortgage', soon ? (soon.days_to_rate_change < 0 ? 'red' : 'amber') : null);
  el.innerHTML = `<div class="stack-lg">${d.items.map((s, i) => mortgagePanel(s, details[i], d.stop_age, d.dob)).join('')}
    <div class="row"><button class="btn" data-act="mort-new">Add another mortgage</button></div>
    <p class="note">Arithmetic on the figures you have given, at today’s rate and payment. Your lender’s own figures win if they differ. Not financial advice.</p></div>`;
  d.items.forEach(s => { if (s.revert_rate) rateEffect(s.id, s.revert_rate, `#mr-${s.id}`, s); });
}

function mortgagePanel(s, d, stopAge, dob) {
  const ccy = s.currency || 'GBP';
  const m = (v, o) => ccy === 'GBP' ? money(v, o) : `<span class="pv">${esc(ccy)} ${known(v) ? Math.round(v).toLocaleString('en-GB') : '—'}</span>`;
  const fixDays = s.days_to_rate_change;
  const fix = !s.fixed_until || !known(fixDays) ? null
    : fixDays < 0 ? { cls: 'red', text: `The ${esc(s.rate_type || 'fixed')} rate ended ${-fixDays} days ago` }
    : fixDays <= 200 ? { cls: 'amber', text: `${fixDays} days until the rate changes` }
    : { cls: '', text: `Fixed until ${fmtDate(s.fixed_until)}` };
  const curve = (d && d.curve) || [];
  const stopYear = dob && stopAge ? +dob.slice(0, 4) + Math.round(+stopAge) : null;
  const chart = curve.length > 1 ? Charts.line({
    series: [{ name: 'Still owed', points: curve.map(p => [p.on, p.balance]), color: 'var(--accent)', area: true }],
    money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney, zero: true,
    vlines: [s.fixed_until ? { at: s.fixed_until, label: 'rate ends', color: 'var(--amber)' } : null,
             stopYear ? { at: `${stopYear}-06-30`, label: 'you stop work', color: 'var(--cyan)' } : null].filter(Boolean),
  }, 220) : '<p class="small muted">Add a rate and a monthly payment and the run-down appears here.</p>';
  // Where each year's payments go: interest against capital, the reason the section exists.
  const byYear = {};
  for (const r of (d && d.schedule) || []) {
    const y = r.on.slice(0, 4);
    const b = byYear[y] || (byYear[y] = { interest: 0, capital: 0 });
    b.interest += r.interest; b.capital += Math.max(0, r.capital);
  }
  const years = Object.entries(byYear).slice(0, 40);
  const split = years.length > 1 ? Charts.bars({ items: years.map(([y, v]) => ({ label: y, long: `${y}`, parts: [
      { name: 'Off the balance', value: v.capital, color: 'var(--accent)' }, { name: 'Interest', value: v.interest, color: 'var(--amber)' }] })),
    money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney }, 190) : '';
  const allowance = known(s.overpay_allowance) && known(s.balance) ? s.balance * s.overpay_allowance / 100 : null;
  return `<section class="panel mort-card">
    <div class="spread"><div><h2>${esc(s.name || s.lender || 'Mortgage')}</h2>
      <p class="small muted">${esc(s.lender || '')}${s.lender ? ' · ' : ''}${known(s.rate) ? `${(+s.rate).toFixed(2)}% ${esc(s.rate_type || '')}` : 'rate not entered'} · ${esc(KIND_WORD[s.repayment_type] || '')}</p></div>
      ${fix ? `<span class="chip ${fix.cls}">${fix.text}</span>` : ''}</div>
    <div class="stat-row">
      <div class="stat"><span class="k">Still owed</span><span class="v">${m(s.balance, { dp: 0 })}</span>
        <span class="tiny muted">${s.estimated && s.projected_months ? `projected from ${fmtDate(s.confirmed_on)}` : s.confirmed_on ? `as at ${fmtDate(s.confirmed_on)}` : 'no balance yet'}</span></div>
      <div class="stat"><span class="k">Monthly payment</span><span class="v">${m(s.monthly_payment, { dp: 2 })}</span>
        <span class="tiny muted">${known(s.interest_this_month) && known(s.capital_this_month) ? `${m(s.interest_this_month, { dp: 0 })} interest, ${m(s.capital_this_month, { dp: 0 })} off the balance` : s.repayment_type === 'interest_only' ? 'interest only' : '—'}</span></div>
      ${s.repayment_type === 'interest_only'
        ? `<div class="stat"><span class="k">Term ends</span><span class="v">${s.payoff_on ? monthYear(s.payoff_on) : '—'}</span>
        <span class="tiny muted">${known(s.balance) && s.payoff_on ? `${m(s.balance, { dp: 0 })} to repay then` : 'add when it started and its term'}</span></div>`
        : `<div class="stat"><span class="k">Clears</span><span class="v">${s.payoff_on ? monthYear(s.payoff_on) : '—'}</span>
        <span class="tiny muted">${known(s.months_left) ? `${Math.round(s.months_left / 12 * 10) / 10} years from now` : 'needs a rate and a payment'}${known(s.paid_off) ? `, ${pct(s.paid_off, { dp: 0 })} paid off` : ''}</span></div>`}
      <div class="stat"><span class="k">${known(s.equity) ? 'Your equity' : 'Interest still to pay'}</span><span class="v">${m(known(s.equity) ? s.equity : s.interest_remaining, { dp: 0 })}</span>
        <span class="tiny muted">${known(s.ltv) ? `${pct(s.ltv, { dp: 0 })} loan to value` : known(s.interest_remaining) ? 'over the rest of the term' : 'add the home’s value for equity'}</span></div>
    </div>
    ${known(s.paid_off) ? `<div class="mort-bar" title="Paid off"><i style="width:${Math.max(2, Math.round(s.paid_off * 100))}%"></i></div>` : ''}
    ${s.never_clears ? '<p class="warnline">That payment doesn’t cover the interest, so the balance grows rather than shrinks. Check the rate and the payment: one of them isn’t what the lender has.</p>' : ''}
    ${s.term_mismatch ? `<p class="warnline">At this payment it clears in ${monthYear(s.term_mismatch.payoff_on)}, but the term ends ${monthYear(s.term_mismatch.term_ends_on)}, ${s.term_mismatch.months} months apart. Either the payment or the rate on file isn’t right.</p>` : ''}
    ${s.ahead_by_months ? `<p class="small">About ${Math.round(s.ahead_by_months / 12 * 10) / 10} years ahead of the original term.</p>` : ''}
    <div class="grid g2">
      <div><h3>${s.repayment_type === 'interest_only' ? 'The balance (interest only: it stays put until the term ends)' : 'How it runs down'}</h3><div style="margin-top:6px">${chart}</div>
        ${known(s.interest_remaining) ? `<p class="chart-note">${m(s.interest_remaining, { dp: 0 })} of interest still to pay at today’s rate and payment.</p>` : ''}</div>
      <div><h3>Where each year’s payments go</h3><div style="margin-top:6px">${split || '<p class="small muted">Needs a rate and a payment.</p>'}</div>
        ${split ? '<div class="legend" style="margin-top:4px"><span><i style="background:var(--accent)"></i>Off the balance</span><span><i style="background:var(--amber)"></i>Interest</span></div>' : ''}</div>
    </div>
    <div class="grid g2">
      <div class="stack" style="gap:8px"><h3>What paying more would do</h3>
        <div class="row wrap"><input type="number" id="mo-amt-${s.id}" min="0" step="50" placeholder="200" style="width:120px" aria-label="Overpayment">
          <select id="mo-kind-${s.id}"><option value="monthly">every month</option><option value="once">once, now</option></select>
          <button class="btn small" data-act="mort-over" data-id="${s.id}">Work it out</button></div>
        <div id="mo-out-${s.id}" class="small"></div>
        <p class="tiny muted">${allowance ? `Your deal lets you overpay about ${m(allowance, { dp: 0 })} a year (${s.overpay_allowance}% of the balance) without a charge. ` : 'Most fixed deals allow 10% of the balance a year without a charge. '}${s.erc_note ? esc(s.erc_note) : ''}</p>
      </div>
      <div class="stack" style="gap:8px"><h3>When the fixed rate ends</h3>
        ${s.revert_rate ? `<div id="mr-${s.id}" class="small muted">Working it out…</div>` : '<p class="small muted">Add the rate it reverts to (on the offer letter) to see the payment after the deal ends.</p>'}
        <div class="row wrap"><input type="number" id="mr-rate-${s.id}" step="0.01" min="0" max="20" placeholder="${S.mortMarket ? S.mortMarket.avg_fix_5y : 6}" style="width:100px" aria-label="A new rate">
          <button class="btn small" data-act="mort-rate" data-id="${s.id}">Try a rate</button></div>
        <div id="mr-try-${s.id}" class="small"></div>
        ${S.mortMarket ? `<p class="tiny muted">New fixes averaged ${S.mortMarket.avg_fix_2y.toFixed(2)}% for two years and ${S.mortMarket.avg_fix_5y.toFixed(2)}% for five on ${fmtDate(S.mortMarket.as_of)} (Moneyfacts). Most lenders let you book a new deal three to six months ahead.</p>` : ''}
      </div>
    </div>
    <details><summary><b>History</b> <span class="muted small">${plural(((d && d.events) || []).length, 'entry', 'entries')}</span></summary>
      <table class="small" style="margin-top:8px;max-width:640px"><tbody>${((d && d.events) || []).map(e => `<tr><td class="nowrap">${fmtDate(e.happened_on)}</td>
        <td>${esc({ statement: 'Balance from a statement', overpayment: 'Overpayment', rate_change: 'Rate changed', valuation: 'Home valued' }[e.kind] || e.kind)}${e.note ? `<div class="tiny muted">${esc(e.note)}</div>` : ''}</td>
        <td class="r">${known(e.amount) ? m(e.amount, { dp: 0 }) : ''}${known(e.rate) ? `${(+e.rate).toFixed(2)}%` : ''}</td></tr>`).join('') || '<tr><td class="muted">Nothing recorded yet.</td></tr>'}</tbody></table></details>
    <div class="row wrap">
      <button class="btn small" data-act="mort-event" data-id="${s.id}" data-kind="statement">Update the balance</button>
      <button class="btn small" data-act="mort-event" data-id="${s.id}" data-kind="overpayment">Record an overpayment</button>
      <button class="btn small" data-act="mort-event" data-id="${s.id}" data-kind="rate_change">Record a new rate</button>
      <button class="btn small" data-act="mort-event" data-id="${s.id}" data-kind="valuation">Record a valuation</button>
      <button class="btn small ghost" data-act="mort-edit" data-id="${s.id}">Change the details</button>
    </div>
  </section>`;
}

async function rateEffect(id, rate, sel, s) {
  try {
    const r = await api(`/api/mortgages/${id}/rate-change?rate=${encodeURIComponent(rate)}`);
    const el = $(sel);
    if (!el) return;
    el.className = 'small';
    el.innerHTML = r.available ? `At ${(+rate).toFixed(2)}% the payment becomes <b>${money(r.payment_then, { dp: 0 })}</b> a month, ${r.difference >= 0 ? 'up' : 'down'} ${money(Math.abs(r.difference), { dp: 0 })} from ${money(r.payment_now, { dp: 0 })}${s && s.fixed_until ? `, from ${monthYear(s.fixed_until)}` : ''}.`
      : 'Not enough on file to work that out.';
  } catch (e) { /* the panel says nothing rather than something wrong */ }
}

ACTS['mort-over'] = async b => {
  const id = b.dataset.id, amt = +$(`#mo-amt-${id}`).value;
  if (!(amt > 0)) { toast('Type an amount first.', true); return; }
  await busy(b, async () => {
    const r = await api(`/api/mortgages/${id}/overpayment?amount=${amt}&kind=${$(`#mo-kind-${id}`).value}`);
    $(`#mo-out-${id}`).innerHTML = r.available ? `<div class="plan-box" style="margin-top:4px">${r.interest_only
      ? `<b>${money(r.interest_saved, { dp: 0 })}</b> less interest, and <b>${money(r.end_balance_after, { dp: 0 })}</b> left to repay when the term ends${r.term_ends_on ? ` in ${monthYear(r.term_ends_on)}` : ''}, instead of ${money(r.end_balance_before, { dp: 0 })}.`
      : `<b>${money(r.interest_saved, { dp: 0 })}</b> less interest, and <b>${plural(r.months_saved, 'month')}</b> sooner: clear by ${monthYear(r.new_payoff_on)} instead of ${monthYear(r.old_payoff_on)}.`}
      <div class="tiny muted" style="margin-top:4px">${esc(r.caveat)}</div></div>` : `<p class="muted">${esc(r.why)}</p>`;
  });
};
ACTS['mort-rate'] = async b => {
  const id = b.dataset.id, rate = $(`#mr-rate-${id}`).value || (S.mortMarket && S.mortMarket.avg_fix_5y);
  if (!rate) return;
  $(`#mr-try-${id}`).innerHTML = '<span class="muted">Working it out…</span>';
  await rateEffect(id, rate, `#mr-try-${id}`, null);
};
ACTS['mort-new'] = () => mortgageForm(null);
ACTS['mort-edit'] = async b => {
  const d = await api(`/api/mortgages/${b.dataset.id}`).catch(e => { toast(e.message, true); return null; });
  if (d) mortgageForm(d.record);
};

function mortgageEvent(id, kind) {
  const today = new Date().toISOString().slice(0, 10);
  const titles = { statement: 'Update the balance', overpayment: 'Record an overpayment', rate_change: 'Record a new rate', valuation: 'Record a valuation of the home' };
  const isRate = kind === 'rate_change';
  openModal({ title: titles[kind], body: `<div class="form-grid">
      <label class="field">Date<input type="date" id="me-date" value="${today}" max="${today}"></label>
      <label class="field">${isRate ? 'New rate (%)' : kind === 'valuation' ? 'What it’s worth' : 'Amount'}<input type="number" id="me-amt" step="${isRate ? '0.01' : '1'}" min="0" placeholder="${isRate ? '4.29' : ''}"></label>
      <label class="field full">Note (optional)<input type="text" id="me-note" placeholder="Anything you’ll want to remember"></label></div>
      ${kind === 'statement' ? '<p class="note" style="margin-top:10px">Statements usually come once a year. In between, Whiskers projects the balance from this figure and says so.</p>' : ''}
      ${isRate ? '<p class="note" style="margin-top:10px">Also change the monthly payment in the details if the lender has told you the new one.</p>' : ''}`,
    foot: `<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="me-save" data-id="${id}" data-kind="${kind}">Save</button>` });
}
ACTS['mort-event'] = b => mortgageEvent(b.dataset.id, b.dataset.kind);
ACTS['me-save'] = async b => {
  const v = $('#me-amt').value.trim(), isRate = b.dataset.kind === 'rate_change';
  if (!v) { toast(isRate ? 'Type the new rate.' : 'Type an amount.', true); return; }
  await busy(b, async () => {
    await api(`/api/mortgages/${b.dataset.id}/events`, { method: 'POST', body: { kind: b.dataset.kind, happened_on: $('#me-date').value,
      amount: isRate ? null : v, rate: isRate ? v : null, note: $('#me-note').value } });
    closeModal(); toast('Saved.'); render();
  });
};

function mortgageForm(r) {
  r = r || {};
  const v = (k, d = '') => (r[k] === null || r[k] === undefined ? d : r[k]);
  const homes = (S.mortAssets || []).filter(a => a.kind === 'property');
  const opt = (list, cur) => list.map(([k, l]) => `<option value="${k}" ${cur === k ? 'selected' : ''}>${l}</option>`).join('');
  openModal({ title: r.id ? 'The mortgage’s details' : 'Add your mortgage', wide: true, body: `
    <p class="small muted" style="max-width:80ch">Only a name and the balance are needed to start; everything else can wait for the next statement. Each extra figure unlocks something on the screen.</p>
    <div class="form-grid" style="margin-top:12px">
      <label class="field">Name<input type="text" id="mf-name" value="${esc(v('name'))}" placeholder="Home mortgage"></label>
      <label class="field">Lender<input type="text" id="mf-lender" value="${esc(v('lender'))}" placeholder="Nationwide"></label>
      <label class="field">Balance owed<input type="number" id="mf-bal" step="0.01" min="0" value="${esc(v('statement_balance'))}"><span class="help">From the latest statement or the lender’s app.</span></label>
      <label class="field">On<input type="date" id="mf-bal-on" value="${esc(String(v('statement_on')).slice(0, 10))}"></label>
      <label class="field">Monthly payment<input type="number" id="mf-pay" step="0.01" min="0" value="${esc(v('monthly_payment'))}"></label>
      <label class="field">Interest rate (%)<input type="number" id="mf-rate" step="0.01" min="0" max="20" value="${esc(v('rate'))}" placeholder="4.29"></label>
      <label class="field">Kind of rate<select id="mf-ratetype">${opt([['fixed', 'Fixed'], ['variable', 'Variable (SVR)'], ['tracker', 'Tracker'], ['discount', 'Discount']], v('rate_type', 'fixed'))}</select></label>
      <label class="field">The deal ends on<input type="date" id="mf-fixed" value="${esc(String(v('fixed_until')).slice(0, 10))}"><span class="help">The date worth knowing: a warning comes 200 days before.</span></label>
      <label class="field">Rate it moves to after that (%)<input type="number" id="mf-revert" step="0.01" min="0" max="20" value="${esc(v('revert_rate'))}" placeholder="7.49"><span class="help">The lender’s standard variable rate, on the offer letter.</span></label>
      <label class="field">Kind of mortgage<select id="mf-type">${opt([['repayment', 'Repayment'], ['interest_only', 'Interest only'], ['part_and_part', 'Part and part']], v('repayment_type', 'repayment'))}</select></label>
      <label class="field">The home it’s on<select id="mf-prop"><option value="">Type its value instead</option>${homes.map(a => `<option value="${a.id}" ${+v('property_asset_id') === a.id ? 'selected' : ''}>${esc(a.name)}${known(a.value) ? ` (£${Math.round(a.value).toLocaleString('en-GB')})` : ''}</option>`).join('')}</select>
        <span class="help">${homes.length ? 'One figure for the house, kept in Settings, so two can never disagree.' : 'Add your home in Settings to keep one figure for it.'}</span></label>
      <label class="field">The home is worth<input type="number" id="mf-value" step="1000" min="0" value="${esc(v('property_value'))}" ${r.property_asset_id ? 'disabled' : ''}></label>
      <label class="field">Overpay without a charge (% of the balance a year)<input type="number" id="mf-allow" step="1" min="0" max="100" value="${esc(v('overpay_allowance'))}" placeholder="10"></label>
      <label class="field">Early repayment charges, in your words<input type="text" id="mf-erc" value="${esc(v('erc_note'))}" placeholder="3% until March 2027, then 2%"></label>
    </div>
    <details style="margin-top:14px"><summary class="small">The original loan, if you have it</summary>
      <div class="form-grid" style="margin-top:10px">
        <label class="field">Amount borrowed<input type="number" id="mf-orig" step="1" min="0" value="${esc(v('original_amount'))}"></label>
        <label class="field">Started on<input type="date" id="mf-start" value="${esc(String(v('started_on')).slice(0, 10))}"></label>
        <label class="field">Term in years<input type="number" id="mf-term" step="1" min="1" max="45" value="${r.term_months ? Math.round(r.term_months / 12) : ''}" placeholder="25"></label>
      </div><p class="tiny muted" style="margin-top:6px">These give the “paid off” share and let Whiskers check the payment clears it by the end of the term.</p></details>
    <label class="field" style="margin-top:12px">Notes (optional)<input type="text" id="mf-notes" value="${esc(v('notes'))}"></label>`,
    foot: `${r.id ? `<button class="btn ghost danger" data-act="mort-del" data-id="${r.id}">Remove the mortgage</button>` : ''}<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="mf-save" data-id="${r.id || ''}">Save</button>` });
  $('#mf-prop').addEventListener('change', e => { $('#mf-value').disabled = !!e.target.value; if (e.target.value) $('#mf-value').value = ''; });
}
ACTS['mf-save'] = async b => {
  const years = +$('#mf-term').value || 0;
  const body = { name: $('#mf-name').value, lender: $('#mf-lender').value, statement_balance: $('#mf-bal').value,
    statement_on: $('#mf-bal-on').value || ($('#mf-bal').value ? new Date().toISOString().slice(0, 10) : ''),
    monthly_payment: $('#mf-pay').value, rate: $('#mf-rate').value, rate_type: $('#mf-ratetype').value,
    fixed_until: $('#mf-fixed').value, revert_rate: $('#mf-revert').value, repayment_type: $('#mf-type').value,
    property_asset_id: $('#mf-prop').value, property_value: $('#mf-prop').value ? '' : $('#mf-value').value,
    overpay_allowance: $('#mf-allow').value, erc_note: $('#mf-erc').value, original_amount: $('#mf-orig').value,
    started_on: $('#mf-start').value, term_months: years ? Math.round(years * 12) : '', notes: $('#mf-notes').value };
  await busy(b, async () => {
    if (b.dataset.id) await api(`/api/mortgages/${b.dataset.id}`, { method: 'PATCH', body });
    else await api('/api/mortgages', { method: 'POST', body });
    closeModal(); toast('Saved.'); render();
  });
};
ACTS['mort-del'] = async b => {
  if (!await confirmBox('Remove this mortgage?', 'Its details and history go. Your home, if it is saved in Settings, stays.', 'Remove', true)) return;
  await api(`/api/mortgages/${b.dataset.id}`, { method: 'DELETE' }).catch(e => toast(e.message, true));
  closeModal();
  render();
};

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

// Only while a section is on: with both off there is no net worth for them to count in.
SETTINGS_PANELS.middle.push(() => !SECTIONS.some(sectionOn) ? '' : `<section class="panel" id="assets-panel"><div class="spread"><h2>Your home and other things you own</h2><button class="btn" data-act="asset-add">Add one</button></div>
  <p class="lede">Counted in your net worth on the Overview. A mortgage can take the home’s value from here, so there is one figure for the house, not two that can disagree.</p>
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
