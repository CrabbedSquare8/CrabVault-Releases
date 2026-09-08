import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const html = fs.readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
const maintenance = fs.readFileSync(new URL('../frontend/maintenance.js', import.meta.url), 'utf8');
const toolsSource = maintenance.slice(maintenance.indexOf('function clearPersonalImportChoice('),
  maintenance.indexOf('async function showRelationSuggestions('));
const identitySource = app.slice(app.indexOf('const addModOverlay ='), app.indexOf('function addInstallTag('));
const installSource = app.slice(app.indexOf('async function cancelPendingInstall('), app.indexOf('// Modal: Settings'));
const settle = async () => { for (let step = 0; step < 16; step++) await Promise.resolve(); };
const plain = value => JSON.parse(JSON.stringify(value));

function setup() {
  const ids = new Map(), dialogs = [], errors = [], alerts = [], requests = [];
  const calls = {install: [], preview: [], backup: [], restorePreview: [], restore: [], refresh: 0, resume: 0};
  const document = {activeElement: null, getElementById: id => ids.get(id) || null};
  class Element {
    constructor(tag = 'div') {
      this.tag = tag; this.children = []; this.nodes = []; this.dataset = {}; this.style = {};
      this.value = ''; this.textContent = ''; this.checked = false; this.disabled = false;
      this.hidden = false; this.isConnected = true; this.listeners = new Map();
      const classes = new Set();
      this.classList = {add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name), toggle: (name, active) => {
          const add = active ?? !classes.has(name); if (add) classes.add(name); else classes.delete(name); return add;
        }};
    }
    set className(value) { this._className = value; for (const name of value.split(/\s+/)) this.classList.add(name); }
    get className() { return this._className || ''; }
    set innerHTML(value) {
      this.html = value; this.children = []; this.nodes = [];
      for (const match of value.matchAll(/<(button|input|span|select)\b([^>]*)>/g)) {
        const element = new Element(match[1]), attributes = match[2];
        element.className = attributes.match(/\bclass="([^"]*)"/)?.[1] || '';
        element.disabled = /\bdisabled\b/.test(attributes);
        element.checked = /\bchecked\b/.test(attributes);
        element.value = attributes.match(/\bvalue="([^"]*)"/)?.[1] || '';
        const id = attributes.match(/\bid="([^"]*)"/)?.[1];
        if (id) { element.id = id; ids.set(id, element); }
        this.children.push(element); this.nodes.push(element);
      }
    }
    get innerHTML() { return this.html || ''; }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    querySelectorAll(selector) {
      if (selector.startsWith('.')) return this.children.filter(child => child.classList.contains(selector.slice(1)));
      return this.children.filter(child => child.tag === selector);
    }
    appendChild(element) { this.children.push(element); }
    addEventListener(type, callback) { this.listeners.set(type, callback); }
    async input(value) { this.value = value; return this.listeners.get('input')?.({target: this}); }
    async click() { if (this.disabled || !this.isConnected) return; return this.onclick?.({target: this}); }
    focus() { document.activeElement = this; }
    remove() { this.isConnected = false; this.children.forEach(child => { child.isConnected = false; }); }
  }
  document.createElement = tag => new Element(tag);
  document.querySelectorAll = () => [];
  for (const id of ['add-mod-overlay', 'character-list-box', 'character-search', 'character-picker', 'character-selected',
    'skin-section', 'skin-chips', 'input-skin-new', 'input-folder', 'install-character-badge', 'install-personal-corrections',
    'install-correction-choice', 'install-correction-note', 'setting-full-backup', 'setting-full-restore', 'add-mod-close',
    'add-mod-cancel', 'add-mod-confirm', 'input-name', 'input-link', 'option-obfuscation', 'option-hybrid', 'option-legacy']) {
    ids.set(id, new Element());
  }
  ids.get('add-mod-overlay').classList.add('open');
  ids.get('add-mod-confirm').textContent = 'Instalar mod';
  const state = {installToken: 'selection', installKind: 'pak', installSourceFolder: 'Meu pacote', installParentBackgroundId: null,
    pickedCharacter: 'Hela', pickedSkin: 'Default', installFolderChosenManually: false,
    personalCorrectionChoice: null, roster: ['Hela', 'Storm', 'Magik', 'Generic']};
  const backend = {
    async get_skins_for_character(character) { return character === 'Generic' ? [] : ['Default', 'Outra skin']; },
    async start_complete_mod_install(token, meta) { calls.install.push({token, meta: plain(meta)}); return {ok: true, record: {id: 'new'}}; },
    async start_full_backup_preview(requestId) { calls.preview.push(requestId); return backupPlan(); },
    async start_full_restore_preview(requestId) { calls.restorePreview.push(requestId); return {...backupPlan(), can_restore: true}; },
    async start_full_backup(token, allowIncomplete) {
      calls.backup.push({token, allowIncomplete}); return {ok: true, complete: !allowIncomplete, path: 'D:\\Chosen\\Backup.zip', warnings: []};
    },
    async start_full_restore(token) { calls.restore.push(token); return {ok: true, path: 'D:\\Chosen\\Restored', warnings: []}; },
  };
  let requestSequence = 0;
  const context = vm.createContext({state, document, api: () => backend,
    escapeHtml: value => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;'),
    formatModSize: value => `${value} MB`, clearPreparedImport: () => {},
    alert: message => alerts.push(message), maintenanceError: (_, error) => errors.push(String(error)),
    reloadAll: async () => { calls.refresh++; }, showModDetailsPage: async () => {},
    pendingOperation: () => null, resumeLastOperation: async () => { calls.resume++; },
    newOperationRequest: kind => `${kind}:request-${++requestSequence}`,
    openComponentDialog: (title, html) => {
      dialogs.filter(dialog => dialog.isConnected).forEach(dialog => dialog.remove());
      const dialog = new Element('dialog'); dialog.title = title; dialog.innerHTML = html; dialogs.push(dialog); return dialog;
    },
    runImportOperation: async (start, title, options) => {
      requests.push({title, options: plain(options)});
      state.importBusy = true;
      try { return await start(); } finally { state.importBusy = false; }
    },
  });
  vm.runInContext(identitySource + toolsSource + installSource, context);
  context.updateSuggestedInstallFolder();
  return {context, state, document, ids, dialogs, calls, backend, errors, alerts, requests,
    get dialog() { return dialogs.at(-1); },
    async choose(offerId) { ids.get('install-correction-choice').value = offerId; await ids.get('install-correction-choice').onchange(); },
    async accept() { await this.dialog.querySelector('.accept-personal-correction').click(); },
  };
}

function offer(extra = {}) {
  return {id: 'opaque-offer', source_name: 'Minhas escolhas', matched_components: 2, total_components: 2, exact_match: true,
    identity: {character: 'Storm', skin: 'Azure Shade'}, component_names: {'body-id': 'Corpo', 'physics-id': 'Física'},
    changes: [{component_id: 'physics-id', component_name: 'Física', fields: ['description', 'requires'],
      before: {description: '', requires: []}, after: {description: 'Complemento', requires: ['body-id']}}],
    state_changes: [{component_id: 'alternative-id', name: 'Outra variante', before: true, after: false}], warnings: [], ...extra};
}
function backupPlan(extra = {}) {
  return {ok: true, token: 'backup-plan-token', complete: true, can_create: true, mods: 4, file_count: 12,
    total_bytes: 1000, required_bytes: 2000, available_bytes: 10000, destination: 'D:\\Chosen', filename: 'Backup.zip', warnings: [], ...extra};
}

let scenarios = 0;
{
  const t = setup();
  for (const result of [null, {ok: true, offers: []}]) {
    t.context.renderPersonalImportChoices(result);
    assert.equal(t.ids.get('install-personal-corrections').hidden, true);
    assert.equal(t.state.personalCorrectionChoice, null);
  }
  t.context.renderPersonalImportChoices({ok: true, offers: [offer()]});
  assert.equal(t.ids.get('install-personal-corrections').hidden, false);
  assert.equal(t.ids.get('install-correction-choice').value, '', 'matching hashes only offer a choice; they do not select it');
  assert.equal(t.dialogs.length, 0);
  assert.equal(t.calls.install.length, 0);
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer()]});
  await t.choose('opaque-offer');
  assert.equal(t.dialog.title, 'Revisar correções pessoais');
  assert.match(t.dialog.innerHTML, /Corpo/);
  assert.doesNotMatch(t.dialog.innerHTML, /body-id/, 'dependency IDs must be displayed as component names');
  assert.match(t.dialog.innerHTML, /Outra variante/);
  assert.equal(t.state.personalCorrectionChoice, null);
  assert.equal(t.state.pickedCharacter, 'Hela');
  assert.equal(t.ids.get('input-folder').value, 'Hela\\Default\\Meu pacote');
  assert.equal(t.calls.install.length, 0);
  t.dialog.remove();
  await t.ids.get('add-mod-confirm').click();
  assert.equal(t.calls.install[0].meta.personal_correction_choice, null, 'closing review must submit no correction choice');
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer()]});
  await t.choose('opaque-offer'); await t.accept();
  assert.equal(t.state.personalCorrectionChoice, 'opaque-offer');
  assert.equal(t.state.pickedCharacter, 'Storm');
  assert.equal(t.state.pickedSkin, 'Azure Shade');
  assert.equal(t.ids.get('input-skin-new').value, 'Azure Shade');
  assert.equal(t.ids.get('input-folder').value, 'Storm\\Azure Shade\\Meu pacote');
  assert.equal(t.calls.install.length, 0, 'accepting reviewed metadata must not install before the main confirmation');
  await t.ids.get('add-mod-confirm').click();
  assert.equal(t.calls.install.length, 1);
  assert.equal(t.calls.install[0].meta.personal_correction_choice, 'opaque-offer');
  assert.equal(t.calls.install[0].meta.character, 'Storm');
  assert.equal(t.calls.install[0].meta.skin, 'Azure Shade');
  assert.equal(t.calls.install[0].meta.folder, 'Storm\\Azure Shade\\Meu pacote');
  assert.equal('send_to_repak' in t.calls.install[0].meta.install_options, false);
  assert.equal(t.requests[0].options.requestId, 'install:selection');
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer({identity: {character: 'Generic', skin: ''}})]});
  await t.choose('opaque-offer'); await t.accept();
  assert.equal(t.state.pickedCharacter, 'Generic');
  assert.equal(t.state.pickedSkin, '');
  assert.equal(t.ids.get('input-skin-new').value, '');
  assert.equal(t.ids.get('input-folder').value, 'Meu pacote');
  await t.ids.get('add-mod-confirm').click();
  assert.equal(t.calls.install[0].meta.skin, '', 'Generic must not silently become Default when accepting stored identity');
  scenarios++;
}
{
  const t = setup();
  await t.ids.get('input-folder').input('Pasta\\Escolhida manualmente');
  t.context.renderPersonalImportChoices({offers: [offer()]});
  await t.choose('opaque-offer'); await t.accept();
  assert.equal(t.state.pickedCharacter, 'Storm');
  assert.equal(t.ids.get('input-folder').value, 'Pasta\\Escolhida manualmente', 'accepting identity must preserve an explicit destination');
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer()]});
  await t.choose('opaque-offer'); await t.accept();
  await t.context.selectCharacter('Magik');
  assert.equal(t.state.personalCorrectionChoice, null);
  assert.equal(t.ids.get('install-correction-choice').value, '');
  assert.match(t.ids.get('install-correction-note').textContent, /desmarcadas/);
  await t.ids.get('add-mod-confirm').click();
  assert.equal(t.calls.install[0].meta.personal_correction_choice, null);
  assert.equal(t.calls.install[0].meta.character, 'Magik');
  scenarios++;
}
{
  for (const useChip of [false, true]) {
    const t = setup();
    t.context.renderPersonalImportChoices({offers: [offer()]});
    await t.choose('opaque-offer'); await t.accept();
    if (useChip) await t.ids.get('skin-chips').children.find(chip => chip.textContent === 'Outra skin').click();
    else await t.ids.get('input-skin-new').input('Minha skin');
    assert.equal(t.state.personalCorrectionChoice, null, 'both typed and existing skin changes must clear saved choices');
    assert.equal(t.state.pickedSkin, useChip ? 'Outra skin' : 'Minha skin');
  }
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer()]});
  await t.choose('opaque-offer'); await t.accept();
  await t.choose('');
  assert.equal(t.state.personalCorrectionChoice, null);
  assert.equal(t.state.pickedCharacter, 'Hela');
  assert.equal(t.state.pickedSkin, 'Default');
  assert.equal(t.ids.get('input-folder').value, 'Hela\\Default\\Meu pacote');
  assert.equal(t.calls.install.length, 0);
  scenarios++;
}
{
  const t = setup();
  t.context.renderPersonalImportChoices({offers: [offer({identity: null, exact_match: false, matched_components: 1})]});
  await t.choose('opaque-offer'); await t.accept();
  assert.equal(t.state.pickedCharacter, 'Hela');
  assert.equal(t.state.pickedSkin, 'Default', 'partial content match must not alter identity');
  assert.equal(t.state.personalCorrectionChoice, 'opaque-offer');
  scenarios++;
}
{
  const t = setup();
  await t.context.prepareFullBackup();
  assert.equal(t.calls.preview.length, 1);
  assert.equal(t.calls.backup.length, 0);
  assert.equal(t.requests[0].options.requestId, t.calls.preview[0]);
  assert.equal(t.dialog.title, 'Criar backup completo');
  assert.match(t.dialog.innerHTML, /Espaço necessário estimado/);
  assert.match(t.dialog.innerHTML, /Disponível no destino/);
  t.dialog.remove();
  assert.equal(t.calls.backup.length, 0, 'closing the preview must never create an archive');
  t.backend.start_full_backup_preview = async requestId => { t.calls.preview.push(requestId); return {ok: false, cancelled: true}; };
  await t.context.prepareFullBackup();
  assert.equal(t.dialogs.length, 1, 'cancelled destination selection must not open a creation confirmation');
  assert.equal(t.calls.backup.length, 0);
  scenarios++;
}
{
  const t = setup();
  t.context.showFullBackupPlan(backupPlan({complete: false, warnings: ['Um arquivo está ausente.']}));
  const checkbox = t.dialog.querySelector('.backup-allow-incomplete');
  const create = t.dialog.querySelector('.confirm-full-backup');
  assert.equal(checkbox.checked, false, 'an incomplete copy must never be opted into by default');
  assert.equal(create.disabled, true);
  await create.click(); await settle();
  assert.equal(t.calls.backup.length, 0);
  checkbox.checked = true; checkbox.onchange();
  assert.equal(create.disabled, false);
  checkbox.checked = false; checkbox.onchange();
  assert.equal(create.disabled, true, 'revoking incomplete-copy consent disables creation again');
  checkbox.checked = true; checkbox.onchange();
  await create.click(); await settle();
  assert.deepEqual(t.calls.backup, [{token: 'backup-plan-token', allowIncomplete: true}]);
  assert.equal(t.requests[0].options.requestId, 'backup:backup-plan-token');
  assert.equal(t.dialog.title, 'Backup incompleto criado');
  scenarios++;
}
{
  const t = setup();
  t.context.showFullBackupPlan(backupPlan({complete: false, can_create: false, available_bytes: 100}));
  const checkbox = t.dialog.querySelector('.backup-allow-incomplete');
  const create = t.dialog.querySelector('.confirm-full-backup');
  checkbox.checked = true; checkbox.onchange();
  assert.equal(create.disabled, true, 'missing space cannot be overridden by incomplete-copy consent');
  await create.click(); await settle();
  assert.equal(t.calls.backup.length, 0);
  assert.match(t.dialog.innerHTML, /Não há espaço suficiente/);
  scenarios++;
}
{
  const t = setup();
  const plan = backupPlan();
  t.context.showFullBackupPlan(plan);
  assert.equal(t.dialog.querySelector('.backup-allow-incomplete'), null);
  await t.dialog.querySelector('.confirm-full-backup').click(); await settle();
  assert.deepEqual(t.calls.backup, [{token: plan.token, allowIncomplete: false}]);
  assert.equal(t.requests[0].options.requestId, `backup:${plan.token}`);
  // Reopening the same review retains the logical request identity for backend deduplication.
  t.context.showFullBackupPlan(plan);
  await t.dialog.querySelector('.confirm-full-backup').click(); await settle();
  assert.equal(t.requests[1].options.requestId, t.requests[0].options.requestId);
  scenarios++;
}
{
  const t = setup();
  await t.context.prepareFullBackup(true);
  assert.equal(t.calls.restorePreview.length, 1);
  assert.equal(t.calls.restore.length, 0);
  assert.equal(t.dialog.title, 'Extrair backup completo');
  await t.dialog.querySelector('.confirm-full-restore').click(); await settle();
  assert.deepEqual(t.calls.restore, ['backup-plan-token']);
  assert.equal(t.requests.at(-1).options.requestId, 'restore:backup-plan-token');
  assert.equal(t.dialog.title, 'Backup extraído e verificado');
  assert.match(t.dialog.innerHTML, /não substitui nem instala automaticamente/);
  scenarios++;
}
{
  const t = setup();
  t.context.pendingOperation = () => ({requestId: 'unfinished'});
  await t.context.prepareFullBackup();
  assert.equal(t.calls.resume, 1);
  assert.equal(t.calls.preview.length, 0, 'unresolved operations are resumed before requesting another backup');
  assert.equal(t.calls.backup.length, 0);
  scenarios++;
}
assert.doesNotMatch(html, /option-repak|Enviar ao Repak|Reempacota o PAK/);
assert.doesNotMatch(app, /send_to_repak|option-repak/);
assert.match(app, /id="add-mod-components"/);
assert.match(app, /start_add_mod_components\(mod\.id, requestId, filepaths, targetComponentId\)/);
assert.match(app, /promote_added_component_to_update/);
assert.match(app, /restore_component_version/);
assert.match(app, /restore_removed_component/);
assert.match(app, /event\.dataTransfer\?\.files/);
assert.match(app, /nova\(s\) variante\(s\) adicionada\(s\) desativada\(s\)/);
assert.match(maintenance, /context\.kind === "component_append"/);
assert.match(html, /id="setting-preserve-import-archives"/);
assert.match(html, /id="setting-delete-import-sources"/);
assert.match(app, /preserve_import_archives: document\.getElementById\("setting-preserve-import-archives"\)\.checked/);
assert.match(app, /delete_import_sources_after_success: document\.getElementById\("setting-delete-import-sources"\)\.checked/);
console.log(`Library tools UI: ${scenarios} scenarios passed.`);
