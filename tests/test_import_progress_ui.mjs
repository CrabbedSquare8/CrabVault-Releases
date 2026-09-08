import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const maintenance = fs.readFileSync(new URL('../frontend/maintenance.js', import.meta.url), 'utf8');
const dialogSource = app.slice(app.indexOf('function openComponentDialog('), app.indexOf('async function showComponentDiagnosis('));
const progressSource = maintenance.slice(maintenance.indexOf('const operationStorageKey ='), maintenance.indexOf('async function refreshOperationNotice('));
const resumeStart = maintenance.indexOf('async function resumeLastOperation(');
const resumeSource = maintenance.slice(resumeStart, maintenance.indexOf('\n}', resumeStart) + 2);
const selectionStart = app.indexOf('async function openInstallSelection(');
const selectionSource = app.slice(selectionStart, app.indexOf('\n}', selectionStart) + 2);
const installSource = app.slice(app.indexOf('async function cancelPendingInstall('), app.indexOf('// Modal: Settings'));
const keyboardSource = app.slice(app.indexOf('document.addEventListener("keydown", async (event) => {'), app.indexOf('function showConflictResults('));

const settle = async () => { for (let step = 0; step < 12; step++) await Promise.resolve(); };

function setup(statuses = [], options = {}) {
  const ids = new Map(), timers = [], alerts = [], calls = {cancel: 0, discard: 0, status: 0, refresh: 0, start: 0, notice: 0, find: 0, recovery: 0, selection: 0};
  const sessionValues = options.sessionValues || new Map(), requestedJobs = [], requestLookups = [], openedSelections = [];
  const sessionStorage = {getItem: key => sessionValues.get(key) ?? null,
    setItem: (key, value) => sessionValues.set(key, String(value)), removeItem: key => sessionValues.delete(key)};
  const document = {activeElement: null, getElementById: id => ids.get(id) || null};
  class Element {
    constructor(name = '') {
      this.name = name; this.disabled = false; this.hidden = false; this.dataset = {}; this.style = {};
      this.textContent = ''; this.value = ''; this.checked = false; this.children = []; this.isConnected = true;
      const names = new Set();
      this.classList = {add: name => names.add(name), remove: name => names.delete(name), contains: name => names.has(name)};
    }
    set innerHTML(value) {
      this.html = value;
      if (!value.includes('diagnostic-dialog')) return;
      const panel = new Element('panel'), close = new Element('close');
      close.textContent = 'Fechar';
      this.nodes = new Map([['.diagnostic-dialog', panel], ['.dialog-close', close]]);
      this.children = [panel, close];
      if (value.includes('operation-cancel')) {
        for (const selector of ['.operation-message', 'progress', '.operation-count', '.operation-cancel']) {
          const node = new Element(selector);
          this.nodes.set(selector, node); this.children.push(node);
        }
        this.nodes.get('.operation-cancel').disabled = true;
      }
    }
    querySelector(selector) {
      if (this.nodes?.has(selector)) return this.nodes.get(selector);
      if (selector.startsWith('button')) return this.children.find(child => ['close', '.operation-cancel'].includes(child.name) && !child.disabled) || null;
      return null;
    }
    querySelectorAll() { return this.children.filter(child => ['close', '.operation-cancel'].includes(child.name) && !child.disabled); }
    getClientRects() { return this.hidden ? [] : [{}]; }
    contains(node) { return node === this || this.children.includes(node); }
    focus() { document.activeElement = this; }
    click() { if (!this.disabled) return this.onclick?.({target: this}); }
    remove() { this.isConnected = false; if (this.id) ids.delete(this.id); }
    removeAttribute(name) { delete this[name]; }
  }
  document.body = {appendChild(element) { if (element.id) ids.set(element.id, element); }};
  document.createElement = () => new Element();
  document.querySelectorAll = () => [];
  const modalBody = new Element('modal-body');
  document.querySelector = selector => selector === '#add-mod-overlay .modal-body' ? modalBody : null;
  document.addEventListener = (type, callback) => { if (type === 'keydown') document.keydown = callback; };
  const buttonIds = ['btn-add-mod', 'btn-add-reshade', 'btn-add-background', 'add-mod-close', 'add-mod-cancel', 'add-mod-confirm'];
  for (const id of [...buttonIds, 'input-name', 'input-link', 'input-folder', 'option-obfuscation', 'option-hybrid', 'option-legacy',
    'btn-install-image', 'input-wants-image', 'install-tags', 'install-image-preview', 'install-character-label',
    'install-folder-label', 'install-options', 'install-modal-title', 'install-modal-hint', 'install-original-name',
    'install-character-badge', 'install-type-badge']) ids.set(id, new Element(id));
  ids.get('add-mod-confirm').textContent = 'Instalar mod';
  ids.get('btn-add-background').disabled = true;
  const addModOverlay = new Element('install-form'); addModOverlay.classList.add('open');
  const state = {installToken: 'selection', installParentBackgroundId: null, pickedCharacter: 'Hela', pickedSkin: 'Default', installKind: 'pak', roster: ['Hela']};
  const backend = {
    async get_operation_status(jobId) { calls.status++; requestedJobs.push(jobId); const next = statuses.shift(); if (next instanceof Error) throw next; assert.ok(next, 'unexpected extra status request'); return next; },
    async find_operation(requestId) { calls.find++; requestLookups.push(requestId); return {ok: true, found: false}; },
    async cancel_operation() { calls.cancel++; return {ok: true}; },
    async cancel_mod_install(token) { calls.discard++; assert.equal(token, 'selection'); return {ok: true}; },
    async start_complete_mod_install(token) { calls.start++; assert.equal(token, 'selection'); return {ok: true, job_id: 'job'}; },
  };
  const context = vm.createContext({state, document, addModOverlay, api: () => backend, escapeHtml: value => value,
    window: {sessionStorage, crypto: {randomUUID: () => 'test-request-id'}},
    setTimeout: (callback, ms) => { timers.push({callback, ms}); }, formatModSize: mb => `${mb} MB`,
    maintenanceError: (_, error) => alerts.push(String(error)), refreshOperationNotice: () => { calls.notice++; },
    alert: message => alerts.push(message), reloadAll: async () => { calls.refresh++; }, showModDetailsPage: async () => {},
    showInterruptedOperations: async () => { calls.recovery++; },
    characterSearch: new Element(), characterPicker: new Element(), characterSelected: new Element(),
    skinSection: new Element(), inputSkinNew: new Element(), renderCharacterPicker: () => {}, renderInstallTree: () => {},
    updateSuggestedInstallFolder: () => {}, renderPersonalImportChoices: () => {},
    selectCharacter: async character => { state.pickedCharacter = character; }, requestAnimationFrame: callback => callback(),
    HTMLInputElement: class {}, HTMLTextAreaElement: class {}, HTMLSelectElement: class {},
    ctxMenu: null, settingsOverlay: null,
  });
  vm.runInContext(dialogSource + progressSource + resumeSource + selectionSource + installSource + keyboardSource, context);
  const openSelection = context.openInstallSelection;
  context.openInstallSelection = async (...args) => { calls.selection++; openedSelections.push(args); return openSelection(...args); };
  const key = (key, overrides = {}) => ({key, target: {}, shiftKey: false, prevented: false, stopped: false,
    preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; }, ...overrides});
  return {context, state, document, ids, alerts, calls, backend, addModOverlay, timers, key, sessionValues, requestedJobs, requestLookups, openedSelections,
    get overlay() { return ids.get('component-diagnostic-overlay'); },
    async tick() { assert.ok(timers.length, 'expected an operation poll'); timers.shift().callback(); await settle(); },
  };
}

const running = (extra = {}) => ({ok: true, state: 'running', message: 'Copiando arquivos…', can_cancel: true, current: 1, total: 2, ...extra});
const completed = {ok: true, state: 'completed', can_cancel: false, result: {ok: true, record: {id: 'new'}}};
const storedOperation = t => JSON.parse(t.sessionValues.get('marvel-manager.pending-operation') || 'null');
const storedPreparation = t => JSON.parse(t.sessionValues.get('marvel-manager.prepared-import') || 'null');
const preparation = {requestId: 'prepare:original', title: 'Preparando importação',
  context: {kind: 'import_prepare', install_kind: 'pak', parent_background_id: null}};
const selectedFiles = {ok: true, token: 'selection', install_kind: 'pak', character: 'Hela', skin: 'Default',
  type: 'Mesh', suggested_name: 'Minha seleção', source_folder: 'Meu pacote'};
let scenarios = 0;

{
  const t = setup([running(), running({can_cancel: false, message: 'Salvando catálogo…'}), completed]);
  const operation = t.context.runImportOperation(async () => ({ok: true, job_id: 'job'}), 'Instalando');
  await settle();
  const overlay = t.overlay;
  assert.equal(t.state.importBusy, true);
  assert.equal(overlay.querySelector('progress').value, 50);
  assert.equal(overlay.querySelector('.operation-count').textContent, '1 de 2');
  assert.equal(t.ids.get('btn-add-mod').disabled, true);
  overlay.onkeydown(t.key('Escape'));
  overlay.onclick({target: overlay});
  assert.equal(overlay.isConnected, true, 'Escape and backdrop cannot close an active operation');
  await t.tick();
  assert.equal(overlay.querySelector('.operation-cancel').disabled, true, 'commit cannot be cancelled');
  await overlay.querySelector('.operation-cancel').click();
  assert.equal(t.calls.cancel, 0);
  const tab = t.key('Tab'); overlay.onkeydown(tab);
  assert.equal(tab.prevented, true);
  assert.equal(t.document.activeElement, overlay.querySelector('.diagnostic-dialog'), 'no focus escape during commit');
  await t.tick();
  assert.equal((await operation).ok, true);
  assert.equal(overlay.isConnected, false);
  assert.equal(t.state.importBusy, false);
  assert.equal(t.ids.get('btn-add-mod').disabled, false);
  assert.equal(t.ids.get('btn-add-background').disabled, true, 'restore pre-existing disabled controls');
  assert.equal(t.calls.notice, 1);
  scenarios++;
}
{
  const t = setup([running(), {ok: true, state: 'cancelled', can_cancel: false, result: {ok: false, cancelled: true}}]);
  const operation = t.context.runImportOperation(async () => ({job_id: 'job'}), 'Preparando',
    {requestId: 'prepare:cancel', context: {kind: 'import_prepare'}});
  await settle();
  await t.overlay.querySelector('.operation-cancel').click();
  await t.overlay.querySelector('.operation-cancel').click();
  assert.equal(t.calls.cancel, 1, 'cancellation cannot be sent twice');
  assert.equal(t.state.importBusy, true, 'wait for backend cleanup before unlocking');
  assert.equal(storedOperation(t).requestId, 'prepare:cancel', 'cancellation request alone is not a completed cleanup');
  await t.tick();
  assert.equal((await operation).cancelled, true);
  assert.equal(t.state.importBusy, false);
  assert.equal(storedOperation(t), null);
  scenarios++;
}
{
  const t = setup([new Error('bridge disconnected'), running(), completed]);
  let starts = 0;
  const operation = t.context.runImportOperation(async () => { starts++; return {job_id: 'job'}; }, 'Instalando',
    {requestId: 'install:retry', context: {kind: 'import_commit'}});
  await settle();
  assert.match(t.overlay.querySelector('.operation-message').textContent, /comunicação foi interrompida/);
  assert.equal(t.state.importBusy, true);
  assert.equal(storedOperation(t).requestId, 'install:retry');
  assert.equal(t.timers[0].ms, 1000);
  await t.tick(); await t.tick();
  assert.equal((await operation).ok, true);
  assert.equal(starts, 1, 'poll reconnect must never restart the import');
  assert.deepEqual(t.requestedJobs, ['job', 'job', 'job']);
  assert.equal(storedOperation(t), null, 'terminal result clears the reconnect descriptor');
  scenarios++;
}
{
  const t = setup();
  assert.equal((await t.context.runImportOperation(async () => ({cancelled: true}), 'Preparando')).cancelled, true);
  assert.equal(t.calls.status, 0);
  assert.equal(t.state.importBusy, false);
  assert.equal(t.overlay, undefined);
  t.state.importBusy = true;
  assert.equal((await t.context.runImportOperation(() => { throw new Error('must not start'); }, 'Duplicada')).ok, false);
  assert.equal(t.state.importBusy, true, 'duplicate caller must not unlock the original operation');
  scenarios++;
}
{
  const t = setup();
  await t.document.keydown(t.key('Escape'));
  assert.equal(t.calls.discard, 1, 'Escape discards the prepared import through the backend');
  assert.equal(t.state.installToken, null);
  assert.equal(t.addModOverlay.classList.contains('open'), false);
  scenarios++;
}
{
  const t = setup();
  t.state.importBusy = true;
  await t.document.keydown(t.key('Escape'));
  await t.context.cancelPendingInstall();
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.discard, 0);
  assert.equal(t.calls.start, 0);
  assert.equal(t.state.installToken, 'selection');
  assert.equal(t.addModOverlay.classList.contains('open'), true);
  scenarios++;
}
{
  const t = setup();
  let resolveCancel;
  t.backend.cancel_mod_install = () => { t.calls.discard++; return new Promise(resolve => { resolveCancel = resolve; }); };
  const cancel = t.context.cancelPendingInstall();
  await t.context.cancelPendingInstall();
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.discard, 1);
  assert.equal(t.calls.start, 0, 'cannot commit while preparation is being discarded');
  resolveCancel({ok: false, error: 'temporary failure'});
  await cancel;
  assert.equal(t.state.installToken, 'selection', 'failed cleanup remains retryable');
  assert.equal(t.addModOverlay.classList.contains('open'), true);
  assert.equal(t.state.installCancelling, false);
  assert.match(t.alerts[0], /Não foi possível cancelar/);
  scenarios++;
}
{
  const t = setup();
  t.backend.start_complete_mod_install = async () => { t.calls.start++; throw new Error('lost start response'); };
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1);
  assert.equal(t.state.installToken, null, 'a potentially consumed token is never resubmitted');
  assert.equal(t.addModOverlay.classList.contains('open'), false);
  assert.equal(t.state.importBusy, false);
  assert.equal(t.ids.get('add-mod-confirm').disabled, false);
  assert.match(t.alerts[0], /Não foi possível confirmar.*Operações interrompidas/);
  assert.equal(storedOperation(t).requestId, 'install:selection', 'uncertain start remains recoverable');
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1);
  scenarios++;
}
{
  const t = setup([completed]);
  t.context.reloadAll = async () => { throw new Error('render failed'); };
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.state.installToken, null);
  assert.match(t.alerts[0], /O mod foi instalado/);
  assert.equal(t.calls.start, 1);
  scenarios++;
}
{
  const t = setup([running(), completed]);
  const operation = t.ids.get('add-mod-confirm').onclick();
  await settle();
  const overlay = t.overlay;
  await t.document.keydown(t.key('Escape'));
  assert.equal(overlay.isConnected, true);
  assert.equal(t.calls.discard, 0, 'global Escape must not reach the underlying import form');
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1, 'no concurrent confirmation');
  await t.tick(); await operation;
  assert.equal(t.calls.refresh, 1);
  assert.equal(t.state.installToken, null);
  scenarios++;
}
{
  const t = setup([completed]);
  t.backend.start_complete_mod_install = async token => {
    t.calls.start++; assert.equal(token, 'selection');
    throw new Error('installation started, but the initial response was lost');
  };
  t.backend.find_operation = async requestId => {
    t.calls.find++; t.requestLookups.push(requestId);
    return {ok: true, found: true, job_id: 'job'};
  };
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1, 'lookup must not repeat the installation request');
  assert.deepEqual(t.requestLookups, ['install:selection']);
  assert.deepEqual(t.requestedJobs, ['job']);
  assert.equal(t.calls.refresh, 1, 'the recovered result follows normal success handling');
  assert.equal(t.state.installToken, null);
  assert.equal(t.alerts.length, 0);
  assert.equal(storedOperation(t), null);
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1, 'a second click after success cannot resubmit the consumed selection');
  scenarios++;
}
{
  const t = setup([running(), new Error('lost bridge'), new Error('still offline'), completed]);
  let starts = 0;
  const operation = t.context.runImportOperation(async () => { starts++; return {job_id: 'same-job'}; }, 'Instalando',
    {requestId: 'install:polling', context: {kind: 'import_commit'}});
  await settle();
  await t.tick();
  assert.equal(t.overlay.querySelector('.operation-cancel').disabled, true, 'cannot cancel through a disconnected bridge');
  assert.equal(storedOperation(t).requestId, 'install:polling');
  await t.tick(); await t.tick();
  assert.equal((await operation).ok, true);
  assert.equal(starts, 1);
  assert.equal(t.calls.find, 0, 'a known job can resume polling directly');
  assert.deepEqual(t.requestedJobs, ['same-job', 'same-job', 'same-job', 'same-job']);
  assert.equal(storedOperation(t), null);
  scenarios++;
}
{
  const t = setup(Array.from({length: 5}, () => new Error('bridge unavailable')));
  const operation = t.ids.get('add-mod-confirm').onclick();
  await settle();
  for (let attempt = 0; attempt < 4; attempt++) await t.tick();
  await operation;
  assert.equal(t.calls.start, 1);
  assert.equal(t.calls.status, 5);
  assert.equal(t.state.importBusy, false);
  assert.equal(t.state.installToken, null, 'a potentially consumed selection cannot be submitted again');
  assert.equal(t.overlay, undefined, 'the failed connection does not trap the interface');
  const saved = storedOperation(t);
  assert.equal(saved.requestId, 'install:selection');
  assert.equal(saved.context.kind, 'import_commit');
  assert.match(t.alerts[0], /Retomar acompanhamento/);
  let duplicateStarts = 0;
  const blocked = await t.context.runImportOperation(async () => { duplicateStarts++; return {job_id: 'duplicate'}; }, 'Nova instalação',
    {requestId: 'install:other-selection', context: {kind: 'import_commit'}});
  assert.equal(blocked.ok, false);
  assert.equal(duplicateStarts, 0, 'an unresolved operation must block a new request before its side effect');
  assert.deepEqual(storedOperation(t), saved);

  // A new JS context represents reloading the page; only sessionStorage survives.
  const reloaded = setup([running(), completed], {sessionValues: t.sessionValues});
  reloaded.state.installToken = null;
  reloaded.backend.find_operation = async requestId => {
    reloaded.calls.find++; reloaded.requestLookups.push(requestId);
    return {ok: true, found: true, job_id: 'job'};
  };
  const resumed = reloaded.context.resumeLastOperation();
  await settle();
  await reloaded.context.resumeLastOperation();
  assert.equal(reloaded.calls.find, 1, 'repeated resume clicks do not create parallel tracking');
  assert.equal(reloaded.state.importBusy, true);
  await reloaded.tick(); await resumed;
  assert.equal(reloaded.calls.start, 0, 'page reload and resume must never call start again');
  assert.deepEqual(reloaded.requestLookups, ['install:selection']);
  assert.deepEqual(reloaded.requestedJobs, ['job', 'job']);
  assert.equal(reloaded.calls.refresh, 1);
  assert.match(reloaded.alerts[0], /Importação concluída/);
  assert.equal(storedOperation(reloaded), null);
  await reloaded.context.resumeLastOperation();
  assert.equal(reloaded.calls.find, 1, 'completed tracking cannot replay after its descriptor is cleared');
  scenarios++;
}
{
  const t = setup();
  t.backend.start_complete_mod_install = async () => { t.calls.start++; throw new Error('initial response lost'); };
  t.backend.find_operation = async () => { t.calls.find++; throw new Error('lookup also offline'); };
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1);
  assert.equal(t.calls.find, 1);
  assert.equal(storedOperation(t).requestId, 'install:selection');
  assert.equal(t.state.installToken, null);
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1);
  assert.equal(t.calls.discard, 0, 'uncertain completion must not discard backend staging');
  scenarios++;
}
{
  const t = setup();
  t.context.rememberOperation({requestId: 'install:previous-process', title: 'Instalando mod', context: {kind: 'import_commit'}});
  await t.context.resumeLastOperation();
  assert.equal(t.calls.find, 1);
  assert.equal(t.calls.start, 0);
  assert.equal(t.calls.recovery, 1, 'a missing job routes to recovery review, not a new installation');
  assert.equal(storedOperation(t), null);
  assert.match(t.alerts[0], /nenhum pedido foi reenviado/);
  scenarios++;
}
{
  const t = setup([{ok: true, state: 'failed', can_cancel: false, result: {ok: false, error: 'Safe rollback finished'}}]);
  const result = await t.context.runImportOperation(async () => ({job_id: 'job'}), 'Instalando',
    {requestId: 'install:failed', context: {kind: 'import_commit'}});
  assert.equal(result.ok, false);
  assert.equal(result.error, 'Safe rollback finished');
  assert.equal(storedOperation(t), null, 'a definitive failure is not an uncertain in-flight operation');
  assert.equal(t.state.importBusy, false);
  scenarios++;
}
{
  const t = setup([running(), completed]);
  await t.context.openInstallSelection(selectedFiles, null, preparation);
  assert.deepEqual(storedPreparation(t), preparation);
  assert.equal(t.context.pendingOperation(), null, 'an open prepared form must not block its own confirmation');
  const install = t.ids.get('add-mod-confirm').onclick();
  await settle();
  assert.equal(t.calls.start, 1);
  assert.equal(storedPreparation(t), null, 'once submitted, the old prepared result must never reopen as an installable selection');
  assert.equal(storedOperation(t).requestId, 'install:selection');
  await t.tick(); await install;
  assert.equal(storedOperation(t), null);
  assert.equal(storedPreparation(t), null);
  scenarios++;
}
{
  const first = setup();
  await first.context.openInstallSelection(selectedFiles, null, preparation);
  const reloaded = setup([{ok: true, state: 'completed', result: selectedFiles}], {sessionValues: first.sessionValues});
  reloaded.state.installToken = null;
  reloaded.addModOverlay.classList.remove('open');
  assert.equal(reloaded.context.pendingOperation().requestId, 'prepare:original');
  reloaded.backend.find_operation = async requestId => {
    reloaded.calls.find++; reloaded.requestLookups.push(requestId);
    return {ok: true, found: true, job_id: 'prepared-job'};
  };
  await reloaded.context.resumeLastOperation();
  assert.equal(reloaded.calls.start, 0, 'reload must not prepare or install the same files again');
  assert.equal(reloaded.calls.selection, 1);
  assert.deepEqual(reloaded.requestLookups, ['prepare:original']);
  assert.deepEqual(reloaded.requestedJobs, ['prepared-job']);
  assert.equal(reloaded.openedSelections[0][0].token, 'selection');
  assert.equal(reloaded.openedSelections[0][2].requestId, 'prepare:original', 'the form keeps its original lookup descriptor');
  assert.equal(reloaded.state.installToken, 'selection');
  assert.equal(reloaded.addModOverlay.classList.contains('open'), true);
  assert.equal(storedOperation(reloaded), null);
  assert.deepEqual(storedPreparation(reloaded), preparation, 'another page reload can still reopen this unsubmitted form');
  assert.equal(reloaded.context.pendingOperation(), null, 'the recovered form can be confirmed normally');
  await reloaded.context.resumeLastOperation();
  assert.equal(reloaded.calls.find, 1, 'an already open form is not recovered a second time');
  scenarios++;
}
{
  const t = setup();
  await t.context.openInstallSelection(selectedFiles, null, preparation);
  t.backend.cancel_mod_install = async () => { t.calls.discard++; return {ok: false, error: 'temporarily locked'}; };
  await t.context.cancelPendingInstall();
  assert.equal(t.state.installToken, 'selection');
  assert.deepEqual(storedPreparation(t), preparation, 'a failed discard must remain recoverable after reload');
  t.backend.cancel_mod_install = async token => { t.calls.discard++; assert.equal(token, 'selection'); return {ok: true}; };
  await t.context.cancelPendingInstall();
  assert.equal(t.calls.discard, 2);
  assert.equal(t.state.installToken, null);
  assert.equal(storedPreparation(t), null, 'only successful discard removes the prepared descriptor');
  assert.equal(t.context.pendingOperation(), null);
  scenarios++;
}
{
  const t = setup();
  await t.context.openInstallSelection(selectedFiles, null, preparation);
  t.backend.start_complete_mod_install = async () => { t.calls.start++; throw new Error('commit response lost'); };
  t.backend.find_operation = async () => { t.calls.find++; throw new Error('bridge offline'); };
  await t.ids.get('add-mod-confirm').onclick();
  assert.equal(t.calls.start, 1);
  assert.equal(storedPreparation(t), null);
  assert.equal(storedOperation(t).context.kind, 'import_commit');
  assert.equal(storedOperation(t).requestId, 'install:selection');
  assert.equal(t.state.installToken, null);
  assert.equal(t.calls.discard, 0, 'uncertain commit must not erase staged files through cancel');
  scenarios++;
}
{
  const t = setup();
  await t.context.openInstallSelection(selectedFiles, null, preparation);
  t.state.installToken = null;
  await t.context.resumeLastOperation();
  assert.equal(t.calls.start, 0);
  assert.equal(t.calls.recovery, 1);
  assert.equal(storedPreparation(t), null, 'missing prepared jobs cannot leave an endless resume banner');
  assert.equal(storedOperation(t), null);
  scenarios++;
}
console.log(`Import progress UI: ${scenarios} scenarios passed.`);
