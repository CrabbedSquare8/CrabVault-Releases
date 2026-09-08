import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const app = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const start = app.indexOf('async function recordImportTiming(');
const end = app.indexOf('function renderModDetailsPage(', start);
const source = app.slice(start, end);

function setup(decision) {
  const calls = {promote: [], reload: 0, details: 0, timings: [], alerts: []};
  const backend = {
    promote_added_component_to_update: async (...args) => {
      calls.promote.push(args);
      return {ok: true};
    },
    record_import_performance: async sample => {
      calls.timings.push(sample);
      return {ok: true};
    },
  };
  const context = vm.createContext({
    api: () => backend,
    reloadAll: async () => { calls.reload += 1; },
    showModDetailsPage: async modId => { calls.details += 1; assert.equal(modId, 'mod'); },
    confirm: () => decision,
    alert: message => calls.alerts.push(message),
    Date,
    performance: {now: (() => { let value = 100; return () => value += 10; })()},
    globalThis: null,
    escapeHtml: value => String(value),
    formatModSize: value => `${value} MB`,
  });
  context.globalThis = context;
  vm.runInContext(source, context);
  return {context, calls};
}

const result = {ok: true, backend_ms: 42, record: {
  added_components: 1,
  added_component_ids: ['new'],
  suggested_updates: [{new_component_id: 'new', target_component_id: 'old', target_name: 'Roupa', reason: 'Assets coincidem.'}],
}};

{
  const test = setup(false);
  await test.context.finishComponentImport(result, 'mod', null, 100);
  await Promise.resolve();
  assert.equal(test.calls.promote.length, 0, 'recusar a sugestão mantém uma variante');
  assert.equal(test.calls.reload, 1);
  assert.match(test.calls.alerts[0], /1 nova\(s\) variante\(s\)/);
  assert.equal(test.calls.timings[0].backend_ms, 42);
}

{
  const test = setup(true);
  await test.context.finishComponentImport(result, 'mod', null, 100);
  assert.deepEqual(test.calls.promote[0], ['mod', 'new', 'old']);
  assert.match(test.calls.alerts[0], /1 componente\(s\) atualizado\(s\)/);
}

assert.match(app, /file\.pywebviewFullPath \|\| file\.path/);
assert.match(app, /preview_remove_component/);
assert.match(app, /restore_component_version/);
console.log('Component lifecycle UI: reviewed suggestion, timing and drag/drop passed.');
