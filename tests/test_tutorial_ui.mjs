import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const appSource = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const html = fs.readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
const css = fs.readFileSync(new URL('../frontend/style.css', import.meta.url), 'utf8');
const start = appSource.indexOf('const TUTORIAL_COPY =');
const end = appSource.indexOf('function renderLanguageSelection()', start);
assert.ok(start >= 0 && end > start, 'tutorial implementation must be available');
const tutorialSource = `${appSource.slice(start, end)}\nglobalThis.__tutorial = {copy:TUTORIAL_COPY, target:tutorialTargetFor, position:positionTutorial, setStep:value => { tutorialStep = value; }};`;

class Classes {
  constructor(values = []) { this.values = new Set(values); }
  contains(value) { return this.values.has(value); }
  toggle(value, enabled) { enabled ? this.values.add(value) : this.values.delete(value); }
}

const dialog = {style:{}, dataset:{}, classList:new Classes(), offsetWidth:420, offsetHeight:330};
const overlay = {classList:new Classes(['open']), querySelector:selector => selector === '.tutorial-dialog' ? dialog : null};
const spotlight = {style:{}, hidden:true};
const focusName = {textContent:''};
const calls = [];
const targets = {
  '#btn-settings': {hidden:false, getBoundingClientRect:() => ({left:1120, top:52, right:1162, bottom:88, width:42, height:36}), scrollIntoView:options => calls.push(options)},
  '#btn-scan-mods': {hidden:false, getBoundingClientRect:() => ({left:900, top:160, right:1040, bottom:200, width:140, height:40}), scrollIntoView:options => calls.push(options)},
};
const document = {
  documentElement:{clientWidth:1200, clientHeight:800},
  querySelector:selector => targets[selector] || null,
  getElementById:id => ({'tutorial-overlay':overlay, 'tutorial-spotlight':spotlight, 'tutorial-focus-name':focusName})[id] || null,
};
const window = {innerWidth:1200, innerHeight:800};
const context = vm.createContext({DEFAULT_LANGUAGE:'pt-BR', document, window, Object, Array, Set,
  requestAnimationFrame:callback => { callback(); return 1; }, cancelAnimationFrame:() => {}});
vm.runInContext(tutorialSource, context);

for (const language of ['pt-BR', 'en']) {
  const copy = context.__tutorial.copy[language];
  assert.equal(copy.chapters.length, 5);
  assert.equal(copy.steps.length, 16);
  assert.ok(copy.steps.every(step => step.chapter && (step.target || step.media)), `${language} steps must point to the real interface or a bundled example`);
  assert.equal(copy.steps.filter(step => step.chapter === 'setup').length, 2);
  assert.equal(copy.steps.filter(step => step.chapter === 'install').length, 6);
  assert.equal(copy.steps.filter(step => step.chapter === 'details').length, 3);
  assert.equal(copy.steps.filter(step => step.chapter === 'scan').length, 1);
  assert.equal(copy.steps.filter(step => step.chapter === 'safety').length, 4);
  assert.equal(copy.steps.filter(step => step.media?.includes('settings-')).length, 3);
  const packageSelection = copy.steps.find(step => step.media?.endsWith('pak-file-selection.png'));
  assert.ok(packageSelection.mediaFocus.x <= 3 && packageSelection.mediaFocus.x + packageSelection.mediaFocus.width >= 85, `${language} package focus must include the ZIP and Unreal trio`);
  const tagsMenu = copy.steps.find(step => step.media?.endsWith('pak-tags.png'));
  assert.ok(tagsMenu.mediaFocus.y <= 22 && tagsMenu.mediaFocus.y + tagsMenu.mediaFocus.height >= 98, `${language} tag focus must include the complete menu`);
  const detailSteps = copy.steps.filter(step => step.media?.endsWith('example-mod-details.png'));
  assert.ok(detailSteps[0].mediaFocus.y <= 5 && detailSteps[0].mediaFocus.y + detailSteps[0].mediaFocus.height >= 66, `${language} identity focus must include tags`);
  assert.ok(detailSteps[1].mediaFocus.label.length <= 5, `${language} component focus label must stay compact`);
  for (const step of copy.steps.filter(step => step.media)) {
    assert.ok(fs.existsSync(new URL(`../frontend/${step.media}`, import.meta.url)), `missing tutorial media: ${step.media}`);
    assert.ok(step.mediaAlt && step.mediaCaption, `media needs accessible explanation: ${step.media}`);
  }
}

context.__tutorial.position();
assert.equal(spotlight.hidden, false);
assert.equal(focusName.textContent, 'Configurações');
assert.equal(spotlight.style.left, '1113px');
assert.equal(dialog.dataset.placement, 'left');
assert.equal(calls.length, 1, 'highlighted control is scrolled into view');

context.__tutorial.setStep(8);
context.__tutorial.position();
assert.equal(spotlight.hidden, true, 'empty libraries use the bundled example instead of requiring a real card');
assert.equal(overlay.classList.contains('is-demo'), true);

context.__tutorial.setStep(11);
context.__tutorial.position();
assert.equal(spotlight.hidden, false);
assert.equal(focusName.textContent, 'Buscar mods instalados');
assert.equal(overlay.classList.contains('is-demo'), false);

assert.match(html, /id="tutorial-spotlight"/);
assert.match(html, /id="tutorial-step-map"/);
assert.match(html, /id="tutorial-media-image"/);
assert.match(html, /id="tutorial-media-focus"/);
assert.match(css, /box-shadow:0 0 0 9999px/);
assert.match(css, /\.tutorial-step-map button\.selected/);
assert.match(css, /\.tutorial-dialog\.has-media/);
assert.match(appSource, /assets\/tutorial\/pak-file-selection\.png/);
assert.match(appSource, /assets\/tutorial\/settings-overview\.png/);
assert.match(appSource, /assets\/tutorial\/settings-import-maintenance\.png/);
assert.match(appSource, /assets\/tutorial\/settings-backups-appearance\.png/);
assert.match(appSource, /Você pode selecionar vários ZIPs ou vários pacotes de uma vez/);
assert.match(appSource, /Buscar mods instalados encontra os pacotes/);
assert.match(appSource, /setting-review-tutorial[\s\S]*closeSettings\(\);[\s\S]*openTutorial\(language\);/);
console.log('Interactive tutorial: chapters, bundled examples, PAK flow, settings, details, scan and spotlight positioning passed.');
