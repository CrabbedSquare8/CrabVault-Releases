import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const start = source.indexOf('function showConflictResults(');
const end = source.indexOf('document.getElementById("btn-scan-mods").onclick', start);
assert.ok(start >= 0 && end > start, 'real conflict UI block must be available');
const localStart = source.indexOf('function renderLocalChange(');
const localEnd = source.indexOf('function thumbnailRequestKey(', localStart);
assert.ok(localStart >= 0 && localEnd > localStart, 'real local rendering entry point must be available');
const conflictCode = source.slice(start, end) + '\n' + source.slice(localStart, localEnd);
const maintenanceSource = fs.readFileSync(new URL('../frontend/maintenance.js', import.meta.url), 'utf8');
const resumeStart = maintenanceSource.indexOf('async function resumeLastOperation(');
const resumeEnd = maintenanceSource.indexOf('function clearPersonalImportChoice(', resumeStart);
assert.ok(resumeStart >= 0 && resumeEnd > resumeStart, 'real resumed operation entry point must be available');
const resumeCode = maintenanceSource.slice(resumeStart, resumeEnd);
const plain = value => JSON.parse(JSON.stringify(value));
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
const settle = async () => { for (let count = 0; count < 12; count++) await Promise.resolve(); };

function component(id, {enabled = true, description = '', name = id} = {}) {
  return {id, name, enabled, description, type: 'Mesh', types: ['Mesh'], files: [{name: `${id}.pak`}]};
}
function mod(id, {enabled = true, priority = 1, components, name} = {}) {
  return {id, name: name || ({cosy: 'z_COSY_BlackWidowAquaticAssassin_A_v1-0_NO_CUPS_9999999_P',
    diane: 'Diane_Foxington_Black_Widow_9999999_P'}[id] || id), enabled, priority,
    character: 'Black Widow', skin: 'Aquatic Assassin', components: components || [component(`${id}-main`)]};
}
function owner(record, index = 0) {
  const part = record.components[index];
  return {mod_id: record.id, component_id: part.id, mod: record.name, component: part.name,
    character: record.character, skin: record.skin, priority: record.priority,
    is_primary: part.description.toLowerCase() === 'principal' || (!part.description && index === 0),
    types: ['Mesh'], files: part.files.map(file => file.name)};
}
function conflict(path, owners, extra = {}) {
  return {asset_path: `Marvel/Content/Meshes/${path}.uasset`, asset_type: 'Mesh', kind: 'automatic',
    owners, tie: true, winner: null, resolution: 'tie', ...extra};
}
function report(conflicts = []) {
  return {ok: true, conflicts, tied_conflicts: conflicts.filter(item => item.tie).length,
    resolved_conflicts: conflicts.filter(item => !item.tie).length, checked_components: 2,
    ignored_physics_components: 0, unreadable: []};
}

function setup(records = [mod('cosy'), mod('diane')]) {
  const elements = new Map();
  class Element {
    constructor(tag = 'div') { this.tag = tag; this.dataset = {}; this.innerHTML = ''; this.textContent = ''; this.disabled = false; this.parts = new Map(); }
    querySelector(selector) {
      if (!this.parts.has(selector)) this.parts.set(selector, new Element(selector));
      return this.parts.get(selector);
    }
    querySelectorAll(selector) {
      if (selector !== '.conflict-disable-opponent') return [];
      return [...this.innerHTML.matchAll(/data-opponent-index="(\d+)"/g)].map((match) => {
        const key = `${selector}:${match[1]}`;
        if (!this.parts.has(key)) this.parts.set(key, new Element(selector));
        const button = this.parts.get(key);
        button.dataset.opponentIndex = match[1];
        button.textContent = 'Desativar mod';
        return button;
      });
    }
    prepend(child) { this.prepended = child; }
    remove() { if (elements.get(this.id) === this) elements.delete(this.id); }
  }
  const manualButton = new Element('button');
  manualButton.id = 'btn-conflicts';
  elements.set(manualButton.id, manualButton);
  const document = {createElement: tag => new Element(tag), getElementById: id => elements.get(id) || null,
    body: {appendChild(element) { elements.set(element.id, element); }}};
  const state = {mods: records, conflictsByMod: new Map(), conflictRecords: [], conflictCheckPerformed: false,
    conflictRevision: 0, conflictRequestSerial: 0, conflictRefreshPending: false, conflictShowResultsPending: false,
    conflictManualCheckInProgress: false, conflictRefreshTimer: null, conflictRefreshInProgress: false};
  const calls = {automatic: [], manual: [], enabled: [], renders: [], alerts: []};
  const timers = new Map();
  let timerSequence = 0, operationSequence = 0;
  const autoResponses = [], manualResponses = [];
  const backend = {
    get_conflicts() { calls.automatic.push({revision: state.conflictRevision}); return autoResponses.shift() || Promise.resolve(report()); },
    start_conflict_check(requestId) { calls.manual.push(requestId); return Promise.resolve({ok: true, job_id: requestId}); },
    set_mods_enabled(ids, enabled) { calls.enabled.push({ids, enabled}); return Promise.resolve({ok: true, changed: ids, errors: []}); },
  };
  const context = vm.createContext({state, document, Map, Set, console, api: () => backend,
    clearTimeout: id => timers.delete(id),
    setTimeout(callback, delay) { const id = ++timerSequence; timers.set(id, {callback, delay}); return id; },
    escapeHtml: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    renderMods() { calls.renders.push(new Map([...state.conflictsByMod].map(([id, value]) => [id, value.count]))); },
    renderCharacters() {}, renderTypes() {}, renderTags() {}, renderFolders() {}, renderHeaderCount() {},
    safeRender: callback => callback(), showConflictResolver() {}, alert: message => calls.alerts.push(message),
    newOperationRequest: kind => `${kind}:${++operationSequence}`,
    async runImportOperation(startOperation) { await startOperation(); return await (manualResponses.shift() || Promise.resolve(report())); },
  });
  vm.runInContext(conflictCode, context);
  vm.runInContext(resumeCode, context);
  return {context, state, calls, elements, timers, manualButton, autoResponses, manualResponses,
    queueAuto(value) { autoResponses.push(value?.promise || Promise.resolve(value)); },
    queueManual(value) { manualResponses.push(value?.promise || Promise.resolve(value)); },
    async flushTimer() {
      assert.ok(timers.size, 'a refresh must be queued');
      const [id, scheduled] = timers.entries().next().value;
      timers.delete(id);
      assert.equal(scheduled.delay, 180);
      scheduled.callback();
      await settle();
    }};
}

const cases = [];
function test(name, work) { cases.push({name, work}); }

test('counts each asset once per mod even with several component owners', () => {
  const a = mod('cosy', {components: [component('a1'), component('a2')]});
  const b = mod('diane');
  const t = setup([a, b]);
  t.context.cacheConflictIndicators([conflict('shared', [owner(a, 0), owner(a, 1), owner(b)])]);
  assert.equal(t.state.conflictsByMod.get(a.id).count, 1);
  assert.equal(t.state.conflictsByMod.get(b.id).count, 1);
  assert.equal(t.state.conflictsByMod.get(b.id).opponents.get(a.id).assets, 1);
});

test('popup disables only the selected competing mod and keeps inspected mod active', async () => {
  const records = [mod('cosy'), mod('diane')];
  const t = setup(records);
  t.context.cacheConflictIndicators([conflict('shared', records.map(item => owner(item)))]);
  t.context.showModConflictDetails(records[0]);
  const overlay = t.elements.get('mod-conflict-details-overlay');
  assert.ok(overlay.innerHTML.includes('Desativar mod'));
  assert.ok(overlay.innerHTML.includes('O mod deste alerta continuará ativo.'));
  const [button] = overlay.querySelectorAll('.conflict-disable-opponent');
  await button.onclick();
  assert.deepEqual(plain(t.calls.enabled), [{ids: ['diane'], enabled: false}]);
  assert.equal(records[0].enabled, true, 'inspected mod stays active');
  assert.equal(records[1].enabled, false, 'only competing mod is disabled');
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.equal(t.elements.has('mod-conflict-details-overlay'), false);
  assert.equal(t.state.conflictRefreshPending, true);
});

test('failed popup action keeps both mods and the conflict available', async () => {
  const records = [mod('cosy'), mod('diane')];
  const t = setup(records);
  t.context.api().set_mods_enabled = async () => ({ok: false, changed: [], errors: [{error: 'jogo em execução'}]});
  t.context.cacheConflictIndicators([conflict('shared', records.map(item => owner(item)))]);
  t.context.showModConflictDetails(records[0]);
  const overlay = t.elements.get('mod-conflict-details-overlay');
  const [button] = overlay.querySelectorAll('.conflict-disable-opponent');
  await button.onclick();
  assert.equal(records[0].enabled, true);
  assert.equal(records[1].enabled, true);
  assert.equal(t.state.conflictsByMod.size, 2);
  assert.equal(t.elements.has('mod-conflict-details-overlay'), true);
  assert.deepEqual(t.calls.alerts, ['jogo em execução']);
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Desativar mod');
});

test('disabling mod immediately clears both cards and popup while retaining other conflicts', () => {
  const records = [mod('cosy'), mod('diane'), mod('third'), mod('fourth')];
  const t = setup(records);
  const initial = [conflict('shared1', records.slice(0, 2).map(item => owner(item))),
    conflict('shared2', records.slice(0, 2).map(item => owner(item))),
    conflict('unrelated', records.slice(2).map(item => owner(item)))];
  t.context.cacheConflictIndicators(initial);
  t.context.showModConflictDetails(records[1]);
  t.context.showConflictResults(report(initial));
  assert.ok(t.elements.has('mod-conflict-details-overlay'));
  records[0].enabled = false;
  assert.equal(records[0].components[0].enabled, true, 'switch selection stays saved inside disabled mod');
  t.context.renderLocalChange();
  assert.equal(t.state.conflictsByMod.has('cosy'), false);
  assert.equal(t.state.conflictsByMod.has('diane'), false);
  assert.equal(t.state.conflictsByMod.get('third').count, 1);
  assert.equal(t.state.conflictsByMod.get('fourth').count, 1);
  assert.equal(t.calls.renders.at(-1).has('cosy'), false, 'filtered state must exist before cards render');
  assert.equal(t.elements.has('mod-conflict-details-overlay'), false, 'already open popup must close');
  const html = t.elements.get('conflicts-overlay').innerHTML;
  assert.ok(!html.includes(records[0].name));
  assert.ok(!html.includes(records[1].name));
  assert.ok(html.includes('unrelated.uasset'));
  assert.ok(t.state.conflictRefreshPending);
});

test('turning off last external component does not manufacture same-mod primary/accompaniment conflict', () => {
  const a = mod('cosy', {components: [component('main'), component('extra')]});
  const b = mod('diane');
  const t = setup([a, b]);
  t.context.cacheConflictIndicators([conflict('shared', [owner(a, 0), owner(a, 1), owner(b)])]);
  b.components[0].enabled = false;
  t.context.renderLocalChange();
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.equal(t.context.currentConflictReport({conflicts: t.state.conflictRecords}).conflicts.length, 0);
});

test('disabling one of three owners preserves the conflict between the other two', () => {
  const records = [mod('cosy'), mod('diane'), mod('third')];
  const t = setup(records);
  const raw = conflict('three', records.map(item => owner(item)));
  t.context.cacheConflictIndicators([raw]);
  records[0].enabled = false;
  t.context.renderLocalChange();
  assert.deepEqual([...t.state.conflictsByMod.keys()].sort(), ['diane', 'third']);
  const current = t.context.currentConflictReport(report([raw]));
  assert.deepEqual(plain(current.conflicts[0].owners.map(item => item.mod_id)).sort(), ['diane', 'third']);
  assert.equal(t.state.conflictsByMod.get('diane').opponents.has('cosy'), false);
  assert.equal(t.state.conflictsByMod.get('diane').opponents.get('third').assets, 1);
});

test('current priorities recalculate ties, winner and preferred component counter', () => {
  const a = mod('cosy', {components: [component('main'), component('extra')]});
  const b = mod('diane');
  const t = setup([a, b]);
  const raw = conflict('priority', [owner(a, 0), owner(a, 1), owner(b)]);
  t.context.cacheConflictIndicators([raw]);
  b.priority = 8;
  t.context.renderLocalChange();
  let current = t.context.currentConflictReport(report([raw]));
  assert.equal(current.conflicts[0].winner.mod_id, 'diane');
  assert.equal(current.conflicts[0].winner.component_id, 'diane-main');
  assert.equal(current.conflicts[0].winner.priority, 8);
  assert.equal(current.resolved_conflicts, 1);
  assert.equal(current.tied_conflicts, 0);
  assert.equal(t.state.conflictsByMod.get('diane').wins, 1);
  assert.equal(t.state.conflictsByMod.get('diane').ties, 0);
  a.priority = 8;
  t.context.renderLocalChange();
  current = t.context.currentConflictReport(report([raw]));
  assert.equal(current.conflicts[0].winner, null);
  assert.equal(current.tied_conflicts, 1);
});

test('stale automatic response is rejected and pending refresh survives an in-progress timer', async () => {
  const t = setup();
  const stale = report([conflict('old', t.state.mods.map(item => owner(item)))]);
  t.context.cacheConflictIndicators(stale.conflicts);
  const oldRequest = deferred();
  t.queueAuto(oldRequest);
  const running = t.context.refreshConflictIndicators();
  assert.equal(t.calls.automatic.length, 1);
  t.state.mods[0].enabled = false;
  t.context.renderLocalChange();
  await t.flushTimer();
  assert.equal(t.calls.automatic.length, 1, 'queued timer must not start a duplicate request');
  assert.equal(t.state.conflictRefreshPending, true);
  oldRequest.resolve(stale);
  await running;
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.ok(t.timers.size, 'completion must requeue the refresh that fired while busy');
  const fresh = deferred();
  t.queueAuto(fresh);
  await t.flushTimer();
  assert.equal(t.calls.automatic.length, 2);
  fresh.resolve(report());
  await settle();
  assert.equal(t.state.conflictRecords.length, 0);
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.equal(t.state.conflictRefreshInProgress, false);
  assert.equal(t.state.conflictRefreshPending, false);
});

test('API failures never resurrect a disabled opponent or its popup', async () => {
  for (const mode of ['reject', 'not-ok']) {
    const t = setup();
    const raw = report([conflict('failed', t.state.mods.map(item => owner(item)))]);
    t.context.cacheConflictIndicators(raw.conflicts);
    t.context.showModConflictDetails(t.state.mods[1]);
    t.state.mods[0].enabled = false;
    t.context.renderLocalChange();
    const request = deferred();
    t.queueAuto(request);
    await t.flushTimer();
    if (mode === 'reject') request.reject(new Error('bridge unavailable'));
    else request.resolve({ok: false, error: 'read failed'});
    await settle();
    assert.equal(t.calls.alerts.length, 0, 'background refresh failure must stay silent');
    assert.equal(t.state.conflictsByMod.size, 0, mode);
    assert.equal(t.elements.has('mod-conflict-details-overlay'), false, mode);
    t.context.showModConflictDetails(t.state.mods[1], {count: 99, opponents: new Map()});
    assert.equal(t.elements.has('mod-conflict-details-overlay'), false, 'stale closure info is not accepted');
  }
});

test('failed refresh requested by manual check alerts once and clears the pending report', async () => {
  for (const mode of ['reject', 'not-ok']) {
    const t = setup();
    t.state.conflictShowResultsPending = true;
    const request = deferred();
    t.queueAuto(request);
    const refreshing = t.context.refreshConflictIndicators();
    if (mode === 'reject') request.reject(new Error('bridge unavailable'));
    else request.resolve({ok: false, error: 'read failed'});
    await refreshing;
    assert.equal(t.calls.alerts.length, 1, mode);
    assert.match(t.calls.alerts[0], /bridge unavailable|read failed/);
    assert.equal(t.state.conflictShowResultsPending, false);
    assert.equal(t.elements.has('conflicts-overlay'), false);
    await t.context.refreshConflictIndicators();
    assert.equal(t.elements.has('conflicts-overlay'), false, 'later automatic success must not open an abandoned report');
  }
});

test('initial local render avoids automatic scan but a checked-empty report stays reactive', async () => {
  const t = setup([mod('cosy', {enabled: false}), mod('diane')]);
  t.context.renderLocalChange();
  assert.equal(t.calls.automatic.length, 0);
  assert.equal(t.timers.size, 0, 'opening app before first check must not schedule work');
  t.context.cacheConflictIndicators([]);
  t.state.mods[0].enabled = true;
  t.context.renderLocalChange();
  const fresh = report([conflict('activated', t.state.mods.map(item => owner(item)))]);
  t.queueAuto(fresh);
  await t.flushTimer();
  assert.equal(t.calls.automatic.length, 1);
  assert.equal(t.state.conflictsByMod.get('cosy').count, 1);
  assert.equal(t.state.conflictsByMod.get('diane').count, 1);
});

test('restoring a stale raw report filters disabled owners without mutating original evidence', () => {
  const t = setup();
  const raw = report([conflict('restored', t.state.mods.map(item => owner(item)))]);
  const frozen = plain(raw);
  t.state.mods[0].enabled = false;
  t.context.showConflictResults(raw);
  assert.ok(t.elements.get('conflicts-overlay').innerHTML.includes('Nenhum asset interno'));
  assert.ok(!t.elements.get('conflicts-overlay').innerHTML.includes(t.state.mods[0].name));
  t.context.cacheConflictIndicators(raw.conflicts);
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.deepEqual(plain(raw), frozen);
});

test('popup lookup uses current state instead of a captured object/info', () => {
  const t = setup();
  const capturedMod = {...t.state.mods[0]};
  const raw = conflict('popup', t.state.mods.map(item => owner(item)));
  t.context.cacheConflictIndicators([raw]);
  const capturedInfo = t.state.conflictsByMod.get('cosy');
  t.state.mods = t.state.mods.map(item => item.id === 'cosy' ? {...item, enabled: false} : item);
  t.context.renderLocalChange();
  t.context.showModConflictDetails(capturedMod, capturedInfo);
  assert.equal(t.elements.has('mod-conflict-details-overlay'), false);
  t.context.showModConflictDetails(t.state.mods[1], capturedInfo);
  assert.equal(t.elements.has('mod-conflict-details-overlay'), false);
});

test('stale manual job is discarded and shows only the fresh follow-up result', async () => {
  const t = setup();
  const old = report([conflict('manual-job-old', t.state.mods.map(item => owner(item)))]);
  const job = deferred();
  t.queueManual(job);
  const checking = t.manualButton.onclick();
  await settle();
  assert.equal(t.manualButton.disabled, true);
  assert.equal(t.calls.manual.length, 1);
  t.state.mods[0].enabled = false;
  t.context.renderLocalChange();
  await t.flushTimer();
  assert.equal(t.calls.automatic.length, 0, 'automatic check waits for manual job');
  job.resolve(old);
  await checking;
  assert.equal(t.elements.has('conflicts-overlay'), false, 'old manual result must never flash');
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.equal(t.state.conflictShowResultsPending, true);
  assert.equal(t.manualButton.disabled, false);
  const fresh = deferred();
  t.queueAuto(fresh);
  await t.flushTimer();
  assert.equal(t.calls.automatic.length, 1);
  fresh.resolve(report());
  await settle();
  assert.ok(t.elements.get('conflicts-overlay').innerHTML.includes('Nenhum asset interno'));
  assert.equal(t.state.conflictShowResultsPending, false);
  assert.equal(t.state.conflictRecords.length, 0);
});

test('two manual checks use new request ids and current result updates popup', async () => {
  const t = setup();
  const raw = report([conflict('manual-result', t.state.mods.map(item => owner(item)))]);
  t.queueManual(raw);
  await t.manualButton.onclick();
  assert.ok(t.elements.get('conflicts-overlay').innerHTML.includes('manual-result.uasset'));
  t.elements.get('conflicts-overlay').querySelector('#conflicts-close').onclick();
  t.queueManual(report());
  await t.manualButton.onclick();
  assert.equal(t.calls.manual.length, 2);
  assert.notEqual(t.calls.manual[0], t.calls.manual[1]);
  assert.equal(t.state.conflictsByMod.size, 0);
  assert.ok(t.elements.get('conflicts-overlay').innerHTML.includes('Nenhum asset interno'));
});

test('a new manual check clears the prior pending report even if the new job is cancelled', async () => {
  const t = setup();
  t.state.conflictShowResultsPending = true;
  t.queueManual({ok: true, cancelled: true});
  await t.manualButton.onclick();
  assert.equal(t.state.conflictShowResultsPending, false);
  assert.equal(t.manualButton.disabled, false);
  await t.context.refreshConflictIndicators();
  assert.equal(t.elements.has('conflicts-overlay'), false);
});

test('resuming a finished conflict job queries the current state instead of replaying its result', async () => {
  const t = setup();
  const old = report([conflict('cached-terminal', t.state.mods.map(item => owner(item)))]);
  t.context.pendingOperation = () => ({requestId: 'old-request', title: 'Conflitos', context: {kind: 'conflicts'}});
  let finds = 0;
  t.context.api().find_operation = async id => { assert.equal(id, 'old-request'); finds++; return {ok: true, found: true}; };
  t.state.mods[0].enabled = false;
  t.queueManual(old);
  const fresh = deferred();
  t.queueAuto(fresh);
  const resuming = t.context.resumeLastOperation();
  await settle();
  assert.equal(finds, 1);
  assert.equal(t.calls.automatic.length, 1);
  assert.equal(t.elements.has('conflicts-overlay'), false, 'terminal result must not flash before the fresh request');
  fresh.resolve(report());
  await resuming;
  assert.ok(t.elements.get('conflicts-overlay').innerHTML.includes('Nenhum asset interno'));
  assert.ok(!t.elements.get('conflicts-overlay').innerHTML.includes('cached-terminal'));
  assert.equal(t.state.conflictsByMod.size, 0);
});

test('disabled owners are removed from manual conflicts across identities as well', () => {
  const records = [mod('cosy'), mod('diane')];
  records[1].character = 'Hela';
  records[0].manual_conflicts = ['diane'];
  const t = setup(records);
  const raw = conflict('manual', records.map(item => ({...owner(item), component_id: 'manual-conflict'})), {kind: 'manual', asset_type: 'Manual'});
  t.context.cacheConflictIndicators([raw]);
  assert.equal(t.state.conflictsByMod.size, 2);
  records[0].enabled = false;
  t.context.renderLocalChange();
  assert.equal(t.state.conflictsByMod.size, 0);
});

test('changed identity and deleted mod cannot reuse an old automatic conflict', () => {
  const t = setup();
  const raw = conflict('identity', t.state.mods.map(item => owner(item)));
  t.context.cacheConflictIndicators([raw]);
  t.state.mods[0].skin = 'Another skin';
  t.context.renderLocalChange();
  assert.equal(t.state.conflictsByMod.size, 0);
  t.state.mods = t.state.mods.filter(item => item.id !== 'diane');
  t.context.cacheConflictIndicators([raw]);
  assert.equal(t.state.conflictsByMod.size, 0);
});

for (const {name, work} of cases) {
  try { await work(); }
  catch (error) { error.message = `${name}: ${error.message}`; throw error; }
}
console.log(`Conflict indicators: ${cases.length} scenarios passed.`);
