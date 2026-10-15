/* Whiskers: importing files, the statements folder, the monthly reminder, and the
   catalogue of UK and South African firms. All from Mittens & Pence.

   Nothing is guessed silently. A dropped file is read and shown first (what it is, the
   rows found, the platform it will go to) and only goes in when somebody says so. The
   statements folder goes in unattended only when the layout is known AND the filename
   names one platform; anything else waits here for a person. */
'use strict';

VIEWS.import = { title: 'Import a file', navTitle: 'Import', sub: 'Drop a statement or holdings file here, or keep a statements folder that is read every time you press Refresh.', render: vImport };

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xlsm,.xls,.ofx,.qfx,.qif,.pdf';
const WRAPPER_WORD = { isa: 'Stocks and shares ISA', gia: 'General investment account', sipp: 'SIPP (a pension you run)', lisa: 'Lifetime ISA' };

async function vImport(el) {
  const [inbox, rem] = await Promise.all([api('/api/inbox'), api('/api/reminder')]);
  const last = inbox.last;
  el.innerHTML = `<div class="stack-lg">
    <section class="panel">
      <div class="dropzone" id="dz" tabindex="0" role="button" aria-label="Choose a file to import">
        <div class="big">Drop a file here, or click to choose one</div>
        <div class="small muted">Freetrade’s activity export, Trading 212’s CSV, or the holdings file from Hargreaves Lansdown, AJ Bell, interactive investor or Vanguard.${S.boot.settings.budget_on ? ' Bank statements too (CSV, OFX, QIF or PDF), for the Budget tab.' : ''} You can drop a file anywhere on the window.</div>
      </div>
      <div id="imp-result" style="margin-top:14px"></div>
    </section>

    <div class="grid g2">
      <section class="panel"><h2>Your statements folder</h2>
        <p class="lede">Put each month’s downloads in this folder and press Refresh. Whatever Whiskers recognises goes in, and the file moves into “Filed”. Anything it can’t place stays put and is listed here. Nothing is ever deleted.</p>
        <dl class="kv"><dt>Folder</dt><dd class="small">${esc(inbox.folder)}${inbox.chosen ? '' : ' <span class="muted">(the usual place)</span>'}</dd>
          <dt>Waiting</dt><dd>${inbox.waiting.length ? inbox.waiting.map(f => `<div class="small">${esc(f)}</div>`).join('') : '<span class="muted">Nothing</span>'}</dd>
          <dt>Last read</dt><dd class="small">${last ? `${ago(last.at)}: ${plural(last.done.length, 'file')} in${last.already.length ? `, ${last.already.length} already in` : ''}${last.left.length ? `, ${last.left.length} left for you` : ''}` : 'Not yet'}</dd></dl>
        ${last && last.left.length ? `<div class="stack" style="gap:6px;margin-top:10px">${last.left.map(x => `<div class="small"><b>${esc(x.file)}</b>: <span class="warnline">${esc(x.why)}</span></div>`).join('')}</div>` : ''}
        ${last && last.done.length ? `<div class="stack" style="gap:4px;margin-top:10px">${last.done.map(x => `<div class="small"><span class="up">✓</span> ${esc(x.file)} → ${esc(x.platform)}</div>`).join('')}</div>` : ''}
        <div class="row wrap" style="margin-top:12px">${onAndroid() ? '' : '<button class="btn" data-act="inbox-open">Open the folder</button>'}<button class="btn" data-act="inbox-read">Read it now</button><button class="btn ghost" data-act="inbox-change">Use a different folder</button></div>
        <p class="note" style="margin-top:8px">Leave each platform’s own filename alone if you can: it usually names the platform, which is how Whiskers knows where the file belongs.</p>
      </section>
      <section class="panel"><h2>A monthly reminder</h2>
        <p class="lede">A strip across the top of Whiskers on the day you choose, until that month’s files are in. Your own calendar can remind you too, wherever you are.</p>
        <div class="row wrap" style="align-items:flex-end">
          <label class="row small"><input type="checkbox" data-act="rem-on" ${rem.on ? 'checked' : ''}> Remind me</label>
          <label class="field">On the<select id="rem-day">${Array.from({ length: 29 }, (_, i) => i + 1).map(n => `<option value="${n}" ${n === Math.min(rem.day, 29) ? 'selected' : ''}>${n === 29 ? 'last day' : ordinal(n)}</option>`).join('')}</select></label>
          <span class="small muted">of each month</span><button class="btn small" data-act="rem-save">Save</button></div>
        <p class="small" style="margin-top:10px">${rem.platforms.length ? `For ${esc(rem.platforms.join(', '))}: the platforms that only update from a file.` : 'No platform needs a file yet: Trading 212 and Monzo update themselves.'} Next due ${fmtDate(rem.next_due)}.</p>
        <div class="row" style="margin-top:10px"><button class="btn" data-act="rem-ics">Add it to my calendar</button></div>
        <p class="note" style="margin-top:6px">Downloads a calendar file that repeats every month. Open it and your calendar (Outlook, Google, Apple) adds the reminder.</p>
      </section>
    </div>

    <section class="panel"><h2>Where each file comes from</h2>
      <p class="lede">The files Whiskers can read, and where each platform keeps them.</p>
      <div class="table-wrap"><table class="small"><tbody>
        ${[['gb-freetrade', 'Freetrade', 'Activity: every trade, dividend and top-up'], ['gb-trading-212', 'Trading 212', 'Activity, if it isn’t connected by key'],
           ['gb-hargreaves-lansdown', 'Hargreaves Lansdown', 'Holdings and values'], ['gb-aj-bell', 'AJ Bell', 'Holdings and values'],
           ['gb-interactive-investor', 'interactive investor', 'Holdings and values'], ['gb-vanguard-investor-uk', 'Vanguard Investor', 'Holdings and values']]
          .map(([id, n, what]) => `<tr><td><b>${n}</b><div class="tiny muted">${what}</div></td><td class="small" data-where="${id}"></td></tr>`).join('')}
      </tbody></table></div>
      <p class="note" style="margin-top:6px">A holdings file is a snapshot: it sets what you hold and what it’s worth on the day it was made. Download a new one each month.</p>
    </section>
  </div>`;
  wireDropzone($('#dz'));
  fillWhere();
  if (S.pendingFile) { const f = S.pendingFile; S.pendingFile = null; setTimeout(() => analyseFile(f), 0); }
}
const ordinal = n => n + (n % 10 === 1 && n !== 11 ? 'st' : n % 10 === 2 && n !== 12 ? 'nd' : n % 10 === 3 && n !== 13 ? 'rd' : 'th');

async function fillWhere() {
  for (const cell of $$('[data-where]')) {
    try { const s = await api(`/api/institutions/${cell.dataset.where}`); cell.textContent = s.where || ''; } catch (e) { /* the row reads fine without it */ }
  }
}

function wireDropzone(dz) {
  if (!dz) return;
  const pick = async () => { const f = await pickFile(ACCEPT); if (f) analyseFile(f); };
  dz.addEventListener('click', pick);
  dz.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); } });
}

// Anywhere on the window: a file dragged over shows the veil, and dropping it opens the
// Import screen with the file already read.
function wireDrop() {
  let depth = 0;
  const veil = $('#drop-veil');
  const hasFiles = e => e.dataTransfer && [...(e.dataTransfer.types || [])].includes('Files');
  window.addEventListener('dragenter', e => { if (!hasFiles(e)) return; depth++; veil.hidden = false; e.preventDefault(); });
  window.addEventListener('dragover', e => { if (!hasFiles(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  window.addEventListener('dragleave', e => { if (!hasFiles(e)) return; depth = Math.max(0, depth - 1); if (!depth) veil.hidden = true; });
  window.addEventListener('drop', e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0; veil.hidden = true;
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    if (!$('#modal').hidden) closeModal();
    if (S.view === 'import' && $('#imp-result')) analyseFile(f);
    else { S.pendingFile = f; go('import'); }
  });
}

async function analyseFile(f) {
  const out = $('#imp-result');
  if (!out) { S.pendingFile = f; go('import'); return; }
  out.innerHTML = `<div class="row"><div class="spinner" style="margin:0"></div><span class="small">Reading ${esc(f.name)}…</span></div>`;
  let r;
  try { r = await api(`/api/import/analyse?name=${encodeURIComponent(f.name)}`, { method: 'POST', body: await f.arrayBuffer(), raw: true }); }
  catch (e) { out.innerHTML = `<div class="plan-box alarm"><b>${esc(f.name)}</b><p class="small" style="margin-top:4px">${esc(e.message)}</p></div>`; return; }
  S.importRep = r;
  const plats = r.platforms || [];
  const bank = r.kind === 'bank';
  const canImport = !bank || S.boot.settings.budget_on;
  const choices = bank ? plats.filter(p => p.provider === 'bank') : plats.filter(p => p.provider !== 'bank');
  const preview = r.preview || [];
  const cols = preview.length ? Object.keys(preview[0]).filter(k => !k.startsWith('_')).slice(0, 8) : [];
  out.innerHTML = `<div class="stack">
    <div class="spread"><div><h3>${esc(r.label || 'A file')}</h3><p class="small muted">${esc(r.filename)}: ${plural(r.rows, 'row')}${r.first ? `, ${fmtDate(r.first)} to ${fmtDate(r.last)}` : ''}${known(r.total) ? `, worth ${money(r.total, { dp: 0 })} in all` : ''}${known(r.cash) && r.cash ? `, including ${money(r.cash, { dp: 0 })} cash` : ''}.</p></div>
      <button class="btn ghost small" data-act="imp-clear">Not this one</button></div>
    ${(r.warnings || []).map(w => `<p class="warnline">${esc(w)}</p>`).join('')}
    ${cols.length ? `<div class="preview-table"><table><thead><tr>${cols.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${preview.slice(0, 12).map(row => `<tr>${cols.map(c => `<td>${typeof row[c] === 'number' ? (/value|cost|amount|price/i.test(c) ? money(row[c], { dp: 2 }) : esc(String(+row[c].toFixed(4)))) : esc(row[c] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : ''}
    ${canImport ? (choices.length ? `<div class="row wrap" style="align-items:flex-end">
        <label class="field">It belongs to<select id="imp-plat">${r.suggested_platform ? '' : '<option value="">Choose…</option>'}${choices.map(p => `<option value="${p.id}" ${p.id === r.suggested_platform ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>
        ${r.kind === 'holdings' ? `<label class="field">Values as at<input type="date" id="imp-asof" value="${esc(r.as_of || new Date().toISOString().slice(0, 10))}"></label>` : ''}
        <button class="btn primary" data-act="imp-commit">Import it</button></div>
        ${r.suggested_platform ? '<p class="tiny muted">Chosen from the filename and the file’s layout. Change it if that’s wrong.</p>' : ''}`
      : `<p class="small">Add the ${bank ? 'bank account' : 'platform'} it comes from first, then drop the file again.</p><div class="row"><button class="btn primary" data-act="add-from-catalogue">Find your platform or account</button></div>`)
      : '<div class="row"><button class="btn" data-go="settings">Switch on the Budget tab in Settings</button></div>'}
    <p class="note">Importing a file that overlaps one already in is safe: nothing is counted twice.</p>
  </div>`;
  wire(out);
}
ACTS['imp-clear'] = () => { $('#imp-result').innerHTML = ''; S.importRep = null; };
ACTS['imp-commit'] = async b => {
  const pid = $('#imp-plat').value;
  if (!pid) { toast('Choose where it belongs first.', true); return; }
  await busy(b, async () => {
    const out = await api('/api/import/commit', { method: 'POST', body: { token: S.importRep.token, platform_id: +pid, as_of: $('#imp-asof') ? $('#imp-asof').value : null } });
    const bits = [];
    if (known(out.holdings)) bits.push(`${plural(out.holdings, 'holding')} set${out.removed ? `, ${out.removed} no longer held` : ''}`);
    if (known(out.trades)) bits.push(plural(out.trades, 'new trade'));
    if (known(out.dividends)) bits.push(plural(out.dividends, 'new dividend'));
    if (known(out.added)) bits.push(plural(out.added, 'new transaction'));
    $('#imp-result').innerHTML = `<div class="plan-box"><b>In it goes: ${esc(out.platform)}.</b><p class="small" style="margin-top:4px">${esc(bits.join(', ') || 'Done')}.${known(out.cash_estimate) ? ` By the file’s arithmetic, cash should be about ${moneyText(out.cash_estimate, 2)}: check it against the app and type the real figure on the platform in Settings.` : ''}</p>
      ${(out.warnings || []).map(w => `<p class="warnline small">${esc(w)}</p>`).join('')}</div>`;
    S.importRep = null;
    pollRefresh();
    checkReminder();
  });
};

ACTS['inbox-open'] = async () => {
  try { const r = await api('/api/inbox/open', { method: 'POST', body: {} }); if (!r.opened) toast(`The folder is ${r.folder}`); }
  catch (e) { toast(e.message, true); }
};
ACTS['inbox-read'] = async b => {
  await busy(b, async () => {
    const r = await api('/api/inbox/import', { method: 'POST', body: {} });
    toast(r.done.length ? `${plural(r.done.length, 'file')} imported.` : r.left.length ? `${plural(r.left.length, 'file')} left for you: see the list.` : 'Nothing new in the folder.', !r.done.length && !!r.left.length);
    pollRefresh();
    render();
  });
};
ACTS['inbox-change'] = async () => {
  const st = await api('/api/inbox');
  openModal({ title: 'The statements folder', body: `<label class="field">Folder<input type="text" id="ib-folder" value="${esc(st.chosen ? st.folder : '')}" placeholder="${esc(st.default)}" spellcheck="false"><span class="help">A whole path. Leave it blank for the usual place: ${esc(st.default)}. A folder in OneDrive works, so a phone can add files to it too.</span></label>`,
    foot: '<button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="ib-save">Save</button>' });
};
ACTS['ib-save'] = async b => {
  await busy(b, async () => { await api('/api/settings', { method: 'PATCH', body: { statements_folder: $('#ib-folder').value } }); closeModal(); toast('Saved.'); render(); });
};
ACTS['rem-on'] = async b => { await api('/api/settings', { method: 'PATCH', body: { reminder_on: b.checked } }).catch(e => toast(e.message, true)); checkReminder(); };
ACTS['rem-save'] = async b => {
  await busy(b, async () => { await api('/api/settings', { method: 'PATCH', body: { reminder_day: +$('#rem-day').value } }); toast('Saved.'); checkReminder(); render(); });
};
ACTS['rem-ics'] = async b => {
  await busy(b, async () => {
    const res = await api('/api/reminder/calendar');
    const said = await saveBlob(await res.blob(), `${S.boot.app.name} - monthly statement reminder.ics`);
    toast(said || 'Downloaded. Open the file and your calendar adds the reminder.');
  });
};

// ---------------------------------------------------------------------------- the strip at the top

async function checkReminder() {
  let r;
  try { r = await api('/api/reminder'); } catch { return; }
  const bar = $('#reminder-banner');
  if (!r.show_banner) { bar.hidden = true; bar.innerHTML = ''; return; }
  bar.innerHTML = `<span><b>Time to fetch ${esc(r.month)}’s statements.</b> Download them from ${esc(r.platforms.join(', '))}, put the files in your statements folder${onAndroid() ? '' : ' (or drop them on this window)'}, then press Refresh.</span><span class="grow"></span>
    ${onAndroid() ? '<button class="btn small" data-go="import">Import</button>' : '<button class="btn small primary" data-act="inbox-open">Open the folder</button>'}
    <button class="btn small ghost" data-act="rem-dismiss">Not now</button>`;
  bar.hidden = false;
  wire(bar);
}
ACTS['rem-dismiss'] = async () => {
  $('#reminder-banner').hidden = true;
  try { await api('/api/reminder/dismiss', { method: 'POST', body: {} }); } catch { /* only cosmetic */ }
};

// A refresh reads the statements folder first; say what it found.
async function afterRefresh(st) {
  try {
    const ib = await api('/api/inbox');
    const last = ib.last;
    if (last && st && st.started && String(last.at) >= String(st.started)) {
      if (last.done.length) toast(`From your statements folder: ${last.done.map(x => `${x.file} → ${x.platform}`).join('; ')}.`);
      if (last.left.length) toast(`${plural(last.left.length, 'file')} in your statements folder need${last.left.length === 1 ? 's' : ''} you. The Import screen says why.`, true);
    }
  } catch { /* the toast is a courtesy */ }
  checkReminder();
}

SETTINGS_PANELS.middle.push(() => `<section class="panel"><h2>Statements folder and reminder</h2>
  <p class="lede">Where Whiskers looks for downloaded statements each time you press Refresh, and the monthly reminder to put them there. Both are on the Import screen.</p>
  <button class="btn" data-go="import">Go to the Import screen</button></section>`);

// ---------------------------------------------------------------------------- the catalogue

ACTS['add-from-catalogue'] = () => {
  openModal({ title: 'Find your platform or account', wide: true, body: `
    <div class="row wrap"><input type="search" id="cat-q" placeholder="Type a name: Hargreaves, Nationwide, NHS Pension, Capitec…" style="flex:1;min-width:240px" autocomplete="off">
      <select id="cat-country"><option value="">UK and South Africa</option><option value="GB">UK</option><option value="ZA">South Africa</option></select></div>
    <div class="cat-results" id="cat-res"></div>
    <p class="note" style="margin-top:8px">Over 270 banks, building societies, platforms and pension providers. Each says how it keeps up to date: <span class="route connect">connects automatically</span> <span class="route file">download a file</span> <span class="route type">type it in</span>. Not there? <a href="#" data-act="cat-manual">Type one in yourself</a>.</p>`,
    foot: '<button class="btn" data-act="close">Close</button>' });
  let t;
  const run = async () => {
    const q = $('#cat-q').value, c = $('#cat-country').value;
    try {
      const r = await api(`/api/institutions?q=${encodeURIComponent(q)}${c ? `&country=${c}` : ''}`);
      $('#cat-res').innerHTML = r.items.map(x => `<button type="button" data-act="cat-pick" data-id="${esc(x.id)}"><span><b>${esc(x.name)}</b><div class="sub">${esc(x.kind_label)}, ${x.country === 'ZA' ? 'South Africa' : 'UK'}</div></span><span class="route ${x.route}">${esc(x.route_label)}</span></button>`).join('')
        || '<p class="small muted" style="padding:8px">Nothing by that name. Try a shorter part of it, or type it in yourself.</p>';
      wire($('#cat-res'));
    } catch (e) { $('#cat-res').innerHTML = `<p class="warnline">${esc(e.message)}</p>`; }
  };
  $('#cat-q').addEventListener('input', () => { clearTimeout(t); t = setTimeout(run, 180); });
  $('#cat-country').addEventListener('change', run);
  run();
};
ACTS['cat-manual'] = () => {
  openModal({ title: 'Type one in yourself', body: `<div class="stack">
    <button class="btn" data-act="add-platform" data-kind="other">An investment platform</button>
    <button class="btn" data-act="bank-add">A bank or savings account</button>
    <button class="btn" data-act="card-add">A credit card</button>
    <button class="btn" data-act="cat-pension">A pension</button>
    <button class="btn" data-act="asset-add">Your home, or something else you own</button></div>`, foot: '<button class="btn" data-act="close">Cancel</button>' });
};
ACTS['cat-pension'] = () => { closeModal(); go('pensions'); };

const DB_SCHEMES = /\b(nhs|teachers|civil service|local government|lgps|police|armed forces|firefighters|uss|universities superannuation|principal civil)\b/i;

ACTS['cat-pick'] = async b => {
  let s;
  try { s = await api(`/api/institutions/${encodeURIComponent(b.dataset.id)}`); } catch (e) { toast(e.message, true); return; }
  S.catPick = s;
  const inst = s.institution;
  const za = inst.country === 'ZA';
  let form = '';
  if (s.becomes === 'platform') {
    form = `<div class="form-grid">
      <label class="field">Name it<input type="text" id="cp-name" value="${esc(inst.name)}${s.wrappers.includes('isa') ? ' ISA' : ''}"></label>
      <label class="field">Kind of account<select id="cp-wrapper">${s.wrappers.map(w => `<option value="${w}">${esc(WRAPPER_WORD[w] || w)}</option>`).join('')}</select></label>
      <label class="field">Its yearly platform fee, if any (£)<input type="number" id="cp-fee" min="0" step="1" placeholder="0"><span class="help">For the X-Ray’s total of what you pay. Fund charges are counted separately.</span></label>
      <label class="row small"><input type="checkbox" id="cp-flex"> A flexible ISA <span class="muted">(money taken out can go back in the same tax year)</span></label></div>`;
  } else if (s.becomes === 'bank') {
    form = `<div class="form-grid">
      <label class="field">Name it<input type="text" id="cp-name" value="${esc(inst.name)}"></label>
      <label class="field">Balance, in ${esc(inst.currency)}<input type="number" id="cp-bal" step="0.01"></label>
      <label class="row small full"><input type="checkbox" id="cp-inplan"> Part of my plan: count it in my Cash sleeve</label></div>
      ${za ? '<p class="tiny muted" style="margin-top:6px">Kept in rand and converted at each day’s rate. South Africa’s deposit insurance, CoDI, covers R100,000 per bank.</p>' : ''}`;
  } else if (s.becomes === 'card') {
    form = `<div class="form-grid"><label class="field">Name it<input type="text" id="cp-name" value="${esc(inst.name)}"></label>
      <label class="field">Owed now (£)<input type="number" id="cp-owed" min="0" step="0.01"></label></div>`;
  } else if (s.becomes === 'pension') {
    form = `<p class="small">${DB_SCHEMES.test(inst.name) ? 'This is usually a final-salary or career-average scheme: a promise of so much a year.' : 'This is usually a pension pot.'} It goes on the Retirement tab’s Pensions screen.</p>`;
  } else {
    form = '<p class="small">Add it with its value; update it when you have a valuation.</p>';
  }
  openModal({ title: inst.name, wide: true, body: `<div class="stack">
    <div class="row"><span class="route ${s.route}">${esc(s.route_label)}</span><span class="small muted">${esc(inst.kind_label)}, ${za ? 'South Africa' : 'UK'}${s.website ? ` · <a href="${esc(s.website)}">website</a>` : ''}</span></div>
    <p class="small" style="max-width:80ch">${esc(s.summary)}</p>
    ${s.where && s.route === 'file' ? `<p class="small"><b>Where the file is:</b> ${esc(s.where)}</p>` : ''}
    ${s.withheld.length ? `<p class="tiny muted">Not offered: ${esc(s.withheld.join('; '))}. They need a paid service or a company licence, which a household app shouldn’t ask for.</p>` : ''}
    ${form}</div>`,
    foot: `<button class="btn" data-act="add-from-catalogue">Back to the list</button><button class="btn primary" data-act="cat-add">${s.becomes === 'pension' ? 'Add the pension' : 'Add it'}</button>` });
};

ACTS['cat-add'] = async b => {
  const s = S.catPick, inst = s.institution, za = inst.country === 'ZA';
  if (s.becomes === 'pension') {
    closeModal();
    go('pensions');
    const kind = za ? 'sa_ra' : DB_SCHEMES.test(inst.name) ? 'db' : 'dc';
    setTimeout(async () => {
      if (!S.pens) S.pens = await api('/api/pensions');
      pensionForm(kind, { name: inst.name.replace(/ Scheme$/, ''), provider: inst.name });
    }, 400);
    return;
  }
  if (s.becomes === 'property') { closeModal(); assetForm({ name: inst.name, kind: 'property' }); return; }
  await busy(b, async () => {
    let body;
    if (s.becomes === 'platform') {
      body = { name: $('#cp-name').value, provider: s.provider || 'other', wrapper: $('#cp-wrapper').value, flexible: $('#cp-flex').checked,
        fee_year: $('#cp-fee').value, currency: inst.currency || 'GBP', country: inst.country, institution: inst.id };
    } else if (s.becomes === 'bank') {
      body = { name: $('#cp-name').value, provider: 'bank', cash: $('#cp-bal').value, in_plan: $('#cp-inplan').checked,
        currency: inst.currency || 'GBP', country: inst.country, institution: inst.id };
    } else {
      body = { name: $('#cp-name').value, provider: 'card', owed: $('#cp-owed').value, country: inst.country, institution: inst.id };
    }
    const r = await api('/api/platforms', { method: 'POST', body });
    closeModal();
    await refreshBoot();
    if (s.provider === 'trading212') { t212Modal(r.id); return; }
    if (s.provider === 'freetrade') { ftImport(r.id); return; }
    if (s.provider === 'monzo') { ACTS['monzo-connect']({ dataset: { id: r.id } }); return; }
    if (s.route === 'file') {
      toast(`${body.name} added. Now download its file (${s.where || 'from its website'}) and drop it on this screen.`);
      go('import');
      return;
    }
    toast(s.becomes === 'platform' ? `${body.name} added. Add what it holds on the Holdings screen (“Add a holding by hand”), or type its cash in Settings.` : `${body.name} added. Update the balance in Settings whenever it changes.`);
    if (body.currency && body.currency !== 'GBP') pollRefresh();
    render();
  });
};
