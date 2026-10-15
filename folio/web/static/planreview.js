/* Whiskers: the plan review, on the Overall tab.

   Eight parts of questions, saved as each is answered, then a draft plan built from them:
   how much risk suits the person (the lower of what they are willing and able to take,
   and only what they need), what to keep an eye on, their own rules, and a list of things
   worth doing. Nothing changes until "Use the ticked parts". Answers that the Retirement
   tab also uses are stored once, so the two can never disagree. */
'use strict';

VIEWS.plan = { title: 'Your plan', navTitle: 'Plan review', sub: 'A full review in eight parts, saved as you go, and the plan it builds around you.', render: vPlan };
S.planPart = S.planPart || 'you';
S.planMode = S.planMode || 'questions';

async function vPlan(el) {
  const d = await api('/api/builder');
  S.builder = d;
  const prog = d.progress;
  const total = prog.parts.reduce((a, p) => a + p.of, 0), done = prog.parts.reduce((a, p) => a + p.done, 0);
  const partBtn = (p, i) => {
    const pr = prog.parts.find(x => x.key === p.key) || { done: 0, of: 0 };
    const complete = pr.of && pr.done === pr.of;
    return `<button type="button" class="${S.planMode === 'questions' && S.planPart === p.key ? 'on' : ''} ${complete ? 'done' : ''}" data-act="plan-part" data-v="${p.key}">
      <span class="n">${complete ? '✓' : i + 1}</span><span>${esc(p.title)}</span><span class="count">${p.key === 'holdings' ? '' : `${pr.done}/${pr.of}`}</span></button>`;
  };
  el.innerHTML = `<div class="stack-lg">
    <div class="spread"><div class="small muted">${done} of ${total} questions answered${prog.updated ? `, last on ${fmtDate(prog.updated)}` : ''}${prog.applied ? `. Plan last used ${fmtDate(prog.applied)}.` : '.'}</div>
      <div class="row wrap"><button class="btn ${S.planMode === 'draft' ? 'primary' : ''}" data-act="plan-mode" data-v="draft">See the plan it builds</button>
        <button class="btn ${S.planMode === 'written' ? 'primary' : ''}" data-act="plan-mode" data-v="written">The written plan</button>
        <button class="btn ghost" data-act="plan-pack">Download the review pack</button>
        <button class="btn ghost" data-act="glossary">Words explained</button></div></div>
    <div class="wizard">
      <nav class="parts" aria-label="Parts of the review">${d.parts.map(partBtn).join('')}
        <button type="button" class="${S.planMode === 'draft' ? 'on' : ''}" data-act="plan-mode" data-v="draft"><span class="n">→</span><span>The plan</span><span class="count"></span></button></nav>
      <div id="plan-main"><div class="spinner"></div></div>
    </div>
    <p class="note">The review follows the steps financial planners use: your circumstances and goals first, then what you have, then a plan to accept or change. It is built from published research and common practice, names kinds of investment and never particular funds, and is not financial advice.</p>
  </div>`;
  setTimeout(() => {
    if (S.planMode === 'draft') planDraft();
    else if (S.planMode === 'written') planWritten();
    else planQuestions(S.planPart);
  }, 0);
}
ACTS['plan-part'] = b => { S.planMode = 'questions'; S.planPart = b.dataset.v; render(); };
ACTS['plan-mode'] = b => { S.planMode = b.dataset.v; render(); };
ACTS['plan-pack'] = async b => {
  await busy(b, async () => {
    const res = await api('/api/builder/pack');
    const said = await saveBlob(await res.blob(), `${S.boot.app.name} review pack ${new Date().toISOString().slice(0, 10)}.md`);
    toast(said || 'Downloaded. It holds everything a reviewer needs, in plain text; read it before you share it.');
  });
};

// ---------------------------------------------------------------------------- the questions

const optVal = (q, raw) => { const o = (q.options || []).find(([v]) => String(v) === raw); return o ? o[0] : raw; };

async function planQuestions(partKey) {
  const box = $('#plan-main');
  if (!box) return;
  const d = S.builder;
  const part = d.parts.find(p => p.key === partKey) || d.parts[0];
  const qs = d.questions.filter(q => q.part === part.key && q.visible);
  const i = d.parts.indexOf(part);
  box.innerHTML = `<section class="panel"><h2>${i + 1}. ${esc(part.title)}</h2><p class="lede">${esc(part.intro)}</p>
    <div class="qs">${qs.map(q => questionHtml(q, d.answers[q.id], d.at[q.id])).join('')}</div>
    <div class="spread" style="margin-top:14px">${i ? `<button class="btn" data-act="plan-part" data-v="${d.parts[i - 1].key}">Back</button>` : '<span></span>'}
      ${i < d.parts.length - 1 ? `<button class="btn primary" data-act="plan-part" data-v="${d.parts[i + 1].key}">Next: ${esc(d.parts[i + 1].title)}</button>`
        : '<button class="btn primary" data-act="plan-mode" data-v="draft">See the plan it builds</button>'}</div></section>`;
  wire(box);
  for (const q of qs) wireQuestion(q);
  if (qs.some(q => q.kind === 'xray')) loadXray($('#q-xray'));
  if (qs.some(q => q.kind === 'pensions')) loadPensionsSummary($('#q-pensions'));
  if (qs.some(q => q.kind === 'isa')) loadIsaSummary($('#q-isa'));
}

function questionHtml(q, a, at) {
  const hint = q.hint ? `<div class="hint">${esc(q.hint)}</div>` : '';
  const why = q.why ? `<div class="why">Why it matters: ${esc(q.why)}</div>` : '';
  const stamp = at ? `<div class="stamp">Answered ${fmtDate(at)}</div>` : '';
  const has = a !== undefined && a !== null && a !== '' && !(Array.isArray(a) && !a.length);
  let input = '';
  if (q.kind === 'one' || q.kind === 'many') {
    const type = q.kind === 'one' ? 'radio' : 'checkbox';
    const picked = q.kind === 'many' ? (a || []).map(String) : [String(a)];
    input = `<div class="opts">${q.options.map(([v, l]) => `<label><input type="${type}" name="q-${q.id}" value="${esc(String(v))}" ${picked.includes(String(v)) ? 'checked' : ''}>${esc(l)}</label>`).join('')}</div>`;
  } else if (q.kind === 'date') {
    input = `<div><input type="date" id="q-${q.id}" value="${esc(a || '')}" max="${new Date().toISOString().slice(0, 10)}"></div>`;
  } else if (q.kind === 'number' || q.kind === 'money') {
    input = `<div class="row">${q.kind === 'money' ? '<span>£</span>' : ''}<input type="number" id="q-${q.id}" value="${esc(a ?? '')}" step="any" min="0" style="width:150px">${q.unit ? `<span class="small muted">${esc(q.unit)}</span>` : ''}</div>`;
  } else if (q.kind === 'list_oneoffs' || q.kind === 'list_income') {
    const kind = q.kind === 'list_oneoffs' ? 'oo' : 'oi';
    input = `<div class="listrows" id="${kind}-list" data-q="${q.id}">${(a || []).map((o, i) => listRow(kind, i, o)).join('')}</div>
      <div class="row"><button class="btn small" data-act="lr-add" data-kind="${kind}">Add one</button><button class="btn small primary" data-act="q-list-save" data-q="${q.id}" data-kind="${kind}">Save these</button></div>`;
  } else if (q.kind === 'pensions') {
    input = '<div id="q-pensions"><div class="spinner"></div></div>';
  } else if (q.kind === 'isa') {
    input = '<div id="q-isa"><div class="spinner"></div></div>';
  } else if (q.kind === 'xray') {
    input = '<div id="q-xray"><div class="spinner"></div></div>';
  }
  return `<div class="q ${has ? 'saved' : ''}" id="qq-${q.id}"><div class="t">${esc(q.text)}</div>${hint}${input}${why}${stamp}</div>`;
}

function wireQuestion(q) {
  const save = async value => {
    try {
      const prog = await api('/api/builder', { method: 'PATCH', body: { answers: { [q.id]: value } } });
      S.builder.answers[q.id] = value;
      S.builder.at[q.id] = new Date().toISOString().slice(0, 10);
      S.builder.progress = prog;
      const box = $(`#qq-${q.id}`);
      if (box) box.classList.toggle('saved', !(value === null || value === '' || (Array.isArray(value) && !value.length)));
      // Questions shown only after another answer (the age you'd cut back, say) appear or
      // go once it is saved, and the part counts update.
      const dependent = S.builder.questions.some(x => x.show_if && x.show_if[q.id]);
      if (dependent) { const d = await api('/api/builder'); S.builder = d; planQuestions(S.planPart); }
      refreshPartCounts();
    } catch (e) { toast(e.message, true); }
  };
  if (q.kind === 'one') {
    $$(`input[name="q-${q.id}"]`).forEach(inp => inp.addEventListener('change', () => save(optVal(q, inp.value))));
  } else if (q.kind === 'many') {
    $$(`input[name="q-${q.id}"]`).forEach(inp => inp.addEventListener('change', () => {
      let vals = $$(`input[name="q-${q.id}"]:checked`).map(i => optVal(q, i.value));
      // "None" and an actual choice can't both be true.
      if (inp.checked && ['none'].includes(inp.value)) { vals = ['none']; $$(`input[name="q-${q.id}"]`).forEach(i => { if (i.value !== 'none') i.checked = false; }); }
      else if (inp.checked) { vals = vals.filter(v => v !== 'none'); const n = $(`input[name="q-${q.id}"][value="none"]`); if (n) n.checked = false; }
      save(vals);
    }));
  } else if (q.kind === 'date' || q.kind === 'number' || q.kind === 'money') {
    const inp = $(`#q-${q.id}`);
    if (!inp) return;
    let t;
    const go = () => { clearTimeout(t); t = setTimeout(() => save(inp.value === '' ? null : q.kind === 'date' ? inp.value : +inp.value), 500); };
    inp.addEventListener('change', go);
    inp.addEventListener('input', () => { if (q.kind !== 'date') go(); });
  }
}
ACTS['q-list-save'] = async b => {
  const items = readList(b.dataset.kind);
  await busy(b, async () => {
    const prog = await api('/api/builder', { method: 'PATCH', body: { answers: { [b.dataset.q]: items } } });
    S.builder.answers[b.dataset.q] = items;
    S.builder.progress = prog;
    toast('Saved.');
    refreshPartCounts();
  });
};

function refreshPartCounts() {
  const prog = S.builder.progress;
  $$('.parts [data-act="plan-part"]').forEach(btn => {
    const pr = prog.parts.find(x => x.key === btn.dataset.v);
    if (!pr) return;
    const c = btn.querySelector('.count');
    if (c && btn.dataset.v !== 'holdings') c.textContent = `${pr.done}/${pr.of}`;
    const complete = pr.of && pr.done === pr.of;
    btn.classList.toggle('done', !!complete);
    const n = btn.querySelector('.n');
    if (n) n.textContent = complete ? '✓' : String(S.builder.parts.findIndex(p => p.key === btn.dataset.v) + 1);
  });
}

async function loadPensionsSummary(box) {
  if (!box) return;
  try {
    const d = await api('/api/pensions');
    box.innerHTML = `${d.items.length ? `<ul class="small" style="padding-left:18px;margin:0 0 8px">${d.items.map(p => `<li><b>${esc(p.name)}</b>: <span class="pv">${esc(p.describe)}</span></li>`).join('')}</ul>` : '<p class="small muted">None added yet.</p>'}
      <button class="btn small" data-go="pensions">${d.items.length ? 'Add or change pensions' : 'Add your pensions'}</button>`;
    wire(box);
  } catch (e) { box.innerHTML = `<p class="warnline">${esc(e.message)}</p>`; }
}
async function loadIsaSummary(box) {
  if (!box) return;
  try {
    const x = await api('/api/xray');
    const w = x.wrappers || {};
    box.innerHTML = `<p class="small">${esc(w.isa_year || 'This tax year')}: ${money(w.isa_used, { dp: 0 })} paid in, ${money(w.isa_left, { dp: 0 })} left of the £20,000, with ${plural(w.isa_days_left || 0, 'day')} to go.${w.gia > 100 ? ` ${money(w.gia, { dp: 0 })} sits in general accounts, outside any ISA.` : ''}</p>
      <p class="small muted" style="margin-top:4px">Worked out from deposits on platforms that report them; check it against your own records. From 6 April 2027, no more than £12,000 a year can go into cash ISAs for anyone under 65.</p>`;
  } catch (e) { box.innerHTML = `<p class="warnline">${esc(e.message)}</p>`; }
}

// ---------------------------------------------------------------------------- the X-Ray

async function loadXray(box) {
  if (!box) return;
  let x;
  try { x = await api('/api/xray'); } catch (e) { box.innerHTML = `<p class="warnline">${esc(e.message)}</p>`; return; }
  box.innerHTML = xrayHtml(x);
  wire(box);
}

function bar(label, frac, colour, right, sub) {
  return `<div class="cat-bar"><span>${esc(label)}${sub ? `<div class="tiny muted">${sub}</div>` : ''}</span><div class="track"><i style="width:${Math.max(0, Math.min(100, (frac || 0) * 100))}%;background:${colour}"></i></div><span class="r small">${right}</span></div>`;
}

function xrayHtml(x) {
  if (x.empty) return '<p class="muted">Nothing priced yet. Add your platforms and press Refresh; the X-Ray looks through what they hold.</p>';
  const c = x.costs || {};
  const themes = (x.themes || []).filter(t => (t.pct || 0) >= 0.005);
  return `<div class="stack">
    <div class="stat-row">
      <div class="stat"><span class="k">Looked through</span><span class="v">${money(x.total, { dp: 0 })}</span><span class="tiny muted">${plural(x.holdings, 'holding')}${x.unpriced ? `, ${x.unpriced} without a price` : ''}</span></div>
      <div class="stat"><span class="k">Charges a year</span><span class="v">${money(c.total, { dp: 0 })}</span><span class="tiny muted">${known(c.pct) ? `${(c.pct * 100).toFixed(2)}% of what is invested` : 'not known'}</span></div>
      <div class="stat"><span class="k">Ten largest holdings</span><span class="v">${pct(x.top10_pct, { dp: 0 })}</span><span class="tiny muted">of everything</span></div>
      <div class="stat"><span class="k">Dividends, 12 months</span><span class="v">${money((x.income || {}).dividends_12m, { dp: 0 })}</span><span class="tiny muted">${known((x.income || {}).yield) ? `${((x.income.yield) * 100).toFixed(1)}% yield` : ''}</span></div>
    </div>
    ${(x.findings || []).length ? `<div class="alerts">${x.findings.map(f => `<button class="alert ${f.level}" type="button" ${f.go ? `data-go="${f.go}"` : ''}><span class="lvl ${f.level}"></span><span class="t">${esc(f.title)}</span><span class="go">${f.go && VIEWS[f.go] ? esc(VIEWS[f.go].title) : ''}</span><span class="d">${esc(f.detail)}</span></button>`).join('')}</div>` : '<p class="none-state">Nothing in the X-Ray needs a look.</p>'}
    <div class="grid g2">
      <div><h3>What it’s made of</h3>${(x.asset_mix || []).map(m => bar(m.label, m.pct, 'var(--accent)', pct(m.pct, { dp: 0 }), m.guessed > 0.5 ? `${pct(m.guessed / m.value, { dp: 0 })} of it guessed from names` : '')).join('')}
        <h3 style="margin-top:14px">Where, roughly</h3>${bar('United States', x.regions.us_pct, '#4f8fd6', pct(x.regions.us_pct, { dp: 0 }))}${bar('United Kingdom', x.regions.uk_pct, '#4f8fd6', pct(x.regions.uk_pct, { dp: 0 }))}${bar('Emerging markets', x.regions.em_pct, '#4f8fd6', pct(x.regions.em_pct, { dp: 0 }))}
        <p class="tiny muted">${esc(x.regions.note)} Covers ${pct(x.regions.coverage, { dp: 0 })} of what is invested.</p>
        <h3 style="margin-top:14px">Currencies</h3>${(x.currencies || []).map(r => bar(r.ccy, r.pct, '#c98a3a', pct(r.pct, { dp: 0 }))).join('')}</div>
      <div><h3>What moves it</h3>${themes.map(t => bar(t.label, t.pct, 'var(--red)', `${pct(t.pct, { dp: 0 })} <span class="muted">${money(t.value, { dp: 0 })}</span>`, known(t.coverage) && t.coverage < 0.95 ? `known for ${pct(t.coverage, { dp: 0 })} of holdings` : '')).join('') || '<p class="small muted">No market force carries much of your money.</p>'}
        <p class="tiny muted">A fund counts for the share of it in each theme: from what you set on the holding, a well-known fund’s published make-up, or a guess from its name.</p>
        ${(x.biggest_companies || []).length ? `<h3 style="margin-top:14px">The biggest companies you own, counting funds</h3>
          <table class="small"><tbody>${x.biggest_companies.slice(0, 8).map(b => `<tr><td>${esc(b.company)}${b.direct && b.via ? ' <span class="chip">directly and in funds</span>' : ''}</td><td class="r">${money(b.true, { dp: 0 })}</td><td class="r num">${pct(b.pct, { dp: 1 })}</td></tr>`).join('')}</tbody></table>` : ''}</div>
    </div>
    ${(x.singles || []).length ? `<div><h3>Single companies</h3><table class="small" style="margin-top:6px"><thead><tr><th>Company</th><th class="r">Of everything</th><th class="r">Since bought</th><th class="r">World index, same dates</th><th>Reason written down</th></tr></thead><tbody>
      ${x.singles.map(sg => `<tr class="click" data-holding="${sg.instrument_id}"><td>${esc(sg.name)}</td><td class="r">${pct(sg.pct, { dp: 1 })}</td><td class="r ${signCls(sg.return)}">${pct(sg.return, { sign: true, dp: 0 })}</td><td class="r">${pct(sg.world, { sign: true, dp: 0 })}</td>
        <td>${sg.thesis ? `<span class="chip green">yes</span>${sg.verdict ? ` <span class="tiny muted">${esc(sg.verdict)}</span>` : ''}` : '<span class="chip amber">not yet</span>'}</td></tr>`).join('')}</tbody></table></div>` : ''}
    ${(c.dear || []).length || (c.unknown || []).length ? `<div><h3>Charges</h3>
      ${(c.dear || []).map(f => `<div class="spread small"><a href="#" data-holding="${f.instrument_id}">${esc(f.name)}</a><span>${(+f.ocf).toFixed(2)}% a year, about ${money(f.cost, { dp: 0 })}</span></div>`).join('')}
      ${(c.unknown || []).length ? `<p class="tiny muted" style="margin-top:4px">Not known for ${c.unknown.slice(0, 6).map(u => `<a href="#" data-holding="${u.instrument_id}">${esc(u.name)}</a>`).join(', ')}: type its yearly charge on its holding page.</p>` : ''}</div>` : ''}
    <p class="note">After Morningstar’s Portfolio X-Ray: what your money really holds once funds are looked through. Approximate where a fund’s make-up isn’t known.</p>
  </div>`;
}

// ---------------------------------------------------------------------------- the draft

async function planDraft() {
  const box = $('#plan-main');
  if (!box) return;
  let d;
  try { d = await api('/api/builder/draft'); } catch (e) { box.innerHTML = `<div class="panel warnline">${esc(e.message)}</div>`; return; }
  S.draft = d;
  const r = d.risk, plan = d.plan, ret = d.retirement;
  const now = Object.fromEntries((d.sleeves_now || []).map(x => [x.name, x.target]));
  const names = [...new Set(plan.sleeves.map(x => x.name).concat((d.sleeves_now || []).map(x => x.name)))];
  const marker = (v, col, label) => known(v) ? `<i style="left:${v}%;background:${col}" title="${esc(label)}: ${Math.round(v)}%"></i>` : '';
  const prog = d.progress;
  const missing = prog.parts.filter(p => p.key !== 'holdings' && p.done < p.of);
  box.innerHTML = `<div class="stack">
    ${missing.length ? `<div class="plan-box"><b>Some questions are still blank</b><p class="small" style="margin-top:4px">${missing.map(p => `${esc(p.title)} (${p.of - p.done})`).join(', ')}. The draft fills the gaps with middle-of-the-road answers; answering them makes it yours.</p></div>` : ''}
    <section class="panel"><h2>How much risk</h2>
      <p class="lede">Three tests, from Bogleheads and the regulator’s rules for advisers: the risk you are willing to take, the risk you are able to take, and the risk you need to take. The plan takes the lower of willing and able, and never more than you need without saying so.</p>
      <div class="meter"><div class="track"><div class="fill" style="width:${r.growth}%"></div>${marker(r.willing, 'var(--amber)', 'Willing')}${marker(r.able, 'var(--cyan)', 'Able')}${marker(r.need, 'var(--green)', 'Need')}</div>
        <div class="keys"><span><i style="background:var(--amber)"></i>Willing: ${r.willing}% in shares</span><span><i style="background:var(--cyan)"></i>Able: ${r.able}%</span>
          ${known(r.need) ? `<span><i style="background:var(--green)"></i>Need: ${Math.round(r.need)}%</span>` : r.need_status === 'beyond' ? '<span class="warnline">Need: more than any mix of investments can give</span>' : '<span class="muted">Need: fill in the retirement basics to see</span>'}<span><b>The plan: ${r.growth}% in shares</b></span></div></div>
      <ul class="small" style="padding-left:18px;display:grid;gap:4px;margin-top:10px">${r.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>
      ${r.alternative ? `<div class="plan-box" style="margin-top:10px"><b>A gentler choice</b><p class="small" style="margin-top:4px">${esc(r.alternative.words)} That would be about ${Math.round(r.alternative.growth)}% in shares.</p></div>` : ''}
      ${r.shortfall ? `<p class="warnline" style="margin-top:8px">${esc(r.shortfall)}</p>` : ''}
    </section>

    <div class="grid g2">
      <section class="panel"><h2>Your target mix</h2>
        <table class="small"><thead><tr><th>Sleeve</th><th class="r">Now</th><th class="r">Proposed</th></tr></thead><tbody>
          ${names.map(n => { const pnew = plan.sleeves.find(x => x.name === n); return `<tr><td>${esc(n)}</td><td class="r muted">${known(now[n]) ? pts(now[n], now[n] % 1 ? 1 : 0) : '—'}</td><td class="r"><b>${pnew ? pts(pnew.target, pnew.target % 1 ? 1 : 0) : '—'}</b></td></tr>`; }).join('')}
        </tbody></table>
        <p class="tiny muted" style="margin-top:6px">Kinds of investment, not particular funds. A global index fund is one fund holding thousands of companies across many countries.</p></section>
      <section class="panel"><h2>What to keep an eye on</h2>
        ${d.watch.main ? `<p><b>${esc(d.watch.titles[d.watch.main] || d.watch.main)}</b>, as your main watch: the dial on the Overall tab.</p>` : `<p>${esc(d.watch.note || 'Markets in general.')}</p>`}
        <ul class="small" style="padding-left:18px;display:grid;gap:4px;margin-top:6px">${d.watch.themes.map(t => `<li><b>${esc(d.watch.titles[t] || t)}</b>: ${esc(d.watch.why[t] || '')}</li>`).join('')}</ul>
        <details style="margin-top:8px"><summary class="small">The signals that come with it (${d.signals.length})</summary>
          <ul class="tiny" style="padding-left:18px;display:grid;gap:3px;margin-top:6px">${d.signals.map(g => `<li><b>${esc(g.title)}</b>: ${esc(g.means || '')}</li>`).join('')}</ul></details>
        <p class="tiny muted" style="margin-top:6px">Now: ${d.watch_now.legacy ? 'the AI trade (the original watch)' : esc((d.watch_now.themes || []).join(', '))}.</p></section>
    </div>

    <div class="grid g2">
      <section class="panel"><h2>Your rules</h2>
        ${plan.rules.length ? `<ul class="small" style="padding-left:18px;display:grid;gap:4px">${plan.rules.map(x => `<li>${esc(x.note)}</li>`).join('')}</ul>` : '<p class="small muted">No rules needed on these answers.</p>'}
        <h3 style="margin-top:12px">Your plan for a fall</h3><p class="small plan-text">${esc(plan.plans.crash)}</p>
        <h3 style="margin-top:10px">If your main watch turns</h3><p class="small plan-text">${esc(plan.plans.ai)}</p>
        ${plan.playbook ? `<h3 style="margin-top:10px">Your ladder, while drawing on your money</h3><ul class="tiny" style="padding-left:18px">${Object.entries(plan.playbook.ladder).map(([k, v]) => `<li>${k}% down: ${esc(v)}</li>`).join('')}</ul>` : ''}</section>
      <section class="panel"><h2>Retirement and the what-ifs</h2>
        ${ret && ret.ready ? `<p>${ret.plan.lasts ? `<span class="up">On these assumptions the money lasts to ${Math.round(ret.plan.horizon)}.</span>` : `<span class="down">On these assumptions the money runs short at about ${Math.floor(ret.plan.runs_out_at)}.</span>`}</p>
          ${ret.need ? `<p class="small" style="margin-top:4px">${esc(ret.need.words)}</p>` : ''}` : `<p class="small muted">The retirement plan needs ${esc(((ret || {}).missing || ['a few details']).join(', '))}.</p>`}
        <div class="stack" style="gap:6px;margin-top:10px">${(d.standard_stress || []).concat(d.theme_scenarios || []).map(x => `<div class="spread small"><span>${esc(x.label)}<div class="tiny muted">${esc(x.why || '')}</div></span><b class="fig down nowrap">${money(-x.loss, { dp: 0 })}</b></div>`).join('')}</div></section>
    </div>

    <section class="panel"><h2>Things worth doing</h2>
      <div>${d.todos.map(t => `<div class="todo"><span class="lvl ${t.level}"></span><b class="small">${narr(t.title.replace(/£[\d,]+/g, m => `[[${m}]]`))}</b><span class="w">${t.when ? esc(/^\d{4}-\d\d-\d\d$/.test(t.when) ? fmtDate(t.when) : t.when) : ''}</span>
        <span class="d">${narr(t.detail.replace(/£[\d,]+/g, m => `[[${m}]]`))}${t.link ? ` <a href="${esc(t.link)}">More</a>` : ''}</span></div>`).join('')}</div></section>

    <section class="panel"><h2>The X-Ray</h2><div id="draft-xray" style="margin-top:8px">${xrayHtml(d.xray)}</div></section>

    <section class="panel"><h2>Use it</h2>
      <p class="lede">Tick what to use. Nothing is sold or bought: the targets, rules and watch are what Whiskers measures your money against from now on. Your answers stay, so the review can be run again any time.</p>
      <div class="checks">
        <label><input type="checkbox" id="ap-sleeves" checked><span>The target mix <span class="small muted">(replaces your current sleeves and targets)</span></span></label>
        <label><input type="checkbox" id="ap-rules" ${plan.rules.length ? 'checked' : 'disabled'}><span>The rules (${plan.rules.length})</span></label>
        <label><input type="checkbox" id="ap-watch" checked><span>What to keep an eye on <span class="small muted">(the Market watch, the dial and the signals)</span></span></label>
        <label><input type="checkbox" id="ap-plans" checked><span>The plan for a fall</span></label>
        ${plan.playbook ? '<label><input type="checkbox" id="ap-ladder" checked><span>The ladder for drawing on your money</span></label>' : ''}
      </div>
      <div class="row" style="margin-top:12px"><button class="btn primary" data-act="plan-apply">Use the ticked parts</button><button class="btn" data-act="plan-mode" data-v="written">See it as a written plan</button></div>
    </section>

    <section class="panel"><details><summary><b>Why it came out this way</b></summary>
      <ul class="small" style="padding-left:18px;display:grid;gap:4px;margin-top:8px">${d.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>
      <h3 style="margin-top:12px">Based on</h3><ul class="tiny" style="padding-left:18px;display:grid;gap:3px">${d.sources.map(([t, u]) => `<li><a href="${esc(u)}">${esc(t)}</a></li>`).join('')}</ul></details></section>
  </div>`;
  wire(box);
}
ACTS['plan-apply'] = async b => {
  const choice = { sleeves: $('#ap-sleeves').checked, rules: $('#ap-rules').checked, watch: $('#ap-watch').checked,
    plans: $('#ap-plans').checked, playbook: $('#ap-ladder') ? $('#ap-ladder').checked : false };
  if (!Object.values(choice).some(Boolean)) { toast('Tick at least one part.', true); return; }
  if (!await confirmBox('Use these parts of the plan?', `${choice.sleeves ? 'Your sleeves and targets are replaced; holdings in sleeves with other names go back to “not in a sleeve yet”. ' : ''}Nothing on any platform changes. You can run the review again at any time.`, 'Use them')) return;
  await busy(b, async () => {
    const r = await api('/api/builder/apply', { method: 'POST', body: choice });
    const next = !choice.sleeves ? '' : (r.sorted || []).length ? 'Check them, and sort anything left, on the Allocation screen.' : 'Sort holdings into the sleeves on the Allocation screen.';
    toast(`Done: ${r.done.join(', ')}. ${next}`);
    await refreshBoot();
    render();
  });
};

// ---------------------------------------------------------------------------- the written plan

async function planWritten() {
  const box = $('#plan-main');
  if (!box) return;
  let w;
  try { w = await api('/api/builder/written'); } catch (e) { box.innerHTML = `<div class="panel warnline">${esc(e.message)}</div>`; return; }
  box.innerHTML = `<div class="stack">
    <div class="row wrap"><button class="btn primary" data-act="plan-print">Print it</button><button class="btn" data-act="plan-html">Save it as a page</button>
      <span class="small muted">An investment policy statement, the Bogleheads call it: everything decided, in one place, to keep and reread before acting in a fall.</span></div>
    ${writtenHtml(w)}</div>`;
  wire(box);
}
function writtenHtml(w) {
  return `<article class="written"><h1>${esc(w.title)}</h1><p class="small muted">Made ${fmtDate(w.made)}</p>
    ${w.sections.map(s => `<h2>${esc(s.title)}</h2><ul>${s.lines.map(l => `<li>${narr(String(l).replace(/£[\d,]+/g, m => `[[${m}]]`))}</li>`).join('')}</ul>`).join('')}
    <p class="note" style="margin-top:18px">${esc(w.footer)}</p></article>`;
}
ACTS['plan-print'] = async () => {
  const w = await api('/api/builder/written').catch(e => { toast(e.message, true); return null; });
  if (!w) return;
  if (onAndroid()) { ACTS['plan-html'](); return; }
  openModal({ title: 'Your written plan', wide: true, body: writtenHtml(w), foot: '<button class="btn" data-act="close">Close</button>' });
  document.body.classList.add('printing');
  const done = () => { document.body.classList.remove('printing'); window.removeEventListener('afterprint', done); };
  window.addEventListener('afterprint', done);
  setTimeout(() => { try { window.print(); } catch (e) { done(); } }, 150);
};
ACTS['plan-html'] = async b => {
  await busy(b, async () => {
    const res = await api('/api/builder/written.html');
    const said = await saveBlob(await res.blob(), `${S.boot.app.name} written plan ${new Date().toISOString().slice(0, 10)}.html`);
    toast(said || 'Saved. Open it in any web browser to read or print it.');
  });
};

// ---------------------------------------------------------------------------- choosing the watch directly

ACTS['watch-change'] = async () => {
  let d;
  try { d = await api('/api/watch'); } catch (e) { toast(e.message, true); return; }
  const w = d.watch, sug = d.suggestion;
  const exp = Object.fromEntries((sug.exposures || []).map(e => [e.theme, e.pct]));
  const on = new Set(w.legacy ? ['ai'] : w.themes);
  openModal({ title: 'What to keep an eye on', wide: true, body: `
    <p class="small" style="max-width:80ch">Tick up to five. The main one becomes the dial on the Overall tab and the Summary. Suggested from what your money rides on${sug.main ? `: <b>${esc(d.library.find(l => l.key === sug.main)?.label || sug.main)}</b> first` : ''}.</p>
    <div class="table-wrap" style="margin-top:10px"><table class="small"><thead><tr><th>Watch</th><th>Main</th><th>Theme</th><th class="r">Your money in it</th><th>Why suggested</th></tr></thead><tbody>
      ${d.library.filter(l => l.key !== 'rand' || exp.rand).map(l => `<tr><td><input type="checkbox" data-wt="${l.key}" ${on.has(l.key) ? 'checked' : ''} aria-label="Watch ${esc(l.label)}"></td>
        <td><input type="radio" name="wt-main" value="${l.key}" ${(w.legacy ? 'ai' : w.main) === l.key ? 'checked' : ''} aria-label="Main watch"></td>
        <td><b>${esc(l.label)}</b><div class="tiny muted">${esc(l.about)}</div></td><td class="r">${known(exp[l.key]) ? pct(exp[l.key], { dp: 0 }) : '—'}</td>
        <td class="tiny muted">${esc((sug.why || {})[l.key] || '')}</td></tr>`).join('')}</tbody></table></div>`,
    foot: `<button class="btn ghost" data-act="watch-legacy">Back to the original AI watch</button><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="watch-save">Save</button>` });
};
ACTS['watch-save'] = async b => {
  const themes = $$('[data-wt]').filter(i => i.checked).map(i => i.dataset.wt);
  const main = ($('input[name="wt-main"]:checked') || {}).value;
  if (!themes.length) { toast('Tick at least one.', true); return; }
  if (themes.length > 5) { toast('Five at most: more lights than that stop meaning anything.', true); return; }
  await busy(b, async () => {
    await api('/api/watch', { method: 'PUT', body: { themes, main: themes.includes(main) ? main : themes[0] } });
    closeModal(); toast('Saved. The lights and the dial now follow it.'); await refreshBoot(); render();
  });
};
ACTS['watch-legacy'] = async b => {
  await busy(b, async () => { await api('/api/watch', { method: 'PUT', body: { legacy: true } }); closeModal(); await refreshBoot(); render(); });
};
