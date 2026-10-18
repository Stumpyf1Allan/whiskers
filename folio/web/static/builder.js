/* Whiskers: the plan builder, a page of its own, opened from Settings › Your plan.

   Five short steps, saved as each answer is given: you and this money, risk, how hands-on,
   your views (a card for each theme: how strongly you believe in it, how worried you are,
   what you want to do about it, and why, in your own words), and what you hold. Then the
   answers are used: with a plan already in Whiskers, as a review of that plan, one
   suggestion at a time with its reason; otherwise as a fresh plan. For a fully bespoke plan
   it saves a brief to give to Claude, and checks the plan file that comes back before
   anything is loaded. Nothing changes until the person says so. */
'use strict';

VIEWS.builder = { title: 'Plan builder', full: true, parent: 'settings', sub: '', render: vBuilder };
S.bStep = S.bStep || 'you';
S.bMode = S.bMode || null;

const B_STEPS = [['you', 'You and this money'], ['risk', 'Risk'], ['hands', 'How hands-on'], ['views', 'Your views'],
  ['holdings', 'What you hold']];
const B_MARK = `<svg viewBox="0 0 64 64" aria-hidden="true" width="34" height="34">
  <path d="M14.5 27 L16.5 10.5 L27 19.2 Q32 17.6 37 19.2 L47.5 10.5 L49.5 27 Q53.5 34.5 49.8 42.2 Q44.5 52 32 52 Q19.5 52 14.2 42.2 Q10.5 34.5 14.5 27Z" style="fill:var(--accent)"/>
  <circle cx="25" cy="32.5" r="2.7" style="fill:var(--panel)"/><circle cx="39" cy="32.5" r="2.7" style="fill:var(--panel)"/>
  <path d="M29.8 38.6 H34.2 L32 41.4Z" style="fill:var(--panel)"/>
  <g style="stroke:var(--ink-2)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none">
    <path d="M22 40 L3.5 36.5"/><path d="M22 43.2 L3 44"/><path d="M23 46.2 L6 51.5"/>
    <path d="M42 40 L49 38.2 L53.5 40.2 L61 30.5" style="stroke:var(--accent)" stroke-width="2"/>
    <path d="M42 43.2 L61 44"/><path d="M41 46.2 L58 51.5"/></g></svg>`;

async function vBuilder(el) {
  const d = await api('/api/builder');
  S.bd = d;
  const prog = d.progress.steps;
  const stepBtn = ([k, l], i) => {
    const pr = prog.find(x => x.key === k);
    const done = pr && pr.of && pr.done === pr.of;
    return `<button type="button" class="${S.bStep === k ? 'on' : ''} ${done ? 'done' : ''}" data-act="b-step" data-v="${k}">
      <span class="n">${done ? '✓' : i + 1}</span><span class="l">${esc(l)}</span>${pr ? `<span class="count">${pr.done}/${pr.of}</span>` : ''}</button>`;
  };
  const resultOn = ['result', 'brief', 'written'].includes(S.bStep);
  el.innerHTML = `<div class="builder">
    <header class="b-head">
      <div class="b-brand">${B_MARK}<div><div class="b-title">Plan builder</div><div class="tiny muted">Whiskers</div></div></div>
      <nav class="b-steps" aria-label="Steps">${B_STEPS.map(stepBtn).join('')}
        <button type="button" class="${resultOn ? 'on' : ''}" data-act="b-step" data-v="holdings"><span class="n">→</span><span class="l">Your plan</span></button></nav>
      <button class="btn" data-act="b-back" type="button">Back to Whiskers</button>
    </header>
    <div id="b-main" class="b-main"><div class="spinner"></div></div>
    <p class="note b-foot">Investing questions only: retirement itself has its own section. Built from published research and common practice; it names kinds of investment, never particular funds, and is not financial advice.</p>
  </div>`;
  setTimeout(() => bShow(S.bStep), 0);
}
ACTS['b-back'] = () => go('settings');
ACTS['b-step'] = b => { S.bStep = b.dataset.v; render(); };
ACTS['b-go'] = b => { S.bStep = b.dataset.v; if (b.dataset.mode) S.bMode = b.dataset.mode; render(); };

function bShow(step) {
  const box = $('#b-main');
  if (!box) return;
  if (step === 'result') return bResult(box);
  if (step === 'brief') return bBrief(box);
  if (step === 'written') return bWritten(box);
  if (step === 'holdings') return bHoldings(box);
  if (step === 'views') return bViews(box);
  return bQuestions(box, step);
}

// ---------------------------------------------------------------------------- questions

const bOpt = (q, raw) => { const o = (q.options || []).find(([v]) => String(v) === raw); return o ? o[0] : raw; };

function bNav(step) {
  const i = B_STEPS.findIndex(([k]) => k === step);
  const prev = B_STEPS[i - 1], next = B_STEPS[i + 1];
  return `<div class="spread" style="margin-top:16px">${prev ? `<button class="btn" data-act="b-go" data-v="${prev[0]}">Back</button>` : '<span></span>'}
    ${next ? `<button class="btn primary" data-act="b-go" data-v="${next[0]}">Next: ${esc(next[1])}</button>` : ''}</div>`;
}

function bQuestions(box, step) {
  const d = S.bd;
  const meta = d.steps.find(s => s.key === step);
  const qs = d.questions.filter(q => q.step === step && q.visible && q.kind !== 'views');
  const derived = (d.facts && d.facts.derived) || {};
  const retOn = d.facts && d.facts.retirement_on;
  const intro = step === 'you' ? (retOn
    ? 'Some of these come from your Retirement section; change them there and they change here.'
    : 'The Retirement section is off, so these are asked here. Switched on, it answers the ones about age and retirement itself.') : '';
  box.innerHTML = `<section class="panel b-panel"><h2>${esc(meta.title)}</h2><p class="lede">${esc(meta.intro)}${intro ? ` ${esc(intro)}` : ''}</p>
    <div class="qs">${qs.map(q => bQuestionHtml(q, d.answers[q.id], d.at[q.id], q.id in derived ? q.from : null)).join('')}</div>
    ${step === 'hands' ? bHandsHelp() : ''}
    ${bNav(step)}</section>`;
  wire(box);
  qs.forEach(q => { if (!(q.id in derived)) bWire(q); });
}

function bQuestionHtml(q, a, at, from) {
  const hint = q.hint ? `<div class="hint">${esc(q.hint)}</div>` : '';
  const why = q.why ? `<div class="why">Why it matters: ${esc(q.why)}</div>` : '';
  const has = a !== undefined && a !== null && a !== '' && !(Array.isArray(a) && !a.length);
  if (from) {
    const words = (q.options || []).find(([v]) => String(v) === String(a));
    return `<div class="q saved"><div class="t">${esc(q.text)}</div><div class="derived"><b>${esc(words ? words[1] : a)}</b>
      <span class="small muted">from your ${from === 'mortgage' ? 'Mortgage' : 'Retirement'} section.</span> <a href="#" data-go="${from === 'mortgage' ? 'mortgage' : 'retirement'}">Change it there</a></div>${why}</div>`;
  }
  let input = '';
  if (q.kind === 'one' || q.kind === 'many') {
    const type = q.kind === 'one' ? 'radio' : 'checkbox';
    const picked = q.kind === 'many' ? (a || []).map(String) : [String(a)];
    input = `<div class="opts">${q.options.map(([v, l]) => `<label><input type="${type}" name="bq-${q.id}" value="${esc(String(v))}" ${picked.includes(String(v)) ? 'checked' : ''}>${esc(l)}</label>`).join('')}</div>`;
  } else if (q.kind === 'money') {
    input = `<div class="row"><span>£</span><input type="number" id="bq-${q.id}" value="${esc(a ?? '')}" step="any" min="0" style="width:160px"></div>`;
  }
  return `<div class="q ${has ? 'saved' : ''}" id="bqq-${q.id}"><div class="t">${esc(q.text)}</div>${hint}${input}${why}${at ? `<div class="stamp">Answered ${fmtDate(at)}</div>` : ''}</div>`;
}

// Saves go one at a time, in the order they were made, so a quick second click can never
// overtake the first.
let bQueue = Promise.resolve();
function bSave(answers) {
  const run = async () => {
    const prog = await api('/api/builder', { method: 'PATCH', body: { answers } });
    if (!answers.views) Object.assign(S.bd.answers, answers);
    S.bd.progress = prog;
    bCounts();
    return prog;
  };
  const next = bQueue.then(run, run);
  bQueue = next.catch(() => {});
  return next;
}
function bCounts() {
  for (const p of S.bd.progress.steps) {
    const btn = $(`.b-steps [data-v="${p.key}"]`);
    if (!btn) continue;
    const c = btn.querySelector('.count');
    if (c) c.textContent = `${p.done}/${p.of}`;
    const done = p.of && p.done === p.of;
    btn.classList.toggle('done', !!done);
    const n = btn.querySelector('.n');
    if (n) n.textContent = done ? '✓' : String(B_STEPS.findIndex(([k]) => k === p.key) + 1);
  }
}

function bWire(q) {
  const save = async value => {
    try {
      await bSave({ [q.id]: value });
      const box = $(`#bqq-${q.id}`);
      if (box) box.classList.toggle('saved', !(value === null || value === '' || (Array.isArray(value) && !value.length)));
      // A question shown only after another answer (how much is drawn, say) appears or goes.
      if (S.bd.questions.some(x => x.show_if && x.show_if[q.id])) { S.bd = await api('/api/builder'); bShow(S.bStep); }
    } catch (e) { toast(e.message, true); }
  };
  if (q.kind === 'one') {
    $$(`input[name="bq-${q.id}"]`).forEach(inp => inp.addEventListener('change', () => save(bOpt(q, inp.value))));
  } else if (q.kind === 'many') {
    $$(`input[name="bq-${q.id}"]`).forEach(inp => inp.addEventListener('change', () => {
      let vals = $$(`input[name="bq-${q.id}"]:checked`).map(i => bOpt(q, i.value));
      // "None" and an actual choice can't both be true.
      if (inp.checked && inp.value === 'none') { vals = ['none']; $$(`input[name="bq-${q.id}"]`).forEach(i => { if (i.value !== 'none') i.checked = false; }); }
      else if (inp.checked) { vals = vals.filter(v => v !== 'none'); const n = $(`input[name="bq-${q.id}"][value="none"]`); if (n) n.checked = false; }
      save(vals);
    }));
  } else if (q.kind === 'money') {
    const inp = $(`#bq-${q.id}`);
    if (!inp) return;
    let t;
    const go = () => { clearTimeout(t); t = setTimeout(() => save(inp.value === '' ? null : +inp.value), 500); };
    inp.addEventListener('input', go);
    inp.addEventListener('change', go);
  }
}

function bHandsHelp() {
  return `<div class="hands-help">${[['Funds only', 'Most of the part in shares is one global index fund; themes, if any, are thin slices. The least to look after.'],
    ['A few themes', 'A global index fund as the core, with room beside it for the themes and companies you believe in.'],
    ['Picking', 'A smaller core and real room for your themes, sectors and single companies, each sized by how strongly you believe in it.']]
    .map(([t, d]) => `<div><b>${t}</b><p class="small muted">${d}</p></div>`).join('')}</div>`;
}

// ---------------------------------------------------------------------------- your views

function bViews(box) {
  const d = S.bd;
  const views = d.answers.views || {};
  const held = d.cards.filter(c => c.held), more = d.cards.filter(c => !c.held);
  const worries = d.questions.find(q => q.id === 'worries'), avoid = d.questions.find(q => q.id === 'avoid');
  const main = d.answers.watch_main || 'auto';
  const libKeys = d.cards.map(c => c.key);
  box.innerHTML = `<div class="stack">
    <section class="panel b-panel"><h2>Your views</h2>
      <p class="lede">${esc(d.steps.find(s => s.key === 'views').intro)} Leave a theme alone if you have no view on it.</p>
      <div class="act-key">${Object.entries(d.actions).map(([k, l]) => `<div><b>${esc(l)}</b><span class="small muted">${esc(d.action_about[k])}</span></div>`).join('')}</div>
    </section>
    ${held.length ? `<h3 class="b-sub">In your money now</h3><div class="tcards">${held.map(c => themeCard(c, views[c.key] || {}, d)).join('')}</div>` : ''}
    <details class="b-more" ${held.length ? '' : 'open'}><summary><b>${held.length ? 'More themes' : 'The themes'}</b> <span class="muted small">${more.length}</span></summary>
      <div class="tcards" style="margin-top:10px">${more.map(c => themeCard(c, views[c.key] || {}, d)).join('')}</div></details>
    <section class="panel b-panel"><h2>Your own themes</h2>
      <p class="lede">Something the list doesn’t have, such as robotics or water. It becomes a sleeve of its own, with your reasons. Whiskers has no warning lights for it.</p>
      <div id="b-custom">${(d.answers.custom || []).map((c, i) => themeCard({ key: `custom:${i}`, label: c.label, about: 'Your own theme.', custom: i }, c, d)).join('')}</div>
      <div class="row" style="margin-top:8px"><input type="text" id="b-custom-name" placeholder="Name it, e.g. Robotics" maxlength="40" style="width:240px"><button class="btn" data-act="b-custom-add">Add it</button></div>
    </section>
    <section class="panel b-panel">
      <div class="qs">${bQuestionHtml(worries, d.answers.worries, d.at.worries)}${bQuestionHtml(avoid, d.answers.avoid, d.at.avoid)}
        <div class="q"><div class="t">The one thing on your dial</div>
          <div class="hint">The dial on the Overview and on Market watch follows one theme. Chosen from your views, it is the one you ride with a parachute, or failing that the one that carries most of your money.</div>
          <div><select id="b-main-watch"><option value="auto" ${main === 'auto' ? 'selected' : ''}>Chosen from my views</option>${libKeys.map(k => `<option value="${k}" ${main === k ? 'selected' : ''}>${esc(d.cards.find(c => c.key === k).title)}</option>`).join('')}</select></div></div></div>
      ${bNav('views')}
    </section>
  </div>`;
  wire(box);
  bWire(worries);
  bWire(avoid);
  $('#b-main-watch').addEventListener('change', e => bSave({ watch_main: e.target.value }).catch(err => toast(err.message, true)));
  $$('.tcard', box).forEach(wireCard);
}

function themeCard(c, v, d) {
  const scale = (field, label, ends) => `<div class="scale"><span class="small">${label}</span>
    <div class="seg5" role="radiogroup" aria-label="${esc(label)}">${[1, 2, 3, 4, 5].map(n => `<button type="button" data-f="${field}" data-v="${n}" class="${v[field] === n ? 'on' : ''}" aria-pressed="${v[field] === n}">${n}</button>`).join('')}</div>
    <span class="tiny muted ends">${ends}</span></div>`;
  const mine = (c.sleeves || []).map(s => `${esc(s.name)} ${pts(s.target, s.target % 1 ? 1 : 0)}`).join(', ');
  return `<div class="tcard ${v.action ? 'set' : ''}" data-theme="${esc(c.key)}" ${c.custom !== undefined ? `data-custom="${c.custom}"` : ''}>
    <div class="spread" style="align-items:flex-start"><div><b>${esc(c.label)}</b><div class="tiny muted">${esc(c.about)}</div></div>
      ${known(c.pct) ? `<div class="r"><div class="fig">${pct(c.pct, { dp: 0 })}</div><div class="tiny muted">of your money</div></div>` : ''}
      ${c.custom !== undefined ? '<button class="btn small ghost" data-act="b-custom-del" type="button">Remove</button>' : ''}</div>
    ${mine ? `<div class="tiny muted">In your plan: ${mine}</div>` : ''}
    ${scale('believe', 'How strongly do you believe in it?', '1 not at all · 5 very strongly')}
    ${scale('worry', 'How worried are you it could fall hard?', '1 not at all · 5 very worried')}
    <div class="acts" role="radiogroup" aria-label="What you want to do">${Object.entries(d.actions).map(([k, l]) => `<button type="button" data-f="action" data-v="${k}" class="${v.action === k ? 'on' : ''} ${k}" aria-pressed="${v.action === k}">${esc(l)}</button>`).join('')}</div>
    <details class="words" ${v.why || v.change || v.action ? 'open' : ''}><summary class="small">In your own words</summary>
      <label class="field">Why I hold it<textarea data-f="why" rows="2" placeholder="What you believe, in a sentence or two">${esc(v.why || '')}</textarea></label>
      <label class="field">What would change my mind<textarea data-f="change" rows="2" placeholder="For example: two quarters of falling orders">${esc(v.change || '')}</textarea></label></details>
  </div>`;
}

function wireCard(card) {
  const theme = card.dataset.theme;
  const custom = card.dataset.custom;
  const put = async (field, value) => {
    try {
      if (custom !== undefined) {
        const list = (S.bd.answers.custom || []).map(x => ({ ...x }));
        list[+custom] = { ...list[+custom], [field]: value };
        await bSave({ custom: list });
      } else {
        const views = S.bd.answers.views || (S.bd.answers.views = {});
        views[theme] = { ...(views[theme] || {}), [field]: value };
        await bSave({ views: { [theme]: { [field]: value } } });
        S.bd.answers.views = views;
      }
      card.classList.toggle('set', !!(field === 'action' ? value : card.querySelector('.acts .on')));
    } catch (e) { toast(e.message, true); }
  };
  card.querySelectorAll('button[data-f]').forEach(btn => btn.addEventListener('click', () => {
    const field = btn.dataset.f, val = field === 'action' ? btn.dataset.v : +btn.dataset.v;
    const was = btn.classList.contains('on');
    card.querySelectorAll(`button[data-f="${field}"]`).forEach(x => { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
    if (!was) { btn.classList.add('on'); btn.setAttribute('aria-pressed', 'true'); }
    if (field === 'action' && !was) { const w = card.querySelector('details.words'); if (w) w.open = true; }
    put(field, was ? null : val);
  }));
  card.querySelectorAll('textarea[data-f]').forEach(t => {
    let timer;
    t.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => put(t.dataset.f, t.value), 700); });
    t.addEventListener('change', () => { clearTimeout(timer); put(t.dataset.f, t.value); });
  });
}
ACTS['b-custom-add'] = async b => {
  const name = ($('#b-custom-name').value || '').trim();
  if (!name) { toast('Give it a name first.', true); return; }
  const list = (S.bd.answers.custom || []).concat([{ label: name }]);
  await busy(b, async () => { await bSave({ custom: list }); bShow('views'); });
};
ACTS['b-custom-del'] = async b => {
  const i = +b.closest('.tcard').dataset.custom;
  const list = (S.bd.answers.custom || []).filter((_, j) => j !== i);
  await bSave({ custom: list }).catch(e => toast(e.message, true));
  bShow('views');
};

// ---------------------------------------------------------------------------- what you hold

async function bHoldings(box) {
  const d = S.bd;
  const missing = d.progress.steps.filter(p => p.done < p.of);
  box.innerHTML = `<div class="stack">
    <section class="panel b-panel"><h2>What you hold</h2><p class="lede">${esc(d.steps.find(s => s.key === 'holdings').intro)}</p>
      <div id="b-xray"><div class="spinner"></div></div></section>
    <section class="panel b-panel"><h2>Use your answers</h2>
      ${missing.length ? `<div class="plan-box" style="margin-bottom:12px"><b>Some questions are still blank</b><p class="small" style="margin-top:4px">${missing.map(p => `${esc(p.title)} (${p.of - p.done})`).join(', ')}. Middle-of-the-road answers fill the gaps; answering them makes it yours.</p></div>` : ''}
      <div class="b-choices">
        ${d.has_plan ? `<button class="b-choice primary" data-act="b-go" data-v="result" data-mode="review" type="button"><b>Review my plan against my answers</b><span>Your sleeves and targets stay as they are unless an answer contradicts them. Each suggestion comes with its reason, ready to tick or leave.</span></button>` : ''}
        <button class="b-choice ${d.has_plan ? '' : 'primary'}" data-act="b-go" data-v="result" data-mode="fresh" type="button"><b>${d.has_plan ? 'Build a fresh plan instead' : 'Build my plan'}</b><span>${d.has_plan ? 'A whole new plan from your answers, to compare with yours. Nothing changes unless you choose to use it.' : 'Sleeves and targets shaped by your answers: the core from how hands-on you are, each theme from how strongly you believe in it, defences from your worries.'}</span></button>
        <button class="b-choice" data-act="b-go" data-v="brief" type="button"><b>A bespoke plan from Claude</b><span>Save a brief with your answers, your views in your own words, your holdings and your plan. Give it to Claude, then load the plan file it sends back: Whiskers checks it first.</span></button>
      </div>
      <div class="spread" style="margin-top:14px"><button class="btn" data-act="b-go" data-v="views">Back</button><button class="btn ghost" data-act="b-go" data-v="written">The written plan</button></div>
    </section></div>`;
  wire(box);
  try { const x = await api('/api/xray'); const xb = $('#b-xray'); if (xb) { xb.innerHTML = xrayHtml(x); wire(xb); } }
  catch (e) { const xb = $('#b-xray'); if (xb) xb.innerHTML = `<p class="warnline">${esc(e.message)}</p>`; }
}

function bar(label, frac, colour, right, sub) {
  return `<div class="cat-bar"><span>${esc(label)}${sub ? `<div class="tiny muted">${sub}</div>` : ''}</span><div class="track"><i style="width:${Math.max(0, Math.min(100, (frac || 0) * 100))}%;background:${colour}"></i></div><span class="r small">${right}</span></div>`;
}

function xrayHtml(x) {
  if (x.empty) return '<p class="muted">Nothing priced yet. Add your platforms and press Refresh; the X-Ray looks through what they hold.</p>';
  const c = x.costs || {};
  const th = (x.themes || []).filter(t => (t.pct || 0) >= 0.005);
  return `<div class="stack">
    <div class="stat-row">
      <div class="stat"><span class="k">Looked through</span><span class="v">${money(x.total, { dp: 0 })}</span><span class="tiny muted">${plural(x.holdings, 'holding')}${x.unpriced ? `, ${x.unpriced} without a price` : ''}</span></div>
      <div class="stat"><span class="k">Charges a year</span><span class="v">${money(c.total, { dp: 0 })}</span><span class="tiny muted">${known(c.pct) ? `${(c.pct * 100).toFixed(2)}% of what is invested` : 'not known'}</span></div>
      <div class="stat"><span class="k">Ten largest holdings</span><span class="v">${pct(x.top10_pct, { dp: 0 })}</span><span class="tiny muted">of everything</span></div>
      <div class="stat"><span class="k">Dividends, 12 months</span><span class="v">${money((x.income || {}).dividends_12m, { dp: 0 })}</span><span class="tiny muted">${known((x.income || {}).yield) ? `${(x.income.yield * 100).toFixed(1)}% yield` : ''}</span></div>
    </div>
    ${(x.findings || []).length ? `<div class="alerts">${x.findings.map(f => `<div class="alert ${f.level}"><span class="lvl ${f.level}"></span><span class="t">${esc(f.title)}</span><span class="go"></span><span class="d">${esc(f.detail)}</span></div>`).join('')}</div>` : '<p class="none-state">Nothing in the X-Ray needs a look.</p>'}
    <div class="grid g2">
      <div><h3>What it’s made of</h3>${(x.asset_mix || []).map(m => bar(m.label, m.pct, 'var(--accent)', pct(m.pct, { dp: 0 }), m.guessed > 0.5 * m.value ? `${pct(m.guessed / m.value, { dp: 0 })} of it guessed from names` : '')).join('')}
        <h3 style="margin-top:14px">Where, roughly</h3>${bar('United States', x.regions.us_pct, '#4f8fd6', pct(x.regions.us_pct, { dp: 0 }))}${bar('United Kingdom', x.regions.uk_pct, '#4f8fd6', pct(x.regions.uk_pct, { dp: 0 }))}${bar('Emerging markets', x.regions.em_pct, '#4f8fd6', pct(x.regions.em_pct, { dp: 0 }))}
        <p class="tiny muted">${esc(x.regions.note)} Covers ${pct(x.regions.coverage, { dp: 0 })} of what is invested.</p></div>
      <div><h3>What moves it</h3>${th.map(t => bar(t.label, t.pct, 'var(--red)', `${pct(t.pct, { dp: 0 })} <span class="muted">${money(t.value, { dp: 0 })}</span>`, known(t.coverage) && t.coverage < 0.95 ? `known for ${pct(t.coverage, { dp: 0 })} of holdings` : '')).join('') || '<p class="small muted">No market force carries much of your money.</p>'}
        <p class="tiny muted">A fund counts for the share of it in each theme: from what you set on the holding, a well-known fund’s published make-up, or a guess from its name.</p>
        ${(x.biggest_companies || []).length ? `<h3 style="margin-top:14px">The biggest companies you own, counting funds</h3>
          <table class="small"><tbody>${x.biggest_companies.slice(0, 8).map(b => `<tr><td>${esc(b.company)}${b.direct && b.via ? ' <span class="chip">directly and in funds</span>' : ''}</td><td class="r">${money(b.true, { dp: 0 })}</td><td class="r num">${pct(b.pct, { dp: 1 })}</td></tr>`).join('')}</tbody></table>` : ''}</div>
    </div>
    <p class="note">After Morningstar’s Portfolio X-Ray: what your money really holds once funds are looked through. Approximate where a fund’s make-up isn’t known.</p>
  </div>`;
}

// ---------------------------------------------------------------------------- the result

function riskHtml(r) {
  const marker = (v, col, label) => known(v) ? `<i style="left:${v}%;background:${col}" title="${esc(label)}: ${Math.round(v)}%"></i>` : '';
  return `<section class="panel b-panel"><h2>How much risk</h2>
    <p class="lede">Three tests, from Bogleheads and the regulator’s rules for advisers: the risk you are willing to take, the risk you are able to take, and the risk you need to take. The plan takes the lower of willing and able, and never more than you need without saying so.</p>
    <div class="meter"><div class="track"><div class="fill" style="width:${r.growth}%"></div>${marker(r.willing, 'var(--amber)', 'Willing')}${marker(r.able, 'var(--cyan)', 'Able')}${marker(r.need, 'var(--green)', 'Need')}</div>
      <div class="keys"><span><i style="background:var(--amber)"></i>Willing: ${r.willing}% in shares</span><span><i style="background:var(--cyan)"></i>Able: ${r.able}%</span>
        ${known(r.need) ? `<span><i style="background:var(--green)"></i>Need: ${Math.round(r.need)}%</span>` : r.need_status === 'beyond' ? '<span class="warnline">Need: more than any mix of investments can give</span>' : '<span class="muted">Need: from the Retirement section, when it is on and filled in</span>'}<span><b>The plan: ${r.growth}% in shares</b></span></div></div>
    <ul class="small b-why">${r.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul>
    ${r.alternative ? `<div class="plan-box" style="margin-top:10px"><b>A gentler choice</b><p class="small" style="margin-top:4px">${esc(r.alternative.words)} That would be about ${Math.round(r.alternative.growth)}% in shares.</p></div>` : ''}
    ${r.shortfall ? `<p class="warnline" style="margin-top:8px">${esc(r.shortfall)}</p>` : ''}
  </section>`;
}

function sectionsOffer(list) {
  const off = (list || []).filter(x => !x.on);
  if (!off.length) return '';
  return `<section class="panel b-panel"><h2>Sections that would suit you</h2>
    <p class="lede">From your answers. Each adds one screen to the sidebar and one line to the Overview, and can be switched off again in Settings, Sections.</p>
    <div class="checks">${off.map(x => `<label><input type="checkbox" data-sec="${x.key}" checked><span><b>${x.key === 'mortgage' ? 'Mortgage' : 'Retirement'}</b><br><span class="small muted">${esc(x.why)}</span></span></label>`).join('')}</div></section>`;
}
const chosenSections = () => Object.fromEntries($$('[data-sec]').map(i => [i.dataset.sec, i.checked]));

async function bResult(box) {
  const mode = S.bMode || (S.bd.has_plan ? 'review' : 'fresh');
  let d;
  try { d = await api(`/api/builder/draft?mode=${mode}`); } catch (e) { box.innerHTML = `<div class="panel warnline">${esc(e.message)}</div>`; return; }
  S.bDraft = d;
  if (d.mode === 'review') return bReview(box, d);
  return bFresh(box, d);
}

const B_GROUPS = [['plan', 'Your targets'], ['protect', 'The protections you asked for'], ['words', 'Your reasons'],
  ['watch', 'What to watch, and your plan for a fall'], ['info', 'Worth knowing']];

function bReview(box, d) {
  const rv = d.review;
  const sugg = rv.suggestions;
  const byGroup = g => sugg.filter(s => s.group === g);
  const card = s => `<label class="sugg ${s.kind}" data-sid="${esc(s.id)}">
      ${s.kind === 'info' ? '<span class="lvl info"></span>' : `<input type="checkbox" data-tick="${esc(s.id)}" ${s.ticked ? 'checked' : ''} ${s.needs ? `data-needs="${esc(s.needs.join(' '))}"` : ''}>`}
      <span><b>${esc(s.title)}</b><span class="small d">${narr(s.reason)}</span>${s.change && s.change.from !== undefined && s.change.to !== undefined ? `<span class="tiny muted">${esc(s.change.sleeve)}: ${pts(s.change.from, s.change.from % 1 ? 1 : 0)} → ${pts(s.change.to, s.change.to % 1 ? 1 : 0)}${s.change.balance ? `, balanced against ${esc(s.change.balance)}` : ''}</span>` : ''}</span></label>`;
  const plan = byGroup('plan');
  box.innerHTML = `<div class="stack">
    ${riskHtml(d.risk)}
    <section class="panel b-panel"><div class="spread"><h2>Your plan, reviewed against your answers</h2><span class="muted small">${plural(sugg.filter(s => s.kind !== 'info').length, 'suggestion')}</span></div>
      <p class="lede">Your own targets stand unless an answer contradicts them. Protections you asked for are ticked, ready to use; anything that changes a target is yours to tick. Nothing is bought or sold: these are what Whiskers measures your money against.</p>
      ${B_GROUPS.map(([g, t]) => {
        const items = byGroup(g);
        if (g === 'plan' && !items.length) return `<h3 class="b-sub">${t}</h3><p class="none-state">Your targets already fit your answers. Nothing to change.</p>`;
        return items.length ? `<h3 class="b-sub">${t}</h3><div class="suggs">${items.map(card).join('')}</div>` : '';
      }).join('')}
    </section>
    <section class="panel b-panel"><h2>Your targets after the ticked changes</h2><div id="b-after"></div></section>
    ${sectionsOffer(d.sections)}
    <section class="panel b-panel"><div class="row wrap"><button class="btn primary" data-act="b-apply">Use the ticked changes</button>
      <button class="btn" data-act="b-go" data-v="result" data-mode="fresh">See a fresh plan instead</button><button class="btn" data-act="b-go" data-v="brief">A bespoke plan from Claude</button>
      <button class="btn ghost" data-act="b-go" data-v="written">The written plan</button></div>
      ${plan.length ? '' : '<p class="note" style="margin-top:8px">A fresh plan is there to compare with, not to replace yours unless you choose it.</p>'}</section>
    <section class="panel b-panel"><details><summary><b>Based on</b></summary><ul class="tiny" style="padding-left:18px;display:grid;gap:3px;margin-top:8px">${d.sources.map(([t, u]) => `<li><a href="${esc(u)}">${esc(t)}</a></li>`).join('')}</ul></details></section>
  </div>`;
  wire(box);
  $$('[data-tick]', box).forEach(cb => cb.addEventListener('change', () => { bDeps(cb); bAfter(); }));
  bAfter();
}

// A step needs its sleeve: ticking the step ticks the sleeve it lands in, and unticking the
// sleeve unticks the steps that need it.
function bDeps(cb) {
  if (cb.checked && cb.dataset.needs) cb.dataset.needs.split(' ').forEach(id => { const n = $(`[data-tick="${CSS.escape(id)}"]`); if (n) n.checked = true; });
  if (!cb.checked) $$('[data-needs]').forEach(x => { if (x.dataset.needs.split(' ').includes(cb.dataset.tick)) x.checked = false; });
}

function bAfter() {
  const d = S.bDraft;
  if (!d || !d.review) return;
  const ticked = new Set($$('[data-tick]').filter(c => c.checked).map(c => c.dataset.tick));
  const rows = d.review.sleeves.map(s => ({ name: s.name, now: s.target, after: s.target }));
  const get = n => rows.find(r => r.name === n);
  for (const s of d.review.suggestions) {
    if (!ticked.has(s.id)) continue;
    const ch = s.change || {};
    if (s.kind === 'target' || s.kind === 'add') {
      let r = get(ch.sleeve);
      if (!r) { r = { name: ch.sleeve, now: null, after: 0, added: true }; rows.push(r); }
      const delta = ch.to - r.after;
      r.after = ch.to;
      const bal = ch.balance && get(ch.balance);
      if (bal && bal !== r) bal.after = Math.max(0, bal.after - delta);
    } else if (s.kind === 'move') {
      const f = get(ch.from_sleeve), t = get(ch.to_sleeve);
      if (f && t) { f.after = Math.max(0, f.after - ch.points); t.after += ch.points; }
    }
  }
  const sum = rows.reduce((a, r) => a + r.after, 0);
  const box = $('#b-after');
  if (!box) return;
  const changed = rows.filter(r => r.now === null || Math.abs(r.after - r.now) > 0.001);
  box.innerHTML = !changed.length ? '<p class="small muted">No target changes ticked: every target stays as it is.</p>'
    : `<table class="small"><thead><tr><th>Sleeve</th><th class="r">Now</th><th class="r">After</th></tr></thead><tbody>${rows.map(r => `<tr class="${r.now === null || Math.abs(r.after - r.now) > 0.001 ? 'chg' : ''}"><td>${esc(r.name)}</td><td class="r muted">${r.now === null ? 'new' : pts(r.now, r.now % 1 ? 1 : 0)}</td><td class="r"><b>${pts(r.after, r.after % 1 ? 1 : 0)}</b></td></tr>`).join('')}</tbody></table>
      <p class="tiny ${Math.abs(sum - 100) < 0.01 ? 'muted' : 'warnline'}" style="margin-top:6px">Targets add up to ${+sum.toFixed(2)}%.</p>`;
}

ACTS['b-apply'] = async b => {
  const ticked = $$('[data-tick]').filter(c => c.checked).map(c => c.dataset.tick);
  const sections = chosenSections();
  if (!ticked.length && !Object.values(sections).some(Boolean)) { toast('Tick at least one thing to use.', true); return; }
  const targets = S.bDraft.review.suggestions.filter(s => ticked.includes(s.id) && ['target', 'add', 'move'].includes(s.kind)).length;
  if (!await confirmBox('Use the ticked changes?', `${targets ? `${plural(targets, 'target change')} and the rest of what you ticked go in. ` : 'What you ticked goes in; every target stays as it is. '}Nothing on any platform changes, and your answers stay, so the builder can be run again any time.`, 'Use them')) return;
  await busy(b, async () => {
    const r = await api('/api/builder/apply', { method: 'POST', body: { mode: 'review', ticked, sections } });
    await refreshBoot();
    buildNav();
    toast(r.done.length ? `Done: ${r.done.join(', ')}.` : 'Nothing needed changing.');
    S.bStep = 'written';
    render();
  });
};

function bFresh(box, d) {
  const plan = d.plan;
  const now = Object.fromEntries((d.sleeves_now || []).map(x => [x.name, x.target]));
  const names = [...new Set(plan.sleeves.map(x => x.name).concat((d.sleeves_now || []).map(x => x.name)))];
  box.innerHTML = `<div class="stack">
    ${riskHtml(d.risk)}
    <div class="grid g2">
      <section class="panel b-panel"><h2>${d.has_plan ? 'A fresh plan, beside yours' : 'Your plan'}</h2>
        <table class="small"><thead><tr><th>Sleeve</th>${d.has_plan ? '<th class="r">Yours</th>' : ''}<th class="r">${d.has_plan ? 'Fresh' : 'Target'}</th></tr></thead><tbody>
          ${names.map(n => { const p = plan.sleeves.find(x => x.name === n); return `<tr><td>${esc(n)}${p && p.why ? `<div class="tiny muted">${esc(p.why)}</div>` : ''}</td>${d.has_plan ? `<td class="r muted">${known(now[n]) ? pts(now[n], now[n] % 1 ? 1 : 0) : '—'}</td>` : ''}<td class="r"><b>${p ? pts(p.target, p.target % 1 ? 1 : 0) : '—'}</b></td></tr>`; }).join('')}
        </tbody></table>
        <p class="tiny muted" style="margin-top:6px">Kinds of investment, not particular funds. A global index fund is one fund holding thousands of companies across many countries.</p></section>
      <section class="panel b-panel"><h2>Why it came out this way</h2><ul class="small b-why">${d.why.map(w => `<li>${esc(w)}</li>`).join('')}</ul></section>
    </div>
    <div class="grid g2">
      <section class="panel b-panel"><h2>Rules and protections</h2>
        ${plan.rules.length ? `<ul class="small b-why">${plan.rules.map(x => `<li>${esc(ruleNote(x.note))}</li>`).join('')}</ul>` : '<p class="small muted">None needed on these answers.</p>'}
        <h3 style="margin-top:12px">If ${esc(d.watch.main ? lowerFirst(d.watch.titles[d.watch.main] || d.watch.main) : 'your main watch')} turns</h3><p class="small plan-text">${esc(plan.plans.ai)}</p>
        <h3 style="margin-top:10px">In any big fall</h3><p class="small plan-text">${esc(plan.plans.crash)}</p></section>
      <section class="panel b-panel"><h2>What to watch</h2>
        ${d.watch.main ? `<p><b>${esc(d.watch.titles[d.watch.main] || d.watch.main)}</b> on the dial.</p>` : `<p>${esc(d.watch.note || 'Markets in general.')}</p>`}
        <ul class="small b-why">${d.watch.themes.map(t => `<li><b>${esc(d.watch.titles[t] || t)}</b>: ${esc(d.watch.why[t] || '')}</li>`).join('')}</ul></section>
    </div>
    ${sectionsOffer(d.sections)}
    <section class="panel b-panel"><h2>Use it</h2>
      <p class="lede">Tick what to use. Nothing is sold or bought: the targets, rules and watch are what Whiskers measures your money against from now on.</p>
      <div class="checks">
        <label><input type="checkbox" id="bf-sleeves" checked><span>The target mix ${d.has_plan ? '<span class="small muted">(replaces your current sleeves and targets)</span>' : ''}</span></label>
        <label><input type="checkbox" id="bf-rules" ${plan.rules.length ? 'checked' : 'disabled'}><span>The rules and protections (${plan.rules.length})</span></label>
        <label><input type="checkbox" id="bf-watch" checked><span>What to watch <span class="small muted">(Market watch, the dial and the signals)</span></span></label>
        <label><input type="checkbox" id="bf-plans" checked><span>The plan for a fall</span></label>
        ${plan.playbook ? '<label><input type="checkbox" id="bf-ladder" checked><span>The ladder for drawing on your money</span></label>' : ''}
      </div>
      <div class="row wrap" style="margin-top:12px"><button class="btn primary" data-act="b-apply-fresh">Use the ticked parts</button>
        ${d.has_plan ? '<button class="btn" data-act="b-go" data-v="result" data-mode="review">Back to the review of my plan</button>' : ''}<button class="btn" data-act="b-go" data-v="brief">A bespoke plan from Claude</button></div>
    </section>
  </div>`;
  wire(box);
}
ACTS['b-apply-fresh'] = async b => {
  const parts = { sleeves: $('#bf-sleeves').checked, rules: $('#bf-rules').checked, watch: $('#bf-watch').checked,
    plans: $('#bf-plans').checked, playbook: $('#bf-ladder') ? $('#bf-ladder').checked : false };
  const sections = chosenSections();
  if (!Object.values(parts).some(Boolean) && !Object.values(sections).some(Boolean)) { toast('Tick at least one part.', true); return; }
  if (!await confirmBox('Use these parts of the plan?', `${parts.sleeves && S.bDraft.has_plan ? 'Your sleeves and targets are replaced; holdings in sleeves with other names go back to “not in a sleeve yet”. ' : ''}Nothing on any platform changes. You can run the builder again at any time.`, 'Use them')) return;
  await busy(b, async () => {
    const r = await api('/api/builder/apply', { method: 'POST', body: { mode: 'fresh', parts, sections } });
    await refreshBoot();
    buildNav();
    toast(`Done: ${r.done.join(', ')}.${parts.sleeves ? ' Check how your holdings are sorted on the Allocation screen.' : ''}`);
    S.bStep = 'written';
    render();
  });
};

// ---------------------------------------------------------------------------- the brief for Claude

function bBrief(box) {
  box.innerHTML = `<div class="stack">
    <section class="panel b-panel"><h2>A bespoke plan from Claude</h2>
      <p class="lede">For a plan written around you rather than built from rules: Whiskers writes a brief with your answers, your views in your own words, what you hold and your current plan. Claude writes the plan file; Whiskers checks it and shows what would change before anything goes in.</p>
      <div class="steps b-brief-steps">
        <div class="step"><div class="stack" style="gap:8px"><h3>Save the brief</h3>
          <label class="row small"><input type="checkbox" id="bb-amounts"> Include amounts in pounds <span class="muted">(without them, holdings are shown as shares of the whole)</span></label>
          <div class="row wrap"><button class="btn primary" data-act="bb-save">Save the brief</button><button class="btn" data-act="bb-copy">Copy it</button></div>
          <p class="tiny muted">It holds no account numbers, keys or passwords. Read it before you share it.</p></div></div>
        <div class="step"><div class="stack" style="gap:8px"><h3>Give it to Claude</h3>
          <p class="small">In the Claude app or at claude.ai, start a new chat, attach the brief or paste it in, and ask: “Please write my Whiskers plan file from this brief.” Claude replies with the plan file in a box marked json, and why.</p></div></div>
        <div class="step"><div class="stack" style="gap:8px"><h3>Check what comes back</h3>
          <div class="row wrap"><button class="btn" data-act="bb-file">Choose the plan file</button><span class="small muted">or paste Claude’s whole reply:</span></div>
          <textarea id="bb-paste" rows="5" placeholder="Paste Claude’s reply here, the json box and all"></textarea>
          <div class="row"><button class="btn primary" data-act="bb-check">Check it</button></div></div></div>
      </div>
    </section>
    <div id="bb-result"></div>
    <div class="row"><button class="btn" data-act="b-go" data-v="holdings">Back</button></div>
  </div>`;
  wire(box);
}
const briefUrl = () => `/api/builder/brief${$('#bb-amounts') && $('#bb-amounts').checked ? '?amounts=1' : ''}`;
ACTS['bb-save'] = async b => {
  await busy(b, async () => {
    const res = await api(briefUrl());
    const said = await saveBlob(await res.blob(), `${S.boot.app.name} plan brief ${new Date().toISOString().slice(0, 10)}.md`);
    toast(said || 'Saved. Attach it to a new chat with Claude.');
  });
};
ACTS['bb-copy'] = async b => {
  await busy(b, async () => {
    const res = await api(briefUrl());
    const text = await res.text();
    try { await navigator.clipboard.writeText(text); toast('Copied. Paste it into a new chat with Claude.'); }
    catch (e) { toast('This window can’t copy; save the brief instead.', true); }
  });
};
ACTS['bb-file'] = async () => {
  const f = await pickFile('.json,.txt,.md,application/json,text/plain');
  if (!f) return;
  bCheck(await f.arrayBuffer());
};
ACTS['bb-check'] = () => {
  const t = ($('#bb-paste').value || '').trim();
  if (!t) { toast('Paste Claude’s reply first, or choose the file.', true); return; }
  bCheck(new TextEncoder().encode(t));
};

async function bCheck(body) {
  const out = $('#bb-result');
  out.innerHTML = '<div class="panel"><div class="spinner"></div></div>';
  let r;
  try { r = await api('/api/builder/check', { method: 'POST', body, raw: true }); }
  catch (e) { out.innerHTML = `<div class="panel warnline">${esc(e.message)}</div>`; return; }
  S.bCheck = r;
  const df = r.diff;
  const word = { new: 'new', removed: 'removed', changed: 'changed', same: '' };
  out.innerHTML = `<section class="panel b-panel"><h2>${r.ok ? 'The plan file checks out' : 'The plan file can’t go in yet'}</h2>
    ${r.about ? `<p class="small muted">${esc(r.about)}</p>` : ''}
    ${r.errors.length ? `<div class="plan-box alarm" style="margin-top:8px"><b>To fix first</b><ul class="small b-why">${r.errors.map(e => `<li>${esc(e)}</li>`).join('')}</ul><p class="tiny" style="margin-top:6px">Tell Claude what is listed here and ask for the file again.</p></div>` : ''}
    ${r.warnings.length ? `<div class="plan-box" style="margin-top:8px"><b>Worth a look against your answers</b><ul class="small b-why">${r.warnings.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : ''}
    ${df ? `<div class="grid g2" style="margin-top:12px">
      <div><h3>Sleeves</h3><table class="small"><thead><tr><th>Sleeve</th><th class="r">Now</th><th class="r">In the file</th><th></th></tr></thead><tbody>
        ${df.sleeves.map(x => `<tr class="${x.change === 'same' ? '' : x.change === 'removed' ? 'rem' : 'chg'}"><td>${esc(x.name)}</td><td class="r muted">${known(x.before) ? pts(x.before, x.before % 1 ? 1 : 0) : '—'}</td><td class="r"><b>${known(x.after) ? pts(x.after, x.after % 1 ? 1 : 0) : '—'}</b></td><td class="tiny muted">${word[x.change] || ''}</td></tr>`).join('')}</tbody></table></div>
      <div>${df.rules.length ? `<h3>Rules</h3><ul class="small b-why">${df.rules.map(x => `<li>${esc(x.words)}${x.change === 'replaces' ? ` <span class="tiny muted">(replaces: ${esc(x.before)})</span>` : ''}</li>`).join('')}</ul>` : ''}
        ${df.watch ? `<h3 style="margin-top:10px">What to watch</h3><p class="small">${esc(df.watch.after.join(', '))}${df.watch.main ? `, with ${esc(lowerFirst(df.watch.main))} on the dial` : ''} <span class="muted">(now ${esc(df.watch.before.join(', '))})</span></p>` : ''}
        ${df.plans.length ? `<h3 style="margin-top:10px">Your plan for a fall</h3>${df.plans.map(p => `<p class="small plan-text"><b>${p.topic === 'crash' ? 'In any big fall' : 'If your main watch turns'}:</b> ${esc(p.after)}</p>`).join('')}` : ''}</div></div>` : ''}
    ${r.ok ? `<div class="row" style="margin-top:12px"><button class="btn primary" data-act="bb-use">Load it into Whiskers</button></div>` : ''}
  </section>`;
  wire(out);
}
ACTS['bb-use'] = async b => {
  if (!S.bCheck || !S.bCheck.token) return;
  if (!await confirmBox('Load this plan?', 'The sleeves, targets, rules and watch in the file go in, as shown above. Nothing on any platform changes.', 'Load it')) return;
  await busy(b, async () => {
    const r = await api('/api/builder/use-checked', { method: 'POST', body: { token: S.bCheck.token } });
    await refreshBoot();
    buildNav();
    toast(`Loaded: ${plural(r.report.sleeves, 'sleeve')}, ${plural(r.report.rules, 'rule')}.${(r.sorted || []).length ? ` ${plural(r.sorted.length, 'holding')} sorted into them.` : ''}`);
    S.bStep = 'written';
    render();
  });
};

// ---------------------------------------------------------------------------- the written plan

async function bWritten(box) {
  let w;
  try { w = await api('/api/builder/written'); } catch (e) { box.innerHTML = `<div class="panel warnline">${esc(e.message)}</div>`; return; }
  box.innerHTML = `<div class="stack">
    <div class="row wrap"><button class="btn primary" data-act="plan-print">Print it</button><button class="btn" data-act="plan-html">Save it as a page</button>
      <button class="btn ghost" data-act="b-go" data-v="holdings">Back to your answers</button><button class="btn ghost" data-act="b-back">Back to Whiskers</button>
      <span class="small muted">An investment policy statement, the Bogleheads call it: everything decided, in one place, to keep and reread before acting in a fall.</span></div>
    ${writtenHtml(w)}</div>`;
  wire(box);
}
function writtenHtml(w) {
  const line = l => `<li>${narr(String(l).replace(/£[\d,]+/g, m => `[[${m}]]`))}</li>`;
  const card = c => `<div class="wcard"><div class="spread"><b>${esc(c.title)}</b><span class="tiny muted">${esc(c.action)}${c.believe ? ` · believe ${c.believe}/5` : ''}${c.worry ? ` · worried ${c.worry}/5` : ''}${c.sleeve ? ` · ${esc(c.sleeve)} ${pts(c.target, c.target % 1 ? 1 : 0)}` : ''}</span></div>
    ${c.why ? `<p class="small"><span class="muted">Why:</span> ${esc(c.why)}</p>` : ''}${c.change ? `<p class="small"><span class="muted">What would change my mind:</span> ${esc(c.change)}</p>` : ''}</div>`;
  return `<article class="written"><h1>${esc(w.title)}</h1><p class="small muted">Made ${fmtDate(w.made)}</p>
    ${w.sections.map(s => `<h2>${esc(s.title)}</h2>${s.kind === 'cards' ? `<div class="wcards">${s.lines.map(card).join('')}</div>` : `<ul>${s.lines.map(line).join('')}</ul>`}`).join('')}
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

// ---------------------------------------------------------------------------- choosing the watch directly (Market watch)

ACTS['watch-change'] = async () => {
  let d;
  try { d = await api('/api/watch'); } catch (e) { toast(e.message, true); return; }
  const w = d.watch, sug = d.suggestion;
  const exp = Object.fromEntries((sug.exposures || []).map(e => [e.theme, e.pct]));
  const on = new Set(w.legacy ? ['ai'] : w.themes);
  openModal({ title: 'What to keep an eye on', wide: true, body: `
    <p class="small" style="max-width:80ch">Tick up to five. The main one becomes the dial on the Overview and on Market watch. Suggested from what your money rides on and your views in the plan builder${sug.main ? `: <b>${esc((d.library.find(l => l.key === sug.main) || {}).label || sug.main)}</b> first` : ''}.</p>
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
