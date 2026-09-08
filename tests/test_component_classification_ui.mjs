import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const worker = source.slice(source.indexOf('const componentClassificationJobs ='),
  source.indexOf('async function showModDetailsPage('));

function setup() {
  let resolve, reject;
  const response = new Promise((yes, no) => { resolve = yes; reject = no; });
  const calls = {analyze: 0, refresh: 0, render: 0, details: 0};
  const state = {detailsModId: 'mod'};
  const status = {textContent: 'Analisando componentes…'};
  const content = {scrollTop: 123};
  const context = vm.createContext({state, console: {error() {}},
    document: {getElementById: id => id === 'mod-detail-content' ? content : status},
    api: () => ({classify_mod_components() { calls.analyze++; return response; }}),
    refreshModInState: async () => { calls.refresh++; return {id: 'mod'}; },
    renderLocalChange: () => calls.render++,
    showModDetailsPage: async (id, options) => {
      assert.equal(id, 'mod');
      assert.equal(options.onlyIfOpen, true);
      calls.details++;
      content.scrollTop = 0;
    },
  });
  vm.runInContext(worker + '\nglobalThis.jobs = componentClassificationJobs;', context);
  return {context, calls, state, status, content, resolve, reject};
}

{
  const t = setup();
  t.context.completeComponentClassification({id: 'mod', component_classification_pending: true});
  t.context.completeComponentClassification({id: 'mod', component_classification_pending: true});
  assert.equal(t.calls.analyze, 1, 'deduplicate simultaneous detail refreshes');
  const job = t.context.jobs.get('mod');
  t.resolve({ok: true, changed: true});
  await job;
  assert.equal(t.calls.refresh, 1);
  assert.equal(t.calls.details, 1);
  assert.equal(t.content.scrollTop, 123);
  assert.equal(t.context.jobs.size, 0);
}
{
  const t = setup();
  t.context.completeComponentClassification({id: 'mod', component_classification_pending: true});
  t.state.detailsModId = 'other';
  const job = t.context.jobs.get('mod');
  t.resolve({ok: true, changed: true});
  await job;
  assert.equal(t.calls.details, 0, 'never reopen a closed or different mod');
  assert.equal(t.calls.refresh, 1, 'still update the library');
}
{
  const t = setup();
  t.context.completeComponentClassification({id: 'mod', component_classification_pending: true});
  const job = t.context.jobs.get('mod');
  t.resolve({ok: true, changed: false});
  await job;
  assert.equal(t.calls.details, 0, 'no refresh loop for unsupported packages');
  assert.equal(t.calls.analyze, 1);
}
{
  const t = setup();
  t.context.completeComponentClassification({id: 'mod', component_classification_pending: true});
  const job = t.context.jobs.get('mod');
  t.reject(new Error('temporary error'));
  await job;
  assert.match(t.status.textContent, /Não foi possível/);
  assert.equal(t.context.jobs.size, 0);
}
console.log('Component classification UI: 4 scenarios passed.');
