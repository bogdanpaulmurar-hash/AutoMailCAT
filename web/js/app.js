// AutoMailCAT interface: plain JavaScript, no external libraries (works offline).
'use strict';

const S = {
  info: null,          // /api/status
  teamId: '',
  data: null,          // /api/team payload of the selected team
  view: 'today',
  dirty: false,
  day: '',             // date shown on the Today page
  plan: null, planSource: '', planReport: null, rotation: {},
  agents: null, rules: null, team: null,
  openRule: '', openAgent: '',
};

// ── helpers ─────────────────────────────────────────────────────────────
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'value') el.value = v;
    else if (k === 'checked') el.checked = !!v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const clone = (x) => JSON.parse(JSON.stringify(x));
const byId = (list) => Object.fromEntries((list || []).map((a) => [a.id, a]));
const fullName = (a) => a ? `${a.first_name || ''} ${a.last_name || ''}`.trim() || '?' : '?';
const lines = (v) => (Array.isArray(v) ? v : String(v || '').split(/\n|,|;/)).map((x) => String(x).trim()).filter(Boolean);
const fmtDate = (iso) => iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '';
const todayIso = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (method !== 'GET') { opts.headers['X-AutoMailCAT'] = '1'; opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body || {}); }
  let res;
  try { res = await fetch('/api/' + path, opts); } catch (e) { throw new Error('network'); }
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty */ }
  if (!res.ok) { const err = new Error(data.error || ('HTTP ' + res.status)); err.code = data.error; err.data = data; throw err; }
  return data;
}
const tq = (path) => path + (path.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(S.teamId);

function toast(msg, bad) {
  const el = h('div', { class: 'toast' + (bad ? ' bad' : '') }, msg);
  document.getElementById('toasts').append(el);
  setTimeout(() => el.remove(), bad ? 7000 : 3500);
}
function fail(e) { toast(e.message === 'network' ? t('err_network') : errText(e.code || e.message), true); }

function modal(title, content, buttons) {
  return new Promise((resolve) => {
    const bg = h('div', { class: 'modal-bg' });
    const close = (v) => { bg.remove(); document.removeEventListener('keydown', onKey); resolve(v); };
    const onKey = (e) => { if (e.key === 'Escape') close(null); };
    document.addEventListener('keydown', onKey);
    const foot = h('footer', {}, (buttons || [{ label: t('close'), value: null }]).map((b) =>
      h('button', { class: 'btn' + (b.primary ? ' primary' : ''), onclick: () => close(b.value) }, b.label)));
    bg.append(h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' }, h('header', {}, title), h('div', { class: 'content' }, content), foot));
    bg.addEventListener('click', (e) => { if (e.target === bg) close(null); });
    document.body.append(bg);
    const first = bg.querySelector('select, input, textarea, button.primary');
    if (first) first.focus();
  });
}
async function ask(question) {
  return modal(question, h('div'), [{ label: t('cancel'), value: false }, { label: t('yes'), value: true, primary: true }]);
}

function field(label, input, hint) {
  return h('label', { class: 'f' }, h('span', {}, label), input, hint ? h('div', { class: 'hint' }, hint) : null);
}
function textIn(value, oninput, attrs) {
  return h('input', { type: 'text', value: value || '', oninput: (e) => oninput(e.target.value), ...(attrs || {}) });
}
function areaIn(value, oninput, attrs) {
  return h('textarea', { oninput: (e) => oninput(e.target.value), ...(attrs || {}) }, Array.isArray(value) ? value.join('\n') : (value || ''));
}
function selectIn(value, options, onchange, attrs) {
  return h('select', { onchange: (e) => onchange(e.target.value), ...(attrs || {}) },
    options.map(([v, label]) => h('option', { value: v, selected: String(v) === String(value) ? 'selected' : null }, label)));
}
function checkIn(label, checked, onchange, hint) {
  return h('label', { class: 'check' }, h('input', { type: 'checkbox', checked, onchange: (e) => onchange(e.target.checked) }),
    h('span', {}, label, hint ? h('div', { class: 'hint' }, hint) : null));
}
function markDirty() { S.dirty = true; const el = document.getElementById('dirty'); if (el) el.classList.remove('hidden'); }

// drag & drop ordering for a list of elements; onMove(from, to)
function sortable(container, itemSelector, onMove) {
  let from = -1;
  const items = () => [...container.querySelectorAll(':scope > ' + itemSelector)];
  const clear = () => items().forEach((x) => x.classList.remove('drop-before', 'drop-after', 'dragging'));
  items().forEach((el, i) => {
    el.draggable = true;
    el.addEventListener('dragstart', (e) => {
      if (e.target.closest('input, textarea, select')) { e.preventDefault(); return; }
      from = i; el.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(i));
    });
    el.addEventListener('dragend', () => { from = -1; clear(); });
    el.addEventListener('dragover', (e) => {
      if (from < 0) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const after = e.clientY > r.top + r.height / 2;
      items().forEach((x) => x.classList.remove('drop-before', 'drop-after'));
      el.classList.add(after ? 'drop-after' : 'drop-before');
    });
    el.addEventListener('drop', (e) => {
      if (from < 0) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      let to = i + (e.clientY > r.top + r.height / 2 ? 1 : 0);
      if (to > from) to -= 1;
      const f = from; clear(); from = -1;
      if (to !== f) onMove(f, to);
    });
  });
}
function moveItem(list, from, to) { const [x] = list.splice(from, 1); list.splice(to, 0, x); }

// ── shell ───────────────────────────────────────────────────────────────
const VIEWS = ['today', 'agents', 'rules', 'journal', 'team', 'demo', 'setup', 'guide'];

function currentTeam() { return (S.info?.teams || []).find((x) => x.id === S.teamId); }

function engineStatus(st) {
  st = st || {};
  if (st.paused) return ['warn', t('eng_paused')];
  switch (st.role) {
    case 'leader': return ['ok', t('eng_leader')];
    case 'standby': return ['ok', t('eng_standby', { pc: st.leader?.pc || '?' })];
    case 'connecting': return ['warn', t('eng_connecting')];
    case 'error': return ['bad', t('eng_error', { msg: errText(st.message) })];
    case 'disabled': return ['', t('eng_disabled')];
    default: return ['', t('eng_stopped')];
  }
}

function renderShell() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  const team = currentTeam();
  const [cls, label] = engineStatus(team?.status);
  const langBtn = (l) => h('button', { class: LANG === l ? 'on' : '', onclick: () => changeLang(l) }, l.toUpperCase());
  app.append(h('header', { class: 'top' },
    h('div', { class: 'brand', html: '' },
      h('img', { src: 'icons/logo.svg', alt: '', width: 30, height: 30 }),
      h('div', {}, 'AutoMailCAT', h('small', {}, t('app_tagline')))),
    (S.info?.teams || []).length ? h('label', { class: 'row small muted' }, t('team'),
      selectIn(S.teamId, S.info.teams.map((x) => [x.id, x.name + (x.reachable ? '' : ' ⚠')]), (v) => switchTeam(v))) : null,
    h('div', { class: 'grow' }),
    team ? h('span', { class: 'pill ' + cls, id: 'engine-pill', title: label }, label) : null,
    h('div', { class: 'lang', role: 'group', 'aria-label': t('language') }, langBtn('ro'), langBtn('en'))));
  const isDemo = team?.demo || S.info?.demo;
  const views = VIEWS.filter((v) => (v !== 'demo' || isDemo) && (team || ['setup', 'guide'].includes(v)));
  app.append(h('nav', { class: 'tabs' }, views.map((v) => h('a', { href: '#/' + v, class: S.view === v ? 'on' : '' }, t('nav_' + v)))));
  app.append(h('main', { id: 'main' }, h('p', { class: 'muted' }, t('loading'))));
}

async function changeLang(l) {
  setLang(l);
  try { await api('POST', 'settings', { language: l }); } catch (e) { /* offline is fine */ }
  route(true);
}

async function switchTeam(id) {
  if (S.dirty && !confirm(t('confirm_leave'))) { renderShell(); return; }
  S.teamId = id; S.dirty = false; S.data = null; S.plan = null;
  try { localStorage.setItem('amc.team', id); } catch (e) { /* ignore */ }
  route(true);
}

async function loadInfo() {
  S.info = await api('GET', 'status');
  if (!S.info.teams.find((x) => x.id === S.teamId)) {
    let saved = '';
    try { saved = localStorage.getItem('amc.team') || ''; } catch (e) { /* ignore */ }
    S.teamId = (S.info.teams.find((x) => x.id === saved) || S.info.teams[0] || {}).id || '';
  }
}

async function loadTeam() {
  S.data = await api('GET', tq('team'));
  S.team = clone(S.data.team); S.agents = clone(S.data.agents); S.rules = clone(S.data.rules);
}

async function route(force) {
  const view = (location.hash.replace(/^#\/?/, '').split('?')[0]) || 'today';
  if (!force && S.dirty && view !== S.view && !confirm(t('confirm_leave'))) { location.hash = '#/' + S.view; return; }
  if (view !== S.view || force) S.dirty = false;
  S.view = VIEWS.includes(view) ? view : 'today';
  try { await loadInfo(); } catch (e) { document.getElementById('app').innerHTML = ''; document.getElementById('app').append(h('main', {}, h('div', { class: 'banner bad' }, t('err_network')))); return; }
  if (!S.info.teams.length && !['setup', 'guide'].includes(S.view)) S.view = 'setup';
  renderShell();
  const main = document.getElementById('main');
  try {
    if (S.teamId && !['setup', 'guide'].includes(S.view)) await loadTeam();
    main.innerHTML = '';
    await PAGES[S.view](main);
  } catch (e) {
    main.innerHTML = '';
    main.append(h('div', { class: 'banner bad' }, e.message === 'network' ? t('err_network') : errText(e.code || e.message)));
    if (e.code === 'team_folder_unreachable') main.append(h('p', {}, h('a', { href: '#/setup' }, t('nav_setup'))));
  }
}

function readOnlyBanner() {
  return S.data && !S.data.can_edit ? h('div', { class: 'banner warn' }, t('read_only')) : null;
}

async function refreshPill() {
  try {
    await loadInfo();
    const pill = document.getElementById('engine-pill');
    const team = currentTeam();
    if (pill && team) {
      const [cls, label] = engineStatus(team.status);
      pill.className = 'pill ' + cls; pill.textContent = label; pill.title = label;
    }
    const w = document.getElementById('engine-extra');
    if (w && team) w.replaceWith(engineExtra(team.status));
  } catch (e) { /* ignore */ }
}

function engineExtra(st) {
  st = st || {};
  const box = h('div', { class: 'row small muted', id: 'engine-extra' });
  if (st.demo) box.append(h('span', { class: 'tag warn' }, t('eng_demo')));
  if (st.waiting) box.append(h('span', { class: 'tag warn' }, t('eng_waiting', { n: st.waiting })));
  if (st.last_sweep) box.append(h('span', {}, t('eng_last_sweep', { t: st.last_sweep.slice(11, 16) })));
  if (st.role === 'leader') {
    box.append(h('button', { class: 'btn small', onclick: () => engineCmd('sweep') }, t('eng_sweep')));
    box.append(h('button', { class: 'btn small', onclick: () => engineCmd(st.paused ? 'resume' : 'pause') }, st.paused ? t('eng_resume') : t('eng_pause')));
  }
  return box;
}
async function engineCmd(action) {
  try { await api('POST', tq('engine'), { action }); setTimeout(refreshPill, 600); } catch (e) { fail(e); }
}

// ── trace text ──────────────────────────────────────────────────────────
function traceList(trace) {
  return h('ol', { class: 'trace' }, (trace || []).map((s) =>
    h('li', { class: s.ok === true ? 'ok' : s.ok === false ? 'no' : '' }, t('tr_' + s.key, s.params || {}))));
}
function stepLabel(step) { return t('step_' + (step || 'wait')); }

// ── Today ───────────────────────────────────────────────────────────────
const PAGES = {};

PAGES.today = async (main) => {
  if (!S.day) S.day = todayIso();
  const res = await api('GET', tq('plan?date=' + S.day));
  S.plan = res.plan; S.planSource = res.source; S.planReport = res.report; S.rotation = res.rotation || {};
  renderToday(main);
};

function renderToday(main) {
  main.innerHTML = '';
  const team = S.data.team;
  const agents = S.data.agents.filter((a) => a.active !== false);
  const ids = byId(S.data.agents);
  const plan = S.plan;
  const editable = S.data.can_edit;
  const isToday = S.day === todayIso();

  main.append(h('div', { class: 'page-head' },
    h('div', {}, h('h1', {}, t('today_title', { d: fmtDate(S.day) })), engineExtra(currentTeam()?.status)),
    h('label', { class: 'row small muted' }, t('today_date'),
      h('input', { type: 'date', value: S.day, onchange: async (e) => {
        if (S.dirty && !confirm(t('confirm_leave'))) { e.target.value = S.day; return; }
        S.day = e.target.value || todayIso(); S.dirty = false; await PAGES.today(main);
      } }))));
  const ro = readOnlyBanner();
  if (ro) main.append(ro);

  if (plan.confirmed) {
    main.append(h('div', { class: 'banner ok' }, t('plan_confirmed', { by: plan.confirmed_by, at: (plan.confirmed_at || '').slice(11, 16) })));
  } else {
    main.append(h('div', { class: 'banner warn' },
      team.before_confirmation === 'previous_plan' ? t('plan_not_confirmed_prev') : t('plan_not_confirmed'), ' ',
      S.planSource.startsWith('previous:') ? t('plan_from_prev', { d: fmtDate(S.planSource.slice(9)) }) : S.planSource === 'empty' ? t('plan_from_empty') : ''));
  }

  // who works today
  const agentsPanel = h('section', { class: 'panel' }, h('h2', {}, t('agents_today')), h('p', { class: 'hint' }, t('agents_today_hint')));
  const grid = h('div', { class: 'agents' });
  for (const a of agents) {
    const st = plan.agents[a.id] || (plan.agents[a.id] = { state: 'absent', reason: '', exceptions: [] });
    const card = h('div', { class: 'agent s-' + st.state });
    const seg = h('div', { class: 'seg', role: 'group' }, ['rotation', 'excluded', 'absent'].map((s) =>
      h('button', { class: (st.state === s ? 'on ' : '') + s, disabled: !editable, onclick: () => {
        st.state = s;
        if (s === 'rotation') { st.reason = ''; st.exceptions = []; plan.intervals.forEach((iv) => { if (!iv.order.includes(a.id)) iv.order.push(a.id); }); }
        markDirty(); renderToday(main);
      } }, t('st_' + s))));
    card.append(h('div', { class: 'row' }, h('span', { class: 'name' }, fullName(a)), h('span', { class: 'spacer' }), h('span', { class: 'tag' }, a.category)), seg);
    if (st.state === 'excluded') {
      const reasons = t('reasons');
      const known = reasons.includes(st.reason);
      const other = h('input', { type: 'text', value: known ? '' : st.reason, placeholder: t('reason_other'), class: known || !st.reason ? 'hidden' : '',
        oninput: (e) => { st.reason = e.target.value; markDirty(); } });
      card.append(field(t('reason'), h('div', {}, selectIn(known ? st.reason : (st.reason ? '__other' : ''),
        [['', t('choose')], ...reasons.map((r) => [r, r]), ['__other', t('reason_other')]],
        (v) => { if (v === '__other') { st.reason = other.value; other.classList.remove('hidden'); other.focus(); } else { st.reason = v; other.classList.add('hidden'); } markDirty(); },
        { disabled: !editable }), other)));
      card.append(h('div', { class: 'small' }, h('div', { class: 'muted' }, t('still_gets')),
        S.info.exceptions.map((ex) => checkIn(t('exc_' + ex), st.exceptions.includes(ex), (on) => {
          st.exceptions = on ? [...st.exceptions, ex] : st.exceptions.filter((x) => x !== ex); markDirty();
        }))));
    }
    if (st.state === 'absent') {
      const b = (a.backups || []).filter((x) => ids[x]).map((x) => fullName(ids[x]));
      card.append(h('div', { class: 'small muted' }, b.length ? t('backups_line', { names: b.join(' → ') }) : t('no_backups')));
    }
    grid.append(card);
  }
  agentsPanel.append(grid);
  main.append(agentsPanel);

  // intervals
  const ivPanel = h('section', { class: 'panel' }, h('h2', {}, t('order_title')), h('p', { class: 'hint' }, t('order_hint')));
  const ivWrap = h('div', { class: 'intervals' });
  plan.intervals.forEach((iv, ivIndex) => {
    const key = `${iv.start}-${iv.end}`;
    const box = h('div', { class: 'interval' });
    box.append(h('div', { class: 'times' }, h('strong', {}, t('interval')),
      h('input', { type: 'time', value: iv.start, disabled: !editable, onchange: (e) => { iv.start = e.target.value; markDirty(); } }), '–',
      h('input', { type: 'time', value: iv.end, disabled: !editable, onchange: (e) => { iv.end = e.target.value; markDirty(); } }),
      h('span', { class: 'spacer' }),
      editable && plan.intervals.length > 1 ? h('button', { class: 'btn icon danger', title: t('remove_interval'), onclick: () => { plan.intervals.splice(ivIndex, 1); markDirty(); renderToday(main); } }, '✕') : null));
    const ol = h('ol', { class: 'order' });
    const inRotation = iv.order.filter((id) => plan.agents[id]?.state === 'rotation');
    const nextPos = isToday && S.rotation[key] !== undefined ? S.rotation[key] : null;
    const validOrder = iv.order.filter((id) => ids[id]);
    validOrder.forEach((id, i) => {
      const st = plan.agents[id]?.state || 'absent';
      const skipped = st !== 'rotation';
      const pos = skipped ? '–' : inRotation.indexOf(id) + 1;
      ol.append(h('li', { class: skipped ? 'skipped' : '' },
        h('span', { class: 'handle', title: t('drag'), 'aria-hidden': 'true' }, '⠿'),
        h('span', { class: 'pos' }, pos),
        h('span', { class: 'who' }, fullName(ids[id]), ' ', skipped ? h('span', { class: 'tag' }, t('st_' + st)) : null,
          nextPos !== null && iv.order.filter((x) => ids[x])[nextPos % Math.max(1, validOrder.length)] === id && plan.confirmed ? h('span', { class: 'next-marker' }, ' ← ' + t('rotation_next')) : null),
        editable ? h('button', { class: 'btn icon', title: t('move_up'), disabled: i === 0, onclick: () => { moveItem(iv.order, iv.order.indexOf(id), Math.max(0, iv.order.indexOf(id) - 1)); markDirty(); renderToday(main); } }, '↑') : null,
        editable ? h('button', { class: 'btn icon', title: t('move_down'), disabled: i === validOrder.length - 1, onclick: () => { const k = iv.order.indexOf(id); moveItem(iv.order, k, Math.min(iv.order.length - 1, k + 1)); markDirty(); renderToday(main); } }, '↓') : null,
        editable ? h('button', { class: 'btn icon', title: t('delete'), onclick: () => { iv.order = iv.order.filter((x) => x !== id); markDirty(); renderToday(main); } }, '✕') : null));
    });
    if (!validOrder.length) ol.append(h('li', { class: 'skipped' }, t('interval_empty')));
    box.append(ol);
    if (editable) sortable(ol, 'li', (f, to) => { const list = iv.order.filter((x) => ids[x]); moveItem(list, f, to); iv.order = list; markDirty(); renderToday(main); });
    const missing = agents.filter((a) => plan.agents[a.id]?.state === 'rotation' && !iv.order.includes(a.id));
    if (missing.length && editable) {
      box.append(h('div', { class: 'small muted', style: 'margin-top:8px' }, t('not_in_interval'), ' ',
        missing.map((a) => h('span', { class: 'chip add', role: 'button', tabindex: 0, onclick: () => { iv.order.push(a.id); markDirty(); renderToday(main); } }, '+ ' + fullName(a)))));
    }
    if (editable && ivIndex > 0) box.append(h('div', { style: 'margin-top:8px' }, h('button', { class: 'btn small', onclick: () => { iv.order = [...plan.intervals[ivIndex - 1].order]; markDirty(); renderToday(main); } }, t('copy_prev_interval'))));
    ivWrap.append(box);
  });
  ivPanel.append(ivWrap);
  if (editable) ivPanel.append(h('div', { style: 'margin-top:10px' }, h('button', { class: 'btn', onclick: () => {
    const last = plan.intervals[plan.intervals.length - 1];
    const start = last ? last.end : '08:00';
    const [hh, mm] = start.split(':').map(Number);
    const end = `${String(Math.min(23, hh + 4)).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
    plan.intervals.push({ start, end: end > start ? end : '23:59', order: last ? [...last.order] : agents.filter((a) => plan.agents[a.id]?.state === 'rotation').map((a) => a.id) });
    markDirty(); renderToday(main);
  } }, '+ ' + t('add_interval'))));
  main.append(ivPanel);

  // message
  const msg = h('section', { class: 'panel' });
  const pre = h('pre', { class: 'message' }, S.planReport?.text || '');
  const channel = team.report.channel;
  msg.append(h('div', { class: 'row' }, h('h2', {}, t('message_preview')), h('span', { class: 'spacer' }),
    h('span', { class: 'tag' }, t('ch_' + channel)),
    h('button', { class: 'btn small', onclick: () => copyText(pre.textContent) }, t('copy_message')),
    channel !== 'copy' && plan.confirmed && isToday && editable ? h('button', { class: 'btn small', onclick: sendMessage }, t('send_message')) : null), pre);
  main.append(msg);
  previewReport(pre);

  if ((plan.history || []).length) {
    main.append(h('section', { class: 'panel' }, h('h2', {}, t('history')),
      h('ul', { class: 'small' }, plan.history.slice().reverse().map((x) => h('li', {}, `${x.at.slice(11, 16)} · ${x.by} · ${x.what}${x.answers?.why ? ' · ' + x.answers.why : ''}`)))));
  }

  if (editable) {
    main.append(h('div', { class: 'sticky-actions' },
      h('span', { id: 'dirty', class: 'small muted' + (S.dirty ? '' : ' hidden') }, t('unsaved')),
      h('button', { class: 'btn', onclick: () => savePlan('save') }, t('save_draft')),
      plan.confirmed ? h('button', { class: 'btn primary', onclick: () => wizard('regenerate') }, t('regenerate'))
        : h('button', { class: 'btn primary', onclick: () => wizard('confirm') }, t('confirm_day'))));
  }
}

let previewTimer = null;
function previewReport(pre) {
  clearTimeout(previewTimer);
  if (!S.dirty) return;
  previewTimer = setTimeout(async () => {
    try { const r = await api('POST', tq('report/preview?date=' + S.day), { plan: S.plan }); pre.textContent = r.report.text; } catch (e) { /* ignore */ }
  }, 250);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast(t('copied')); }
  catch (e) {
    const ta = h('textarea', { style: 'position:fixed;left:-9999px' }, text); document.body.append(ta); ta.select();
    try { document.execCommand('copy'); toast(t('copied')); } catch (e2) { /* ignore */ } ta.remove();
  }
}

async function sendMessage() {
  try { const r = await api('POST', tq('report/send'), {}); toast(t('message_sent', { ch: t('ch_' + r.channel) })); } catch (e) { fail(e); }
}

async function savePlan(action, answers) {
  try {
    const res = await api('PUT', tq('plan?date=' + S.day), { plan: S.plan, rev: S.plan._rev || 0, action, answers: answers || {} });
    S.dirty = false;
    S.plan = res.plan; S.planReport = res.report;
    if (action === 'confirm') toast(t('done_confirm'));
    else if (action === 'regenerate') toast(t('done_regen'));
    else toast(t('saved'));
    if (res.reassigned) toast(t('done_reassigned', { n: res.reassigned }));
    if (res.reassign_error) toast(errText(res.reassign_error), true);
    if (res.sent) toast(t('message_sent', { ch: t('ch_' + res.sent) }));
    if (res.send_error) toast(errText(res.send_error), true);
    const r = await api('GET', tq('plan?date=' + S.day));
    S.plan = r.plan; S.planSource = r.source; S.planReport = r.report; S.rotation = r.rotation || {};
    renderToday(document.getElementById('main'));
    setTimeout(refreshPill, 1500);
  } catch (e) { fail(e); }
}

async function wizard(kind) {
  const answers = kind === 'confirm'
    ? { pending: 'distribute', rotation: 'restart', send: 'yes' }
    : { assigned: 'backup', rotation: 'continue', send: 'yes', why: t('a_why')[0] };
  const q = (label, key, opts) => field(label, selectIn(answers[key], opts, (v) => { answers[key] = v; }));
  const content = h('div', { class: 'grid' });
  if (kind === 'confirm') {
    content.append(q(t('q_pending'), 'pending', [['distribute', t('a_pending_distribute')], ['leave', t('a_pending_leave')]]));
    content.append(q(t('q_rotation'), 'rotation', [['restart', t('a_rotation_restart')], ['continue', t('a_rotation_continue')]]));
  } else {
    content.append(q(t('q_why'), 'why', t('a_why').map((x) => [x, x])));
    content.append(q(t('q_assigned'), 'assigned', [['keep', t('a_assigned_keep')], ['backup', t('a_assigned_backup')], ['rotation', t('a_assigned_rotation')], ['fallback', t('a_assigned_fallback')]]));
    content.append(q(t('q_rotation'), 'rotation', [['continue', t('a_rotation_continue')], ['restart', t('a_rotation_restart')]]));
  }
  if (S.data.team.report.channel === 'copy') content.append(h('div', { class: 'hint' }, t('wiz_copy_note')));
  else content.append(q(t('q_send'), 'send', [['yes', t('a_send_yes')], ['no', t('a_send_no')]]));
  const ok = await modal(t(kind === 'confirm' ? 'wiz_confirm_title' : 'wiz_regen_title', { d: fmtDate(S.day) }), content,
    [{ label: t('cancel'), value: false }, { label: t(kind === 'confirm' ? 'wiz_ok_confirm' : 'wiz_ok_regen'), value: true, primary: true }]);
  if (ok) await savePlan(kind, answers);
}

// ── Agents ──────────────────────────────────────────────────────────────
PAGES.agents = async (main) => renderAgents(main);

function renderAgents(main) {
  main.innerHTML = '';
  const editable = S.data.can_edit;
  const ids = byId(S.agents);
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('agents_title')), h('p', { class: 'muted' }, t('agents_hint')))));
  const ro = readOnlyBanner(); if (ro) main.append(ro);
  const list = h('div', {});
  S.agents.forEach((a, index) => {
    const open = S.openAgent === a.id;
    const item = h('div', { class: 'item' + (a.active === false ? ' off' : '') });
    item.append(h('div', { class: 'head', onclick: () => { S.openAgent = open ? '' : a.id; renderAgents(main); } },
      h('span', { class: 'title' }, fullName(a)), h('span', { class: 'tag' }, a.category || fullName(a)),
      a.folder ? h('span', { class: 'tag' }, '📁 ' + a.folder) : null,
      h('span', { class: 'sub' }, (a.backups || []).filter((b) => ids[b]).length ? t('backups_line', { names: a.backups.filter((b) => ids[b]).map((b) => fullName(ids[b])).join(' → ') }) : ''),
      h('span', { class: 'spacer' }), h('span', { class: 'muted' }, open ? '▴' : '▾')));
    if (open) {
      const set = (k) => (v) => { a[k] = v; markDirty(); };
      const body = h('div', { class: 'body grid' });
      body.append(h('div', { class: 'grid g3' },
        field(t('first_name'), textIn(a.first_name, set('first_name'), { disabled: !editable })),
        field(t('last_name'), textIn(a.last_name, set('last_name'), { disabled: !editable })),
        field(t('email'), textIn(a.email, set('email'), { disabled: !editable, type: 'email' }))));
      const folderInput = textIn(a.folder, set('folder'), { disabled: !editable });
      body.append(h('div', { class: 'grid g2' },
        field(t('category'), textIn(a.category, set('category'), { disabled: !editable, placeholder: t('category_default') })),
        field(t('folder'), h('div', { class: 'row', style: 'flex-wrap:nowrap' }, folderInput,
          editable ? h('button', { class: 'btn small', onclick: async () => { const f = await pickOutlookFolder(); if (f !== null) { folderInput.value = f; a.folder = f; markDirty(); } } }, t('pick_folder')) : null), t('folder_hint'))));
      // backups
      const chips = h('div', { class: 'row' });
      (a.backups || []).forEach((b, bi) => {
        if (!ids[b]) return;
        chips.append(h('span', { class: 'chip' }, `${bi + 1}. ${fullName(ids[b])}`,
          editable ? h('button', { title: t('delete'), onclick: () => { a.backups.splice(bi, 1); markDirty(); renderAgents(main); } }, '✕') : null));
      });
      const candidates = S.agents.filter((x) => x.id !== a.id && !(a.backups || []).includes(x.id) && x.active !== false);
      if (editable && candidates.length) {
        chips.append(selectIn('', [['', '+ ' + t('add_backup')], ...candidates.map((x) => [x.id, fullName(x)])],
          (v) => { if (v) { a.backups = [...(a.backups || []), v]; markDirty(); renderAgents(main); } }, { style: 'width:auto' }));
      }
      body.append(field(t('backups'), chips));
      body.append(field(t('aliases'), areaIn(a.aliases, (v) => { a.aliases = lines(v); markDirty(); }, { disabled: !editable, rows: 2 }), t('aliases_hint')));
      body.append(h('div', { class: 'row' }, checkIn(t('active'), a.active !== false, (v) => { a.active = v; markDirty(); }),
        h('span', { class: 'spacer' }),
        editable ? h('button', { class: 'btn small', disabled: index === 0, onclick: () => { moveItem(S.agents, index, index - 1); markDirty(); renderAgents(main); } }, '↑') : null,
        editable ? h('button', { class: 'btn small', disabled: index === S.agents.length - 1, onclick: () => { moveItem(S.agents, index, index + 1); markDirty(); renderAgents(main); } }, '↓') : null,
        editable ? h('button', { class: 'btn small danger', onclick: async () => {
          if (await ask(t('delete_agent_q', { name: fullName(a) }))) {
            S.agents.splice(index, 1); S.agents.forEach((x) => { x.backups = (x.backups || []).filter((b) => b !== a.id); }); markDirty(); renderAgents(main);
          } } }, t('delete')) : null));
      item.append(body);
    }
    list.append(item);
  });
  main.append(list);
  if (editable) {
    main.append(h('div', { class: 'sticky-actions' },
      h('span', { id: 'dirty', class: 'small muted' + (S.dirty ? '' : ' hidden') }, t('unsaved')),
      h('button', { class: 'btn', onclick: () => {
        const id = Math.random().toString(16).slice(2, 10);
        S.agents.push({ id, first_name: '', last_name: t('new_agent'), email: '', aliases: [], category: '', folder: '', backups: [], active: true });
        S.openAgent = id; markDirty(); renderAgents(main);
      } }, '+ ' + t('add_agent')),
      h('button', { class: 'btn primary', onclick: async () => {
        try {
          const r = await api('PUT', tq('agents'), { agents: S.agents, rev: S.data.agents_rev });
          S.data.agents = r.agents; S.data.agents_rev = r.rev; S.agents = clone(r.agents); S.dirty = false; toast(t('saved')); renderAgents(main);
        } catch (e) { fail(e); }
      } }, t('save'))));
  }
}

async function pickOutlookFolder() {
  const listBox = h('div', { class: 'folder-list' }, h('p', { class: 'muted', style: 'padding:8px' }, t('folders_loading')));
  const filter = h('input', { type: 'text', placeholder: '…' });
  let chosen = null;
  const p = modal(t('pick_folder'), h('div', { class: 'grid' }, filter, listBox), [{ label: t('cancel'), value: null }]);
  try {
    const r = await api('GET', tq('folders'));
    const draw = () => {
      listBox.innerHTML = '';
      const f = filter.value.toLowerCase();
      r.folders.filter((x) => !f || x.toLowerCase().includes(f)).forEach((x) => listBox.append(h('button', { onclick: () => { chosen = x; document.querySelector('.modal-bg')?.click(); } }, x)));
    };
    filter.addEventListener('input', draw); draw();
  } catch (e) { listBox.innerHTML = ''; listBox.append(h('p', { class: 'banner bad' }, errText(e.code || e.message))); }
  await p;
  return chosen;
}

// ── Rules ───────────────────────────────────────────────────────────────
PAGES.rules = async (main) => renderRules(main);

function ruleSummary(r, ids) {
  const parts = [];
  if (r.all.length) parts.push('∀ ' + r.all.join(' + '));
  if (r.any.length) parts.push('∃ ' + r.any.join(' / '));
  if (r.none.length) parts.push('¬ ' + r.none.join(' / '));
  if (r.from.length) parts.push('✉ ' + r.from.join(' / '));
  let target = r.assign === 'rotation' ? t('assign_rotation') : r.assign.startsWith('agent:') ? fullName(ids[r.assign.slice(6)]) : '';
  const extra = [...r.categories, r.folder ? '📁 ' + r.folder : ''].filter(Boolean).join(', ');
  return `${parts.join(' · ') || '—'}  →  ${[target, extra].filter(Boolean).join(' + ') || '—'}`;
}

function renderRules(main) {
  main.innerHTML = '';
  const editable = S.data.can_edit;
  const ids = byId(S.agents);
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('rules_title')), h('p', { class: 'muted' }, t('rules_hint')))));
  const ro = readOnlyBanner(); if (ro) main.append(ro);
  const cols = h('div', { class: 'cols' });
  const left = h('div', {});
  const list = h('div', {});
  S.rules.forEach((r, index) => {
    const open = S.openRule === r.id;
    const info = !r.stop && !r.assign;
    const item = h('div', { class: 'item' + (r.enabled ? '' : ' off') });
    item.append(h('div', { class: 'head', onclick: (e) => { if (e.target.closest('button')) return; S.openRule = open ? '' : r.id; renderRules(main); } },
      editable ? h('span', { class: 'handle', title: t('drag') }, '⠿') : null,
      h('span', { class: 'pos' }, index + 1),
      h('div', { style: 'min-width:0;flex:1' }, h('div', { class: 'row' }, h('span', { class: 'title' }, r.name || t('new_rule')),
        info ? h('span', { class: 'tag' }, t('rule_info')) : null, r.enabled ? null : h('span', { class: 'tag' }, t('rule_off'))),
      h('div', { class: 'sub' }, ruleSummary(r, ids))),
      h('span', { class: 'muted' }, open ? '▴' : '▾')));
    if (open) item.append(ruleEditor(r, index, main, editable));
    list.append(item);
  });
  left.append(list);
  if (editable) sortable(list, '.item', (f, to) => { moveItem(S.rules, f, to); markDirty(); renderRules(main); });
  cols.append(left, tester());
  main.append(cols);
  if (editable) {
    main.append(h('div', { class: 'sticky-actions' },
      h('span', { id: 'dirty', class: 'small muted' + (S.dirty ? '' : ' hidden') }, t('unsaved')),
      h('button', { class: 'btn', onclick: () => {
        const id = Math.random().toString(16).slice(2, 10);
        S.rules.push({ id, name: t('new_rule'), enabled: true, all: [], any: [], none: [], from: [], where: ['subject', 'body', 'to_cc', 'from', 'attachments'], high_only: false, assign: '', categories: [], folder: '', stop: true, note: '' });
        S.openRule = id; markDirty(); renderRules(main);
      } }, '+ ' + t('add_rule')),
      h('button', { class: 'btn primary', onclick: async () => {
        try {
          const r = await api('PUT', tq('rules'), { rules: S.rules, rev: S.data.rules_rev });
          S.data.rules = r.rules; S.data.rules_rev = r.rev; S.rules = clone(r.rules); S.dirty = false; toast(t('saved')); renderRules(main);
        } catch (e) { fail(e); }
      } }, t('save'))));
  }
}

function ruleEditor(r, index, main, editable) {
  const dis = { disabled: !editable };
  const set = (k) => (v) => { r[k] = v; markDirty(); };
  const setList = (k) => (v) => { r[k] = lines(v); markDirty(); };
  const body = h('div', { class: 'body grid' });
  body.append(h('div', { class: 'grid g2' },
    field(t('rule_name'), textIn(r.name, set('name'), dis)),
    h('div', { style: 'align-self:end' }, checkIn(t('enabled'), r.enabled, set('enabled')))));
  body.append(h('div', { class: 'grid g2' },
    field(t('cond_all'), areaIn(r.all, setList('all'), { ...dis, rows: 3 })),
    field(t('cond_any'), areaIn(r.any, setList('any'), { ...dis, rows: 3 })),
    field(t('cond_none'), areaIn(r.none, setList('none'), { ...dis, rows: 2 })),
    field(t('cond_from'), areaIn(r.from, setList('from'), { ...dis, rows: 2 }))));
  body.append(h('div', { class: 'hint' }, t('terms_hint')));
  if (!r.all.length && !r.any.length && !r.from.length) body.append(h('div', { class: 'banner warn small' }, t('rule_no_conditions')));
  const whereBox = h('div', { class: 'row' }, ['subject', 'body', 'to_cc', 'from', 'attachments'].map((w) =>
    checkIn(t('w_' + w), r.where.includes(w), (on) => { r.where = on ? [...r.where, w] : r.where.filter((x) => x !== w); markDirty(); })));
  body.append(field(t('where'), whereBox));
  body.append(checkIn(t('high_only'), r.high_only, set('high_only')));
  const assignOpts = [['', t('assign_none')], ['rotation', t('assign_rotation')], ...S.agents.filter((a) => a.active !== false).map((a) => ['agent:' + a.id, fullName(a)])];
  body.append(h('div', { class: 'grid g2' },
    field(t('who_gets'), selectIn(r.assign, assignOpts, (v) => { r.assign = v; if (v) r.stop = true; markDirty(); renderRules(main); }, dis)),
    field(t('rule_categories'), areaIn(r.categories, setList('categories'), { ...dis, rows: 2 }))));
  const folderIn = textIn(r.folder, set('folder'), dis);
  body.append(field(t('rule_folder'), h('div', { class: 'row', style: 'flex-wrap:nowrap' }, folderIn,
    editable ? h('button', { class: 'btn small', onclick: async () => { const f = await pickOutlookFolder(); if (f !== null) { folderIn.value = f; r.folder = f; markDirty(); } } }, t('pick_folder')) : null)));
  body.append(r.assign ? h('div', { class: 'hint' }, t('stop_forced')) : checkIn(t('stop'), r.stop, (v) => { r.stop = v; markDirty(); renderRules(main); }));
  if (editable) body.append(h('div', { class: 'row end' },
    h('button', { class: 'btn small', disabled: index === 0, onclick: () => { moveItem(S.rules, index, index - 1); markDirty(); renderRules(main); } }, '↑ ' + t('move_up')),
    h('button', { class: 'btn small', disabled: index === S.rules.length - 1, onclick: () => { moveItem(S.rules, index, index + 1); markDirty(); renderRules(main); } }, '↓ ' + t('move_down')),
    h('button', { class: 'btn small danger', onclick: async () => { if (await ask(t('delete_rule_q', { name: r.name }))) { S.rules.splice(index, 1); markDirty(); renderRules(main); } } }, t('delete'))));
  return body;
}

const TEST = { subject: '', body: '', sender_email: '', to: '', cc: '', attachments: '', importance: 'normal', thread_category: '', time: '' };
function tester() {
  const panel = h('section', { class: 'panel' }, h('h2', {}, t('tester_title')), h('p', { class: 'hint' }, t('tester_hint')));
  const set = (k) => (v) => { TEST[k] = v; };
  const out = h('div', {});
  panel.append(h('div', { class: 'grid' },
    field(t('t_subject'), textIn(TEST.subject, set('subject'))),
    field(t('t_body'), areaIn(TEST.body, set('body'), { rows: 4 })),
    h('div', { class: 'grid g2' },
      field(t('t_from'), textIn(TEST.sender_email, set('sender_email'))),
      field(t('t_attachments'), textIn(TEST.attachments, set('attachments')))),
    h('div', { class: 'grid g2' },
      field(t('t_to'), textIn(TEST.to, set('to'))),
      field(t('t_cc'), textIn(TEST.cc, set('cc')))),
    h('div', { class: 'grid g3' },
      field(t('t_importance'), selectIn(TEST.importance, [['normal', t('t_normal')], ['high', t('t_high')]], set('importance'))),
      field(t('t_thread'), selectIn(TEST.thread_category, [['', '—'], ...S.agents.map((a) => [a.category || fullName(a), a.category || fullName(a)])], set('thread_category'))),
      field(t('t_time'), h('input', { type: 'time', value: TEST.time, onchange: (e) => { TEST.time = e.target.value; } }))),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', onclick: async () => {
      try {
        const r = await api('POST', tq('test'), { mail: { ...TEST }, rules: S.rules, agents: S.agents, time: TEST.time });
        const d = r.decision; const ids = byId(S.agents);
        out.innerHTML = '';
        const who = d.agent_id ? fullName(ids[d.agent_id]) : (d.step === 'wait' ? t('step_wait') : '—');
        out.append(h('div', { class: 'result' }, h('div', { class: 'muted small' }, t('t_result')),
          h('div', { class: 'big' }, who, d.intended_agent_id ? h('span', { class: 'muted small' }, ' (' + t('via_backup', { name: fullName(ids[d.intended_agent_id]) }) + ')') : null),
          h('div', { class: 'row', style: 'margin:6px 0' }, h('span', { class: 'tag ok' }, stepLabel(d.step)), d.categories.map((c) => h('span', { class: 'chip' }, c)), d.folder ? h('span', { class: 'tag' }, '📁 ' + d.folder) : null),
          traceList(d.trace)));
      } catch (e) { fail(e); }
    } }, t('t_run')), h('span', { class: 'hint' }, t('t_unsaved_note'))),
    out));
  return panel;
}

// ── Journal ─────────────────────────────────────────────────────────────
const JF = { day: '', agent: '', step: '' };
PAGES.journal = async (main) => {
  if (!JF.day) JF.day = todayIso();
  const r = await api('GET', tq('journal?date=' + JF.day));
  const ids = byId(S.data.agents);
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('journal_title')), h('p', { class: 'muted' }, t('journal_hint'))),
    h('div', { class: 'row' },
      h('input', { type: 'date', value: JF.day, onchange: (e) => { JF.day = e.target.value || todayIso(); route(true); } }),
      selectIn(JF.agent, [['', t('filter_agent') + ': ' + t('all')], ...S.data.agents.map((a) => [a.id, fullName(a)])], (v) => { JF.agent = v; route(true); }, { style: 'width:auto' }),
      selectIn(JF.step, [['', t('filter_step') + ': ' + t('all')], ...['thread', 'name', 'rule', 'rule_only', 'rotation', 'fallback', 'manual', 'reassigned'].map((s) => [s, stepLabel(s)])], (v) => { JF.step = v; route(true); }, { style: 'width:auto' }),
      h('button', { class: 'btn small', onclick: () => route(true) }, '↻'))));
  let entries = r.entries.slice().reverse();
  if (JF.agent) entries = entries.filter((e) => e.agent === JF.agent);
  if (JF.step) entries = entries.filter((e) => (e.step || e.status) === JF.step || e.status === JF.step);
  const panel = h('section', { class: 'panel' });
  if (!entries.length) { panel.append(h('p', { class: 'muted' }, t('journal_empty'))); main.append(panel); return; }
  panel.append(h('p', { class: 'small muted' }, t('count_total', { n: entries.length })));
  const table = h('table', { class: 'list' }, h('thead', {}, h('tr', {}, ['col_time', 'col_subject', 'col_from', 'col_to', 'col_how', 'col_cats'].map((c) => h('th', {}, t(c))))));
  const tbody = h('tbody');
  for (const e of entries) {
    const who = e.agent ? fullName(ids[e.agent]) : '—';
    const how = e.status === 'error' ? h('span', { class: 'tag bad' }, t('status_error')) : h('span', { class: 'tag' + (e.step === 'fallback' ? ' warn' : ' ok') }, stepLabel(e.step || e.status));
    const tr = h('tr', { class: 'click' },
      h('td', {}, (e.at || '').slice(11, 16)), h('td', {}, e.subject), h('td', { class: 'small muted' }, e.from),
      h('td', {}, who, e.intended ? h('div', { class: 'small muted' }, t('via_backup', { name: fullName(ids[e.intended]) })) : null,
        e.previous ? h('div', { class: 'small muted' }, '← ' + fullName(ids[e.previous])) : null),
      h('td', {}, how), h('td', { class: 'small' }, (e.categories || []).join(', '), e.folder ? ' 📁 ' + e.folder : ''));
    const detail = h('tr', { class: 'hidden' }, h('td', { colspan: 6 }, e.error ? h('div', { class: 'banner bad small' }, errText(e.error)) : null, traceList(e.trace), h('div', { class: 'small muted' }, `PC: ${e.pc || ''} · ${e.received || ''}`)));
    tr.addEventListener('click', () => detail.classList.toggle('hidden'));
    tbody.append(tr, detail);
  }
  table.append(tbody);
  panel.append(table);
  main.append(panel);
};

// ── Team ────────────────────────────────────────────────────────────────
PAGES.team = async (main) => renderTeam(main);

function renderTeam(main) {
  main.innerHTML = '';
  const tm = S.team;
  const editable = S.data.can_edit;
  const dis = { disabled: !editable };
  const set = (k, obj) => (v) => { (obj || tm)[k] = v; markDirty(); };
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('team_title')), h('p', { class: 'muted' }, t('team_hint')))));
  const ro = readOnlyBanner(); if (ro) main.append(ro);

  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('sec_mailbox')),
    h('div', { class: 'grid g2' },
      field(t('team_name'), textIn(tm.name, set('name'), dis)),
      field(t('team_aliases'), areaIn(tm.team_aliases, (v) => { tm.team_aliases = lines(v); markDirty(); }, { ...dis, rows: 2 }), t('team_aliases_hint')),
      field(t('mailbox'), textIn(tm.mailbox, set('mailbox'), dis), t('mailbox_hint')),
      field(t('source_folder'), textIn(tm.source_folder, set('source_folder'), dis), t('source_folder_hint'))),
    field(t('mode'), selectIn(tm.mode, [['category', t('mode_category')], ['folder', t('mode_folder')], ['both', t('mode_both')]], set('mode'), dis)),
    h('div', { class: 'grid g2' },
      field(t('fallback_category'), textIn(tm.fallback_category, set('fallback_category'), dis)),
      field(t('fallback_folder'), textIn(tm.fallback_folder, set('fallback_folder'), dis))),
    h('div', { class: 'row' }, h('button', { class: 'btn', onclick: async () => {
      try { const r = await api('POST', tq('categories'), {}); toast(r.added.length ? t('categories_created', { list: r.added.join(', ') }) : t('categories_none')); } catch (e) { fail(e); }
    } }, t('create_categories')))));

  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('sec_logic')),
    checkIn(t('use_thread'), tm.use_thread, set('use_thread')),
    checkIn(t('use_names'), tm.use_names, set('use_names')),
    checkIn(t('name_requires_team'), tm.name_requires_team, set('name_requires_team')),
    checkIn(t('match_to_cc'), tm.match_to_cc_address, set('match_to_cc_address')),
    checkIn(t('backups_of_backups'), tm.follow_backups_of_backups, set('follow_backups_of_backups')),
    h('div', { class: 'grid g3' },
      field(t('no_backup'), selectIn(tm.no_backup, [['rotation', t('no_backup_rotation')], ['fallback', t('no_backup_fallback')]], set('no_backup'), dis)),
      field(t('before_conf'), selectIn(tm.before_confirmation, [['wait', t('before_wait')], ['previous_plan', t('before_prev')]], set('before_confirmation'), dis)),
      field(t('outside'), selectIn(tm.outside_intervals, [['nearest', t('outside_nearest')], ['fallback', t('outside_fallback')]], set('outside_intervals'), dis))),
    h('div', { class: 'grid g2' },
      field(t('lookback'), selectIn(tm.lookback_days, [[0, t('lookback_0')], [1, '1 ' + t('day')], [2, '2 ' + t('days')], [3, '3 ' + t('days')], [7, '7 ' + t('days')]], (v) => { tm.lookback_days = Number(v); markDirty(); }, dis)),
      field(t('sweep'), selectIn(tm.sweep_minutes, [[2, '2 ' + t('minutes')], [5, '5 ' + t('minutes')], [10, '10 ' + t('minutes')], [15, '15 ' + t('minutes')], [30, '30 ' + t('minutes')]], (v) => { tm.sweep_minutes = Number(v); markDirty(); }, dis)))));

  const rep = tm.report;
  const chan = h('div', { class: 'grid' });
  const drawChan = () => {
    chan.innerHTML = '';
    if (rep.channel === 'webhook') chan.append(field(t('webhook_url'), textIn(rep.webhook_url, set('webhook_url', rep), { ...dis, placeholder: 'https://…' }), t('howto_webhook')));
    if (rep.channel === 'email') chan.append(field(t('email_to'), textIn(rep.email_to, set('email_to', rep), dis), t('howto_email')));
  };
  drawChan();
  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('sec_report')),
    h('div', { class: 'grid g2' },
      field(t('report_lang'), selectIn(tm.language, [['ro', 'Română'], ['en', 'English']], set('language'), dis)),
      field(t('channel'), selectIn(rep.channel, [['copy', t('channel_copy')], ['webhook', t('channel_webhook')], ['email', t('channel_email')]], (v) => { rep.channel = v; markDirty(); drawChan(); }, dis))),
    chan,
    checkIn(t('include_rules'), rep.include_rules, set('include_rules', rep)),
    checkIn(t('include_backups'), rep.include_backups, set('include_backups', rep))));

  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('sec_engine')),
    h('div', { class: 'grid g2' },
      field(t('preferred_pc'), textIn(tm.engine.preferred_pc, set('preferred_pc', tm.engine), dis), t('preferred_pc_hint', { pc: S.info.pc })),
      field(t('stale'), selectIn(tm.engine.stale_minutes, [[2, '2 ' + t('minutes')], [5, '5 ' + t('minutes')], [10, '10 ' + t('minutes')], [30, '30 ' + t('minutes')]], (v) => { tm.engine.stale_minutes = Number(v); markDirty(); }, dis))),
    checkIn(t('start_outlook'), tm.engine.start_outlook, set('start_outlook', tm.engine))));

  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('sec_people')),
    field(t('editors'), areaIn(tm.editors, (v) => { tm.editors = lines(v); markDirty(); }, { ...dis, rows: 3 }), t('editors_hint', { user: S.info.user }))));

  if (editable) main.append(h('div', { class: 'sticky-actions' },
    h('span', { id: 'dirty', class: 'small muted' + (S.dirty ? '' : ' hidden') }, t('unsaved')),
    h('button', { class: 'btn primary', onclick: async () => {
      try {
        const r = await api('PUT', tq('team'), { team: tm, rev: S.data.team._rev });
        S.data.team = r.team; S.team = clone(r.team); S.dirty = false; toast(t('saved')); route(true);
      } catch (e) { fail(e); }
    } }, t('save'))));
}

// ── Setup ───────────────────────────────────────────────────────────────
PAGES.setup = async (main) => {
  const info = S.info;
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('setup_title')), h('p', { class: 'muted' }, t('setup_hint')))));
  const list = h('section', { class: 'panel' }, h('h2', {}, t('teams_here')));
  if (!info.teams.length) list.append(h('p', { class: 'muted' }, t('no_teams')));
  for (const tm of info.teams) {
    const [cls, label] = engineStatus(tm.status);
    list.append(h('div', { class: 'item' }, h('div', { class: 'head', style: 'cursor:default' },
      h('div', { style: 'flex:1;min-width:0' }, h('div', { class: 'title' }, tm.name), h('div', { class: 'sub' }, tm.folder)),
      tm.reachable ? h('span', { class: 'pill ' + cls }, label) : h('span', { class: 'tag bad' }, t('unreachable')),
      checkIn(t('engine_here'), tm.engine, async (on) => { try { await api('POST', 'engine?t=' + tm.id, { action: on ? 'enable' : 'disable' }); route(true); } catch (e) { fail(e); } }),
      h('button', { class: 'btn small danger', onclick: async () => { if (await ask(t('remove_team_q'))) { try { await api('POST', 'teams/remove?t=' + tm.id, {}); route(true); } catch (e) { fail(e); } } } }, t('remove')))));
  }
  main.append(list);

  const form = { folder: '', name: '', mailbox: '' };
  const folderIn = textIn('', (v) => { form.folder = v; });
  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('add_team')),
    field(t('team_folder'), h('div', { class: 'row', style: 'flex-wrap:nowrap' }, folderIn,
      h('button', { class: 'btn', onclick: async () => { try { const r = await api('POST', 'pick-folder', { title: t('team_folder') }); if (r.folder) { folderIn.value = r.folder; form.folder = r.folder; } } catch (e) { fail(e); } } }, t('browse'))), t('team_folder_hint')),
    h('div', { class: 'grid g2' },
      field(t('new_team_name'), textIn('', (v) => { form.name = v; })),
      field(t('mailbox'), textIn('', (v) => { form.mailbox = v; }), t('mailbox_hint'))),
    h('div', { class: 'row end' }, h('button', { class: 'btn primary', onclick: async () => {
      try { const r = await api('POST', 'teams/add', { ...form, language: LANG }); S.teamId = r.id; try { localStorage.setItem('amc.team', r.id); } catch (e) { /* ignore */ } toast(t('saved')); location.hash = '#/team'; route(true); } catch (e) { fail(e); }
    } }, t('add')))));

  const st = info.settings;
  const own = info.devpilot_owns;
  main.append(h('section', { class: 'panel grid' }, h('h2', {}, t('app_settings')),
    info.devpilot ? h('div', { class: 'banner ok small' }, t('devpilot_on')) : null,
    checkIn(t('open_browser'), st.open_browser_on_start, (v) => api('POST', 'settings', { open_browser_on_start: v }).catch(fail)),
    own.keepawake ? null : checkIn(t('keep_awake'), st.keep_awake, (v) => api('POST', 'settings', { keep_awake: v }).catch(fail)),
    own.autostart ? null : checkIn(t('autostart'), info.autostart, (v) => api('POST', 'settings', { autostart: v }).catch(fail)),
    h('p', { class: 'small muted' }, t('version', { v: info.version, user: info.user, pc: info.pc }))));
};

// ── Demo ────────────────────────────────────────────────────────────────
const DM = { subject: '', body: '', sender_email: 'client@example.test', to: '', cc: '', importance: 'normal', reply_to: '', attachments: '' };
PAGES.demo = async (main) => {
  const r = await api('GET', tq('demo/mails'));
  main.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, t('demo_title')), h('p', { class: 'muted' }, t('demo_hint'))),
    h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: async () => { try { await api('POST', tq('demo/seed'), {}); setTimeout(() => route(true), 1500); } catch (e) { fail(e); } } }, t('demo_seed')),
      h('button', { class: 'btn danger', onclick: async () => { try { await api('POST', tq('demo/clear'), {}); route(true); } catch (e) { fail(e); } } }, t('demo_clear')))));
  const set = (k) => (v) => { DM[k] = v; };
  const cols = h('div', { class: 'cols' });
  const box = h('section', { class: 'panel' }, h('h2', {}, t('demo_box')));
  const table = h('table', { class: 'list' }, h('thead', {}, h('tr', {}, h('th', {}, t('col_time')), h('th', {}, t('col_subject')), h('th', {}, t('col_cats')))));
  const tb = h('tbody');
  r.mails.slice().reverse().forEach((m) => tb.append(h('tr', {}, h('td', {}, m.received.slice(11, 16)), h('td', {}, m.subject, h('div', { class: 'small muted' }, m.sender_email)),
    h('td', {}, m.categories.map((c) => h('span', { class: 'chip' }, c)), ' 📁 ', m.folder || t('demo_folder_inbox')))));
  table.append(tb); box.append(table);
  const form = h('section', { class: 'panel grid' }, h('h2', {}, t('demo_send')),
    field(t('demo_reply_to'), selectIn(DM.reply_to, [['', t('demo_new_thread')], ...r.mails.slice(-30).reverse().map((m) => [m.id, m.subject])], set('reply_to'))),
    field(t('t_subject'), textIn(DM.subject, set('subject'))),
    field(t('t_body'), areaIn(DM.body, set('body'), { rows: 4 })),
    h('div', { class: 'grid g2' }, field(t('t_from'), textIn(DM.sender_email, set('sender_email'))), field(t('t_cc'), textIn(DM.cc, set('cc')))),
    h('div', { class: 'grid g2' }, field(t('t_attachments'), textIn(DM.attachments, set('attachments'))),
      field(t('t_importance'), selectIn(DM.importance, [['normal', t('t_normal')], ['high', t('t_high')]], set('importance')))),
    h('div', { class: 'row end' }, h('button', { class: 'btn primary', onclick: async () => {
      try { await api('POST', tq('demo/mail'), { mail: { ...DM, sender_name: DM.sender_email } }); DM.subject = ''; DM.body = ''; DM.reply_to = ''; setTimeout(() => route(true), 1500); } catch (e) { fail(e); }
    } }, t('demo_send'))));
  cols.append(box, form);
  main.append(cols);
};

// ── Guide ───────────────────────────────────────────────────────────────
const GUIDE = {
  ro: `<h1>Ghid rapid</h1>
<h2>Ce face AutoMailCAT</h2>
<p>Urmărește căsuța partajată a echipei în Outlook-ul deschis și, pentru fiecare mail nou, alege agentul și pune categoria lui (sau mută mailul în folderul lui). Ordinea de verificare:</p>
<ol><li><b>Același fir de discuție</b> – reply-ul rămâne la agentul care a preluat firul.</li>
<li><b>Agent numit</b> – adresa lui în To/CC sau numele + prenumele + numele echipei în mail.</li>
<li><b>Reguli cu cuvinte-cheie</b> – de sus în jos, prima regulă îndeplinită se aplică.</li>
<li><b>Rotație</b> – următorul agent din ordinea intervalului curent.</li>
<li><b>De verificat</b> – dacă nu se poate altfel.</li></ol>
<p>Dacă agentul ales lipsește, mailul merge la backup-ul lui, apoi la backup-ul backup-ului.</p>
<h2>În fiecare dimineață</h2>
<ol><li>Deschide <b>Ziua de azi</b>. Propunerea e copiată din ziua anterioară.</li>
<li>Marchează pentru fiecare agent: <b>În rotație</b>, <b>Exclus</b> (cu motiv și ce primește totuși) sau <b>Absent</b>.</li>
<li>Trage numele în ordinea dorită, pentru fiecare interval orar.</li>
<li>Apasă <b>Confirmă ziua</b>, răspunde la cele câteva întrebări și mesajul zilnic pleacă în Teams (sau îl copiezi).</li></ol>
<p>Dacă se schimbă ceva în timpul zilei, modifică și apasă <b>Regenerează</b>: alegi ce se întâmplă cu mailurile deja alocate celor care nu mai sunt disponibili.</p>
<h2>Bine de știut</h2>
<ul><li>Motorul rulează pe un singur PC al echipei (pe cel cu Outlook deschis). Dacă acel PC se închide, preia altul în câteva minute.</li>
<li>Mailurile sosite cât timp niciun PC nu rulează sunt procesate la următoarea pornire.</li>
<li>Dacă cineva schimbă manual categoria unui mail, AutoMailCAT nu o mai atinge, iar reply-urile urmează categoria nouă.</li>
<li>Pagina <b>Jurnal</b> arată pentru fiecare mail de ce a ajuns la cine. Pagina <b>Reguli</b> are un tester în care încerci un mail fără să schimbi nimic.</li>
<li>Nu folosiți virgulă sau punct și virgulă în numele categoriilor.</li></ul>`,
  en: `<h1>Quick guide</h1>
<h2>What AutoMailCAT does</h2>
<p>It watches the team's shared mailbox in the open Outlook and, for every new mail, chooses the agent and sets his category (or moves the mail to his folder). Order of evaluation:</p>
<ol><li><b>Same conversation</b> – a reply stays with the agent who owns the conversation.</li>
<li><b>Agent named</b> – his address in To/CC, or first name + last name + team name in the mail.</li>
<li><b>Keyword rules</b> – top to bottom, the first matching rule applies.</li>
<li><b>Rotation</b> – the next agent in the order of the current interval.</li>
<li><b>To check</b> – when nothing else is possible.</li></ol>
<p>If the chosen agent is absent, the mail goes to his backup, then to the backup's backup.</p>
<h2>Every morning</h2>
<ol><li>Open <b>Today</b>. The proposal is copied from the previous day.</li>
<li>For each agent choose <b>In rotation</b>, <b>Out of rotation</b> (with a reason and what he still gets) or <b>Absent</b>.</li>
<li>Drag the names into the order you want, for each time interval.</li>
<li>Press <b>Confirm the day</b>, answer the few questions and the daily message goes to Teams (or you copy it).</li></ol>
<p>If something changes during the day, edit and press <b>Regenerate</b>: you choose what happens to mails already assigned to people who are no longer available.</p>
<h2>Good to know</h2>
<ul><li>The engine runs on one PC of the team (the one with Outlook open). If that PC is switched off, another takes over within minutes.</li>
<li>Mails that arrive while no PC runs the engine are processed at the next start.</li>
<li>If someone changes a mail's category by hand, AutoMailCAT leaves it alone and replies follow the new category.</li>
<li>The <b>Journal</b> shows why each mail went to whom. The <b>Rules</b> page has a tester to try a mail without changing anything.</li>
<li>Do not use commas or semicolons in category names.</li></ul>`,
};
PAGES.guide = async (main) => { main.append(h('section', { class: 'panel guide', html: GUIDE[LANG] || GUIDE.ro })); };

// ── start ───────────────────────────────────────────────────────────────
window.addEventListener('hashchange', () => route(false));
window.addEventListener('beforeunload', (e) => { if (S.dirty) { e.preventDefault(); e.returnValue = ''; } });
(async () => {
  try { const info = await api('GET', 'status'); setLang(info.settings.language || 'ro'); } catch (e) { setLang('ro'); }
  await route(true);
  setInterval(() => { if (!document.hidden) refreshPill(); }, 10000);
})();
