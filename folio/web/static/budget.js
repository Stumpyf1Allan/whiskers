/* Whiskers: the Budget tab, off unless switched on in Settings.

   Bank statements in; spending by category against a monthly budget; money saved kept
   apart from money spent; transfers between your own accounts counted as neither. One
   click teaches it a merchant, and every matching row follows. */
'use strict';

VIEWS.budget = { title: 'Budget', sub: 'This month’s money in, out and saved, by category, against the budgets you set.', render: vBudget };
VIEWS.transactions = { title: 'Transactions', sub: 'Every row from your bank statements. Sort one and Whiskers can remember the merchant.', render: vTransactions };
S.budgetPeriod = S.budgetPeriod || null;
S.txFilter = S.txFilter || { q: '', category: '', platform: '', uncategorised: false };

async function vBudget(el) {
  if (!S.boot.settings.budget_on) { budgetOff(el); return; }
  const d = await api(`/api/budget${S.budgetPeriod ? `?period=${S.budgetPeriod}` : ''}`);
  const m = d.month;
  if (!d.accounts.some(a => a.n)) {
    el.innerHTML = `<div class="stack-lg" style="max-width:900px"><section class="panel"><h2>Bring in a bank statement</h2>
      <p class="lede">Download a statement from your bank (a CSV file is best; OFX, QIF, Excel and most PDFs work too) and drop it on the Import screen, or put it in your statements folder.</p>
      <p class="small">${d.accounts.length ? `Bank accounts: ${esc(d.accounts.map(a => a.name).join(', '))}.` : 'Add the bank account first: Find your platform or account, then pick your bank.'}</p>
      <div class="row wrap" style="margin-top:10px">${d.accounts.length ? '' : '<button class="btn primary" data-act="add-from-catalogue">Find your bank</button>'}<button class="btn" data-go="import">Go to the Import screen</button></div></section></div>`;
    return;
  }
  const groups = {};
  for (const ln of m.lines) (groups[ln.parent] = groups[ln.parent] || []).push(ln);
  const maxSpend = Math.max(1, ...m.lines.map(l => Math.max(l.spent, l.budget || 0)));
  el.innerHTML = `<div class="stack-lg">
    <div class="spread"><div class="row"><button class="btn small" data-act="bud-period" data-v="${d.previous}">←</button><h2>${esc(m.label)}</h2>
      ${m.period < d.current ? `<button class="btn small" data-act="bud-period" data-v="${d.next}">→</button>` : ''}</div>
      <div class="row wrap"><button class="btn" data-act="bud-suggest">Set budgets from the last three months</button><button class="btn" data-go="import">Import a statement</button></div></div>
    <div class="figures">
      <div class="hero"><div class="k">Left over</div><div class="v ${signCls(m.left)}">${money(m.left, { dp: 0 })}</div><div class="s">money in, less spending and saving</div></div>
      <div><div class="k">Money in</div><div class="v">${money(m.in, { dp: 0 })}</div><div class="s">pay, refunds, interest</div></div>
      <div><div class="k">Spent</div><div class="v">${money(m.out, { dp: 0 })}</div><div class="s">${m.budget_total ? `of ${money(m.budget_total, { dp: 0 })} budgeted` : 'no budgets set yet'}</div></div>
      <div><div class="k">Saved</div><div class="v">${money(m.saved, { dp: 0 })}</div><div class="s">into savings and investments</div></div>
    </div>
    ${m.uncategorised ? `<div class="plan-box"><b>${plural(m.uncategorised, 'transaction')} not sorted yet</b> <button class="btn small" data-act="bud-sort">Sort them</button></div>` : ''}
    <div class="grid g-main">
      <section class="panel"><h2>By category</h2>
        <p class="lede">The bar is what has gone out; the tick is the budget. ${m.through < 1 && m.through > 0 ? `${pct(m.through, { dp: 0 })} of the month has gone.` : ''}</p>
        ${Object.entries(groups).map(([parent, lines]) => `<h3 style="margin-top:12px">${esc(parent)}</h3>${lines.map(l => {
          const over = l.budget && l.spent > l.budget;
          return `<div class="cat-bar"><span>${esc(l.name)}</span>
            <div class="track" title="${l.budget ? `Budget ${moneyText(l.budget, 0)}` : 'No budget'}"><i style="width:${l.spent / maxSpend * 100}%;background:${over ? 'var(--red)' : 'var(--accent)'}"></i>${l.budget ? `<b style="position:absolute;top:-2px;left:${l.budget / maxSpend * 100}%;width:2px;height:16px;background:var(--ink)"></b>` : ''}</div>
            <span class="r small">${money(l.spent, { dp: 0 })}${l.id ? ` <input type="number" min="0" step="5" value="${known(l.budget) ? l.budget : ''}" placeholder="budget" data-budget="${l.id}" style="width:84px" aria-label="Budget for ${esc(l.name)}">` : ''}</span></div>`;
        }).join('')}`).join('') || '<p class="muted">Nothing spent this month yet.</p>'}
        <div class="row" style="margin-top:12px"><button class="btn primary" data-act="bud-save">Save the budgets</button></div>
      </section>
      <section class="panel"><h2>The last twelve months</h2>
        ${Charts.bars({ items: d.history.map(h => ({ label: MONTHS[+h.period.slice(5) - 1], long: h.period, parts: [{ name: 'Spent', value: h.out, color: 'var(--amber)' }, { name: 'Saved', value: h.saved, color: 'var(--accent)' }] })),
          overlay: [{ name: 'Money in', values: d.history.map(h => h.in), color: 'var(--green)' }], money: true, fmt: v => moneyText(v, 0), yfmt: compactMoney }, 230)}
        <div class="legend" style="margin-top:6px"><span><i style="background:var(--amber)"></i>Spent</span><span><i style="background:var(--accent)"></i>Saved</span><span><i style="background:var(--green)"></i>Money in</span></div>
        <h3 style="margin-top:14px">Accounts</h3><table class="small"><tbody>${d.accounts.map(a => `<tr><td>${esc(a.name)}</td><td class="muted">${a.n ? `${fmtDate(a.first)} to ${fmtDate(a.last)}` : 'no statements yet'}</td><td class="r">${plural(a.n, 'row')}</td></tr>`).join('')}</tbody></table>
      </section>
    </div>
    ${m.unconverted ? `<p class="warnline">${plural(m.unconverted, 'row')} in another currency left out until an exchange rate arrives: press Refresh.</p>` : ''}
  </div>`;
}

function budgetOff(el) {
  el.innerHTML = `<div class="panel" style="max-width:760px"><h2>The Budget tab is switched off</h2><p class="lede">Switch it on in Settings to import bank statements and set monthly budgets. While it’s off it isn’t counted anywhere.</p><button class="btn" data-go="settings">Go to Settings</button></div>`;
}

ACTS['bud-period'] = b => { S.budgetPeriod = b.dataset.v; render(); };
ACTS['bud-sort'] = () => { S.txFilter.uncategorised = true; go('transactions'); };
ACTS['bud-save'] = async b => {
  await busy(b, async () => {
    for (const inp of $$('[data-budget]')) {
      await api(`/api/budget/categories/${inp.dataset.budget}`, { method: 'PUT', body: { budget: inp.value === '' ? null : inp.value } });
    }
    toast('Budgets saved.'); render();
  });
};
ACTS['bud-suggest'] = async b => {
  const r = await api('/api/budget/suggest').catch(e => { toast(e.message, true); return null; });
  if (!r) return;
  if (!r.items.length) { toast('Not enough history yet: import two or three months of statements first.', true); return; }
  openModal({ title: 'Budgets from the last three months', body: `<p class="small muted">Each category’s average over the last three whole months, rounded up to £5. Change any before saving.</p>
    <table class="small" style="margin-top:8px"><tbody>${r.items.map(x => `<tr><td>${esc(x.parent)}: ${esc(x.name)}</td><td class="r"><input type="number" min="0" step="5" data-sugg="${x.id}" value="${x.suggested}" style="width:100px"></td></tr>`).join('')}</tbody></table>`,
    foot: '<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="bud-sugg-save">Use these</button>' });
};
ACTS['bud-sugg-save'] = async b => {
  await busy(b, async () => {
    for (const inp of $$('[data-sugg]')) await api(`/api/budget/categories/${inp.dataset.sugg}`, { method: 'PUT', body: { budget: inp.value } });
    closeModal(); toast('Budgets set.'); render();
  });
};

async function vTransactions(el) {
  if (!S.boot.settings.budget_on) { budgetOff(el); return; }
  const f = S.txFilter;
  const qs = new URLSearchParams({ q: f.q, category: f.category, platform: f.platform, uncategorised: f.uncategorised ? '1' : '' });
  const d = await api(`/api/transactions?${qs}`);
  const opts = cur => `<option value="">Not sorted</option>${Object.entries(d.categories.reduce((a, c) => { (a[c.parent] = a[c.parent] || []).push(c); return a; }, {}))
    .map(([p, list]) => `<optgroup label="${esc(p)}">${list.map(c => `<option value="${c.id}" ${c.id === cur ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</optgroup>`).join('')}`;
  el.innerHTML = `<div class="stack">
    <div class="row wrap"><input type="search" id="tx-q" placeholder="Find a transaction" value="${esc(f.q)}" style="width:220px">
      <select id="tx-plat"><option value="">Every account</option>${d.accounts.map(a => `<option value="${a.id}" ${String(a.id) === f.platform ? 'selected' : ''}>${esc(a.name)}</option>`).join('')}</select>
      <label class="row small"><input type="checkbox" id="tx-unc" ${f.uncategorised ? 'checked' : ''}> Only the ones not sorted</label>
      <label class="row small"><input type="checkbox" id="tx-remember" checked> Remember the merchant when I sort one</label></div>
    <div class="panel" style="padding:6px 8px"><div class="table-wrap"><table><thead><tr><th>Date</th><th>Description</th><th>Account</th><th class="r">Amount</th><th style="width:240px">Category</th></tr></thead><tbody>
      ${d.items.map(t => `<tr><td class="nowrap">${fmtDate(t.posted_on)}</td><td>${esc(t.description)}${t.category_by === 'rule' || t.category_by === 'builtin' ? `<div class="tiny muted">${t.category_by === 'rule' ? 'sorted by your rule' : 'sorted automatically'}</div>` : ''}</td>
        <td class="small muted">${esc(t.account)}</td><td class="r ${signCls(t.amount)}">${t.currency && t.currency !== 'GBP' ? `<span class="pv">${esc(t.currency)} ${(+t.amount).toFixed(2)}</span>` : money(t.amount, { dp: 2, sign: true })}</td>
        <td><select data-tx="${t.id}" aria-label="Category">${opts(t.category_id)}</select></td></tr>`).join('') || '<tr><td colspan="5" class="muted">Nothing matches.</td></tr>'}
    </tbody></table></div></div>
    <p class="note">Showing up to 400 rows, newest first.</p></div>`;
  const q = $('#tx-q', el);
  q.addEventListener('input', () => { f.q = q.value; clearTimeout(S._txq); S._txq = setTimeout(render, 300); });
  $('#tx-plat', el).addEventListener('change', e => { f.platform = e.target.value; render(); });
  $('#tx-unc', el).addEventListener('change', e => { f.uncategorised = e.target.checked; render(); });
  $$('[data-tx]', el).forEach(sel => sel.addEventListener('change', async () => {
    try {
      const r = await api(`/api/transactions/${sel.dataset.tx}`, { method: 'PATCH', body: { category_id: sel.value || null, remember: $('#tx-remember').checked } });
      toast(r.filled ? `Sorted, and ${plural(r.filled, 'other like it', 'others like it')} too.` : 'Sorted.');
      if (r.filled || f.uncategorised) render();
    } catch (e) { toast(e.message, true); }
  }));
}
