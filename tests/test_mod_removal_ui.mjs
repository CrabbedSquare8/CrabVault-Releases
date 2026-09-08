import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const start = source.indexOf('function openModRemovalDialog(');
const end = source.indexOf('// ---------------------------------------------------------\n// Render: lista de mods', start);
assert.ok(start >= 0 && end > start, 'real removal dialog must be available');
const dialogSource = source.slice(start, end);

class Control {
  constructor(selector) {
    this.selector = selector; this.disabled = false; this.textContent = ''; this.attributes = {};
    this.classes = new Set(); this.classList = {add:value => this.classes.add(value)};
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  focus() { document.activeElement = this; }
}

class Overlay extends Control {
  constructor() { super('overlay'); this.dataset = {}; this.parts = new Map(); this.isConnected = false; }
  querySelector(selector) {
    if (!this.parts.has(selector)) this.parts.set(selector, new Control(selector));
    return this.parts.get(selector);
  }
  contains(value) { return [...this.parts.values()].includes(value); }
  remove() { this.isConnected = false; if (document.current === this) document.current = null; }
}

const document = {
  current: null, activeElement: new Control('previous'),
  getElementById(id) { return id === 'mod-removal-overlay' ? this.current : null; },
  createElement() { return new Overlay(); },
  body: {appendChild(overlay) { overlay.isConnected = true; document.current = overlay; }},
};

function setup(language, {permanent = false, result = {ok:true}} = {}) {
  const calls = [], renders = [];
  const mod = {id:'mod', name:'A_Test_9999999_P'};
  const state = {mods:[mod], selectedModIds:new Set(['mod']), focusedModId:'mod'};
  const backend = {
    async delete_mod(id) { calls.push(['remove', id]); return result; },
    async delete_mod_permanently(id) { calls.push(['permanent', id]); return result; },
  };
  const window = {getUiLanguage:() => language, uiText:value => value};
  const context = vm.createContext({document, window, state, api:() => backend,
    escapeHtml:value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    renderLocalChange:() => renders.push(true), Set, Error});
  vm.runInContext(dialogSource, context);
  const overlay = context.openModRemovalDialog(mod, {permanent});
  return {context, overlay, mod, state, calls, renders};
}

{
  const test = setup('en');
  assert.match(test.overlay.innerHTML, /Remove mod/);
  assert.match(test.overlay.innerHTML, /Cancel/);
  assert.match(test.overlay.innerHTML, /will be kept in mods_storage/);
  assert.doesNotMatch(test.overlay.innerHTML, /Cancelar|Remover este mod/);
  await test.overlay.querySelector('.mod-removal-confirm').onclick();
  assert.deepEqual(test.calls, [['remove', 'mod']]);
  assert.equal(test.state.mods.length, 0);
  assert.equal(test.state.selectedModIds.size, 0);
  assert.equal(test.state.focusedModId, null);
  assert.equal(test.renders.length, 1);
  assert.equal(test.overlay.isConnected, false);
}

{
  const test = setup('pt-BR', {permanent:true});
  assert.match(test.overlay.innerHTML, /Excluir permanentemente/);
  assert.match(test.overlay.innerHTML, /Cancelar/);
  assert.match(test.overlay.innerHTML, /não pode ser desfeita/);
  const button = test.overlay.querySelector('.mod-removal-confirm');
  await button.onclick();
  assert.deepEqual(test.calls, [], 'the review step must never delete data');
  assert.equal(test.overlay.dataset.step, 'final');
  assert.equal(test.overlay.querySelector('#mod-removal-title').textContent, 'Confirmação final');
  assert.equal(button.textContent, 'Sim, apagar tudo');
  await button.onclick();
  assert.deepEqual(test.calls, [['permanent', 'mod']]);
}

{
  const test = setup('en', {permanent:true, result:{ok:false, error:'blocked'}});
  const button = test.overlay.querySelector('.mod-removal-confirm');
  await button.onclick();
  assert.deepEqual(test.calls, []);
  assert.equal(test.overlay.querySelector('#mod-removal-title').textContent, 'Final confirmation');
  assert.equal(button.textContent, 'Yes, delete everything');
  await button.onclick();
  assert.equal(test.overlay.isConnected, true, 'failed deletion keeps the review open');
  assert.equal(test.state.mods.length, 1);
  assert.equal(test.overlay.querySelector('.mod-removal-error').textContent, 'blocked');
  assert.equal(button.disabled, false);
  assert.equal(button.textContent, 'Yes, delete everything');
}

console.log('Mod removal UI: bilingual two-step permanent review, exact APIs, success and failure passed.');
