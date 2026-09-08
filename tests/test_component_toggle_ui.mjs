import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const start = source.indexOf('document.querySelectorAll(".component-switch:not(.cinematic-switch):not(.background-addon-switch)")');
const handler = source.slice(start, source.indexOf('  if (!ordering) {', start));
const maintenance = fs.readFileSync(new URL('../frontend/maintenance.js', import.meta.url), 'utf8');
const filterStart = maintenance.indexOf('function simplifyComponentActions(');
const filterEnd = maintenance.indexOf('document.getElementById("setting-pending-classifications")', filterStart);
assert.ok(filterStart >= 0 && filterEnd > filterStart, 'real component filter must be available');
const filterSource = maintenance.slice(filterStart, filterEnd);
assert.match(filterSource, /component-manage[\s\S]*button\.textContent = "Gerenciar"[\s\S]*button\.title = "Gerenciar componente"/, 'nested component action must have a readable label and tooltip');

function setup(result = {ok: true}) {
  const button = {dataset: {componentId: 'alternative'}, disabled: false};
  const content = {scrollTop: 240};
  const state = {detailsModId: 'mod', switches: {main: true, alternative: false, physics: false}};
  const calls = [], alerts = [];
  const context = vm.createContext({state, mod: {id: 'mod'},
    document: {querySelectorAll: () => [button], getElementById: () => content},
    api: () => ({toggle_component: async (mod, component) => { calls.push(['toggle', mod, component]); return result; }}),
    refreshModInState: async mod => {
      calls.push(['refresh', mod]);
      state.switches = {main: false, alternative: true, physics: true};
    },
    renderLocalChange: () => calls.push(['render']),
    showModDetailsPage: async (mod, options) => {
      calls.push(['details', mod, options.onlyIfOpen]);
      if (state.detailsModId === mod) content.scrollTop = 0;
    },
    alert: message => alerts.push(message),
  });
  vm.runInContext(handler, context);
  return {button, state, calls, alerts, content};
}

{
  const t = setup();
  await t.button.onclick();
  assert.deepEqual(t.state.switches, {main: false, alternative: true, physics: true}, 'refresh must include excluded alternative and required complement');
  assert.deepEqual(t.calls.map(call => call[0]), ['toggle', 'refresh', 'render', 'details']);
  assert.equal(t.calls.at(-1)[2], true, 'detail refresh must never reopen another/closed mod');
  assert.equal(t.content.scrollTop, 240);
  assert.equal(t.button.disabled, false);
}
{
  const t = setup({ok: false, error: 'O jogo está aberto.'});
  await t.button.onclick();
  assert.deepEqual(t.state.switches, {main: true, alternative: false, physics: false});
  assert.equal(t.calls.length, 1, 'failed toggle does not claim updated switches');
  assert.equal(t.alerts[0], 'O jogo está aberto.');
  assert.equal(t.button.disabled, false);
}

function filterSetup(savedKind = '') {
  const components = [
    {id: 'variation', types: ['Mesh']},
    {id: 'complement', types: ['Texture']},
  ];
  const rows = components.map(component => ({
    dataset: {componentId: component.id}, hidden: false,
    querySelector(selector) {
      if (selector !== '.component-actions') return null;
      return {querySelectorAll: () => []};
    },
  }));
  const buttons = ['', 'variant', 'extra'].map(kind => ({
    dataset: {kind}, selected: false, attributes: {},
    classList: {toggle(name, value) { if (name === 'selected') this.owner.selected = value; }, owner: null},
    setAttribute(name, value) { this.attributes[name] = value; },
    closest: () => null,
  }));
  buttons.forEach(button => { button.classList.owner = button; button.closest = selector => selector === 'button' ? button : null; });
  const filters = {className: '', innerHTML: '', onclick: null, querySelectorAll: selector => selector === 'button' ? buttons : []};
  const container = {
    before(element) { this.filters = element; },
    querySelectorAll: selector => selector === '.detail-component' ? rows : [],
  };
  const state = {componentKindFilters: new Map(savedKind ? [['mod', savedKind]] : [])};
  const translations = {Todos:'All', Variações:'Variations', Complementos:'Add-ons'};
  const context = vm.createContext({state, window:{uiText:value => translations[value] || value}, document: {
    querySelector: selector => selector === '#mod-detail-content .detail-components' ? container : null,
    createElement: () => filters,
  }});
  vm.runInContext(filterSource, context);
  context.simplifyComponentActions({id: 'mod'}, components, false);
  return {context, state, rows, buttons, filters};
}

{
  const t = filterSetup('extra');
  assert.match(t.filters.innerHTML, />All \(2\)</);
  assert.match(t.filters.innerHTML, />Variations \(1\)</);
  assert.match(t.filters.innerHTML, />Add-ons \(1\)</);
  assert.doesNotMatch(t.filters.innerHTML, /Todos|Variações|Complementos/);
  assert.deepEqual(t.rows.map(row => row.hidden), [true, false], 'saved Complementos tab must be restored after render');
  assert.equal(t.buttons[2].selected, true);
  assert.equal(t.buttons[2].attributes['aria-pressed'], 'true');
  t.filters.onclick({target: t.buttons[1]});
  assert.equal(t.state.componentKindFilters.get('mod'), 'variant');
  assert.deepEqual(t.rows.map(row => row.hidden), [false, true]);
  const rerendered = filterSetup(t.state.componentKindFilters.get('mod'));
  assert.deepEqual(rerendered.rows.map(row => row.hidden), [false, true], 'Variações tab must survive another detail render');
  assert.equal(rerendered.buttons[1].selected, true);
}

console.log('Component toggle UI: cascade, rejected operation and persistent tabs passed.');
