import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const helpers = source.slice(source.indexOf('let detailRequestSerial ='), source.indexOf('const componentClassificationJobs ='));
const opening = source.slice(source.indexOf('async function showModDetailsPage('), source.indexOf('function renderModDetailsPage('));
const closing = source.slice(source.indexOf('function closeModDetailsPage('), source.indexOf('document.getElementById("mod-detail-close").onclick'));
const tick = () => new Promise(resolve => setImmediate(resolve));
const media = (name, key = name) => ({name, thumbnail_key: key, media_type: 'image'});

function setup() {
  function element() {
    const classes = new Set();
    return {innerHTML: '', scrollTop: 0, attrs: {},
      classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x)},
      setAttribute(key, value) {this.attrs[key] = value;},
    };
  }
  const elements = new Map();
  const getElementById = id => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  const state = {mods: [{id: 'a', name: 'Mod A'}, {id: 'b', name: 'Mod B'}], detailsModId: null,
    cinematicSectionStates: new Map(), selectedComponentIds: new Set()};
  const requests = [], previews = [], renders = [], replacements = [], opened = [];
  let coverDrains = 0;
  const context = vm.createContext({state, console,
    document: {getElementById, querySelectorAll: () => [], createElement: element,
      querySelector: selector => ({querySelector: () => ({setAttribute() {}, replaceWith(node) {replacements.push({selector, node});}})}),
    },
    api: () => ({
      get_mod_details: (id, includePreviews) => new Promise((resolve, reject) => requests.push({id, includePreviews, resolve, reject})),
      get_gallery_preview: (id, name) => new Promise((resolve, reject) => previews.push({id, name, resolve, reject})),
    }),
    escapeHtml: text => String(text), displayModName: text => text,
    preserveModThumbnail: (mod, old) => {
      if (mod.thumbnail_key && mod.thumbnail_key === old?.thumbnail_key) mod.image_url = old.image_url;
      return mod;
    },
    galleryImageLabel: image => image.name,
    isGalleryVideo: image => image.media_type === 'video',
    openGalleryViewer: (mod, index) => opened.push([mod.id, index]),
    renderModDetailsPage: (mod, serial) => {
      renders.push(mod);
      getElementById('mod-detail-content').innerHTML = 'Componentes e controles';
      context.loadDetailGalleryPreviews(mod, serial);
    },
    renderMods() {}, drainThumbnailQueue() {coverDrains++;},
  });
  vm.runInContext(helpers + opening + closing, context);
  return {context, state, requests, previews, renders, replacements, opened, getElementById, coverDrains: () => coverDrains};
}

{
  const t = setup();
  const first = t.context.showModDetailsPage('a');
  const duplicate = t.context.showModDetailsPage('a');
  assert.equal(t.requests.length, 1, 'repeated clicks share the pending metadata request');
  assert.equal(t.requests[0].includePreviews, false, 'metadata request must never await image generation');
  assert.ok(t.getElementById('mod-detail-overlay').classList.contains('open'), 'click opens the page immediately');
  assert.match(t.getElementById('mod-detail-content').innerHTML, /Mod A.*Carregando detalhes/s);
  t.requests[0].resolve({id: 'a', gallery_images: ['one', 'two', 'three', 'four'].map(name => media(name))});
  await Promise.all([first, duplicate]);
  assert.equal(t.renders.length, 1);
  assert.match(t.getElementById('mod-detail-content').innerHTML, /Componentes/);
  assert.equal(t.getElementById('mod-detail-content').attrs['aria-busy'], 'false');
  assert.equal(t.previews.length, 2, 'controls are usable while only two image requests run');
  t.previews[0].resolve({ok: true, preview_url: 'data:one', thumbnail_key: 'one'});
  await tick();
  assert.equal(t.previews.length, 3, 'next image starts only when a worker finishes');
  assert.equal(t.replacements.length, 1);
  t.replacements[0].node.onclick();
  assert.deepEqual(t.opened, [['a', 0]], 'loaded preview keeps the original viewer action');
  t.context.closeModDetailsPage();
  t.previews[1].resolve({ok: true, preview_url: 'data:two', thumbnail_key: 'two'});
  t.previews[2].reject(new Error('unreadable image'));
  await tick();
  assert.equal(t.previews.length, 3, 'closing drops images that have not started');
  assert.equal(t.replacements.length, 1, 'late images do not modify a closed page');
  assert.equal(t.coverDrains(), 1, 'card cover loading resumes on close');
  const requestCount = t.requests.length;
  await t.context.showModDetailsPage('a');
  assert.equal(t.requests.length, requestCount, 'reopening unchanged details reuses frontend metadata');
  assert.equal(t.renders.length, 2, 'cached metadata renders the reopened page immediately');
}
{
  const t = setup();
  const request = t.context.showModDetailsPage('a');
  t.context.closeModDetailsPage();
  t.requests[0].resolve({id: 'a'});
  await request;
  assert.equal(t.renders.length, 0, 'closing during metadata loading must not reopen the detail');
  assert.equal(t.getElementById('mod-detail-overlay').classList.contains('open'), false);
}
{
  const t = setup();
  const old = t.context.showModDetailsPage('a');
  const latest = t.context.showModDetailsPage('b');
  t.requests[1].resolve({id: 'b'});
  await latest;
  t.requests[0].resolve({id: 'a'});
  await old;
  assert.deepEqual(t.renders.map(mod => mod.id), ['b'], 'out-of-order responses respect the latest selection');
  assert.equal(t.state.detailsModId, 'b');
}
{
  const t = setup();
  const first = t.context.showModDetailsPage('a');
  t.context.closeModDetailsPage();
  const second = t.context.showModDetailsPage('a');
  t.requests[0].resolve({id: 'a', name: 'stale'});
  await first;
  assert.equal(t.renders.length, 0, 'old response cannot win after reopening the same mod');
  t.requests[1].resolve({id: 'a', name: 'fresh'});
  await second;
  assert.equal(t.renders[0].name, 'fresh');
}
{
  const t = setup();
  await t.context.showModDetailsPage('a', {onlyIfOpen: true});
  assert.equal(t.requests.length, 0, 'background refresh cannot open an unrelated page');
  const first = t.context.showModDetailsPage('a');
  t.requests[0].reject(new Error('Falha temporária'));
  await first;
  assert.match(t.getElementById('mod-detail-content').innerHTML, /Falha temporária.*Tentar novamente/s);
  const retry = t.getElementById('retry-mod-details').onclick();
  assert.equal(t.requests.length, 2, 'failed requests can be retried');
  t.requests[1].resolve({id: 'a'});
  await retry;
  assert.equal(t.renders.length, 1);
}
{
  const t = setup();
  t.state.mods[0].thumbnail_key = 'cover-v1';
  t.state.mods[0].image_url = 'data:cover';
  const opening = t.context.showModDetailsPage('a');
  t.requests[0].resolve({id: 'a', thumbnail_key: 'cover-v1', gallery_images: [media('cover.png', 'cover-v1'),
    {name: 'clip.mp4', media_type: 'video'}]});
  await opening;
  assert.equal(t.previews.length, 0, 'reuse ready cover in gallery; do not decode a video as an image');
  assert.equal(t.renders[0].gallery_images[0].preview_url, 'data:cover');
  const changed = t.context.showModDetailsPage('a');
  t.requests[1].resolve({id: 'a', thumbnail_key: 'cover-v2', gallery_images: [media('cover.png', 'cover-v2')]});
  await changed;
  assert.equal(t.previews.length, 1, 'same filename with new revision needs a new preview');
  t.previews[0].resolve({ok: true, preview_url: 'data:stale', thumbnail_key: 'cover-v1'});
  await tick();
  assert.equal(t.replacements.length, 0, 'changed file during generation must not apply an old preview');
}
{
  const t = setup();
  const a = t.context.showModDetailsPage('a');
  t.requests[0].resolve({id: 'a', gallery_images: [media('a1'), media('a2'), media('a3')]});
  await a;
  const b = t.context.showModDetailsPage('b');
  t.requests[1].resolve({id: 'b', gallery_images: [media('b1'), media('b2')]});
  await b;
  assert.equal(t.previews.length, 2, 'changing mods does not exceed the global image worker limit');
  t.previews[0].resolve({ok: true, preview_url: 'data:a1', thumbnail_key: 'a1'});
  await tick();
  assert.equal(t.previews[2].name, 'b1', 'new page takes the next available worker');
  assert.equal(t.replacements.length, 0, 'obsolete page never receives late media');
  t.previews[1].resolve({ok: true, preview_url: 'data:a2', thumbnail_key: 'a2'});
  await tick();
  assert.equal(t.previews[3].name, 'b2');
  t.previews[2].resolve({ok: false});
  t.previews[3].resolve({ok: true, preview_url: 'data:b2', thumbnail_key: 'b2'});
  await tick();
  assert.equal(t.replacements.length, 1, 'one broken image does not prevent the next image');
}
{
  const t = setup();
  const initial = t.context.showModDetailsPage('a');
  t.requests[0].resolve({id: 'a', name: 'initial'});
  await initial;
  const firstChange = t.context.showModDetailsPage('a', {onlyIfOpen: true});
  const nextChange = t.context.showModDetailsPage('a', {onlyIfOpen: true});
  assert.equal(t.requests.length, 3, 'a new mutation refresh must not reuse metadata requested before that mutation');
  t.requests[2].resolve({id: 'a', name: 'latest change'});
  await nextChange;
  t.requests[1].resolve({id: 'a', name: 'earlier change'});
  await firstChange;
  assert.deepEqual(t.renders.map(mod => mod.name), ['initial', 'latest change']);
}
console.log('Detail loading UI: 8 scenarios passed.');
